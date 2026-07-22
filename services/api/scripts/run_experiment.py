"""
Harness de experimentação: prova EMPÍRICA de que as melhorias do algoritmo
de LLM ajudam (ou não), antes de ligar qualquer flag pago por padrão.

Desenho experimental:
- TRATAMENTO: as feature flags (compliance no prompt, autofill de
  especialidade, corte de evidência) mudam APENAS a geração.
- MEDIÇÃO: uniforme e pós-hoc para TODAS as configs — fidelidade
  (decompose-then-verify), relevância (juiz), precisão de citação
  (determinística), tamanho, aprovação, contaminação e custo. Se a medição
  dependesse das flags, o baseline não teria número para comparar.

Uso (na pasta services/api, com .env carregando OPENAI_API_KEY e DATABASE_URL):

  # Validar a fiação sem gastar (fallbacks rodam, custo R$0):
  python3 scripts/run_experiment.py --dry-run

  # Smoke test aprovado (~R$6): 8 casos x 2 configs
  python3 scripts/run_experiment.py --configs baseline,all --max-cases 8

  # Sweep isolando cada melhoria (mais caro, sob demanda):
  python3 scripts/run_experiment.py --configs baseline,+compliance,+evidence,all --max-cases 8
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("scripts/test_output_experiment")

# Custo estimado por laudo por config (2x gpt-4o + medição em gpt-4o-mini)
EST_COST_BRL_PER_RUN = 0.40

# ─── Configs experimentais ───────────────────────────────────────────────────
# Cada config define APENAS flags de geração. A medição é sempre igual.
CONFIGS = {
    "baseline": {
        "COMPLIANCE_PROMPT_ENABLED": False,
        "ESPECIALIDADE_AUTOFILL_ENABLED": False,
        "EVIDENCE_RERANK_CUT": 0,
        "FAITHFULNESS_GATE_ENABLED": False,
        "QUALITY_METRICS_ENABLED": False,
        "DYNAMIC_FEWSHOT_ENABLED": False,
    },
    "+compliance": {
        "COMPLIANCE_PROMPT_ENABLED": True,
        "ESPECIALIDADE_AUTOFILL_ENABLED": True,
        "EVIDENCE_RERANK_CUT": 0,
        "FAITHFULNESS_GATE_ENABLED": False,
        "QUALITY_METRICS_ENABLED": False,
        "DYNAMIC_FEWSHOT_ENABLED": False,
    },
    "+evidence": {
        "COMPLIANCE_PROMPT_ENABLED": False,
        "ESPECIALIDADE_AUTOFILL_ENABLED": False,
        "EVIDENCE_RERANK_CUT": 6,
        "FAITHFULNESS_GATE_ENABLED": False,
        "QUALITY_METRICS_ENABLED": False,
        "DYNAMIC_FEWSHOT_ENABLED": False,
    },
    "all": {
        "COMPLIANCE_PROMPT_ENABLED": True,
        "ESPECIALIDADE_AUTOFILL_ENABLED": True,
        "EVIDENCE_RERANK_CUT": 6,
        "FAITHFULNESS_GATE_ENABLED": True,
        "QUALITY_METRICS_ENABLED": True,
        "DYNAMIC_FEWSHOT_ENABLED": False,  # precisa de edits reais no banco
    },
}

# Respostas canônicas para as perguntas A/B/C (mesmas para todas as configs)
CANNED_ANSWERS = {
    "falha_terapeutica": (
        "AINEs orais e fisioterapia motora por 12 semanas, seguidos de 2 "
        "infiltrações de corticoide em 6 meses, sem melhora funcional"
    ),
    "risco_nao_realizacao": (
        "Progressão da doença com perda funcional irreversível e necessidade "
        "de procedimento de maior porte e morbidade"
    ),
    "diagnostico": "Confirmado por exame de imagem e avaliação clínica",
}


def _load_scenarios(max_cases: int) -> list[dict]:
    """Reusa os cenários do simulate_doctor (inclui casos adversariais)."""
    from scripts.simulate_doctor import SCENARIOS
    return SCENARIOS[:max_cases]


async def _find_product(db, keyword: str):
    from sqlalchemy import select
    from app.db.models import Product
    rows = (await db.execute(select(Product))).scalars().all()
    kw = keyword.lower()
    for p in rows:
        if kw in (p.nome or "").lower():
            return p
    # fallback: primeiro produto (mantém o experimento rodando)
    return rows[0] if rows else None


def _apply_config(config: dict):
    from app.core.config import settings
    for key, value in config.items():
        setattr(settings, key, value)


async def _run_case(db, scenario: dict, config_name: str) -> dict | None:
    """Roda o pipeline real para um cenário e devolve resultado + medição."""
    from app.services.agents.pipeline import ReportPipeline

    product = await _find_product(db, scenario.get("product_keyword", ""))
    if product is None:
        print(f"    !! produto não encontrado p/ '{scenario.get('product_keyword')}' — pulando")
        return None

    medico_inputs = {
        "paciente_nome": scenario.get("paciente_nome", "Paciente Teste"),
        "health_plan": scenario.get("health_plan", ""),
    }
    if scenario.get("especialidade") and "autofill" not in scenario.get("id", ""):
        medico_inputs["especialidade"] = scenario["especialidade"]

    result = await ReportPipeline.start(
        product=product,
        template=None,
        diagnostico=scenario["diagnostico"],
        cid=scenario["cid"],
        medico_inputs=medico_inputs,
        db=db,
    )
    if result.get("error"):
        print(f"    !! erro: {result['error']}")
        return None

    # Responde as perguntas A/B/C com respostas canônicas (iguais p/ todas configs)
    for _ in range(3):
        if result.get("step") != "questions":
            break
        answers = {}
        for q in result.get("questions", []):
            secao = q.get("secao", "")
            answers[secao] = CANNED_ANSWERS.get(
                secao, (q.get("opcoes") or [{}])[0].get("texto", "Sim")
            )
        result = await ReportPipeline.answer(result["session_id"], answers)
        if result.get("error"):
            print(f"    !! erro no answer: {result['error']}")
            return None

    session = ReportPipeline.get_session(result.get("session_id", ""))
    measurement = await _measure(result, session, product)
    ReportPipeline._cleanup_session(result.get("session_id", ""))
    return {"scenario": scenario["id"], "config": config_name,
            "result_meta": _result_meta(result), "measurement": measurement,
            # Texto completo: permite re-medir com um medidor melhor sem
            # pagar a regeneração (o caro são os 2 agentes gpt-4o).
            "texto": result.get("justificativa") or ""}


def _result_meta(result: dict) -> dict:
    usage = (result.get("usage") or {}).get("totals", {})
    return {
        "aprovado": result.get("aprovado"),
        "tamanho_chars": len(result.get("justificativa") or ""),
        "n_referencias": len(result.get("referencias") or []),
        "approval_score": result.get("approval_score"),
        "custo_brl": usage.get("cost_brl"),
        "tokens": usage.get("total_tokens"),
        "motivos_bloqueio": result.get("motivo_bloqueio"),
    }


async def _measure(result: dict, session, product) -> dict:
    """Medição uniforme pós-hoc — independe das flags de geração."""
    texto = result.get("justificativa") or ""
    clinical = session.clinical_evidences if session else []
    pubmed = session.pubmed_evidences if session else []
    medico = session.medico_inputs if session else {}

    m: dict = {}

    # 1. Fidelidade (decompose-then-verify)
    try:
        from app.services.agents.faithfulness import verify_faithfulness
        f = await verify_faithfulness(texto, product, clinical, pubmed, medico)
        m["faithfulness"] = f.score
        m["claims_verificaveis"] = f.verifiable_claims
        m["claims_sem_sustentacao"] = len(f.ungrounded)
        m["cobertura"] = f.cobertura
        m["claims_total"] = f.total_claims
        if f.token_usage:
            m["custo_medicao_brl"] = round(f.token_usage.cost_brl, 4)
    except Exception as e:
        m["faithfulness_error"] = str(e)

    # 2. Relevância + citação (todas as fontes legítimas da Regra #11)
    try:
        from app.services.quality_metrics import compute_quality_metrics
        extra_refs = list(getattr(product, "referencias_bibliograficas", None) or [])
        research = getattr(session, "research_result", None) if session else None
        if research:
            extra_refs += [e.referencia for e in research.evidencias if e.referencia]
            extra_refs += list(research.referencias or [])
        q = await compute_quality_metrics(
            texto,
            cid=medico.get("cid", ""),
            diagnostico=medico.get("diagnostico", ""),
            product_name=getattr(product, "nome", ""),
            clinical_evidences=clinical,
            pubmed_evidences=pubmed,
            faithfulness_score=m.get("faithfulness"),
            extra_references=extra_refs,
        )
        m["relevancy"] = q.relevancy
        m["citation"] = q.citation
        m["citation_details"] = (q.details or {}).get("citation", {})
        if q.token_usage:
            m["custo_medicao_brl"] = round(
                m.get("custo_medicao_brl", 0.0) + q.token_usage.cost_brl, 4
            )
    except Exception as e:
        m["quality_error"] = str(e)

    # 3. Contaminação (determinístico)
    # `all_products` é OBRIGATÓRIO aqui: sem ele a detecção cruzada entre
    # produtos nem roda, e a métrica media só idioma e artefatos de IA — foi
    # exatamente por isso que um smoke test anterior reportou "contaminação 0"
    # sem ter testado mistura de produtos.
    try:
        from app.services.contamination_detector import check_contamination
        outros = session.other_products if session else None
        c = check_contamination(texto, product, all_products=outros or None)
        m["contaminacao_bloqueante"] = c.has_blocking
        m["contaminacao_issues"] = len(c.issues)
        m["contaminacao_produtos_comparados"] = len(outros or [])
        m["contaminacao_tipos"] = sorted({i.tipo for i in c.issues})
    except Exception as e:
        m["contamination_error"] = str(e)

    return m


def _summarize(rows: list[dict]) -> dict:
    """Tabela comparativa: média das métricas por config."""
    by_config: dict[str, list[dict]] = {}
    for r in rows:
        by_config.setdefault(r["config"], []).append(r)

    def _avg(items, path1, path2):
        vals = [
            it[path1].get(path2) for it in items
            if isinstance(it[path1].get(path2), (int, float))
        ]
        return round(sum(vals) / len(vals), 3) if vals else None

    summary = {}
    for config, items in by_config.items():
        summary[config] = {
            "n_casos": len(items),
            "faithfulness_media": _avg(items, "measurement", "faithfulness"),
            "cobertura_media": _avg(items, "measurement", "cobertura"),
            "relevancy_media": _avg(items, "measurement", "relevancy"),
            "citation_media": _avg(items, "measurement", "citation"),
            "claims_sem_sustentacao_media": _avg(items, "measurement", "claims_sem_sustentacao"),
            "contaminacao_bloqueante": sum(
                1 for it in items if it["measurement"].get("contaminacao_bloqueante")
            ),
            # Quantos produtos a detecção cruzada de fato comparou. Se vier 0,
            # a coluna de contaminação não significa nada — é cegueira, não
            # ausência de contaminação.
            "produtos_comparados_media": _avg(items, "measurement", "contaminacao_produtos_comparados"),
            "tamanho_medio_chars": _avg(items, "result_meta", "tamanho_chars"),
            "aprovados_pipeline": sum(1 for it in items if it["result_meta"].get("aprovado")),
            "approval_score_medio": _avg(items, "result_meta", "approval_score"),
            "custo_medio_brl": _avg(items, "result_meta", "custo_brl"),
        }
    return summary


def _print_table(summary: dict):
    cols = [
        ("config", 12), ("n", 3), ("fidelid.", 9), ("relev.", 7), ("citação", 8),
        ("s/sust.", 8), ("contam.", 8), ("chars", 6), ("aprov.", 7), ("score", 6), ("R$", 6),
    ]
    print("\n" + "═" * 84)
    print("RESULTADO DO EXPERIMENTO")
    print("═" * 84)
    print(" | ".join(name.ljust(w) for name, w in cols))
    print("-" * 84)
    for config, s in summary.items():
        def _f(v):
            return "—" if v is None else (f"{v}" if isinstance(v, int) else f"{v:.3f}")
        row = [
            config.ljust(12), str(s["n_casos"]).ljust(3),
            _f(s["faithfulness_media"]).ljust(9), _f(s["relevancy_media"]).ljust(7),
            _f(s["citation_media"]).ljust(8), _f(s["claims_sem_sustentacao_media"]).ljust(8),
            str(s["contaminacao_bloqueante"]).ljust(8),
            ("—" if s["tamanho_medio_chars"] is None else str(int(s["tamanho_medio_chars"]))).ljust(6),
            str(s["aprovados_pipeline"]).ljust(7),
            _f(s["approval_score_medio"]).ljust(6),
            _f(s["custo_medio_brl"]).ljust(6),
        ]
        print(" | ".join(row))
    print("═" * 84)


async def main():
    parser = argparse.ArgumentParser(description="Experimento A/B do algoritmo de LLM")
    parser.add_argument("--configs", default="baseline,all",
                        help=f"Configs separadas por vírgula ({', '.join(CONFIGS)})")
    parser.add_argument("--max-cases", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true",
                        help="Sem OPENAI (fallbacks rodam) — valida a fiação a R$0")
    parser.add_argument("--yes", action="store_true", help="Não pedir confirmação de custo")
    args = parser.parse_args()

    config_names = [c.strip() for c in args.configs.split(",") if c.strip()]
    for c in config_names:
        if c not in CONFIGS:
            print(f"Config desconhecida: {c}. Válidas: {', '.join(CONFIGS)}")
            sys.exit(1)

    if args.dry_run:
        os.environ["OPENAI_API_KEY"] = ""
        from app.core.config import settings
        settings.OPENAI_API_KEY = ""
        print(">> DRY-RUN: sem chamadas OpenAI (fallbacks determinísticos, custo R$0)\n")

    scenarios = _load_scenarios(args.max_cases)
    n_runs = len(scenarios) * len(config_names)
    projected = n_runs * EST_COST_BRL_PER_RUN

    print(f"Experimento: {len(scenarios)} casos × {len(config_names)} configs = {n_runs} gerações")
    if not args.dry_run:
        print(f"Custo projetado: ~R${projected:.2f} (≈R${EST_COST_BRL_PER_RUN:.2f}/geração)")
        if not args.yes:
            resp = input("Prosseguir? [s/N] ").strip().lower()
            if resp not in ("s", "sim", "y", "yes"):
                print("Abortado.")
                sys.exit(0)

    from app.db.session import AsyncSessionLocal
    from app.core.config import settings

    original = {k: getattr(settings, k) for k in CONFIGS["all"]}
    rows = []
    try:
        for config_name in config_names:
            print(f"\n── Config: {config_name} ──")
            _apply_config(CONFIGS[config_name])
            for i, sc in enumerate(scenarios, 1):
                print(f"  [{i}/{len(scenarios)}] {sc['id']}...", flush=True)
                async with AsyncSessionLocal() as db:
                    try:
                        row = await _run_case(db, sc, config_name)
                        if row:
                            rows.append(row)
                            meas = row["measurement"]
                            print(
                                f"      fidelidade={meas.get('faithfulness')} "
                                f"relev={meas.get('relevancy')} cit={meas.get('citation')} "
                                f"chars={row['result_meta']['tamanho_chars']}"
                            )
                    except Exception as e:
                        print(f"    !! exceção: {e}")
    finally:
        for k, v in original.items():
            setattr(settings, k, v)

    if not rows:
        print("\nNenhum caso completou — verifique DATABASE_URL/seed de produtos.")
        sys.exit(1)

    summary = _summarize(rows)
    _print_table(summary)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Nome único por execução — não sobrescreve experimentos anteriores.
    import time as _time
    stamp = _time.strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"experiment_{stamp}.json"
    out.write_text(json.dumps({"summary": summary, "runs": rows}, ensure_ascii=False, indent=2))
    latest = OUTPUT_DIR / "experiment_result.json"
    latest.write_text(json.dumps({"summary": summary, "runs": rows}, ensure_ascii=False, indent=2))
    print(f"\nDetalhes salvos em {out} (e {latest})")


if __name__ == "__main__":
    asyncio.run(main())
