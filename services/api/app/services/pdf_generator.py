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


# Títulos de seção inseridos pelo Redator (devem espelhar writer._SECTION_TITLES).
_SECTION_TITLES = [
    "QUADRO CLÍNICO E HISTÓRIA",
    "FALHA TERAPÊUTICA PRÉVIA",
    "JUSTIFICATIVA TÉCNICA E SUPERIORIDADE DO MATERIAL",
    "EVIDÊNCIA CIENTÍFICA",
    "RISCO DA NÃO REALIZAÇÃO",
    "CONCLUSÃO",
]


def _normalize_title(line: str) -> str:
    """Normaliza uma linha para comparação com títulos de seção."""
    import re
    t = line.strip().upper()
    t = re.sub(r"^\d+[\.\)]\s*", "", t)   # remove numeração "1. "
    t = t.rstrip(":.").strip()
    return t


def _split_into_sections(body: str) -> list[dict]:
    """Divide o corpo da justificativa em seções tituladas.

    O Redator produz o corpo com títulos em MAIÚSCULAS por seção. Esta função
    reconstrói (titulo, parágrafos) para renderização com cabeçalhos próprios.
    Se nenhum título conhecido for encontrado (ex.: Auditor reflowou o texto),
    devolve uma única seção "Justificativa Técnica" com o corpo inteiro.
    """
    if not body or not body.strip():
        return []

    known = {_normalize_title(t): t for t in _SECTION_TITLES}
    # Títulos em capitalização de exibição (Title Case-ish, mantém acentos).
    display = {
        "QUADRO CLÍNICO E HISTÓRIA": "Quadro Clínico e História",
        "FALHA TERAPÊUTICA PRÉVIA": "Falha Terapêutica Prévia",
        "JUSTIFICATIVA TÉCNICA E SUPERIORIDADE DO MATERIAL": "Justificativa Técnica e Superioridade do Material",
        "EVIDÊNCIA CIENTÍFICA": "Evidência Científica",
        "RISCO DA NÃO REALIZAÇÃO": "Risco da Não Realização",
        "CONCLUSÃO": "Conclusão",
    }

    sections: list[dict] = []
    current = None
    for raw_line in body.split("\n"):
        norm = _normalize_title(raw_line)
        if norm in known:
            current = {"titulo": display.get(known[norm], known[norm].title()), "buffer": []}
            sections.append(current)
        else:
            if current is None:
                current = {"titulo": "Justificativa Técnica", "buffer": []}
                sections.append(current)
            current["buffer"].append(raw_line)

    # Converte buffers em parágrafos; descarta seções vazias.
    result = []
    known_count = sum(1 for s in sections if s["titulo"] != "Justificativa Técnica")
    if known_count == 0:
        # Nenhum título reconhecido → seção única com o corpo inteiro.
        return [{"titulo": "Justificativa Técnica", "paragrafos": _split_paragraphs(body)}]

    for s in sections:
        conteudo = "\n".join(s["buffer"]).strip()
        paragrafos = _split_paragraphs(conteudo)
        if paragrafos:
            result.append({"titulo": s["titulo"], "paragrafos": paragrafos})
    return result


def _generate_qr_png(url: str) -> bytes:
    """Gera QR Code como PNG em bytes."""
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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
    medico_rqe: str = "",
    aprovado: bool = True,
    falha_terapeutica: str = "",
    risco_nao_realizacao: str = "",
    base_legal: str = "",
    signed_at_str: str = "",
    signature_hash: str = "",
    verification_url: str = "",
    # Identidade do emissor (timbrado)
    clinica_nome: str = "",
    clinica_logo_url: str = "",
    # Identificação anti-glosa
    paciente_dob: str = "",
    paciente_carteirinha: str = "",
    paciente_cpf: str = "",
    guia_numero: str = "",
    atendimento_numero: str = "",
    cids_secundarios: list = None,
    materiais_tuss: list = None,
    registro_anvisa: str = "",
    compliance_texto: str = "",
) -> bytes:
    """Gera PDF em bytes. Tenta WeasyPrint, fallback para ReportLab."""
    kwargs = dict(
        justificativa=justificativa or "",
        paciente_nome=paciente_nome or "",
        cid=cid or "",
        diagnostico_resumo=diagnostico_resumo or "",
        produto_nome=produto_nome or "",
        convenio=convenio or "",
        especialidade=especialidade or "",
        codigo_tuss=codigo_tuss or "",
        referencias=referencias or [],
        checklist=checklist or {},
        medico_nome=medico_nome or "",
        medico_crm=medico_crm or "",
        medico_rqe=medico_rqe or "",
        aprovado=aprovado,
        falha_terapeutica=falha_terapeutica or "",
        risco_nao_realizacao=risco_nao_realizacao or "",
        base_legal=base_legal or "",
        signed_at_str=signed_at_str or "",
        signature_hash=signature_hash or "",
        verification_url=verification_url or "",
        clinica_nome=clinica_nome or "",
        clinica_logo_url=clinica_logo_url or "",
        paciente_dob=paciente_dob or "",
        paciente_carteirinha=paciente_carteirinha or "",
        paciente_cpf=paciente_cpf or "",
        guia_numero=guia_numero or "",
        atendimento_numero=atendimento_numero or "",
        cids_secundarios=cids_secundarios or [],
        materiais_tuss=materiais_tuss or [],
        registro_anvisa=registro_anvisa or "",
        compliance_texto=compliance_texto or "",
    )

    try:
        return _generate_weasyprint(**kwargs)
    except Exception as e:
        logger.warning(
            "WeasyPrint indisponível/falhou (%s) — usando fallback ReportLab "
            "(layout reduzido). Verifique as libs do WeasyPrint no ambiente.", e
        )
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

    # QR Code base64 para verificação (só se assinado)
    verification_url = kwargs.get("verification_url") or ""
    qr_b64 = ""
    if verification_url:
        import base64
        qr_b64 = base64.b64encode(_generate_qr_png(verification_url)).decode()

    html_content = template.render(
        paciente_nome=kwargs.get("paciente_nome") or "Não informado",
        cid=kwargs.get("cid") or "",
        diagnostico_resumo=kwargs.get("diagnostico_resumo") or "",
        produto_nome=kwargs.get("produto_nome") or "—",
        convenio=kwargs.get("convenio") or "Não informado",
        especialidade=kwargs.get("especialidade") or "",
        codigo_tuss=kwargs.get("codigo_tuss") or "",
        secoes=_split_into_sections(kwargs.get("justificativa", "")),
        base_legal_paragrafos=_split_paragraphs(kwargs.get("base_legal", "")),
        compliance_texto=_split_paragraphs(kwargs.get("compliance_texto", "")),
        referencias=refs,
        checklist=kwargs.get("checklist"),
        medico_nome=kwargs.get("medico_nome"),
        medico_crm=kwargs.get("medico_crm"),
        medico_rqe=kwargs.get("medico_rqe") or "",
        clinica_nome=kwargs.get("clinica_nome") or "",
        clinica_logo_url=kwargs.get("clinica_logo_url") or "",
        paciente_dob=kwargs.get("paciente_dob") or "",
        paciente_carteirinha=kwargs.get("paciente_carteirinha") or "",
        paciente_cpf=kwargs.get("paciente_cpf") or "",
        guia_numero=kwargs.get("guia_numero") or "",
        atendimento_numero=kwargs.get("atendimento_numero") or "",
        cids_secundarios=kwargs.get("cids_secundarios") or [],
        materiais_tuss=kwargs.get("materiais_tuss") or [],
        registro_anvisa=kwargs.get("registro_anvisa") or "",
        data_emissao=datetime.now().strftime("%d/%m/%Y"),
        protocolo=protocolo,
        watermark=watermark,
        signed_at_str=kwargs.get("signed_at_str") or "",
        signature_hash=kwargs.get("signature_hash") or "",
        qr_b64=qr_b64,
        verification_url=verification_url,
    )

    pdf_bytes = weasyprint.HTML(string=html_content).write_pdf(
        presentational_hints=True,
        # PDF/UA accessibility: set document metadata
        uncompressed_pdf=False,
    )
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
    clinica_nome = kwargs.get("clinica_nome") or "Relatório Médico Complementar"
    header_data = [
        [
            [Paragraph(clinica_nome, s_title),
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
    dob = kwargs.get("paciente_dob") or "—"
    carteirinha = kwargs.get("paciente_carteirinha") or "—"
    guia = kwargs.get("guia_numero") or "—"
    atend = kwargs.get("atendimento_numero") or ""
    guia_atend = f"{guia}" + (f" / {atend}" if atend else "")
    anvisa = kwargs.get("registro_anvisa") or ""
    cids_sec = kwargs.get("cids_secundarios") or []

    meta_data = [
        [Paragraph("<b>Paciente:</b>", s_meta_label), Paragraph(paciente, s_meta_value),
         Paragraph("<b>Nascimento:</b>", s_meta_label), Paragraph(dob, s_meta_value)],
        [Paragraph("<b>Convênio:</b>", s_meta_label), Paragraph(convenio, s_meta_value),
         Paragraph("<b>Carteirinha:</b>", s_meta_label), Paragraph(carteirinha, s_meta_value)],
        [Paragraph("<b>Diagnóstico (CID):</b>", s_meta_label), Paragraph(cid_diag, s_meta_value),
         Paragraph("<b>Guia / Atend.:</b>", s_meta_label), Paragraph(guia_atend, s_meta_value)],
        [Paragraph("<b>Especialidade:</b>", s_meta_label), Paragraph(espec, s_meta_value),
         Paragraph("<b>Código TUSS:</b>", s_meta_label), Paragraph(tuss, s_meta_value)],
        [Paragraph("<b>Material OPME:</b>", s_meta_label), Paragraph(produto, s_meta_value),
         Paragraph("<b>Reg. ANVISA:</b>", s_meta_label), Paragraph(anvisa or "—", s_meta_value)],
    ]
    if cids_sec:
        meta_data.append([
            Paragraph("<b>CID secundários:</b>", s_meta_label),
            Paragraph(", ".join(str(c) for c in cids_sec), s_meta_value),
            Paragraph("", s_meta_label), Paragraph("", s_meta_value),
        ])
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
    story.append(Spacer(1, 12))

    # ── MATERIAIS TABLE ──
    materiais = kwargs.get("materiais_tuss") or []
    if materiais:
        mat_rows = [[
            Paragraph("<b>Código TUSS</b>", s_meta_value),
            Paragraph("<b>Descrição do material</b>", s_meta_value),
            Paragraph("<b>Qtd.</b>", s_meta_value),
        ]]
        for m in materiais:
            if not isinstance(m, dict):
                continue
            mat_rows.append([
                Paragraph(str(m.get("codigo") or "—"), s_meta_value),
                Paragraph(str(m.get("nome") or "—"), s_meta_value),
                Paragraph(str(m.get("qtd") or 1), s_meta_value),
            ])
        mat_table = Table(mat_rows, colWidths=[3.5*cm, 10.5*cm, 2*cm])
        mat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#eef2f9")),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER_BLUE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_BLUE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(mat_table)
        story.append(Spacer(1, 12))

    def _esc(p: str) -> str:
        return p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ── HELPER: Add pre-split section ──
    def add_paras(title: str, paragrafos: list, style=s_body):
        if not paragrafos:
            return
        story.append(Paragraph(title.upper(), s_section_title))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_BLUE, spaceAfter=6))
        for p in paragrafos:
            story.append(Paragraph(_esc(p), style))

    # ── CLINICAL SECTIONS (parsed from justificativa body) ──
    for sec in _split_into_sections(kwargs.get("justificativa", "")):
        add_paras(sec["titulo"], sec["paragrafos"])

    # Adequação DUT/Rol (compliance)
    add_paras("Adequação ao Rol / DUT (ANS)",
              _split_paragraphs(kwargs.get("compliance_texto", "")), style=s_legal)

    # Legal block (different style)
    bl = kwargs.get("base_legal", "")
    if bl and bl.strip():
        story.append(Paragraph("FUNDAMENTAÇÃO LEGAL", s_section_title))
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_BLUE, spaceAfter=6))
        for p in _split_paragraphs(bl):
            story.append(Paragraph(_esc(p), s_legal))

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
    from reportlab.platypus import Image as RLImage
    story.append(Spacer(1, 24))
    nome = kwargs.get("medico_nome") or "[Nome do Médico Responsável]"
    crm = kwargs.get("medico_crm") or "CRM: __________"
    rqe = kwargs.get("medico_rqe") or ""
    if rqe:
        crm = f"{crm} · RQE {rqe}"
    signed_at_str = kwargs.get("signed_at_str") or ""
    sig_hash = kwargs.get("signature_hash") or ""
    verification_url = kwargs.get("verification_url") or ""

    if signed_at_str:
        # Bloco visual de assinatura eletrônica com QR Code
        short_hash = f"{sig_hash[:16]}...{sig_hash[-8:]}" if len(sig_hash) >= 24 else sig_hash
        s_sig_name = ParagraphStyle("SigName", fontName="Helvetica-Bold", fontSize=10, textColor=DARK)
        s_sig_crm = ParagraphStyle("SigCrm", fontName="Helvetica", fontSize=8, textColor=GRAY)
        s_sig_label = ParagraphStyle("SigLabel", fontName="Helvetica", fontSize=7, textColor=GRAY)
        s_sig_date = ParagraphStyle("SigDate", fontName="Helvetica-Bold", fontSize=9, textColor=NAVY)
        s_sig_hash = ParagraphStyle("SigHash", fontName="Courier", fontSize=6.5, textColor=LIGHT_GRAY)
        s_sig_scan = ParagraphStyle("SigScan", fontName="Helvetica", fontSize=6, textColor=GRAY, alignment=1)

        sig_left = (
            f"<b>{nome}</b><br/>"
            f'<font color="#888888" size="8">{crm}</font><br/><br/>'
            f'<font color="#888888" size="7">Assinado eletronicamente em</font><br/>'
            f'<font color="#1a3c6e"><b>{signed_at_str}</b></font>'
        )
        if short_hash:
            sig_left += f'<br/><font color="#aaaaaa" size="6.5">SHA-256: {short_hash}</font>'

        s_sig_combined = ParagraphStyle("SigCombined", fontName="Helvetica", fontSize=9,
                                        textColor=DARK, leading=13)
        left_cell = Paragraph(sig_left, s_sig_combined)

        if verification_url:
            qr_bytes = _generate_qr_png(verification_url)
            qr_img = RLImage(io.BytesIO(qr_bytes), width=2.3*cm, height=2.3*cm)
            right_cell = [qr_img, Paragraph("Verificar autenticidade", s_sig_scan)]
        else:
            right_cell = Paragraph("", s_sig_scan)

        sig_table = Table([[left_cell, right_cell]], colWidths=[13.2*cm, 3.3*cm])
        sig_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, NAVY),
            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#f4f7ff")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(sig_table)
    else:
        # Bloco simples para documentos não assinados
        story.append(HRFlowable(width="35%", thickness=0.8, color=HexColor("#444444"), hAlign="CENTER"))
        story.append(Spacer(1, 4))
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
        f"Documento gerado em {data_emissao} • Protocolo {protocolo} • "
        f"Informações médicas confidenciais (LGPD Art. 11)",
        s_footer,
    ))

    def _page_number(canvas, doc_):
        """Rodapé com numeração de página (paridade com o WeasyPrint)."""
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(LIGHT_GRAY)
        canvas.drawCentredString(A4[0] / 2.0, 1.2 * cm, f"Página {doc_.page}")
        canvas.drawRightString(A4[0] - 2.2 * cm, 1.2 * cm, f"Protocolo {protocolo}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_page_number, onLaterPages=_page_number)
    buffer.seek(0)
    pdf_bytes = buffer.read()
    logger.info("PDF gerado via ReportLab: %d bytes, protocolo=%s", len(pdf_bytes), protocolo)
    return pdf_bytes
