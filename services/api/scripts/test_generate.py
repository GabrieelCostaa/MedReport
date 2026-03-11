"""
Script de teste em massa: gera relatórios para vários cenários via pipeline direto.
Uso:  cd services/api && python scripts/test_generate.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

SCENARIOS = [
    {
        "nome": "Opus - Gonartrose Bilateral",
        "product_keyword": "Kit EC2 - Linha Opus",
        "paciente": "Gabriel Costa",
        "cid": "M17.0",
        "diagnostico": "Gonartrose bilateral de joelhos, grau III Kellgren-Lawrence, com dor crônica e limitação funcional significativa",
        "especialidade": "Ortopedia",
        "health_plan": "Unimed",
    },
    {
        "nome": "Adhesion - Aderências Peritoneais",
        "product_keyword": "Adhesion STP+",
        "paciente": "Maria Silva",
        "cid": "K66.0",
        "diagnostico": "Aderências peritoneais pós-cirúrgicas com obstrução intestinal parcial recorrente",
        "especialidade": "Cirurgia Geral",
        "health_plan": "Bradesco Saúde",
    },
    {
        "nome": "Laser - Hipertrofia de Cornetos",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "João Oliveira",
        "cid": "J34.3",
        "diagnostico": "Hipertrofia de cornetos nasais inferiores bilaterais refratária a tratamento clínico",
        "especialidade": "Otorrinolaringologia",
        "health_plan": "Amil",
    },
    {
        "nome": "Biossilex - Osteomielite",
        "product_keyword": "Biossilex",
        "paciente": "Carlos Mendes",
        "cid": "M86.9",
        "diagnostico": "Osteomielite crônica de tíbia com falha de consolidação e infecção recorrente",
        "especialidade": "Ortopedia",
        "health_plan": "SulAmérica",
    },
    {
        "nome": "Vitagraft - Pseudoartrose",
        "product_keyword": "Vitagraft",
        "paciente": "Ana Pereira",
        "cid": "M84.1",
        "diagnostico": "Pseudoartrose de fêmur com falha de consolidação óssea após fratura prévia",
        "especialidade": "Ortopedia",
        "health_plan": "Porto Seguro",
    },
    {
        "nome": "Opus - Gonartrose Unilateral",
        "product_keyword": "Kit EC2 - Linha Opus",
        "paciente": "Roberto Almeida",
        "cid": "M17.1",
        "diagnostico": "Gonartrose unilateral de joelho direito, grau II-III Kellgren-Lawrence, com derrame articular recorrente e sinovite crônica",
        "especialidade": "Ortopedia",
        "health_plan": "Cassi",
    },
    {
        "nome": "Adhesion - Obstrução Intestinal",
        "product_keyword": "Adhesion STP+",
        "paciente": "Fernanda Lima",
        "cid": "K56.5",
        "diagnostico": "Obstrução intestinal por bridas peritoneais com necessidade de lise cirúrgica e prevenção de recidiva",
        "especialidade": "Cirurgia Geral",
        "health_plan": "Unimed",
    },
    {
        "nome": "Laser - Amigdalectomia",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Pedro Santos",
        "cid": "J35.1",
        "diagnostico": "Hipertrofia amigdaliana grau IV com apneia obstrutiva do sono moderada-grave e infecções de repetição",
        "especialidade": "Otorrinolaringologia",
        "health_plan": "SulAmérica",
    },
    {
        "nome": "Enxerto Composto - Peyronie",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Marcos Ribeiro",
        "cid": "N48.6",
        "diagnostico": "Doença de Peyronie com curvatura peniana >60 graus, placa fibrótica estável e disfunção erétil associada",
        "especialidade": "Urologia",
        "health_plan": "Bradesco Saúde",
    },
    {
        "nome": "Opus - Condropatia Patelar",
        "product_keyword": "Kit EC2 - Linha Opus",
        "paciente": "Luciana Ferreira",
        "cid": "M17.0",
        "diagnostico": "Condropatia patelar grau III-IV com lesão condral focal e falha de tratamento conservador prolongado por 18 meses",
        "especialidade": "Ortopedia",
        "health_plan": "Amil",
    },
]

SEPARATOR = "=" * 80


async def run_all():
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Product, ReportTemplate
    from app.services.agents.pipeline import ReportPipeline

    output_dir = Path("scripts/test_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    async with AsyncSessionLocal() as db:
        prod_result = await db.execute(select(Product))
        all_products = {p.nome: p for p in prod_result.scalars().all()}

        tmpl_result = await db.execute(select(ReportTemplate))
        all_templates = {}
        for t in tmpl_result.scalars().all():
            if t.produto_id:
                all_templates[str(t.produto_id)] = t

        print(f"\n{SEPARATOR}")
        print(f"  TESTE EM MASSA - {len(SCENARIOS)} cenários")
        print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print(f"{SEPARATOR}\n")
        print(f"Produtos no banco: {list(all_products.keys())}\n")

        for i, scenario in enumerate(SCENARIOS, 1):
            product = None
            for name, p in all_products.items():
                if scenario["product_keyword"].lower() in name.lower():
                    product = p
                    break

            if not product:
                print(f"[{i}/{len(SCENARIOS)}] SKIP: Produto '{scenario['product_keyword']}' não encontrado")
                results.append({"cenario": scenario["nome"], "status": "SKIP", "motivo": "produto não encontrado"})
                continue

            template = all_templates.get(str(product.id))

            medico_inputs = {
                "paciente_nome": scenario["paciente"],
                "cid": scenario["cid"],
                "diagnostico": scenario["diagnostico"],
                "surgery_description": "",
                "health_plan": scenario.get("health_plan", ""),
                "especialidade": scenario.get("especialidade", ""),
            }

            print(f"[{i}/{len(SCENARIOS)}] Gerando: {scenario['nome']}...")
            print(f"  Produto: {product.nome} | CID: {scenario['cid']} | Paciente: {scenario['paciente']}")

            t0 = time.time()
            try:
                result = await ReportPipeline.start(
                    product=product,
                    template=template,
                    diagnostico=scenario["diagnostico"],
                    cid=scenario["cid"],
                    medico_inputs=medico_inputs,
                    db=db,
                )
                elapsed = time.time() - t0

                if result.get("step") == "questions":
                    answers = {}
                    for q in result.get("questions", []):
                        secao = q["secao"]
                        opcoes = q.get("opcoes", [])
                        answers[secao] = opcoes[0]["texto"] if opcoes else "Tratamento conservador sem melhora"
                    print(f"  -> Respondendo {len(answers)} perguntas automáticas...")
                    result = await ReportPipeline.answer(result["session_id"], answers)
                    elapsed = time.time() - t0

                justificativa = result.get("justificativa", "")
                aprovado = result.get("aprovado", False)
                checklist = result.get("checklist", {})
                refs = result.get("referencias", [])

                checklist_ok = sum(1 for v in checklist.values() if v)
                checklist_total = len(checklist)
                char_count = len(justificativa)

                status = "OK" if aprovado else "REVIEW"

                filename = f"{i:02d}_{scenario['product_keyword'].replace(' ', '_').replace('-', '')}.txt"
                filepath = output_dir / filename
                with open(filepath, "w") as f:
                    f.write(f"CENÁRIO: {scenario['nome']}\n")
                    f.write(f"PRODUTO: {product.nome}\n")
                    f.write(f"PACIENTE: {scenario['paciente']}\n")
                    f.write(f"CID: {scenario['cid']}\n")
                    f.write(f"DIAGNÓSTICO: {scenario['diagnostico']}\n")
                    f.write(f"APROVADO: {aprovado}\n")
                    f.write(f"CHECKLIST: {checklist_ok}/{checklist_total}\n")
                    f.write(f"CARACTERES: {char_count}\n")
                    f.write(f"TEMPO: {elapsed:.1f}s\n")
                    f.write(f"REFERÊNCIAS: {json.dumps(refs, ensure_ascii=False)}\n")
                    motivo_bloqueio = result.get("motivo_bloqueio")
                    if motivo_bloqueio:
                        f.write(f"MOTIVO BLOQUEIO: {json.dumps(motivo_bloqueio, ensure_ascii=False)}\n")
                    f.write(f"\n{'=' * 60}\n")
                    f.write(f"RELATÓRIO GERADO:\n{'=' * 60}\n\n")
                    f.write(justificativa)
                    f.write(f"\n\n{'=' * 60}\n")
                    f.write(f"CHECKLIST DETALHADO:\n{json.dumps(checklist, indent=2, ensure_ascii=False)}\n")
                    f.write(f"\nAUDIT LOG:\n{json.dumps(result.get('audit_log', []), indent=2, ensure_ascii=False)}\n")

                motivo_bloqueio = result.get("motivo_bloqueio")
                status_line = f"  -> {status} | {char_count} chars | checklist {checklist_ok}/{checklist_total} | {elapsed:.1f}s"
                if motivo_bloqueio:
                    status_line += f"\n     BLOQUEIO: {motivo_bloqueio[0]}" if len(motivo_bloqueio) == 1 else f"\n     BLOQUEIOS: {len(motivo_bloqueio)} motivos"
                print(status_line)
                print(f"  -> Salvo em: {filepath}")

                results.append({
                    "cenario": scenario["nome"],
                    "status": status,
                    "chars": char_count,
                    "checklist": f"{checklist_ok}/{checklist_total}",
                    "tempo": f"{elapsed:.1f}s",
                    "aprovado": aprovado,
                    "arquivo": str(filepath),
                })

            except Exception as e:
                elapsed = time.time() - t0
                print(f"  -> ERRO: {e} ({elapsed:.1f}s)")
                results.append({"cenario": scenario["nome"], "status": "ERRO", "motivo": str(e)})

            print()

    print(f"\n{SEPARATOR}")
    print("  RESUMO FINAL")
    print(f"{SEPARATOR}\n")

    for r in results:
        icon = "✓" if r.get("aprovado") else "✗" if r["status"] == "ERRO" else "~"
        line = f"  {icon} {r['cenario']}: {r['status']}"
        if "chars" in r:
            line += f" | {r['chars']} chars | checklist {r['checklist']} | {r['tempo']}"
        elif "motivo" in r:
            line += f" ({r['motivo']})"
        print(line)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    review_count = sum(1 for r in results if r["status"] == "REVIEW")
    err_count = sum(1 for r in results if r["status"] in ("ERRO", "SKIP"))
    print(f"\n  Total: {ok_count} aprovados | {review_count} para revisão | {err_count} erros/skips")
    print(f"  Arquivos salvos em: {output_dir.resolve()}\n")

    summary_path = output_dir / "resumo.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  Resumo JSON: {summary_path}\n")


if __name__ == "__main__":
    asyncio.run(run_all())
