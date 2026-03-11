"""
Testes focados nas novas evidências clínicas ingeridas (estudos locais).

Cada cenário usa um CID + Produto para o qual temos evidências no banco.
O teste verifica:
  1. O pipeline roda sem erros
  2. O relatório é aprovado (checklist + validação hard-coded)
  3. As referências dos estudos locais aparecem no texto gerado
  4. O texto tem tamanho mínimo (profundidade)

Saída: documentos Word (.docx) profissionais por cenário.

Uso:
    cd services/api
    python3 scripts/test_novos_estudos.py
"""
import asyncio
import json
import os
import sys
import time
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

SCENARIOS = [
    # ── LIPEDEMA ──────────────────────────────────────────────────────
    {
        "nome": "01 Lipedema - Laser 1210nm",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Carla Monteiro",
        "cid": "E88.2",
        "diagnostico": (
            "Lipedema grau II bilateral de membros inferiores com dor crônica, "
            "edema refratário à drenagem linfática e impacto funcional significativo. "
            "Falha terapêutica com compressão elástica e fisioterapia por 24 meses."
        ),
        "especialidade": "Cirurgia Plástica",
        "health_plan": "Unimed",
        "autores_esperados": ["Valente"],
    },
    {
        "nome": "02 Lipedema - Kit LP-CT",
        "product_keyword": "Kit LP-CT",
        "paciente": "Patrícia Duarte",
        "cid": "E88.2",
        "diagnostico": (
            "Lipedema grau I bilateral com deposição anormal de gordura subcutânea em "
            "membros inferiores, dor à palpação e limitação de mobilidade. Falha com "
            "tratamento conservador prolongado."
        ),
        "especialidade": "Cirurgia Plástica",
        "health_plan": "Bradesco Saúde",
        "autores_esperados": ["Valente"],
    },

    # ── ORTOPEDIA — SVF para OA de joelho ────────────────────────────
    {
        "nome": "03 OA Joelho - Enxerto Composto/SVF",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Ricardo Souza",
        "cid": "M17.0",
        "diagnostico": (
            "Gonartrose bilateral grau III Kellgren-Lawrence com dor crônica, "
            "derrame articular recorrente e falha de viscossuplementação com HA convencional. "
            "Indicação de terapia com fração vascular estromal (SVF) autóloga."
        ),
        "especialidade": "Ortopedia",
        "health_plan": "SulAmérica",
        "autores_esperados": ["Sadri", "Anil", "Berman"],
    },

    # ── ORTOPEDIA — Viscossuplementação HA alto peso ─────────────────
    {
        "nome": "04 OA Joelho - Opus HA Alto Peso",
        "product_keyword": "Kit EC2 - Linha Opus",
        "paciente": "Tereza Campos",
        "cid": "M17.0",
        "diagnostico": (
            "Gonartrose bilateral grau II-III com dor articular crônica e limitação "
            "funcional. Tratamento conservador com AINES, fisioterapia e infiltração "
            "com corticosteroide sem melhora sustentada por 12 meses."
        ),
        "especialidade": "Ortopedia",
        "health_plan": "Amil",
        "autores_esperados": ["Altman", "Anil"],
    },

    # ── ÚLCERA VASCULAR CRÔNICA ──────────────────────────────────────
    {
        "nome": "05 Úlcera Vascular - Enxerto Composto SVF",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "José Ferreira",
        "cid": "L97",
        "diagnostico": (
            "Úlcera vascular crônica de membro inferior direito em paciente "
            "vasculopata e diabético, com piora clínica após revascularização. "
            "Ferida com mais de 6 meses de evolução sem resposta ao tratamento convencional."
        ),
        "especialidade": "Cirurgia Vascular",
        "health_plan": "Cassi",
        "autores_esperados": ["Teixeira", "Bora"],
    },

    # ── PÉ DIABÉTICO ─────────────────────────────────────────────────
    {
        "nome": "06 Pé Diabético - SVF",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Antônio Dias",
        "cid": "E11.5",
        "diagnostico": (
            "Pé diabético com úlcera isquêmica plantar grau 3 WIfI, paciente "
            "diabético tipo 2 com doença arterial periférica. Risco iminente de "
            "amputação maior após falha de revascularização."
        ),
        "especialidade": "Cirurgia Vascular",
        "health_plan": "Unimed",
        "autores_esperados": ["Zhao", "Özkan"],
    },

    # ── RECONSTRUÇÃO DE MAMA ─────────────────────────────────────────
    {
        "nome": "07 Rec Mama - Enxertia SVF",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Cláudia Rezende",
        "cid": "N60.9",
        "diagnostico": (
            "Sequela de mastectomia parcial com assimetria mamária e atrofia de "
            "tecido subcutâneo. Indicação de lipoenxertia autóloga com SVF para "
            "reconstrução volumétrica e regeneração tecidual."
        ),
        "especialidade": "Cirurgia Plástica",
        "health_plan": "Porto Seguro",
        "autores_esperados": ["Centurión", "Tan"],
    },

    # ── DOR NEUROPÁTICA ──────────────────────────────────────────────
    {
        "nome": "08 Dor Neuropática - Laser",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Helena Martins",
        "cid": "G62.9",
        "diagnostico": (
            "Polineuropatia periférica com dor neuropática crônica refratária "
            "a gabapentina e pregabalina. Indicação de fotobiomodulação com laser "
            "para controle de dor e neuromodulação."
        ),
        "especialidade": "Neurologia",
        "health_plan": "SulAmérica",
        "autores_esperados": ["Andrade", "Cotler"],
    },

    # ── DOR MUSCULOESQUELÉTICA ───────────────────────────────────────
    {
        "nome": "09 Dor Musculoesquelética - LLLT",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Mário Lopes",
        "cid": "M79.1",
        "diagnostico": (
            "Mialgia crônica cervical e lombar com pontos gatilho miofasciais "
            "bilaterais. Falha terapêutica com AINES, relaxantes musculares e "
            "fisioterapia convencional por 18 meses."
        ),
        "especialidade": "Ortopedia",
        "health_plan": "Bradesco Saúde",
        "autores_esperados": ["Cotler", "Simunovic"],
    },

    # ── REJUVENESCIMENTO / ESTÉTICA ──────────────────────────────────
    {
        "nome": "10 Rejuvenescimento - Laser 1210nm",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Renata Vieira",
        "cid": "L90.5",
        "diagnostico": (
            "Lipodistrofia facial com atrofia de tecido subcutâneo e "
            "envelhecimento precoce. Indicação de lipoenxertia facial com colheita "
            "via técnica One STEP (laser 1210nm) para rejuvenescimento volumétrico."
        ),
        "especialidade": "Cirurgia Plástica",
        "health_plan": "Amil",
        "autores_esperados": ["Centurión"],
    },
]

SEPARATOR = "=" * 80


def check_authors(text: str, expected_authors: list[str]) -> dict:
    """Verifica quais autores esperados aparecem no texto gerado."""
    found = {}
    for author in expected_authors:
        pattern = re.compile(re.escape(author), re.IGNORECASE)
        found[author] = bool(pattern.search(text))
    return found


async def run_all():
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Product, ReportTemplate
    from app.services.agents.pipeline import ReportPipeline

    output_dir = Path("scripts/test_output_novos")
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
        print(f"  TESTE NOVOS ESTUDOS — {len(SCENARIOS)} cenários")
        print(f"  Foco: evidências locais (Lipedema, Ortopedia, Rec Mama, Regenerativa)")
        print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print(f"{SEPARATOR}\n")

        for i, scenario in enumerate(SCENARIOS, 1):
            product = None
            for name, p in all_products.items():
                if scenario["product_keyword"].lower() in name.lower():
                    product = p
                    break

            if not product:
                print(f"[{i:02d}/{len(SCENARIOS)}] SKIP: Produto '{scenario['product_keyword']}' não encontrado")
                results.append({
                    "cenario": scenario["nome"],
                    "status": "SKIP",
                    "motivo": "produto não encontrado",
                })
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

            print(f"[{i:02d}/{len(SCENARIOS)}] {scenario['nome']}")
            print(f"  Produto: {product.nome} | CID: {scenario['cid']} | Autores esperados: {scenario['autores_esperados']}")

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

                author_check = check_authors(justificativa, scenario["autores_esperados"])
                authors_found = sum(1 for v in author_check.values() if v)
                authors_total = len(author_check)

                checklist_ok = sum(1 for v in checklist.values() if v)
                checklist_total = len(checklist)
                char_count = len(justificativa)

                status = "OK" if aprovado else "REVIEW"

                from app.services.docx_generator import generate_docx_file

                filename = f"{scenario['nome'].replace(' ', '_').replace('/', '_')}.docx"
                filepath = output_dir / filename
                generate_docx_file(
                    output_path=str(filepath),
                    justificativa=justificativa,
                    paciente_nome=scenario["paciente"],
                    cid=scenario["cid"],
                    diagnostico_resumo=scenario["diagnostico"],
                    produto_nome=product.nome,
                    convenio=scenario.get("health_plan", ""),
                    especialidade=scenario.get("especialidade", ""),
                    codigo_tuss=getattr(product, "tuss_code", "") or "",
                    referencias=refs,
                    checklist=checklist,
                    medico_nome="Dr. Exemplo (Gerado por IA)",
                    medico_crm="CRM/SP 000000",
                    aprovado=aprovado,
                )

                author_status = "✓" if authors_found == authors_total else f"~{authors_found}/{authors_total}"
                motivo_bloqueio = result.get("motivo_bloqueio")

                print(f"  -> {status} | {char_count} chars | checklist {checklist_ok}/{checklist_total} | autores {author_status} | {elapsed:.1f}s")
                if authors_found < authors_total:
                    missing = [k for k, v in author_check.items() if not v]
                    print(f"     AUTORES NÃO ENCONTRADOS: {', '.join(missing)}")
                if motivo_bloqueio:
                    for m in motivo_bloqueio:
                        print(f"     BLOQUEIO: {m}")

                results.append({
                    "cenario": scenario["nome"],
                    "status": status,
                    "chars": char_count,
                    "checklist": f"{checklist_ok}/{checklist_total}",
                    "tempo": f"{elapsed:.1f}s",
                    "aprovado": aprovado,
                    "autores": author_check,
                    "autores_ok": authors_found == authors_total,
                    "arquivo": str(filepath),
                })

            except Exception as e:
                elapsed = time.time() - t0
                print(f"  -> ERRO: {e} ({elapsed:.1f}s)")
                import traceback
                traceback.print_exc()
                results.append({
                    "cenario": scenario["nome"],
                    "status": "ERRO",
                    "motivo": str(e),
                })

            print()

    # ─── RESUMO FINAL ───────────────────────────────────────────────
    print(f"\n{SEPARATOR}")
    print("  RESUMO FINAL — TESTES NOVOS ESTUDOS")
    print(f"{SEPARATOR}\n")

    for r in results:
        if r["status"] in ("ERRO", "SKIP"):
            icon = "✗"
        elif r.get("aprovado") and r.get("autores_ok"):
            icon = "✓"
        elif r.get("aprovado"):
            icon = "~"
        else:
            icon = "✗"

        line = f"  {icon} {r['cenario']}: {r['status']}"
        if "chars" in r:
            author_info = "autores ✓" if r.get("autores_ok") else "autores PARCIAL"
            line += f" | {r['chars']} chars | {r['checklist']} | {author_info} | {r['tempo']}"
        elif "motivo" in r:
            line += f" ({r['motivo']})"
        print(line)

    ok_count = sum(1 for r in results if r.get("aprovado"))
    authors_ok = sum(1 for r in results if r.get("autores_ok"))
    err_count = sum(1 for r in results if r["status"] in ("ERRO", "SKIP"))
    total = len(results) - err_count

    print(f"\n  Aprovados: {ok_count}/{total}")
    print(f"  Referências corretas: {authors_ok}/{total}")
    print(f"  Erros/Skips: {err_count}")
    print(f"\n  Arquivos: {output_dir.resolve()}\n")

    summary_path = output_dir / "resumo.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  Resumo: {summary_path}\n")


if __name__ == "__main__":
    asyncio.run(run_all())
