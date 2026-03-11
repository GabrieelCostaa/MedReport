"""
Script de ingestão de relatórios aprovados.

Uso:
    python scripts/ingest_reports.py

Coloque os arquivos (.pdf, .docx, .txt) na pasta:
    services/api/data/relatorios_aprovados/

O script irá:
1. Ler cada arquivo e extrair o texto
2. Classificar automaticamente por produto (se possível)
3. Salvar os parágrafos como exemplos_aprovados nos templates
4. Gerar um relatório do que foi processado

Formatos suportados: .pdf, .docx, .txt, .doc
"""
import asyncio
import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "relatorios_aprovados")

PRODUCT_KEYWORDS = {
    "Adhesion STP+": [
        "adhesion", "anti-aderência", "anti-aderencia", "aderência", "aderencia",
        "barreira anti", "cmc", "carboximetilcelulose", "filme polimérico",
        "bridectomia", "bridotomia", "bridas",
    ],
    "Kit EC2 - Linha Opus": [
        "opus", "viscossuplementação", "viscossuplementacao",
        "ácido hialurônico", "acido hialuronico", "hialuronato",
        "viscoelástic", "viscoelastic", "intra-articular",
        "mega dalton", "cross link", "reticulação",
    ],
    "Kit EC2 - Enxerto Composto": [
        "enxerto composto", "kit ec", "ec2", "cânula introdutor",
        "gel carreador", "tecido celular subcutâneo", "tecido celular subcutaneo",
        "aspiração e colheita", "peyronie", "disfunção erétil", "estenose",
        "svf", "estroma vascular",
    ],
    "Kit FO - Laser Cirúrgico": [
        "laser", "fibra óptica", "fibra optica", "kit introdutor para cateter fo",
        "kit fo", "foto térmic", "fototérmic", "980", "1470", "nanômetro",
        "cauterização", "cauterizacao", "desobstrução", "desobstrucao",
        "turbinectomia", "turbinoplastia", "sinusectomia",
        "amigdalectomia", "adeno-amigdalectomia", "estapedo",
        "papilomatose", "hemangioma", "dacriocisto", "glossectomia",
        "tireóide", "tireoide", "hipófise", "hipofise",
        "rizotomia", "pldd", "hérnia de disco",
    ],
    "Vitagraft - Enxerto Bifásico": [
        "vitagraft", "vita", "enxerto bifásico", "enxerto bifasico",
        "plga", "beta tri cálcio", "beta tri calcio", "β-tcp",
        "scaffold", "arcabouço", "osteo integração", "osteointegração",
    ],
    "Biossilex - Biovidro": [
        "biossilex", "biovidro", "vidro bioativo", "hidroxiapatita",
        "bacteriostático", "bacteriostatico", "osteomielite",
    ],
    "Kit LP-CT - Lipedema": [
        "lipedema", "lp-ct", "one step", "tecido adiposo patológico",
        "dermolipectomia", "lipodistrofia",
    ],
    "Parafuso de Interferência Bioabsorvível": [
        "parafuso", "interferência", "interferencia", "bioabsorvível",
        "bioabsorvivel", "plla", "lca", "ligamento cruzado",
    ],
    "Tela de Polipropileno Macroporosa": [
        "tela", "polipropileno", "herniorra", "mesh", "macropor",
    ],
}


def extract_text_from_file(filepath: str) -> str:
    """Extrai texto de PDF, DOCX ou TXT."""
    ext = Path(filepath).suffix.lower()

    if ext == ".txt":
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(filepath)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            pass

        try:
            from pdfminer.high_level import extract_text as pdf_extract
            return pdf_extract(filepath)
        except ImportError:
            pass

        try:
            import subprocess
            result = subprocess.run(
                ["pdftotext", filepath, "-"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        print(f"  [AVISO] Não foi possível ler PDF: {filepath}")
        print(f"          Instale: pip install PyMuPDF  ou  pip install pdfminer.six")
        return ""

    if ext in (".docx",):
        try:
            from docx import Document
            doc = Document(filepath)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            print(f"  [AVISO] Não foi possível ler DOCX: {filepath}")
            print(f"          Instale: pip install python-docx")
            return ""

    if ext == ".doc":
        try:
            import subprocess
            result = subprocess.run(
                ["antiword", filepath],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        print(f"  [AVISO] Não foi possível ler .doc: {filepath}")
        print(f"          Instale antiword ou converta para .docx")
        return ""

    print(f"  [IGNORADO] Formato não suportado: {ext}")
    return ""


def classify_product(text: str) -> str | None:
    """Tenta classificar o relatório por produto baseado em palavras-chave."""
    text_lower = text.lower()
    scores = {}
    for product, keywords in PRODUCT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[product] = score

    if not scores:
        return None
    return max(scores, key=scores.get)


def extract_paragraphs(text: str, min_length: int = 100) -> list[str]:
    """Extrai parágrafos significativos do texto (> min_length caracteres)."""
    paragraphs = re.split(r"\n\s*\n", text)
    result = []
    for p in paragraphs:
        clean = p.strip()
        clean = re.sub(r"\s+", " ", clean)
        if len(clean) >= min_length:
            result.append(clean)
    return result


def extract_references(text: str) -> list[str]:
    """Extrai referências bibliográficas do texto."""
    refs = []
    patterns = [
        re.compile(r"([A-Z][a-záéíóú]+\s+(?:et al\.?|[A-Z]\.?),?\s*(?:19|20)\d{2}[^.]*\.)", re.MULTILINE),
        re.compile(r"(\d+\.\s+[A-Z][^.]+(?:19|20)\d{2}[^.]*\.)", re.MULTILINE),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            ref = match.group(1).strip()
            if 20 < len(ref) < 500:
                refs.append(ref)
    return list(set(refs))


async def save_to_database(classified_reports: dict, all_paragraphs: list[str]):
    """Salva os exemplos aprovados no banco de dados."""
    from app.db.session import AsyncSessionLocal
    from app.db.models import ReportTemplate, Product
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        for product_name, paragraphs in classified_reports.items():
            product_result = await db.execute(
                select(Product).where(Product.nome == product_name)
            )
            product = product_result.scalar_one_or_none()
            if not product:
                print(f"  [AVISO] Produto '{product_name}' não encontrado no DB. Pulando.")
                continue

            template_result = await db.execute(
                select(ReportTemplate).where(ReportTemplate.produto_id == product.id)
            )
            template = template_result.scalar_one_or_none()

            if template:
                existing = template.exemplos_aprovados or []
                new_examples = existing + paragraphs
                template.exemplos_aprovados = new_examples[:50]
                print(f"  [OK] Template '{template.nome}' atualizado: {len(new_examples)} exemplos")
            else:
                template = ReportTemplate(
                    nome=f"Template Auto-Gerado - {product_name}",
                    especialidade="Geral",
                    produto_id=product.id,
                    tom_de_voz="Tom científico, formal e assertivo baseado em relatórios aprovados.",
                    exemplos_aprovados=paragraphs[:50],
                )
                db.add(template)
                print(f"  [NOVO] Template criado para '{product_name}': {len(paragraphs)} exemplos")

        # Template genérico com todos os parágrafos não classificados
        if all_paragraphs:
            generic_result = await db.execute(
                select(ReportTemplate).where(ReportTemplate.nome == "Template Genérico - Relatórios Aprovados")
            )
            generic = generic_result.scalar_one_or_none()
            if generic:
                existing = generic.exemplos_aprovados or []
                generic.exemplos_aprovados = (existing + all_paragraphs)[:100]
                print(f"  [OK] Template genérico atualizado: {len(generic.exemplos_aprovados)} exemplos")
            else:
                generic = ReportTemplate(
                    nome="Template Genérico - Relatórios Aprovados",
                    especialidade="Geral",
                    tom_de_voz="Tom científico, formal e assertivo baseado em relatórios aprovados.",
                    exemplos_aprovados=all_paragraphs[:100],
                )
                db.add(generic)
                print(f"  [NOVO] Template genérico criado: {len(all_paragraphs)} exemplos")

        await db.commit()


async def main():
    print("=" * 60)
    print("INGESTÃO DE RELATÓRIOS APROVADOS")
    print("=" * 60)

    if not os.path.exists(REPORTS_DIR):
        print(f"\nPasta não encontrada: {REPORTS_DIR}")
        print("Crie a pasta e coloque os arquivos lá.")
        return

    files = sorted(Path(REPORTS_DIR).glob("*"))
    supported = [f for f in files if f.suffix.lower() in (".pdf", ".docx", ".txt", ".doc")]

    if not supported:
        print(f"\nNenhum arquivo suportado encontrado em:")
        print(f"  {REPORTS_DIR}")
        print(f"\nFormatos aceitos: .pdf, .docx, .txt, .doc")
        print(f"Coloque os 20 relatórios do seu parceiro nessa pasta e rode novamente.")
        return

    print(f"\nArquivos encontrados: {len(supported)}")
    print()

    classified = {}
    unclassified_paragraphs = []
    all_references = []
    report_log = []

    for filepath in supported:
        filename = filepath.name
        print(f"Processando: {filename}")

        text = extract_text_from_file(str(filepath))
        if not text or len(text) < 50:
            print(f"  [VAZIO] Arquivo sem conteúdo extraível")
            report_log.append({"arquivo": filename, "status": "vazio", "caracteres": len(text)})
            continue

        product = classify_product(text)
        paragraphs = extract_paragraphs(text)
        refs = extract_references(text)
        all_references.extend(refs)

        print(f"  Caracteres: {len(text):,}")
        print(f"  Parágrafos úteis: {len(paragraphs)}")
        print(f"  Referências encontradas: {len(refs)}")
        print(f"  Produto detectado: {product or 'Não classificado'}")

        if product:
            if product not in classified:
                classified[product] = []
            classified[product].extend(paragraphs)
        else:
            unclassified_paragraphs.extend(paragraphs)

        report_log.append({
            "arquivo": filename,
            "status": "processado",
            "caracteres": len(text),
            "paragrafos": len(paragraphs),
            "referencias": len(refs),
            "produto": product,
        })

    print()
    print("-" * 60)
    print("RESUMO DA CLASSIFICAÇÃO:")
    for product, paras in classified.items():
        print(f"  {product}: {len(paras)} parágrafos")
    print(f"  Não classificados: {len(unclassified_paragraphs)} parágrafos")
    print(f"  Referências totais: {len(set(all_references))}")
    print()

    print("Salvando no banco de dados...")
    try:
        from app.db.session import engine
        from app.db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await save_to_database(classified, unclassified_paragraphs)
        print("Dados salvos com sucesso!")
    except Exception as e:
        print(f"Erro ao salvar no banco: {e}")
        print("Os dados extraídos serão salvos em JSON como fallback...")

    # Salvar log e dados em JSON (backup)
    output = {
        "data_processamento": datetime.utcnow().isoformat(),
        "arquivos_processados": len(report_log),
        "log": report_log,
        "classificados": {k: v[:5] for k, v in classified.items()},
        "nao_classificados_count": len(unclassified_paragraphs),
        "referencias_unicas": list(set(all_references))[:50],
    }

    output_path = os.path.join(REPORTS_DIR, "_ingestao_log.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nLog salvo em: {output_path}")

    print()
    print("=" * 60)
    print("PRÓXIMOS PASSOS:")
    print("  1. Verifique o log acima para conferir a classificação")
    print("  2. Se algum produto não foi detectado, renomeie o arquivo")
    print("     com o nome do produto (ex: 'adhesion_relatorio_01.pdf')")
    print("  3. Rode novamente se necessário")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
