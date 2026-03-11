"""
Teste completo da integração PubMed: 15+ cenários cobrindo todos os fluxos.

Grupos:
  A — CIDs com evidências internas (internas + PubMed)
  B — CIDs SEM evidências internas (PubMed puro)
  C — Cenários de borda (CID inválido, kill switch, cache, etc.)

Gera DOCX para cada cenário + resumo JSON.

Uso:
    cd services/api
    python scripts/test_pubmed_integration.py
"""
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

SCENARIOS = [
    # ── GRUPO A: CIDs com evidências internas ────────────────────────
    {
        "id": 1,
        "grupo": "A",
        "nome": "Lipedema - Laser (interno + PubMed)",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Carla Monteiro",
        "cid": "E88.2",
        "diagnostico": (
            "Lipedema grau II bilateral de membros inferiores com dor crônica, "
            "edema refratário à drenagem linfática. Falha terapêutica com compressão "
            "elástica e fisioterapia por 24 meses."
        ),
        "especialidade": "Cirurgia Plástica",
        "health_plan": "Unimed",
        "autores_esperados": ["Valente"],
        "expect_internal": True,
        "expect_pubmed": True,
    },
    {
        "id": 2,
        "grupo": "A",
        "nome": "OA Joelho - Enxerto SVF (interno + PubMed)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Ricardo Souza",
        "cid": "M17.0",
        "diagnostico": (
            "Gonartrose bilateral grau III Kellgren-Lawrence com dor crônica, "
            "derrame articular recorrente e falha de viscossuplementação. "
            "Indicação de SVF autóloga."
        ),
        "especialidade": "Ortopedia",
        "health_plan": "SulAmérica",
        "autores_esperados": ["Sadri"],
        "expect_internal": True,
        "expect_pubmed": True,
    },
    {
        "id": 3,
        "grupo": "A",
        "nome": "Rec Mama - Enxertia SVF (interno + PubMed)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Cláudia Rezende",
        "cid": "N60.9",
        "diagnostico": (
            "Sequela de mastectomia parcial com assimetria mamária e atrofia. "
            "Indicação de lipoenxertia autóloga com SVF."
        ),
        "especialidade": "Cirurgia Plástica",
        "health_plan": "Porto Seguro",
        "autores_esperados": ["Centurión"],
        "expect_internal": True,
        "expect_pubmed": True,
    },
    {
        "id": 4,
        "grupo": "A",
        "nome": "Pé Diabético - SVF (interno + PubMed)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Antônio Dias",
        "cid": "E11.5",
        "diagnostico": (
            "Pé diabético com úlcera isquêmica plantar grau 3 WIfI. "
            "Risco iminente de amputação maior após falha de revascularização."
        ),
        "especialidade": "Cirurgia Vascular",
        "health_plan": "Unimed",
        "autores_esperados": ["Zhao"],
        "expect_internal": True,
        "expect_pubmed": True,
    },

    # ── GRUPO B: CIDs SEM evidências internas (PubMed puro) ─────────
    {
        "id": 5,
        "grupo": "B",
        "nome": "Coxartrose - produto genérico (PubMed puro)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Fernando Almeida",
        "cid": "M16.1",
        "diagnostico": (
            "Coxartrose unilateral direita grau IV Tönnis com dor incapacitante "
            "e limitação de marcha. Falha terapêutica com AINES e fisioterapia."
        ),
        "especialidade": "Ortopedia",
        "health_plan": "Amil",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": True,
    },
    {
        "id": 6,
        "grupo": "B",
        "nome": "LCA - Parafuso Bioabsorvível (PubMed puro)",
        "product_keyword": "Adhesion STP+",
        "paciente": "Lucas Mendes",
        "cid": "S83.5",
        "diagnostico": (
            "Lesão de ligamento cruzado anterior do joelho esquerdo com "
            "instabilidade articular. Indicação de reconstrução ligamentar."
        ),
        "especialidade": "Ortopedia",
        "health_plan": "Bradesco Saúde",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": True,
    },
    {
        "id": 7,
        "grupo": "B",
        "nome": "Aderências Intestinais (PubMed puro)",
        "product_keyword": "Adhesion STP+",
        "paciente": "Maria José",
        "cid": "K56.5",
        "diagnostico": (
            "Aderências intestinais pós-operatórias com episódios de obstrução "
            "intestinal parcial recorrente."
        ),
        "especialidade": "Cirurgia Geral",
        "health_plan": "SulAmérica",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": True,
    },
    {
        "id": 8,
        "grupo": "B",
        "nome": "Manguito Rotador (PubMed puro)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Roberto Silva",
        "cid": "M75.1",
        "diagnostico": (
            "Síndrome do manguito rotador com ruptura parcial do supraespinhal "
            "direito. Dor crônica e limitação funcional refratária."
        ),
        "especialidade": "Ortopedia",
        "health_plan": "Unimed",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": True,
    },
    {
        "id": 9,
        "grupo": "B",
        "nome": "Varizes MMII (PubMed puro)",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Ana Paula",
        "cid": "I83.0",
        "diagnostico": (
            "Varizes de membros inferiores com insuficiência venosa crônica "
            "grau C4 CEAP. Dermatite ocre e eczema."
        ),
        "especialidade": "Cirurgia Vascular",
        "health_plan": "Bradesco Saúde",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": True,
    },
    {
        "id": 10,
        "grupo": "B",
        "nome": "Neoplasia Mama (PubMed puro)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Juliana Costa",
        "cid": "C50.9",
        "diagnostico": (
            "Neoplasia maligna de mama com indicação de reconstrução mamária "
            "pós-mastectomia radical."
        ),
        "especialidade": "Cirurgia Plástica",
        "health_plan": "Amil",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": True,
    },

    # ── GRUPO C: Cenários de borda ───────────────────────────────────
    {
        "id": 11,
        "grupo": "C",
        "nome": "CID inválido Z99.9 (deve gerar mesmo sem PubMed)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Teste Borda",
        "cid": "Z99.9",
        "diagnostico": "Condição genérica para teste de borda.",
        "especialidade": "Cirurgia Geral",
        "health_plan": "Teste",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": False,
    },
    {
        "id": 12,
        "grupo": "C",
        "nome": "Produto sem dados técnicos (validator não bloqueia)",
        "product_keyword": "Adhesion STP+",
        "paciente": "Teste Borda 2",
        "cid": "K66.0",
        "diagnostico": "Aderências peritoneais pós-cirúrgicas com obstrução recorrente.",
        "especialidade": "Cirurgia Geral",
        "health_plan": "Teste",
        "autores_esperados": [],
        "expect_internal": False,
        "expect_pubmed": True,
    },
    {
        "id": 13,
        "grupo": "C",
        "nome": "PubMed desligado (kill switch)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Teste Kill Switch",
        "cid": "M17.0",
        "diagnostico": "Gonartrose bilateral para teste de kill switch.",
        "especialidade": "Ortopedia",
        "health_plan": "Teste",
        "autores_esperados": [],
        "expect_internal": True,
        "expect_pubmed": False,
        "kill_switch": True,
    },
    {
        "id": 14,
        "grupo": "C",
        "nome": "CID repetido (cache - 2a vez mais rápido)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Teste Cache",
        "cid": "M17.0",
        "diagnostico": "Gonartrose bilateral para teste de cache PubMed.",
        "especialidade": "Ortopedia",
        "health_plan": "Teste",
        "autores_esperados": [],
        "expect_internal": True,
        "expect_pubmed": True,
        "cache_test": True,
    },
    {
        "id": 15,
        "grupo": "C",
        "nome": "CID com muitas evidências (limita a 10)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Teste Limite",
        "cid": "M17.0",
        "diagnostico": "Gonartrose bilateral para teste de limite de evidências.",
        "especialidade": "Ortopedia",
        "health_plan": "Teste",
        "autores_esperados": [],
        "expect_internal": True,
        "expect_pubmed": True,
        "check_pubmed_limit": True,
    },
]

SEPARATOR = "=" * 80
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m~\033[0m"


def check_authors(text: str, expected_authors: list[str]) -> dict:
    found = {}
    for author in expected_authors:
        pattern = re.compile(re.escape(author), re.IGNORECASE)
        found[author] = bool(pattern.search(text))
    return found


def validate_pubmed_quality(pubmed_evidences: list[dict]) -> list[str]:
    """Valida qualidade dos abstracts PubMed (seção 4.4 do plano)."""
    issues = []
    for ev in pubmed_evidences:
        pmid = ev.get("pmid", "?")
        if not ev.get("snippet"):
            issues.append(f"PMID {pmid}: abstract vazio")
        autor = ev.get("autor", "")
        if len(autor) < 3 or any(c.isdigit() for c in autor):
            issues.append(f"PMID {pmid}: autor inválido '{autor}'")
        ano = ev.get("ano", "")
        if not ano.isdigit() or not (2000 <= int(ano) <= 2026):
            issues.append(f"PMID {pmid}: ano fora do range '{ano}'")
        if not str(ev.get("pmid", "")).isdigit():
            issues.append(f"PMID {pmid}: PMID não numérico")
    return issues


async def run_scenario(scenario, db, all_products, all_templates, output_dir, first_run_times=None):
    """Roda um cenário individual e retorna resultado."""
    from app.services.agents.pipeline import ReportPipeline
    from app.services.pubmed_service import get_evidences_for_cid
    from app.core.config import settings

    product = None
    for name, p in all_products.items():
        if scenario["product_keyword"].lower() in name.lower():
            product = p
            break

    if not product:
        return {
            "id": scenario["id"],
            "grupo": scenario["grupo"],
            "cenario": scenario["nome"],
            "status": "SKIP",
            "motivo": f"Produto '{scenario['product_keyword']}' não encontrado",
        }

    template = all_templates.get(str(product.id))

    kill_switch_active = scenario.get("kill_switch", False)
    original_enabled = settings.PUBMED_ENABLED
    if kill_switch_active:
        settings.PUBMED_ENABLED = False

    medico_inputs = {
        "paciente_nome": scenario["paciente"],
        "cid": scenario["cid"],
        "diagnostico": scenario["diagnostico"],
        "surgery_description": "",
        "health_plan": scenario.get("health_plan", ""),
        "especialidade": scenario.get("especialidade", ""),
    }

    t0 = time.time()
    try:
        pubmed_evs = await get_evidences_for_cid(
            db, scenario["cid"], product.nome, scenario["diagnostico"]
        )

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
            result = await ReportPipeline.answer(result["session_id"], answers)
            elapsed = time.time() - t0

        justificativa = result.get("justificativa", "")
        aprovado = result.get("aprovado", False)
        checklist = result.get("checklist", {})
        refs = result.get("referencias", [])
        usage = result.get("usage", {})

        author_check = check_authors(justificativa, scenario["autores_esperados"])
        pubmed_quality_issues = validate_pubmed_quality(pubmed_evs) if pubmed_evs else []

        from app.services.docx_generator import generate_docx_file

        filename = f"{scenario['id']:02d}_{scenario['nome'].replace(' ', '_').replace('/', '_')}.docx"
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

        checklist_ok = sum(1 for v in checklist.values() if v)
        checklist_total = len(checklist)

        validations = []
        validations.append(("pipeline sem erro", True))
        validations.append(("checklist completo", checklist_ok == checklist_total and checklist_total == 6))
        validations.append(("DOCX gerado", filepath.exists()))

        if scenario["autores_esperados"]:
            authors_ok = all(author_check.values())
            validations.append(("autores citados", authors_ok))

        if scenario.get("expect_pubmed") and not kill_switch_active:
            has_pubmed = len(pubmed_evs) > 0
            validations.append(("PubMed usado", has_pubmed))

        if kill_switch_active:
            validations.append(("PubMed NÃO usado (kill switch)", len(pubmed_evs) == 0))

        if scenario.get("check_pubmed_limit"):
            validations.append(("PubMed <= 10 artigos", len(pubmed_evs) <= 10))

        if scenario.get("cache_test") and first_run_times:
            first_time = first_run_times.get(scenario["cid"])
            if first_time:
                validations.append(("cache mais rápido", elapsed < first_time))

        if pubmed_quality_issues:
            for issue in pubmed_quality_issues:
                validations.append((f"quality: {issue}", False))

        validations.append(("custo registrado", bool(usage)))

        return {
            "id": scenario["id"],
            "grupo": scenario["grupo"],
            "cenario": scenario["nome"],
            "status": "OK" if aprovado else "REVIEW",
            "aprovado": aprovado,
            "chars": len(justificativa),
            "checklist": f"{checklist_ok}/{checklist_total}",
            "tempo": f"{elapsed:.1f}s",
            "tempo_s": elapsed,
            "pubmed_count": len(pubmed_evs),
            "autores": author_check,
            "validations": validations,
            "usage": usage,
            "arquivo": str(filepath),
            "pubmed_quality_issues": pubmed_quality_issues,
        }

    except Exception as e:
        elapsed = time.time() - t0
        import traceback
        traceback.print_exc()
        return {
            "id": scenario["id"],
            "grupo": scenario["grupo"],
            "cenario": scenario["nome"],
            "status": "ERRO",
            "motivo": str(e),
            "tempo": f"{elapsed:.1f}s",
        }
    finally:
        if kill_switch_active:
            settings.PUBMED_ENABLED = original_enabled


async def run_all():
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Product, ReportTemplate

    output_dir = Path("scripts/test_output_pubmed")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    first_run_times = {}

    async with AsyncSessionLocal() as db:
        prod_result = await db.execute(select(Product))
        all_products = {p.nome: p for p in prod_result.scalars().all()}

        tmpl_result = await db.execute(select(ReportTemplate))
        all_templates = {}
        for t in tmpl_result.scalars().all():
            if t.produto_id:
                all_templates[str(t.produto_id)] = t

        print(f"\n{SEPARATOR}")
        print(f"  TESTE INTEGRAÇÃO PUBMED — {len(SCENARIOS)} cenários")
        print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print(f"{SEPARATOR}\n")

        for i, scenario in enumerate(SCENARIOS, 1):
            print(f"[{i:02d}/{len(SCENARIOS)}] [{scenario['grupo']}] {scenario['nome']}")
            print(f"  CID: {scenario['cid']} | Produto: {scenario['product_keyword']}")

            res = await run_scenario(scenario, db, all_products, all_templates, output_dir, first_run_times)
            results.append(res)

            if res.get("tempo_s") and scenario["cid"] not in first_run_times:
                first_run_times[scenario["cid"]] = res["tempo_s"]

            if res["status"] == "ERRO":
                print(f"  -> ERRO: {res.get('motivo', '?')}")
            elif res["status"] == "SKIP":
                print(f"  -> SKIP: {res.get('motivo', '?')}")
            else:
                validations = res.get("validations", [])
                passed = sum(1 for _, ok in validations if ok)
                total = len(validations)
                icon = PASS if passed == total else (WARN if passed > total // 2 else FAIL)
                print(f"  -> {icon} {res['status']} | {res['chars']} chars | checklist {res['checklist']} | "
                      f"PubMed: {res.get('pubmed_count', 0)} | {res['tempo']}")

                fails = [(n, ok) for n, ok in validations if not ok]
                for name, _ in fails:
                    print(f"     {FAIL} {name}")

            print()

    # ─── RESUMO FINAL ───────────────────────────────────────────────
    print(f"\n{SEPARATOR}")
    print("  RESUMO FINAL — INTEGRAÇÃO PUBMED")
    print(f"{SEPARATOR}\n")

    total_validations = 0
    total_passed = 0
    for r in results:
        validations = r.get("validations", [])
        v_passed = sum(1 for _, ok in validations if ok)
        v_total = len(validations)
        total_validations += v_total
        total_passed += v_passed

        if r["status"] in ("ERRO", "SKIP"):
            icon = FAIL
        elif v_passed == v_total and v_total > 0:
            icon = PASS
        else:
            icon = WARN

        print(f"  {icon} [{r['grupo']}] {r['cenario']}: {r['status']} ({v_passed}/{v_total} checks)")

    print(f"\n  {'─' * 50}")
    ok_count = sum(1 for r in results if r.get("aprovado"))
    err_count = sum(1 for r in results if r["status"] in ("ERRO", "SKIP"))
    pipeline_total = len(results) - err_count

    # Usage totals
    total_tokens = 0
    total_usd = 0.0
    total_brl = 0.0
    for r in results:
        usage = r.get("usage", {})
        totals = usage.get("totals", {}) if isinstance(usage, dict) else {}
        total_tokens += totals.get("total_tokens", 0)
        total_usd += totals.get("cost_usd", 0)
        total_brl += totals.get("cost_brl", 0)

    print(f"  Cenários executados: {pipeline_total}/{len(SCENARIOS)}")
    print(f"  Relatórios aprovados: {ok_count}/{pipeline_total}")
    print(f"  Validações: {total_passed}/{total_validations}")
    print(f"  Erros/Skips: {err_count}")
    print(f"\n  Custo total: {total_tokens:,} tokens | ${total_usd:.4f} | R${total_brl:.4f}")
    print(f"\n  Arquivos DOCX: {output_dir.resolve()}")

    summary_path = output_dir / "resumo.json"
    safe_results = []
    for r in results:
        sr = {k: v for k, v in r.items() if k != "usage"}
        usage = r.get("usage", {})
        if isinstance(usage, dict):
            sr["usage_totals"] = usage.get("totals", {})
        safe_results.append(sr)

    with open(summary_path, "w") as f:
        json.dump(safe_results, f, indent=2, ensure_ascii=False)
    print(f"  Resumo JSON: {summary_path}\n")


if __name__ == "__main__":
    asyncio.run(run_all())
