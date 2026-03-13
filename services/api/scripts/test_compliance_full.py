"""
Teste end-to-end de toda a integração ANS Compliance.
Cobre TODAS as fases do plano:
  Fase 1: Models + ETL (DutEngine, TussValidator, Anvisa)
  Fase 2: Motor DUT-as-Code + Validadores
  Fase 3: Pipeline DUT-aware + Approval Score
  Fase 4: Modo Fora do Rol + Dossiê de Exceção
  Fase 5: Geração de relatórios completos via pipeline

Uso: cd services/api && python3 scripts/test_compliance_full.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

OUTPUT_DIR = Path("scripts/test_output_compliance")
SEP = "=" * 80

SCENARIOS = [
    {
        "id": "01_rol_dut_atende",
        "nome": "Rol/DUT — Paciente atende todos os critérios",
        "product_keyword": "Kit EC2 - Linha Opus",
        "paciente": "Carlos Alberto Mendes",
        "cid": "M17.1",
        "diagnostico": "Gonartrose primária unilateral de joelho direito, grau III de Kellgren-Lawrence, com dor crônica há 2 anos e limitação funcional",
        "especialidade": "Ortopedia",
        "health_plan": "Unimed",
        "patient_data": {
            "idade": 62,
            "imc": 28.5,
            "tempo_tratamento_conservador_meses": 12,
            "finalidade": "terapeutico",
        },
        "expected_mode": "fora_do_rol",
    },
    {
        "id": "02_rol_dut_parcial",
        "nome": "Rol/DUT — Paciente atende parcialmente (dados faltantes)",
        "product_keyword": "Kit EC2 - Linha Opus",
        "paciente": "Maria Fernanda Silva",
        "cid": "M17.0",
        "diagnostico": "Gonartrose bilateral de joelhos, grau III Kellgren-Lawrence, com sinovite crônica e derrame articular recorrente",
        "especialidade": "Ortopedia",
        "health_plan": "Bradesco Saúde",
        "patient_data": {
            "idade": 55,
        },
        "expected_mode": "fora_do_rol",
    },
    {
        "id": "03_cobertura_direta",
        "nome": "Cobertura Direta — Procedimento no Rol sem DUT",
        "product_keyword": "Adhesion STP+",
        "paciente": "João Pedro Oliveira",
        "cid": "K66.0",
        "diagnostico": "Aderências peritoneais pós-cirúrgicas com obstrução intestinal parcial recorrente",
        "especialidade": "Cirurgia Geral",
        "health_plan": "Amil",
        "patient_data": {
            "idade": 45,
            "finalidade": "terapeutico",
        },
        "expected_mode": "cobertura_direta",
    },
    {
        "id": "04_fora_do_rol",
        "nome": "Fora do Rol — Dossiê de Exceção + STF Checklist",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente": "Marcos Antonio Ribeiro",
        "cid": "N48.6",
        "diagnostico": "Doença de Peyronie com curvatura peniana >60 graus, placa fibrótica estável e disfunção erétil associada",
        "especialidade": "Urologia",
        "health_plan": "SulAmérica",
        "patient_data": {
            "idade": 58,
            "finalidade": "terapeutico",
        },
        "expected_mode": "fora_do_rol",
    },
    {
        "id": "05_laser_otorrino",
        "nome": "Laser — Especialidade diferente (ORL)",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente": "Ana Carolina Ferreira",
        "cid": "J34.3",
        "diagnostico": "Hipertrofia de cornetos nasais inferiores bilaterais refratária a tratamento clínico por 8 meses",
        "especialidade": "Otorrinolaringologia",
        "health_plan": "Porto Seguro",
        "patient_data": {
            "idade": 38,
            "tempo_tratamento_conservador_meses": 8,
            "finalidade": "terapeutico",
        },
        "expected_mode": "cobertura_direta",
    },
    {
        "id": "06_biossilex_ortopedia",
        "nome": "Biossilex — Osteomielite crônica",
        "product_keyword": "Biossilex",
        "paciente": "Roberto Almeida Santos",
        "cid": "M86.9",
        "diagnostico": "Osteomielite crônica de tíbia com falha de consolidação e infecção recorrente, após 3 desbridamentos sem resolução",
        "especialidade": "Ortopedia",
        "health_plan": "Cassi",
        "patient_data": {
            "idade": 52,
            "finalidade": "terapeutico",
        },
        "expected_mode": "cobertura_direta",
    },
]


def _safe_serialize(obj):
    """Serializa objetos complexos para JSON."""
    if hasattr(obj, "__dict__"):
        return {k: _safe_serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_safe_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    return obj


async def test_phase_1_2_services(db):
    """Fase 1-2: Testa DutEngine, TussValidator e ApprovalScore diretamente."""
    print(f"\n{SEP}")
    print("  FASE 1-2: SERVIÇOS DE COMPLIANCE (sem pipeline)")
    print(f"{SEP}\n")

    results = {}

    from app.services.dut_engine import DutEngine, evaluate_dsl, build_evaluation
    from app.services.tuss_validator import TussValidator
    from app.services.approval_score import compute_approval_score

    engine = DutEngine(db)
    validator = TussValidator(db)

    # --- DUT Engine: DSL evaluation (offline, sem DB) ---
    print("[1/6] Testando DUT Engine — avaliação DSL determinística...")
    test_dsl = {
        "criterios": [
            {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": 18, "descricao": "Idade >= 18 anos"},
            {"id": "B", "tipo": "deterministico", "campo_paciente": "imc", "operador": ">=", "valor": 35, "descricao": "IMC >= 35 kg/m2"},
            {"id": "C", "tipo": "deterministico", "campo_paciente": "tempo_tratamento_conservador_meses", "operador": ">=", "valor": 6, "descricao": "Falha conservador >= 6 meses"},
            {"id": "D", "tipo": "subjetivo", "descricao": "Motivação e expectativa adequadas", "requer_llm": True},
        ],
        "exclusoes": [
            {"id": "EX1", "tipo": "exclusao", "campo_paciente": "finalidade", "operador": "==", "valor": "estetico", "descricao": "Excluído uso estético"},
        ],
    }

    # Cenário: todos critérios atendidos
    patient_full = {"idade": 45, "imc": 38, "tempo_tratamento_conservador_meses": 12, "finalidade": "terapeutico"}
    dsl_results_full = evaluate_dsl(test_dsl, patient_full)
    eval_full = build_evaluation(dsl_results_full)
    print(f"  Todos atendidos: met={len(eval_full.criteria_met)}, unmet={len(eval_full.criteria_unmet)}, "
          f"subjective={len(eval_full.criteria_subjective)}, unknown={len(eval_full.criteria_unknown)}, "
          f"exclusion={eval_full.exclusion_triggered is not None}")

    # Cenário: IMC insuficiente
    patient_partial = {"idade": 45, "imc": 28, "tempo_tratamento_conservador_meses": 12, "finalidade": "terapeutico"}
    dsl_results_partial = evaluate_dsl(test_dsl, patient_partial)
    eval_partial = build_evaluation(dsl_results_partial)
    print(f"  IMC insuficiente: met={len(eval_partial.criteria_met)}, unmet={len(eval_partial.criteria_unmet)}")

    # Cenário: exclusão ativada (estético)
    patient_exclusion = {"idade": 45, "imc": 38, "tempo_tratamento_conservador_meses": 12, "finalidade": "estetico"}
    dsl_results_excl = evaluate_dsl(test_dsl, patient_exclusion)
    eval_excl = build_evaluation(dsl_results_excl)
    print(f"  Exclusão estético: exclusion_triggered={eval_excl.exclusion_triggered is not None}")

    # Cenário: dados faltantes
    patient_missing = {"idade": 45}
    dsl_results_missing = evaluate_dsl(test_dsl, patient_missing)
    eval_missing = build_evaluation(dsl_results_missing)
    print(f"  Dados faltantes: unknown={len(eval_missing.criteria_unknown)}")

    results["dut_engine_dsl"] = {
        "all_met": {"met": len(eval_full.criteria_met), "unmet": len(eval_full.criteria_unmet), "excl": eval_full.exclusion_triggered is None},
        "partial": {"met": len(eval_partial.criteria_met), "unmet": len(eval_partial.criteria_unmet)},
        "exclusion": {"triggered": eval_excl.exclusion_triggered is not None},
        "missing_data": {"unknown": len(eval_missing.criteria_unknown)},
    }
    print("  -> OK\n")

    # --- TUSS Validator ---
    print("[2/6] Testando TUSS Validator — validação de código TUSS 19...")
    tuss_valid = await validator.validate_opme_code("30715016")
    print(f"  TUSS 30715016: válido={tuss_valid.valido}, nome={tuss_valid.nome or 'N/A'}, msg={tuss_valid.mensagem}")
    tuss_invalid = await validator.validate_opme_code("99999999")
    print(f"  TUSS 99999999: válido={tuss_invalid.valido}, msg={tuss_invalid.mensagem}")
    results["tuss_validator"] = {
        "valid_code": {"valido": tuss_valid.valido, "msg": tuss_valid.mensagem},
        "invalid_code": {"valido": tuss_invalid.valido, "msg": tuss_invalid.mensagem},
    }
    print("  -> OK\n")

    # --- TISS Field Validation ---
    print("[3/6] Testando TISS — regra TUSS 19 em campo Honorários...")
    tiss_ok = await validator.validate_tiss_field("solicitacao_opme", "materiais", "30715016")
    print(f"  OPME em campo materiais: permitido={tiss_ok.permitido}, msg={tiss_ok.mensagem}")
    tiss_bloq = await validator.validate_tiss_field("solicitacao_opme", "honorarios", "30715016")
    print(f"  OPME em campo honorários: permitido={tiss_bloq.permitido}, msg={tiss_bloq.mensagem}")
    results["tiss_validator"] = {
        "opme_materiais": {"permitido": tiss_ok.permitido},
        "opme_honorarios": {"permitido": tiss_bloq.permitido, "msg": tiss_bloq.mensagem},
    }
    print("  -> OK\n")

    # --- Anvisa Check ---
    print("[4/6] Testando Anvisa — status de registro...")
    anvisa_active = await validator.check_anvisa_status("80117900XXX")
    print(f"  Registro 80117900XXX: status={anvisa_active.status}, alerta={anvisa_active.alerta}")
    anvisa_unknown = await validator.check_anvisa_status("REGISTRO_INEXISTENTE")
    print(f"  Registro inexistente: status={anvisa_unknown.status}, alerta={anvisa_unknown.alerta}")
    results["anvisa"] = {
        "known_reg": {"status": anvisa_active.status},
        "unknown_reg": {"status": anvisa_unknown.status},
    }
    print("  -> OK\n")

    # --- Approval Score ---
    print("[5/6] Testando Approval Score — cálculo com diferentes cenários...")
    score_full = compute_approval_score(
        dut_evaluation=eval_full,
        tuss_validation=tuss_valid,
        anvisa_status=anvisa_active,
        evidence_count=5,
        has_justification=True,
        cid_procedure_consistent=True,
    )
    print(f"  Cenário completo: score={score_full.score}, nível={score_full.nivel}")
    print(f"    Componentes: {score_full.componentes}")
    if score_full.alertas:
        print(f"    Alertas: {score_full.alertas}")
    if score_full.gaps:
        print(f"    Gaps: {score_full.gaps[:3]}")

    score_empty = compute_approval_score(
        evidence_count=0,
        has_justification=False,
    )
    print(f"  Cenário vazio: score={score_empty.score}, nível={score_empty.nivel}")

    results["approval_score"] = {
        "full": {"score": score_full.score, "nivel": score_full.nivel, "components": score_full.componentes},
        "empty": {"score": score_empty.score, "nivel": score_empty.nivel},
    }
    print("  -> OK\n")

    # --- Compliance Layer ---
    print("[6/6] Testando Compliance Layer — build_compliance_context...")
    from app.services.compliance_layer import build_compliance_context
    ctx = await build_compliance_context(
        db=db,
        procedure_code="30715016",
        patient_data=patient_full,
        produto_registro_anvisa="80117900XXX",
        evidence_count=3,
    )
    print(f"  Mode: {ctx.mode}")
    print(f"  TUSS válido: {ctx.tuss_validation.valido if ctx.tuss_validation else 'N/A'}")
    print(f"  Anvisa: {ctx.anvisa_status.status if ctx.anvisa_status else 'N/A'}")
    print(f"  Score: {ctx.approval_score.score if ctx.approval_score else 'N/A'}")
    print(f"  STF Checklist: {'Sim' if ctx.stf_checklist else 'Não'}")
    results["compliance_layer"] = {
        "mode": ctx.mode,
        "has_score": ctx.approval_score is not None,
        "score": ctx.approval_score.score if ctx.approval_score else None,
    }
    print("  -> OK\n")

    return results


async def test_phase_3_4_pipeline(db):
    """Fase 3-4: Gera relatórios via pipeline para cada cenário."""
    print(f"\n{SEP}")
    print(f"  FASE 3-4: PIPELINE COMPLETO — {len(SCENARIOS)} CENÁRIOS")
    print(f"{SEP}\n")

    from sqlalchemy import select
    from app.db.models import Product, ReportTemplate
    from app.services.agents.pipeline import ReportPipeline

    prod_result = await db.execute(select(Product))
    all_products = {p.nome: p for p in prod_result.scalars().all()}

    tmpl_result = await db.execute(select(ReportTemplate))
    all_templates = {}
    for t in tmpl_result.scalars().all():
        if t.produto_id:
            all_templates[str(t.produto_id)] = t

    print(f"Produtos disponíveis: {list(all_products.keys())}\n")

    results = []

    for i, sc in enumerate(SCENARIOS, 1):
        product = None
        for name, p in all_products.items():
            if sc["product_keyword"].lower() in name.lower():
                product = p
                break

        if not product:
            print(f"[{i}/{len(SCENARIOS)}] SKIP: '{sc['product_keyword']}' não encontrado")
            results.append({"id": sc["id"], "nome": sc["nome"], "status": "SKIP"})
            continue

        template = all_templates.get(str(product.id))

        medico_inputs = {
            "paciente_nome": sc["paciente"],
            "cid": sc["cid"],
            "diagnostico": sc["diagnostico"],
            "surgery_description": "",
            "health_plan": sc.get("health_plan", ""),
            "especialidade": sc.get("especialidade", ""),
        }
        medico_inputs.update(sc.get("patient_data", {}))

        progress_log = []

        async def on_progress(step, msg):
            progress_log.append(f"[{step}] {msg}")

        print(f"[{i}/{len(SCENARIOS)}] {sc['nome']}")
        print(f"  Produto: {product.nome} | CID: {sc['cid']} | Paciente: {sc['paciente']}")

        t0 = time.time()
        try:
            result = await ReportPipeline.start(
                product=product,
                template=template,
                diagnostico=sc["diagnostico"],
                cid=sc["cid"],
                medico_inputs=medico_inputs,
                db=db,
                on_progress=on_progress,
            )

            if result.get("step") == "questions":
                answers = {}
                for q in result.get("questions", []):
                    secao = q["secao"]
                    opcoes = q.get("opcoes", [])
                    answers[secao] = opcoes[0]["texto"] if opcoes else "Tratamento conservador sem melhora"
                print(f"  -> Respondendo {len(answers)} pergunta(s)...")
                result = await ReportPipeline.answer(result["session_id"], answers, on_progress=on_progress)

            elapsed = time.time() - t0
            justificativa = result.get("justificativa", "")
            aprovado = result.get("aprovado", False)
            checklist = result.get("checklist", {})
            refs = result.get("referencias", [])
            approval_score = result.get("approval_score")
            approval_nivel = result.get("approval_nivel")
            compliance_mode = result.get("compliance_mode")
            stf_checklist = result.get("stf_checklist")
            dut_suggestions = result.get("dut_suggestions")
            approval_componentes = result.get("approval_componentes")
            approval_explicacao = result.get("approval_explicacao")
            approval_alertas = result.get("approval_alertas")
            approval_gaps = result.get("approval_gaps")

            checklist_ok = sum(1 for v in checklist.values() if v)
            checklist_total = len(checklist)
            char_count = len(justificativa)
            word_count = len(justificativa.split())

            status = "OK" if aprovado else "REVIEW"

            # Verificações de qualidade
            issues = []
            if "Fechamento Checkmate" in justificativa:
                issues.append("VAZAMENTO: 'Fechamento Checkmate' presente no texto")
            if "[inserir" in justificativa.lower():
                issues.append("PLACEHOLDER: '[inserir...]' encontrado no texto")
            for term in ["catastrófico", "insubstituível", "garantido", "garantia de aprovação"]:
                if term.lower() in justificativa.lower():
                    issues.append(f"LINGUAGEM: termo proibido '{term}' encontrado")

            has_cabeçalho_dup = ("Paciente:" in justificativa[:300] and
                                "Diagnóstico:" in justificativa[:300] and
                                "Material Solicitado:" in justificativa[:300])
            if has_cabeçalho_dup:
                issues.append("DUPLICAÇÃO: Cabeçalho do paciente repetido dentro da justificativa")

            legal_in_body = justificativa.lower().count("rn 424") + justificativa.lower().count("rn 395") + justificativa.lower().count("rn 428")
            base_legal = result.get("base_legal", "")
            legal_in_field = base_legal.lower().count("rn 424") + base_legal.lower().count("rn 395") + base_legal.lower().count("rn 428")
            if legal_in_body > 0 and legal_in_field > 0:
                issues.append(f"DUPLICAÇÃO: Fundamentação legal no corpo ({legal_in_body}x) E no campo separado ({legal_in_field}x)")

            refs_formatted = True
            for ref in refs:
                if isinstance(ref, dict):
                    ref_str = json.dumps(ref)
                    if "{'texto'" in ref_str or "\"texto\":" not in ref_str:
                        pass  # dict is expected
                elif "{'texto'" in str(ref):
                    refs_formatted = False
                    issues.append("REFERÊNCIAS: Dict Python cru detectado nas referências")
                    break

            # Salvar output
            filepath = OUTPUT_DIR / f"{sc['id']}.txt"
            with open(filepath, "w") as f:
                f.write(f"{'=' * 70}\n")
                f.write(f"CENÁRIO: {sc['nome']}\n")
                f.write(f"{'=' * 70}\n")
                f.write(f"ID: {sc['id']}\n")
                f.write(f"PRODUTO: {product.nome}\n")
                f.write(f"PACIENTE: {sc['paciente']}\n")
                f.write(f"CID: {sc['cid']}\n")
                f.write(f"DIAGNÓSTICO: {sc['diagnostico']}\n")
                f.write(f"CONVÊNIO: {sc.get('health_plan', '')}\n")
                f.write(f"PATIENT DATA: {json.dumps(sc.get('patient_data', {}), ensure_ascii=False)}\n")
                f.write(f"\n--- RESULTADOS ---\n")
                f.write(f"STATUS: {status}\n")
                f.write(f"APROVADO: {aprovado}\n")
                f.write(f"CHECKLIST: {checklist_ok}/{checklist_total}\n")
                f.write(f"CARACTERES: {char_count}\n")
                f.write(f"PALAVRAS: {word_count}\n")
                f.write(f"TEMPO: {elapsed:.1f}s\n")
                f.write(f"\n--- COMPLIANCE ANS ---\n")
                f.write(f"MODO: {compliance_mode or 'não determinado'}\n")
                f.write(f"SCORE: {approval_score or 'N/A'}\n")
                f.write(f"NÍVEL: {approval_nivel or 'N/A'}\n")
                f.write(f"COMPONENTES: {json.dumps(approval_componentes or {}, ensure_ascii=False, indent=2)}\n")
                f.write(f"EXPLICAÇÃO: {json.dumps(approval_explicacao or [], ensure_ascii=False)}\n")
                f.write(f"ALERTAS: {json.dumps(approval_alertas or [], ensure_ascii=False)}\n")
                f.write(f"GAPS: {json.dumps(approval_gaps or [], ensure_ascii=False)}\n")
                f.write(f"SUGESTÕES DUT: {json.dumps(dut_suggestions or [], ensure_ascii=False)}\n")
                if stf_checklist:
                    f.write(f"STF CHECKLIST: {json.dumps(stf_checklist, ensure_ascii=False, indent=2)}\n")
                f.write(f"\n--- VERIFICAÇÃO DE QUALIDADE ---\n")
                if issues:
                    for iss in issues:
                        f.write(f"  ⚠ {iss}\n")
                else:
                    f.write(f"  ✓ Sem problemas detectados\n")
                f.write(f"\n--- CHECKLIST DETALHADO ---\n")
                f.write(json.dumps(checklist, indent=2, ensure_ascii=False) + "\n")
                f.write(f"\n--- REFERÊNCIAS ---\n")
                for ri, ref in enumerate(refs, 1):
                    if isinstance(ref, dict):
                        f.write(f"  {ri}. {ref.get('texto', str(ref))}")
                        if ref.get('pmid'):
                            f.write(f" (PMID: {ref['pmid']})")
                        if ref.get('link'):
                            f.write(f" [{ref['link']}]")
                        f.write(f" [{ref.get('source', '?')}]\n")
                    else:
                        f.write(f"  {ri}. {ref}\n")
                f.write(f"\n--- PROGRESS LOG ---\n")
                for pl in progress_log:
                    f.write(f"  {pl}\n")
                f.write(f"\n{'=' * 70}\n")
                f.write(f"RELATÓRIO GERADO:\n{'=' * 70}\n\n")
                f.write(justificativa)
                f.write(f"\n\n{'=' * 70}\n")
                f.write(f"BASE LEGAL (campo separado):\n{'=' * 70}\n\n")
                f.write(base_legal or "(vazio)")
                f.write(f"\n\n{'=' * 70}\n")
                f.write(f"AUDIT LOG:\n{'=' * 70}\n\n")
                f.write(json.dumps(result.get("audit_log", []), indent=2, ensure_ascii=False))
                f.write("\n")

            # Print resumo
            score_str = f"{approval_score:.0f}/100 ({approval_nivel})" if approval_score else "N/A"
            issues_str = f" | {len(issues)} problema(s)" if issues else ""
            print(f"  -> {status} | {word_count} palavras | checklist {checklist_ok}/{checklist_total} "
                  f"| score {score_str} | modo: {compliance_mode or '?'} | {elapsed:.1f}s{issues_str}")
            if issues:
                for iss in issues:
                    print(f"     ⚠ {iss}")
            print(f"  -> Salvo: {filepath}")

            results.append({
                "id": sc["id"],
                "nome": sc["nome"],
                "status": status,
                "aprovado": aprovado,
                "palavras": word_count,
                "caracteres": char_count,
                "checklist": f"{checklist_ok}/{checklist_total}",
                "compliance_mode": compliance_mode,
                "approval_score": approval_score,
                "approval_nivel": approval_nivel,
                "approval_componentes": approval_componentes,
                "issues": issues,
                "tempo": f"{elapsed:.1f}s",
                "refs_count": len(refs),
                "arquivo": str(filepath),
            })

        except Exception as e:
            elapsed = time.time() - t0
            import traceback
            tb = traceback.format_exc()
            print(f"  -> ERRO: {e} ({elapsed:.1f}s)")

            filepath = OUTPUT_DIR / f"{sc['id']}_ERRO.txt"
            with open(filepath, "w") as f:
                f.write(f"ERRO no cenário: {sc['nome']}\n\n{tb}\n")
                f.write(f"\nProgress log:\n")
                for pl in progress_log:
                    f.write(f"  {pl}\n")

            results.append({
                "id": sc["id"],
                "nome": sc["nome"],
                "status": "ERRO",
                "erro": str(e),
                "tempo": f"{elapsed:.1f}s",
                "arquivo": str(filepath),
            })

        print()

    return results


async def main():
    from app.db.session import AsyncSessionLocal

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{SEP}")
    print(f"  TESTE COMPLETO — INTEGRAÇÃO ANS COMPLIANCE")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{SEP}")

    all_results = {}

    async with AsyncSessionLocal() as db:
        # Fase 1-2: Serviços diretos
        phase12 = await test_phase_1_2_services(db)
        all_results["fase_1_2_services"] = phase12

        # Fase 3-4: Pipeline completo
        phase34 = await test_phase_3_4_pipeline(db)
        all_results["fase_3_4_pipeline"] = phase34

    # Resumo final
    print(f"\n{SEP}")
    print("  RESUMO FINAL")
    print(f"{SEP}\n")

    print("  FASE 1-2 (Serviços):")
    for key, val in phase12.items():
        print(f"    ✓ {key}: OK")

    print(f"\n  FASE 3-4 (Pipeline — {len(phase34)} cenários):")
    total_issues = 0
    for r in phase34:
        icon = "✓" if r["status"] == "OK" else "✗" if r["status"] == "ERRO" else "~"
        line = f"    {icon} {r['nome']}: {r['status']}"
        if r.get("approval_score"):
            line += f" | score {r['approval_score']:.0f} ({r.get('approval_nivel', '?')})"
        if r.get("compliance_mode"):
            line += f" | {r['compliance_mode']}"
        if r.get("issues"):
            line += f" | ⚠ {len(r['issues'])} problema(s)"
            total_issues += len(r["issues"])
        if r.get("erro"):
            line += f" | {r['erro'][:60]}"
        print(line)

    ok = sum(1 for r in phase34 if r["status"] == "OK")
    review = sum(1 for r in phase34 if r["status"] == "REVIEW")
    err = sum(1 for r in phase34 if r["status"] in ("ERRO", "SKIP"))
    print(f"\n  Total: {ok} aprovados | {review} para revisão | {err} erros/skips | {total_issues} problemas de qualidade")

    summary_path = OUTPUT_DIR / "resumo_compliance.json"
    with open(summary_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Resumo JSON: {summary_path}")
    print(f"  Outputs em: {OUTPUT_DIR.resolve()}\n")


if __name__ == "__main__":
    asyncio.run(main())
