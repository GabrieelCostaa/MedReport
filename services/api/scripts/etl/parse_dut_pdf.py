"""
ETL: Parse do DUT (Anexo II) — Diretrizes de Utilização.

Estratégia em 3 etapas:
1. Segmentação determinística (pré-LLM): pdfplumber para extrair texto, identificar âncoras
2. Estruturação com LLM: GPT-4o gera JSON com evidence_spans
3. Validação pós-LLM: validadores automáticos

Notas de rodapé são capturadas e viram regras de exclusão na DSL.
"""
import asyncio
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

DUT_PDF_URL = "https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/atualizacao-do-rol-de-procedimentos/Anexo_II_DUT_2021_RN_465.2021_RN628.2025_RN629.2025.pdf/@@download/file"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ans"

DUT_ANCHOR_RE = re.compile(
    r"(?:DUT|Diretriz\s+de\s+Utiliza[çc][ãa]o)\s*(?:n[ºo°.]?\s*)?(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Real format in Anexo II: "N. TÍTULO DO PROCEDIMENTO" (e.g. "1. ABLAÇÃO POR...")
# Must be at start of line, number followed by dot, then uppercase text
DUT_NUMBERED_RE = re.compile(
    r"^(\d{1,3})\.\s+([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s,;/\-\(\)]{10,})",
    re.MULTILINE,
)


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def download_dut_pdf(url: str = DUT_PDF_URL) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True, timeout=180) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def segment_dut_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Etapa 1: Segmentação determinística.
    Extrai texto página a página com pdfplumber, identifica âncoras de DUT,
    gera chunks com texto + páginas + número da DUT.

    O Anexo II usa formato "N. TÍTULO" (ex: "1. ABLAÇÃO POR RADIOFREQUÊNCIA...")
    onde N é o número sequencial da DUT.
    """
    import pdfplumber

    chunks = []
    current_dut = None
    current_title = ""
    current_text = []
    current_pages = []
    footnotes = []
    in_content = False  # Skip TOC pages

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""

            # Detect start of actual content (after TOC)
            if not in_content:
                if "ANEXO II - DIRETRIZES DE UTILIZAÇÃO" in page_text:
                    in_content = True
                else:
                    continue

            lines = page_text.split("\n")

            for line in lines:
                # Skip header repetitions
                if "ANEXO II - DIRETRIZES DE UTILIZAÇÃO" in line:
                    continue

                # Try both anchor patterns
                match = DUT_ANCHOR_RE.search(line)
                if not match:
                    match = DUT_NUMBERED_RE.match(line.strip())

                if match:
                    # Save previous DUT
                    if current_dut and current_text:
                        chunks.append({
                            "numero_dut": current_dut,
                            "titulo": current_title,
                            "texto": "\n".join(current_text),
                            "page_start": current_pages[0] if current_pages else page_num,
                            "page_end": current_pages[-1] if current_pages else page_num,
                            "footnotes": footnotes[:],
                        })
                    current_dut = match.group(1)
                    current_title = match.group(2).strip() if match.lastindex >= 2 else _extract_title([line])
                    current_text = [line]
                    current_pages = [page_num]
                    footnotes = []
                else:
                    if current_dut:
                        current_text.append(line)
                        if page_num not in current_pages:
                            current_pages.append(page_num)

                # Capture footnotes
                if re.match(r"^\s*nota\s*:?", line, re.IGNORECASE):
                    footnotes.append(line.strip())

    if current_dut and current_text:
        chunks.append({
            "numero_dut": current_dut,
            "titulo": current_title,
            "texto": "\n".join(current_text),
            "page_start": current_pages[0] if current_pages else 0,
            "page_end": current_pages[-1] if current_pages else 0,
            "footnotes": footnotes,
        })

    return chunks


def _extract_title(lines: list[str]) -> str:
    """Extrai título da DUT das primeiras linhas."""
    for line in lines[:3]:
        cleaned = DUT_ANCHOR_RE.sub("", line).strip(" –-:.")
        if len(cleaned) > 5:
            return cleaned
    return lines[0] if lines else ""


async def structure_dut_with_llm(chunk: dict, openai_api_key: str) -> dict:
    """
    Etapa 2: Estruturação com LLM.
    Pede GPT-4o para gerar JSON estruturado a partir do texto da DUT.
    Exige evidence_spans obrigatórios.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=openai_api_key)

    prompt = f"""Analise o texto abaixo de uma Diretriz de Utilização (DUT) da ANS brasileira.
Gere um JSON estruturado com os seguintes campos:

{{
  "numero_dut": "{chunk['numero_dut']}",
  "titulo": "título da DUT",
  "criterios": [
    {{
      "id": "A",
      "tipo": "deterministico" ou "subjetivo",
      "campo_paciente": "nome do campo (idade, imc, etc.)" ou null se subjetivo,
      "operador": ">=", "<=", "==", "!=", ">", "<", "in", "between" ou null,
      "valor": valor numérico ou string ou null,
      "unidade": "anos", "meses", "kg/m2" etc. ou null,
      "descricao": "descrição legível do critério",
      "evidence_span": "trecho EXATO do texto que fundamenta este critério",
      "page_ref": número da página
    }}
  ],
  "exclusoes": [
    {{
      "id": "EX1",
      "tipo": "exclusao",
      "descricao": "descrição da exclusão",
      "evidence_span": "trecho EXATO do texto",
      "origem": "nota_rodape" ou "corpo"
    }}
  ],
  "exames_exigidos": ["lista de exames"],
  "documentos_exigidos": ["lista de documentos"],
  "logica": "expressão lógica ex: A AND B AND (C OR D) AND NOT EX1"
}}

REGRAS OBRIGATÓRIAS:
- Todo critério DEVE ter um evidence_span com trecho do texto original
- Notas de rodapé que excluem cobertura DEVEM virar itens em "exclusoes"
- Critérios numéricos (idade, IMC, tempo) são "deterministico"
- Critérios subjetivos (motivação, condição clínica) são "subjetivo"
- NÃO invente critérios que não estão no texto

TEXTO DA DUT {chunk['numero_dut']} (páginas {chunk['page_start']}-{chunk['page_end']}):

{chunk['texto'][:6000]}

NOTAS DE RODAPÉ ENCONTRADAS:
{chr(10).join(chunk.get('footnotes', [])) or 'Nenhuma'}
"""

    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        return {"error": "Failed to parse LLM response", "raw": resp.choices[0].message.content}


def validate_structured_dut(structured: dict) -> list[str]:
    """
    Etapa 3: Validação pós-LLM.
    Retorna lista de warnings. Lista vazia = tudo OK.
    """
    warnings = []

    if "error" in structured:
        warnings.append(f"LLM parse failed: {structured.get('error')}")
        return warnings

    criterios = structured.get("criterios", [])
    if not criterios:
        warnings.append("Nenhum critério extraído")

    for c in criterios:
        if not c.get("evidence_span"):
            warnings.append(f"Critério {c.get('id', '?')} sem evidence_span")
        if c.get("tipo") == "deterministico":
            if not c.get("campo_paciente"):
                warnings.append(f"Critério determinístico {c.get('id', '?')} sem campo_paciente")
            if c.get("operador") is None:
                warnings.append(f"Critério determinístico {c.get('id', '?')} sem operador")

    for ex in structured.get("exclusoes", []):
        if not ex.get("evidence_span"):
            warnings.append(f"Exclusão {ex.get('id', '?')} sem evidence_span")

    if not structured.get("logica"):
        warnings.append("Campo 'logica' ausente")

    return warnings


def build_dsl_from_structured(structured: dict) -> dict:
    """Constrói a DSL determinística a partir da saída estruturada do LLM."""
    dsl = {"criterios": [], "exclusoes": [], "logica": structured.get("logica", "")}

    for c in structured.get("criterios", []):
        entry = {
            "id": c.get("id"),
            "tipo": c.get("tipo", "subjetivo"),
            "descricao": c.get("descricao", ""),
        }
        if c.get("tipo") == "deterministico":
            entry["campo_paciente"] = c.get("campo_paciente")
            entry["operador"] = c.get("operador")
            entry["valor"] = c.get("valor")
            if c.get("unidade"):
                entry["unidade"] = c["unidade"]
        else:
            entry["requer_llm"] = True
        dsl["criterios"].append(entry)

    for ex in structured.get("exclusoes", []):
        dsl["exclusoes"].append({
            "id": ex.get("id"),
            "tipo": "exclusao",
            "descricao": ex.get("descricao", ""),
            "origem": ex.get("origem", "corpo"),
        })

    return dsl


async def ingest_dut_rules(db_session, chunks: list[dict], structured_list: list[dict],
                            version_id, source_url: str, source_hash: str) -> dict:
    """Insere DUTs parseadas no banco."""
    from app.db.models import DutRule

    inserted = 0
    for chunk, structured in zip(chunks, structured_list):
        warnings = validate_structured_dut(structured)
        dsl = build_dsl_from_structured(structured)

        confidence = 1.0
        if warnings:
            confidence = max(0.3, 1.0 - len(warnings) * 0.15)

        faixa_min = None
        faixa_max = None
        for c in structured.get("criterios", []):
            if c.get("campo_paciente") == "idade":
                if c.get("operador") in (">=", ">"):
                    faixa_min = c.get("valor")
                elif c.get("operador") in ("<=", "<"):
                    faixa_max = c.get("valor")

        rule = DutRule(
            numero_dut=chunk["numero_dut"],
            titulo=structured.get("titulo", chunk.get("titulo", "")),
            procedimento_nome=structured.get("titulo", ""),
            procedimento_codigo=None,
            criterios_json=structured,
            criterios_texto=chunk["texto"],
            criterios_dsl=dsl,
            exames_exigidos=structured.get("exames_exigidos"),
            documentos_exigidos=structured.get("documentos_exigidos"),
            faixa_etaria_min=faixa_min,
            faixa_etaria_max=faixa_max,
            condicoes_vedacao=structured.get("exclusoes"),
            version_id=version_id,
            revisado_humano=False,
            source_url=source_url,
            source_hash=source_hash,
            page_start=chunk.get("page_start"),
            page_end=chunk.get("page_end"),
            extraction_confidence=confidence,
            extraction_warnings=warnings if warnings else None,
        )
        db_session.add(rule)
        inserted += 1

    await db_session.commit()
    return {"inserted": inserted}


async def run_etl(db_session=None, openai_api_key: str = ""):
    """Executa ETL completo da DUT."""
    print("[DUT ETL] Baixando PDF...")
    pdf_bytes = await download_dut_pdf()
    sha = compute_sha256(pdf_bytes)
    print(f"[DUT ETL] PDF baixado: {len(pdf_bytes)} bytes, SHA256: {sha[:16]}...")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "DUT_Anexo_II.pdf").write_bytes(pdf_bytes)

    print("[DUT ETL] Segmentando DUTs...")
    chunks = segment_dut_pdf(pdf_bytes)
    print(f"[DUT ETL] {len(chunks)} DUTs segmentadas")

    if not openai_api_key:
        print("[DUT ETL] Sem OPENAI_API_KEY, pulando estruturação LLM")
        return {"chunks_segmented": len(chunks), "sha256": sha}

    print("[DUT ETL] Estruturando com GPT-4o...")
    structured_list = []
    for i, chunk in enumerate(chunks):
        print(f"  [{i+1}/{len(chunks)}] DUT {chunk['numero_dut']}...")
        structured = await structure_dut_with_llm(chunk, openai_api_key)
        structured_list.append(structured)

    total_warnings = sum(len(validate_structured_dut(s)) for s in structured_list)
    print(f"[DUT ETL] Estruturação completa. Warnings totais: {total_warnings}")

    if db_session:
        from app.db.models import DutVersion
        version = DutVersion(
            versao=datetime.utcnow().strftime("%Y%m%d"),
            rn_numeros=["465/2021", "628/2025", "629/2025"],
            hash_arquivo=sha,
            url_fonte=DUT_PDF_URL,
            data_publicacao=datetime.utcnow(),
        )
        db_session.add(version)
        await db_session.flush()
        result = await ingest_dut_rules(
            db_session, chunks, structured_list,
            version.id, DUT_PDF_URL, sha,
        )
        print(f"[DUT ETL] Resultado: {result}")
        return result

    return {"chunks_segmented": len(chunks), "structured": len(structured_list), "sha256": sha}


if __name__ == "__main__":
    import os
    asyncio.run(run_etl(openai_api_key=os.getenv("OPENAI_API_KEY", "")))
