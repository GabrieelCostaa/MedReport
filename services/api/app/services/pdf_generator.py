"""
Serviço de geração de PDF para relatórios OPME.
Estratégia: WeasyPrint (HTML→PDF) com fallback ReportLab (programático).
"""
import io
import logging
import uuid
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


def _split_paragraphs(text: str) -> list[str]:
    """Divide texto em parágrafos, removendo linhas vazias."""
    if not text:
        return []
    paragraphs = []
    for block in text.split("\n\n"):
        clean = block.strip()
        if clean:
            paragraphs.append(clean.replace("\n", " "))
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]
    return paragraphs


def _format_ref(ref) -> str:
    if isinstance(ref, dict):
        text = ref.get("texto") or ref.get("text") or str(ref)
        pmid = ref.get("pmid", "")
        doi = ref.get("doi", "")
        if pmid:
            text += f" (PMID: {pmid})"
        elif doi:
            text += f" (DOI: {doi})"
        return text
    return str(ref)


def generate_pdf_bytes(
    justificativa: str,
    paciente_nome: str,
    cid: str,
    diagnostico_resumo: str,
    produto_nome: str,
    convenio: str = "",
    especialidade: str = "",
    codigo_tuss: str = "",
    referencias: list = None,
    checklist: dict = None,
    medico_nome: str = "",
    medico_crm: str = "",
    aprovado: bool = True,
    falha_terapeutica: str = "",
    risco_nao_realizacao: str = "",
    base_legal: str = "",
) -> bytes:
    """Gera PDF em bytes. Tenta WeasyPrint, fallback para ReportLab."""
    # Sanitize inputs
    justificativa = justificativa or ""
    paciente_nome = paciente_nome or ""
    cid = cid or ""
    diagnostico_resumo = diagnostico_resumo or ""
    produto_nome = produto_nome or ""
    convenio = convenio or ""
    especialidade = especialidade or ""
    codigo_tuss = codigo_tuss or ""
    referencias = referencias or []
    checklist = checklist or {}
    medico_nome = medico_nome or ""
    medico_crm = medico_crm or ""
    falha_terapeutica = falha_terapeutica or ""
    risco_nao_realizacao = risco_nao_realizacao or ""
    base_legal = base_legal or ""

    kwargs = dict(
        justificativa=justificativa,
        paciente_nome=paciente_nome,
        cid=cid,
        diagnostico_resumo=diagnostico_resumo,
        produto_nome=produto_nome,
        convenio=convenio,
        especialidade=especialidade,
        codigo_tuss=codigo_tuss,
        referencias=referencias,
        checklist=checklist,
        medico_nome=medico_nome,
        medico_crm=medico_crm,
        aprovado=aprovado,
        falha_terapeutica=falha_terapeutica,
        risco_nao_realizacao=risco_nao_realizacao,
        base_legal=base_legal,
    )

    try:
        return _generate_weasyprint(**kwargs)
    except Exception as e:
        logger.warning("WeasyPrint falhou (%s), usando ReportLab", e)
        return _generate_reportlab(**kwargs)


def _generate_weasyprint(**kwargs) -> bytes:
    """Gera PDF via WeasyPrint (HTML template)."""
    import weasyprint

    template = _jinja_env.get_template("report_pdf.html")
    protocolo = f"OPME-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    watermark = None if kwargs.get("aprovado", True) else "RASCUNHO"

    refs = []
    for ref in (kwargs.get("referencias") or []):
        refs.append(ref if isinstance(ref, dict) else str(ref))

    html_content = template.render(
        paciente_nome=kwargs.get("paciente_nome") or "Não informado",
        cid=kwargs.get("cid") or "",
        diagnostico_resumo=kwargs.get("diagnostico_resumo") or "",
        produto_nome=kwargs.get("produto_nome") or "—",
        convenio=kwargs.get("convenio") or "Não informado",
        especialidade=kwargs.get("especialidade") or "",
        codigo_tuss=kwargs.get("codigo_tuss") or "",
        justificativa_paragrafos=_split_paragraphs(kwargs.get("justificativa", "")),
        falha_terapeutica_paragrafos=_split_paragraphs(kwargs.get("falha_terapeutica", "")),
        risco_paragrafos=_split_paragraphs(kwargs.get("risco_nao_realizacao", "")),
        base_legal_paragrafos=_split_paragraphs(kwargs.get("base_legal", "")),
        referencias=refs,
        checklist=kwargs.get("checklist"),
        medico_nome=kwargs.get("medico_nome"),
        medico_crm=kwargs.get("medico_crm"),
        data_emissao=datetime.now().strftime("%d/%m/%Y"),
        protocolo=protocolo,
        watermark=watermark,
    )

    pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
    logger.info("PDF gerado via WeasyPrint: %d bytes, protocolo=%s", len(pdf_bytes), protocolo)
    return pdf_bytes


def _generate_reportlab(**kwargs) -> bytes:
    """Fallback: gera PDF profissional via ReportLab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable,
    )

    buffer = io.BytesIO()
    protocolo = f"OPME-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    data_emissao = datetime.now().strftime("%d/%m/%Y")

    # Colors
    NAVY = HexColor("#1a3c6e")
    DARK = HexColor("#2d2d2d")
    BODY_COLOR = HexColor("#333333")
    GRAY = HexColor("#6b6b6b")
    LIGHT_GRAY = HexColor("#999999")
    BG_BLUE = HexColor("#f0f4fa")
    BORDER_BLUE = HexColor("#dce3ee")
    BG_LEGAL = HexColor("#f8f6f0")
    GOLD = HexColor("#c8a834")
    BG_CHECK = HexColor("#f5f8f5")
    GREEN = HexColor("#27ae60")
    RED_CK = HexColor("#c0392b")

    # Styles
    s_title = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=15, textColor=NAVY, leading=18)
    s_subtitle = ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=8.5, textColor=LIGHT_GRAY, leading=11)
    s_date = ParagraphStyle("Date", fontName="Helvetica", fontSize=8, textColor=LIGHT_GRAY, alignment=TA_RIGHT, leading=10)
    s_meta_label = ParagraphStyle("MetaLabel", fontName="Helvetica-Bold", fontSize=9, textColor=NAVY, leading=12)
    s_meta_value = ParagraphStyle("MetaValue", fontName="Helvetica", fontSize=9, textColor=DARK, leading=12)
    s_section_title = ParagraphStyle("SectionTitle", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY,
                                      spaceAfter=4, spaceBefore=12, leading=13)
    s_body = ParagraphStyle("Body", fontName="Helvetica", fontSize=10.5, textColor=BODY_COLOR,
                            alignment=TA_JUSTIFY, leading=15, firstLineIndent=2*cm, spaceAfter=6)
    s_legal = ParagraphStyle("Legal", fontName="Helvetica", fontSize=9.5, textColor=GRAY,
                             alignment=TA_JUSTIFY, leading=13, spaceAfter=4, leftIndent=0.5*cm)
    s_ref = ParagraphStyle("Ref", fontName="Helvetica", fontSize=8.5, textColor=GRAY, leading=11, spaceAfter=2,
                           leftIndent=0.5*cm)
    s_ref_title = ParagraphStyle("RefTitle", fontName="Helvetica-Bold", fontSize=9, textColor=NAVY, leading=12, spaceBefore=8)
    s_center = ParagraphStyle("Center", fontName="Helvetica", fontSize=10, alignment=TA_CENTER, leading=14)
    s_center_bold = ParagraphStyle("CenterBold", fontName="Helvetica-Bold", fontSize=10.5, textColor=DARK, alignment=TA_CENTER, leading=14)
    s_center_sm = ParagraphStyle("CenterSm", fontName="Helvetica", fontSize=8.5, textColor=GRAY, alignment=TA_CENTER, leading=11)
    s_footer = ParagraphStyle("Footer", fontName="Helvetica", fontSize=7.5, textColor=LIGHT_GRAY, alignment=TA_CENTER, leading=10)
    s_check = ParagraphStyle("Check", fontName="Helvetica", fontSize=8.5, textColor=BODY_COLOR, leading=11)

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2*cm, bottomMargin=2.5*cm,
    )

    story = []

    # ── HEADER ──
    # Title + date in a table
    header_data = [
        [
            [Paragraph("Relatório Médico Complementar", s_title),
             Paragraph("Justificativa Técnica para Autorização de Material OPME", s_subtitle)],
            [Paragraph(data_emissao, s_date),
             Paragraph(f"Protocolo: {protocolo}", s_date)],
        ]
    ]
    header_table = Table(header_data, colWidths=[12*cm, 5*cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 2.5, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    # ── METADATA TABLE ──
    paciente = kwargs.get("paciente_nome") or "Não informado"
    convenio = kwargs.get("convenio") or "Não informado"
    cid = kwargs.get("cid") or ""
    diag = kwargs.get("diagnostico_resumo") or ""
    cid_diag = f"{cid} — {diag}" if cid and diag else cid or diag or "—"
    espec = kwargs.get("especialidade") or "—"
    produto = kwargs.get("produto_nome") or "—"
    tuss = kwargs.get("codigo_tuss") or "—"

    meta_data = [
        [Paragraph("<b>Paciente:</b>", s_meta_label), Paragraph(paciente, s_meta_value),
         Paragraph("<b>Convênio:</b>", s_meta_label), Paragraph(convenio, s_meta_value)],
        [Paragraph("<b>Diagnóstico (CID):</b>", s_meta_label), Paragraph(cid_diag, s_meta_value),
         Paragraph("<b>Especialidade:</b>", s_meta_label), Paragraph(espec, s_meta_value)],
        [Paragraph("<b>Material OPME:</b>", s_meta_label), Paragraph(produto, s_meta_value),
         Paragraph("<b>Código TUSS:</b>", s_meta_label), Paragraph(tuss, s_meta_value)],
    ]
    meta_table = Table(meta_data, colWidths=[3.2*cm, 5.3*cm, 3.2*cm, 5.3*cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_BLUE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # ── HELPER: Add section ──
    def add_section(title: str, text: str, style=s_body):
        if not text or not text.strip():
            return
        story.append(Paragraph(title.upper(), s_section_title))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_BLUE, spaceAfter=6))
        for p in _split_paragraphs(text):
            # Escape XML entities for ReportLab
            safe_p = p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_p, style))

    # ── SECTIONS ──
    add_section("Justificativa Técnica", kwargs.get("justificativa", ""))
    add_section("Falha Terapêutica e Tratamentos Prévios", kwargs.get("falha_terapeutica", ""))
    add_section("Risco da Não Realização do Procedimento", kwargs.get("risco_nao_realizacao", ""))

    # Legal block (different style)
    bl = kwargs.get("base_legal", "")
    if bl and bl.strip():
        story.append(Paragraph("FUNDAMENTAÇÃO LEGAL", s_section_title))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_BLUE, spaceAfter=6))
        for p in _split_paragraphs(bl):
            safe_p = p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe_p, s_legal))

    # ── REFERÊNCIAS ──
    refs = kwargs.get("referencias") or []
    if refs:
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#dddddd"), spaceAfter=6))
        story.append(Paragraph("Referências Bibliográficas", s_ref_title))
        for i, ref in enumerate(refs, 1):
            text = _format_ref(ref)
            safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(f"{i}. {safe_text}", s_ref))

    # ── CHECKLIST ──
    ck = kwargs.get("checklist")
    if ck and isinstance(ck, dict):
        story.append(Spacer(1, 8))
        ck_items = list(ck.items())
        ck_rows = []
        for i in range(0, len(ck_items), 2):
            row = []
            for j in range(2):
                if i + j < len(ck_items):
                    item, status = ck_items[i + j]
                    icon = "✓" if status else "✗"
                    color = GREEN if status else RED_CK
                    label = item.replace("_", " ").title()
                    row.append(Paragraph(f'<font color="{color}">{icon}</font>  {label}', s_check))
                else:
                    row.append("")
            ck_rows.append(row)

        if ck_rows:
            ck_table = Table(ck_rows, colWidths=[8.5*cm, 8.5*cm])
            ck_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BG_CHECK),
                ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#d0ddd0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(ck_table)

    # ── ASSINATURA ──
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="35%", thickness=0.8, color=HexColor("#444444"), hAlign="CENTER"))
    story.append(Spacer(1, 4))
    nome = kwargs.get("medico_nome") or "[Nome do Médico Responsável]"
    crm = kwargs.get("medico_crm") or "CRM: __________"
    story.append(Paragraph(nome, s_center_bold))
    story.append(Paragraph(crm, s_center_sm))

    # ── WATERMARK (draft) ──
    if not kwargs.get("aprovado", True):
        story.append(Spacer(1, 10))
        s_wm = ParagraphStyle("Watermark", fontName="Helvetica-Bold", fontSize=12,
                              textColor=LIGHT_GRAY, alignment=TA_CENTER)
        story.append(Paragraph("[ RASCUNHO — PENDENTE DE APROVAÇÃO ]", s_wm))

    # ── FOOTER ──
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#eeeeee"), spaceAfter=4))
    story.append(Paragraph(
        f"Documento gerado em {data_emissao} • Protocolo {protocolo} • Informações médicas confidenciais",
        s_footer,
    ))

    doc.build(story)
    buffer.seek(0)
    pdf_bytes = buffer.read()
    logger.info("PDF gerado via ReportLab: %d bytes, protocolo=%s", len(pdf_bytes), protocolo)
    return pdf_bytes
