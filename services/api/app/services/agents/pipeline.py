"""
Orquestrador do pipeline multi-agente: Pesquisador -> Redator -> Auditor.
"""
import logging
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

logger = logging.getLogger(__name__)


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


class ReportPipeline:
    """
    Pipeline multi-agente para geração de relatórios OPME.

    Fluxo:
    1. start() -> pesquisa + identifica lacunas
    2. Se há lacunas -> retorna perguntas A/B/C
    3. answer() -> recebe respostas do médico
    4. generate() -> redação + auditoria
    5. Resultado: texto auditado + checklist
    """

    _sessions: dict[str, PipelineSession] = {}

    @classmethod
    def get_session(cls, session_id: str) -> Optional[PipelineSession]:
        return cls._sessions.get(session_id)

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
    ) -> dict:
        """
        Inicia pipeline: executa Agente A (Pesquisador).
        Retorna session_id e perguntas A/B/C se houver lacunas.
        """
        session_id = str(uuid.uuid4())
        session = PipelineSession(
            session_id=session_id,
            product=product,
            template=template,
            medico_inputs=medico_inputs,
        )
        session.step = "researching"
        cls._sessions[session_id] = session

        async def _emit(step, label):
            if on_progress:
                await on_progress(step, label)

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

        # Compliance layer: DUT, TUSS, Anvisa
        try:
            from app.services.compliance_layer import build_compliance_context
            await _emit("researching", "Verificando conformidade regulatória ANS...")
            compliance_ctx = await build_compliance_context(
                db=db,
                procedure_code=getattr(product, "codigo_tuss_sugerido", "") or "",
                patient_data=medico_inputs,
                produto_registro_anvisa=getattr(product, "registro_anvisa", "") or "",
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
    async def answer(cls, session_id: str, answers: dict, on_progress=None) -> dict:
        """
        Recebe respostas A/B/C do médico e avança o pipeline.
        """
        session = cls._sessions.get(session_id)
        if not session:
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

        session.step = "writing"
        n_ev = len(session.clinical_evidences) + len(session.pubmed_evidences)
        await _emit("writing", f"Redigindo justificativa técnica para {session.product.nome}...")
        if n_ev > 0:
            await _emit("writing", f"Fundamentando com {n_ev} evidências científicas...")
        logger.info("Pipeline redação: session=%s", session.session_id)

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

        word_count = len((draft.justificativa_completa or "").split())
        await _emit("writing", f"Redação concluída — {word_count} palavras geradas")

        session.step = "auditing"
        await _emit("auditing", f"Confrontando dados técnicos de {session.product.nome} com base oficial...")
        logger.info("Pipeline auditoria: session=%s", session.session_id)

        audit_result = await audit(
            draft, session.product,
            clinical_evidences=session.clinical_evidences,
            pubmed_evidences=session.pubmed_evidences,
        )
        session.audit_result = audit_result
        if audit_result.token_usage:
            session.usage.add(audit_result.token_usage)

        corrections = sum(1 for a in audit_result.audit_log if a.tipo == "correcao")
        if corrections > 0:
            await _emit("auditing", f"{corrections} correção(ões) aplicada(s) para conformidade")
        else:
            await _emit("auditing", "Dados técnicos verificados — sem divergências")

        session.step = "validating"
        await _emit("validating", "Executando validação determinística de conformidade...")
        logger.info("Pipeline validação hard-coded: session=%s", session.session_id)

        validation = validate_technical_data(
            audit_result.texto_corrigido,
            session.product,
        )

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
        for issue in validation.issues:
            if issue.severidade == "bloqueante":
                motivos_bloqueio.append(
                    f"O valor '{issue.valor_no_texto}' foi identificado como {issue.campo} incorreto. "
                    f"O valor oficial é '{issue.valor_oficial}'."
                )

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
                final_score = compute_approval_score(
                    dut_evaluation=getattr(session.compliance_context, "dut_evaluation", None),
                    tuss_validation=getattr(session.compliance_context, "tuss_validation", None),
                    tiss_validation=getattr(session.compliance_context, "tiss_validation", None),
                    anvisa_status=getattr(session.compliance_context, "anvisa_status", None),
                    evidence_count=len(session.clinical_evidences) + len(session.pubmed_evidences),
                    has_justification=bool(audit_result.texto_corrigido),
                    cid_procedure_consistent=True,
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
            except Exception as e:
                logger.warning("Compliance score failed: %s", e)

        await _emit("done", "Relatório finalizado")

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
