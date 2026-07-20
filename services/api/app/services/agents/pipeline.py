"""
Orquestrador do pipeline multi-agente: Pesquisador -> Redator -> Auditor.
"""
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .researcher import research, ResearchResult, GapQuestion, _fetch_clinical_evidences, _fetch_pubmed_evidences
from .writer import write_justification, DraftReport
from .auditor import audit, AuditResult
from .checklist import ReportChecklist
from .validator import validate_technical_data, ValidationResult
from .token_tracker import PipelineUsage
from app.core.config import settings
from app.services.observability import create_pipeline_trace

logger = logging.getLogger(__name__)


# Patterns to infer evidence level from PubMed snippets
_LEVEL_PATTERNS = [
    (r"meta.?analy|meta.?análise", "meta-analise"),
    (r"systematic review|revisão sistemática", "revisao-sistematica"),
    (r"randomized|randomised|randomizado|ensaio clínico randomizado|RCT", "rct"),
    (r"cohort|coorte", "coorte"),
    (r"case.?control|caso.?controle", "caso-controle"),
    (r"case series|série de casos", "serie_casos"),
]


def _infer_evidence_levels(
    pubmed_evidences: list[dict],
    clinical_evidences: list[dict],
) -> list[str]:
    """Infer evidence levels from PubMed snippets and clinical evidences."""
    levels = []
    for ev in (pubmed_evidences or []):
        snippet = (ev.get("snippet", "") or "").lower()
        titulo = (ev.get("titulo", "") or "").lower()
        text = f"{titulo} {snippet}"
        matched = False
        for pattern, level in _LEVEL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                levels.append(level)
                matched = True
                break
        if not matched and text.strip():
            levels.append("serie_casos")  # conservative default
    for ev in (clinical_evidences or []):
        nivel = (ev.get("nivel_evidencia", "") or "").lower().replace(" ", "_")
        if nivel:
            levels.append(nivel)
    return levels


def _enrich_references(
    refs: list[str],
    pubmed_evidences: list[dict],
    clinical_evidences: list[dict],
) -> list[dict]:
    """Enriquece referências com DOI, PMID e links verificáveis."""
    pubmed_by_author = {}
    for ev in (pubmed_evidences or []):
        key = ev.get("autor", "").lower().split()[0] if ev.get("autor") else ""
        if key:
            pubmed_by_author[key] = ev

    enriched = []
    for ref_text in refs:
        ref_lower = ref_text.lower()
        item = {"texto": ref_text, "source": "internal"}

        for ev in (pubmed_evidences or []):
            autor = ev.get("autor", "").lower()
            if autor and autor in ref_lower:
                item["pmid"] = ev.get("pmid", "")
                item["doi"] = ev.get("doi", "")
                item["source"] = "pubmed"
                if ev.get("pmid"):
                    item["link"] = f"https://pubmed.ncbi.nlm.nih.gov/{ev['pmid']}/"
                elif ev.get("doi"):
                    item["link"] = f"https://doi.org/{ev['doi']}"
                break

        if "link" not in item:
            for ev in (clinical_evidences or []):
                autor = ev.get("autor", "").lower()
                if autor and autor in ref_lower:
                    doi = ev.get("doi", "")
                    if doi:
                        item["doi"] = doi
                        item["link"] = f"https://doi.org/{doi}"
                    break

        enriched.append(item)

    return enriched


@dataclass
class PipelineSession:
    """Estado de uma sessão do pipeline multi-agente."""
    session_id: str
    user_id: Optional[str] = None  # dono da sessão (checagem de autorização)
    step: str = "init"  # init | researching | questions | writing | auditing | done
    product: object = None
    template: object = None
    medico_inputs: dict = field(default_factory=dict)
    research_result: Optional[ResearchResult] = None
    pending_questions: list[dict] = field(default_factory=list)
    answered_questions: dict = field(default_factory=dict)
    draft: Optional[DraftReport] = None
    audit_result: Optional[AuditResult] = None
    clinical_evidences: list = field(default_factory=list)
    pubmed_evidences: list = field(default_factory=list)
    usage: PipelineUsage = field(default_factory=PipelineUsage)
    compliance_context: object = None  # ComplianceContext when available
    tuss_selection: object = None  # TussSelection when available
    other_products: list = field(default_factory=list)  # p/ detecção cross-produto
    # Campos administrativos (carteirinha, guia etc.) que NÃO entram no prompt,
    # apenas são persistidos no Report ao final (fluxo com perguntas A/B/C).
    extra_report_fields: dict = field(default_factory=dict)


class ReportPipeline:
    """
    Pipeline multi-agente para geração de relatórios OPME.

    Fluxo:
    1. start() -> pesquisa + identifica lacunas
    2. Se há lacunas -> retorna perguntas A/B/C
    3. answer() -> recebe respostas do médico
    4. generate() -> redação + auditoria
    5. Resultado: texto auditado + checklist

    Sessions are stored in Redis (with TTL + user_id auth) or in-memory fallback.
    The in-process _sessions dict is kept as a local cache for the current request
    lifecycle only. Persistent state goes to Redis via session_store.
    """

    _sessions: dict[str, PipelineSession] = {}

    @classmethod
    def get_session(cls, session_id: str) -> Optional[PipelineSession]:
        return cls._sessions.get(session_id)

    @classmethod
    def _cleanup_session(cls, session_id: str):
        """Remove session from in-process cache after completion."""
        cls._sessions.pop(session_id, None)

    @classmethod
    async def start(
        cls,
        product,
        template,
        diagnostico: str,
        cid: str,
        medico_inputs: dict,
        db: Optional[AsyncSession] = None,
        on_progress=None,
        user_id: Optional[str] = None,
        extra_report_fields: Optional[dict] = None,
    ) -> dict:
        """
        Inicia pipeline: executa Agente A (Pesquisador).
        Retorna session_id e perguntas A/B/C se houver lacunas.
        """
        # Validate CID format
        if not cid or not re.match(r"^[A-Z]\d{2}(\.\d{1,2})?$", cid.strip().upper()):
            return {"error": f"CID inválido: '{cid}'. Formato esperado: A00, A00.0 ou A00.00"}

        session_id = str(uuid.uuid4())
        session = PipelineSession(
            session_id=session_id,
            user_id=user_id,
            product=product,
            template=template,
            medico_inputs=medico_inputs,
            extra_report_fields=extra_report_fields or {},
        )
        session.step = "researching"
        cls._sessions[session_id] = session

        # Persist to Redis with user_id auth (mesma session_id do pipeline)
        if user_id:
            from .session_store import create_session as store_create
            await store_create(user_id, {
                "product_id": str(product.id),
                "step": "researching",
            }, session_id=session_id)

        # Carrega fingerprints de OUTROS produtos p/ detecção de contaminação cruzada
        # (nomes/registros ANVISA de outro produto vazando no texto). Capado.
        if db is not None:
            try:
                from sqlalchemy import select as _select
                from app.db.models import Product as _Product
                others = await db.execute(
                    _select(_Product).where(_Product.id != product.id).limit(200)
                )
                session.other_products = list(others.scalars().all())
            except Exception as e:
                logger.debug("Falha ao carregar outros produtos p/ contaminação: %s", e)

        async def _emit(step, label):
            if on_progress:
                await on_progress(step, label)

        # Guard inputs against prompt injection
        try:
            from app.services.guardrails import guard_pipeline_input
            medico_inputs = guard_pipeline_input(medico_inputs)
            session.medico_inputs = medico_inputs
            if medico_inputs.get("_injection_detected"):
                logger.warning("Prompt injection detected in session %s — inputs sanitized", session_id)
        except Exception as e:
            logger.debug("Guardrails check skipped: %s", e)

        # Create observability trace for this pipeline run
        trace = create_pipeline_trace(
            session_id=session_id,
            user_id=user_id or "",
            product_name=product.nome,
            cid=cid,
        )
        session.medico_inputs["_trace"] = trace

        logger.info("Pipeline iniciado: session=%s, product=%s", session_id, product.nome)

        # Auto-enriquecimento: gera ficha técnica se produto está incompleto
        try:
            from app.services.product_enrichment import enrich_product, needs_enrichment
            if db and needs_enrichment(product):
                await enrich_product(db, product, cid=cid, on_progress=on_progress)
        except Exception as e:
            logger.warning("Auto-enriquecimento falhou (continuando): %s", e)

        await _emit("researching", f"Consultando base de evidências para CID {cid}...")

        session.clinical_evidences = await _fetch_clinical_evidences(db, cid, product.id)
        n_internal = len(session.clinical_evidences)
        if n_internal > 0:
            await _emit("researching", f"{n_internal} evidência(s) interna(s) verificada(s) encontrada(s)")
        else:
            await _emit("researching", "Nenhuma evidência interna pré-validada para este CID")

        await _emit("researching", "Pesquisando artigos indexados no PubMed...")
        session.pubmed_evidences = await _fetch_pubmed_evidences(db, cid, product.nome, diagnostico)
        n_pubmed = len(session.pubmed_evidences)
        if n_pubmed > 0:
            await _emit("researching", f"{n_pubmed} artigo(s) científico(s) relevante(s) identificado(s)")

        # TUSS Selection: pick best code for this diagnosis
        selected_tuss_code = getattr(product, "codigo_tuss_sugerido", "") or ""
        try:
            from app.services.tuss_selector import select_best_tuss
            tuss_sel = await select_best_tuss(
                db=db,
                product_id=product.id,
                cid=cid,
                diagnosis=diagnostico,
                product_fallback_tuss=selected_tuss_code,
            )
            session.tuss_selection = tuss_sel
            selected_tuss_code = tuss_sel.tuss_code
            if tuss_sel.confidence != "fallback":
                await _emit("researching", f"TUSS {tuss_sel.tuss_code} selecionado: {tuss_sel.procedure_name}")
        except Exception as e:
            logger.warning("TUSS selector failed (using fallback): %s", e)

        # Compliance layer: DUT, TUSS, Anvisa
        try:
            from app.services.compliance_layer import build_compliance_context
            await _emit("researching", "Verificando conformidade regulatória ANS...")
            compliance_ctx = await build_compliance_context(
                db=db,
                procedure_code=selected_tuss_code,
                patient_data=medico_inputs,
                health_plan=medico_inputs.get("health_plan", "") or "",
                produto_registro_anvisa=getattr(product, "registro_anvisa", "") or "",
                # Doctor is authenticated on Hugo platform = prescription is implicit
                medico_crm="HUGO_AUTH",
                # Declaratory field: assumed true (doctor would contest if false)
                declaracao_ans=True,
                evidence_count=n_internal + n_pubmed,
                on_progress=on_progress,
            )
            session.compliance_context = compliance_ctx
            if compliance_ctx.mode == "fora_do_rol":
                await _emit("researching", "Modo Fora do Rol ativado — Dossiê de Exceção será gerado")
            elif compliance_ctx.mode == "rol_dut" and compliance_ctx.dut_evaluation:
                met = len(compliance_ctx.dut_evaluation.criteria_met)
                total = compliance_ctx.dut_evaluation.total_criteria
                await _emit("researching", f"DUT: {met}/{total} critérios atendidos pelo paciente")
        except Exception as e:
            logger.warning("Compliance layer unavailable: %s", e)
            session.compliance_context = None

        await _emit("researching", "Analisando contexto clínico e identificando lacunas...")
        research_result = await research(product, diagnostico, cid, template, db=db)
        session.research_result = research_result
        session.medico_inputs["cid"] = cid
        session.medico_inputs["diagnostico"] = diagnostico

        if research_result.token_usage:
            session.usage.add(research_result.token_usage)

        if research_result.lacunas:
            session.step = "questions"
            session.pending_questions = [
                {
                    "secao": q.secao,
                    "pergunta": q.pergunta,
                    "opcoes": q.opcoes,
                }
                for q in research_result.lacunas
            ]

            return {
                "session_id": session_id,
                "step": "questions",
                "questions": session.pending_questions,
                "sugestao_tuss": research_result.sugestao_tuss,
                "especialidade": research_result.especialidade_detectada,
            }

        return await cls._generate(session, on_progress=on_progress)

    @classmethod
    async def answer(cls, session_id: str, answers: dict, on_progress=None, user_id: Optional[str] = None) -> dict:
        """
        Recebe respostas A/B/C do médico e avança o pipeline.
        """
        session = cls._sessions.get(session_id)
        if session is not None:
            # Cache local: revalida o dono antes de prosseguir (evita acesso cross-user)
            if user_id and session.user_id and session.user_id != user_id:
                logger.warning(
                    "answer() acesso negado: session=%s requested_by=%s owner=%s",
                    session_id, user_id, session.user_id,
                )
                return {"error": "Sessão não encontrada ou não autorizada"}
        else:
            # Try to verify session exists in Redis (even if not in local cache)
            if user_id:
                from .session_store import get_session as store_get
                stored = await store_get(session_id, user_id)
                if stored is None:
                    return {"error": "Sessão não encontrada ou não autorizada"}
            return {"error": "Sessão não encontrada"}

        session.answered_questions.update(answers)

        for key, value in answers.items():
            # Defensive: if frontend sends option dict, extract text
            if isinstance(value, dict) and "texto" in value:
                value = value["texto"]
            session.medico_inputs[key] = value

        session.pending_questions = [
            q for q in session.pending_questions
            if q["secao"] not in answers
        ]

        if session.pending_questions:
            return {
                "session_id": session_id,
                "step": "questions",
                "questions": session.pending_questions,
            }

        return await cls._generate(session, on_progress=on_progress)

    @classmethod
    async def _generate(cls, session: PipelineSession, on_progress=None) -> dict:
        """Executa Agente B (Redator) -> Agente C (Auditor) -> Camada 4 (Validador Hard-Coded)."""

        async def _emit(step: str, label: str):
            if on_progress:
                await on_progress(step, label)

        trace = session.medico_inputs.get("_trace")

        session.step = "writing"
        n_ev = len(session.clinical_evidences) + len(session.pubmed_evidences)
        await _emit("writing", f"Redigindo justificativa técnica para {session.product.nome}...")
        if n_ev > 0:
            await _emit("writing", f"Fundamentando com {n_ev} evidências científicas...")
        logger.info("Pipeline redação: session=%s", session.session_id)

        # Trace: Writer agent
        gen_ctx = trace.generation("writer", model=settings.OPENAI_MODEL_WRITER, input_data={"cid": session.medico_inputs.get("cid")}) if trace else None
        if gen_ctx:
            gen_ctx.__enter__()

        draft = await write_justification(
            research=session.research_result,
            product=session.product,
            template=session.template,
            medico_inputs=session.medico_inputs,
            clinical_evidences=session.clinical_evidences,
            pubmed_evidences=session.pubmed_evidences,
        )
        session.draft = draft
        if draft.token_usage:
            session.usage.add(draft.token_usage)

        if gen_ctx:
            gen_ctx.update(
                output={"length": len(draft.justificativa_completa or "")},
                usage={"input": draft.token_usage.prompt_tokens, "output": draft.token_usage.completion_tokens} if draft.token_usage else None,
            )
            gen_ctx.__exit__(None, None, None)

        # NOTA: o passo de "self-consistency" (3 rascunhos + votação de frases) foi
        # removido. Ele triplicava o custo do Redator e, por um bug de temperatura
        # fixa, degenerava a votação e apagava frases legítimas — encurtando o laudo.
        # A factualidade é garantida pelo Auditor (LLM) + validador determinístico
        # (validate_technical_data) + detector de contaminação, logo abaixo.

        word_count = len((draft.justificativa_completa or "").split())
        await _emit("writing", f"Redação concluída — {word_count} palavras geradas")

        session.step = "auditing"
        await _emit("auditing", f"Confrontando dados técnicos de {session.product.nome} com base oficial...")
        logger.info("Pipeline auditoria: session=%s", session.session_id)

        audit_gen = trace.generation("auditor", model=settings.OPENAI_MODEL_AUDITOR) if trace else None
        if audit_gen:
            audit_gen.__enter__()

        audit_result = await audit(
            draft, session.product,
            clinical_evidences=session.clinical_evidences,
            pubmed_evidences=session.pubmed_evidences,
        )
        session.audit_result = audit_result
        if audit_result.token_usage:
            session.usage.add(audit_result.token_usage)

        if audit_gen:
            audit_gen.update(
                output={"aprovado": audit_result.aprovado, "corrections": len(audit_result.audit_log)},
                usage={"input": audit_result.token_usage.prompt_tokens, "output": audit_result.token_usage.completion_tokens} if audit_result.token_usage else None,
            )
            audit_gen.__exit__(None, None, None)

        corrections = sum(1 for a in audit_result.audit_log if a.tipo == "correcao")
        if corrections > 0:
            await _emit("auditing", f"{corrections} correção(ões) aplicada(s) para conformidade")
        else:
            await _emit("auditing", "Dados técnicos verificados — sem divergências")

        session.step = "validating"
        await _emit("validating", "Executando validação determinística de conformidade...")
        logger.info("Pipeline validação hard-coded: session=%s", session.session_id)

        val_span = trace.span("hard-validator") if trace else None
        if val_span:
            val_span.__enter__()

        validation = validate_technical_data(
            audit_result.texto_corrigido,
            session.product,
            medico_inputs=session.medico_inputs,
        )

        if val_span:
            val_span.update(output={
                "aprovado": validation.aprovado,
                "issues": len(validation.issues),
                "entities": len(validation.entities_found),
            })
            val_span.__exit__(None, None, None)

        audit_log = [
            {"tipo": a.tipo, "campo": a.campo, "original": a.original,
             "corrigido": a.corrigido, "motivo": a.motivo}
            for a in audit_result.audit_log
        ]

        if validation.issues:
            for issue in validation.issues:
                audit_log.append({
                    "tipo": "hard_validation",
                    "campo": issue.campo,
                    "original": issue.valor_no_texto,
                    "corrigido": issue.valor_oficial,
                    "motivo": f"[{issue.severidade.upper()}] {issue.tipo}: valor no texto '{issue.valor_no_texto}' diverge do oficial '{issue.valor_oficial}'",
                })

        final_approved = audit_result.aprovado and validation.aprovado
        session.step = "done"

        motivos_bloqueio = []
        if not audit_result.aprovado:
            missing = [k for k, v in audit_result.checklist.items() if not v]
            if missing:
                motivos_bloqueio.append(f"Checklist incompleto: faltam {', '.join(missing)}")
        _CLINICAL_ISSUE_MSGS = {
            "indicacao_off_label": "Produto não indicado para este diagnóstico",
            "contraindicacao_presente": "Contraindicação detectada no diagnóstico",
            "cid_inconsistente": "CID incompatível com o produto solicitado",
            "copypaste_detectado": "Nome de outro paciente detectado no diagnóstico (possível copy/paste)",
            "diagnostico_ausente": "Diagnóstico não informado",
        }
        for issue in validation.issues:
            if issue.severidade == "bloqueante":
                msg = _CLINICAL_ISSUE_MSGS.get(issue.tipo)
                if msg:
                    detail = f": {issue.valor_no_texto}" if issue.valor_no_texto else ""
                    motivos_bloqueio.append(f"{msg}{detail}")
                else:
                    motivos_bloqueio.append(
                        f"O valor '{issue.valor_no_texto}' foi identificado como {issue.campo} incorreto. "
                        f"O valor oficial é '{issue.valor_oficial}'."
                    )

        # ── Contamination detection ────────────────────────────────────
        try:
            from app.services.contamination_detector import check_contamination
            contamination = check_contamination(
                audit_result.texto_corrigido,
                session.product,
                all_products=session.other_products or None,
            )
            if contamination.has_blocking:
                for issue in contamination.issues:
                    if issue.severidade == "bloqueante":
                        motivos_bloqueio.append(
                            f"Contaminação ({issue.tipo}): {issue.descricao}"
                        )
                final_approved = False
        except Exception as e:
            logger.warning("Contamination check failed (non-blocking): %s", e)

        logger.info(
            "Pipeline concluído: session=%s, aprovado=%s, hard_validation=%s",
            session.session_id, final_approved, validation.aprovado,
        )

        enriched_refs = _enrich_references(
            audit_result.referencias_validadas,
            session.pubmed_evidences,
            session.clinical_evidences,
        )

        # Compliance: recalculate score with justification
        compliance_data = {}
        if session.compliance_context:
            try:
                from app.services.approval_score import compute_approval_score
                evidence_lvls = _infer_evidence_levels(
                    session.pubmed_evidences, session.clinical_evidences,
                )
                final_score = compute_approval_score(
                    dut_evaluation=getattr(session.compliance_context, "dut_evaluation", None),
                    tuss_validation=getattr(session.compliance_context, "tuss_validation", None),
                    tiss_validation=getattr(session.compliance_context, "tiss_validation", None),
                    anvisa_status=getattr(session.compliance_context, "anvisa_status", None),
                    operadora_glosa=getattr(session.compliance_context, "operadora_glosa", None),
                    evidence_count=len(session.clinical_evidences) + len(session.pubmed_evidences),
                    evidence_levels=evidence_lvls or None,
                    has_justification=bool(audit_result.texto_corrigido),
                    cid_procedure_consistent=not any(
                        i.campo in ("cid_inconsistente", "indicacao_off_label")
                        for i in validation.issues
                    ),
                    compliance_mode=session.compliance_context.mode,
                    stf_checklist=getattr(session.compliance_context, "stf_checklist", None),
                )
                compliance_data = {
                    "approval_score": final_score.score,
                    "approval_nivel": final_score.nivel,
                    "approval_componentes": final_score.componentes,
                    "approval_explicacao": final_score.explicacao,
                    "approval_alertas": final_score.alertas,
                    "approval_gaps": final_score.gaps,
                    "compliance_mode": session.compliance_context.mode,
                }
                if session.compliance_context.stf_checklist:
                    compliance_data["stf_checklist"] = session.compliance_context.stf_checklist
                if session.compliance_context.dut_suggestions:
                    compliance_data["dut_suggestions"] = session.compliance_context.dut_suggestions
                og = getattr(session.compliance_context, "operadora_glosa", None)
                if og is not None:
                    compliance_data["operadora_glosa"] = og.to_dict()
                    compliance_data["operadora_registro_ans"] = og.registro_ans
                # Texto da seção "Adequação ao Rol/DUT" do PDF (persistido no Report)
                try:
                    from app.services.compliance_layer import build_compliance_summary_text
                    compliance_data["compliance_texto"] = build_compliance_summary_text(
                        session.compliance_context
                    )
                except Exception as e:
                    logger.debug("compliance_texto não gerado: %s", e)
            except Exception as e:
                logger.warning("Compliance score failed: %s", e)

        await _emit("done", "Relatório finalizado")

        # Trace: final scores
        if trace:
            trace.score("approved", 1.0 if final_approved else 0.0, f"checklist={audit_result.checklist}")
            trace.score("hard_validation", 1.0 if validation.aprovado else 0.0, f"{len(validation.issues)} issues")
            trace.flush()

        # Cleanup: remove session from in-process cache (data is saved to DB)
        cls._cleanup_session(session.session_id)

        result = {
            "session_id": session.session_id,
            "step": "done",
            "justificativa": audit_result.texto_corrigido,
            "aprovado": final_approved,
            "motivo_bloqueio": motivos_bloqueio if motivos_bloqueio else None,
            "checklist": audit_result.checklist,
            "audit_log": audit_log,
            "audit_summary": {
                "data_corrections": [
                    f"{a.campo}: {a.motivo}" for a in audit_result.audit_log
                    if a.tipo == "correcao"
                ],
                "sources_cited": audit_result.referencias_validadas,
                "checklist": audit_result.checklist,
                "hard_validation": {
                    "passed": validation.aprovado,
                    "issues_count": len(validation.issues),
                    "blocking_issues": [
                        {"campo": i.campo, "texto": i.valor_no_texto,
                         "oficial": i.valor_oficial, "tipo": i.tipo}
                        for i in validation.issues if i.severidade == "bloqueante"
                    ],
                    "entities_found": len(validation.entities_found),
                },
            },
            "referencias": enriched_refs,
            "diagnostico_resumo": draft.diagnostico_resumo,
            "falha_terapeutica": draft.falha_terapeutica,
            "risco_nao_realizacao": draft.risco_nao_realizacao,
            "base_legal": draft.base_legal,
            "usage": session.usage.to_dict(),
        }
        result.update(compliance_data)
        return result

    @classmethod
    async def regenerate(
        cls,
        session_id: str,
        adjustments: dict,
    ) -> dict:
        """Re-gera com ajustes do médico."""
        session = cls._sessions.get(session_id)
        if not session:
            return {"error": "Sessão não encontrada"}

        session.medico_inputs.update(adjustments)
        session.step = "writing"
        return await cls._generate(session)
