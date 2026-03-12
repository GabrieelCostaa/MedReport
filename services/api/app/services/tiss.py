"""Geração de guias TISS (XML) e PDF profissional para relatórios OPME."""
from io import BytesIO
import xml.etree.ElementTree as ET
from datetime import datetime

from app.db.models import Report


def _format_ref(ref) -> str:
    """Extrai texto legível de uma referência (dict ou string)."""
    if isinstance(ref, dict):
        text = ref.get("texto") or ref.get("text") or ""
        if not text:
            return str(ref)
        pmid = ref.get("pmid", "")
        doi = ref.get("doi", "")
        link = ref.get("link", "")
        suffix = ""
        if pmid:
            suffix = f" (PMID: {pmid})"
        elif doi:
            suffix = f" (DOI: {doi})"
        return f"{text}{suffix}"
    return str(ref)


def build_guia_solicitacao_xml(report: Report) -> str:
    """Monta XML da guia de solicitação conforme padrão TISS."""
    ns = "http://www.ans.gov.br/padroes/tiss/schemas"
    ns_prefix = f"{{{ns}}}"
    root = ET.Element(f"{ns_prefix}guiaSolicitacao")
    header = ET.SubElement(root, f"{ns_prefix}cabecalhoGuia")
    ET.SubElement(header, f"{ns_prefix}numeroGuiaPrestador").text = str(report.id).replace("-", "")[:20]
    ET.SubElement(header, f"{ns_prefix}dataEmissao").text = (report.created_at or datetime.utcnow()).strftime("%Y-%m-%d")
    body = ET.SubElement(root, f"{ns_prefix}dadosSolicitacao")
    ET.SubElement(body, f"{ns_prefix}cid").text = report.cid or ""
    ET.SubElement(body, f"{ns_prefix}diagnostico").text = (report.diagnosis or "")[:500]
    ET.SubElement(body, f"{ns_prefix}descricaoProcedimento").text = (report.surgery_description or "")[:500]
    ET.SubElement(body, f"{ns_prefix}materiaisOPME").text = (report.materials or "")[:500]
    ET.SubElement(body, f"{ns_prefix}operadora").text = (report.health_plan or "")[:100]
    if getattr(report, 'justificativa_ia', None):
        ET.SubElement(body, f"{ns_prefix}justificativaTecnica").text = report.justificativa_ia[:5000]
    ET.register_namespace("", ns)
    rough = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + rough


def _truncate_word(text: str, max_len: int = 100) -> str:
    """Trunca texto no limite de caracteres respeitando palavra inteira."""
    if not text or len(text) <= max_len:
        return text or "-"
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated + "..." if truncated != text else text


def _build_report_html(report: Report) -> str:
    """Monta HTML do relatório médico profissional."""
    data_emissao = (report.created_at or datetime.utcnow()).strftime("%d/%m/%Y")
    paciente = getattr(report, 'paciente_nome', None) or 'Não informado'
    especialidade = getattr(report, 'especialidade', None) or ''

    refs_html = ""
    referencias = getattr(report, 'referencias_bib', None) or []
    if referencias:
        refs_items = "".join(f"<li>{_format_ref(ref)}</li>" for ref in referencias)
        refs_html = f"""
        <div class="section">
            <h3>Referências Bibliográficas</h3>
            <ol class="references">{refs_items}</ol>
        </div>
        """

    base_legal = getattr(report, 'base_legal_ans', None) or ''
    base_legal_html = ""
    if base_legal:
        base_legal_html = f"""
        <div class="section legal">
            <h3>Fundamentação Legal</h3>
            <p>{base_legal}</p>
        </div>
        """

    justificativa = getattr(report, 'justificativa_ia', None) or ''
    if not justificativa:
        justificativa = f"""
        Paciente com diagnóstico de {report.diagnosis or '[diagnóstico]'} (CID {report.cid or '[CID]'}),
        para o qual se faz necessária a realização de {report.surgery_description or '[procedimento]'}
        com utilização de {report.materials or '[materiais]'}.
        """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
@page {{
    size: A4;
    margin: 2cm 2.5cm;
}}
body {{
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a1a;
}}
.header {{
    text-align: center;
    border-bottom: 2px solid #2c5f2d;
    padding-bottom: 15px;
    margin-bottom: 25px;
}}
.header h1 {{
    font-size: 16pt;
    color: #2c5f2d;
    margin: 0;
    letter-spacing: 1px;
}}
.header h2 {{
    font-size: 12pt;
    color: #555;
    margin: 5px 0 0 0;
    font-weight: normal;
}}
.meta-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 20px;
    background: #f8f9fa;
    padding: 15px;
    border-radius: 4px;
    margin-bottom: 25px;
    font-size: 10pt;
}}
.meta-grid .label {{
    font-weight: bold;
    color: #333;
}}
.meta-grid .value {{
    color: #555;
}}
.section {{
    margin-bottom: 20px;
}}
.section h3 {{
    font-size: 12pt;
    color: #2c5f2d;
    border-bottom: 1px solid #ddd;
    padding-bottom: 5px;
    margin-bottom: 10px;
}}
.body-text {{
    text-align: justify;
    text-indent: 2em;
}}
.body-text p {{
    margin-bottom: 10px;
}}
.legal {{
    background: #f0f7f0;
    padding: 12px 15px;
    border-left: 3px solid #2c5f2d;
    border-radius: 0 4px 4px 0;
    font-size: 10pt;
}}
.references {{
    font-size: 9pt;
    color: #555;
}}
.references li {{
    margin-bottom: 3px;
}}
.signature {{
    margin-top: 50px;
    text-align: center;
}}
.signature .line {{
    width: 250px;
    border-top: 1px solid #333;
    margin: 0 auto 5px auto;
}}
.signature .name {{
    font-weight: bold;
}}
.footer {{
    margin-top: 30px;
    text-align: center;
    font-size: 8pt;
    color: #999;
    border-top: 1px solid #ddd;
    padding-top: 10px;
}}
</style>
</head>
<body>

<div class="header">
    <h1>RELATÓRIO MÉDICO - JUSTIFICATIVA TÉCNICA</h1>
    <h2>Solicitação de Material OPME</h2>
</div>

<div class="meta-grid">
    <div><span class="label">Paciente:</span> <span class="value">{paciente}</span></div>
    <div><span class="label">Data:</span> <span class="value">{data_emissao}</span></div>
    <div><span class="label">CID:</span> <span class="value">{report.cid or '-'}</span></div>
    <div><span class="label">Especialidade:</span> <span class="value">{especialidade or '-'}</span></div>
    <div><span class="label">Procedimento:</span> <span class="value">{_truncate_word(report.surgery_description, 100)}</span></div>
    <div><span class="label">Convênio:</span> <span class="value">{report.health_plan or '-'}</span></div>
    <div><span class="label">Material OPME:</span> <span class="value">{report.materials or '-'}</span></div>
    <div><span class="label">Código TUSS:</span> <span class="value">{', '.join(t.get('code', '') for t in (report.tuss_codes or [])) or '-'}</span></div>
</div>

<div class="section">
    <h3>Justificativa Técnica</h3>
    <div class="body-text">
        {''.join(f'<p>{p.strip()}</p>' for p in justificativa.split(chr(10)) if p.strip())}
    </div>
</div>

{base_legal_html}

{refs_html}

<div class="signature">
    <div class="line"></div>
    <div class="name">Médico Responsável</div>
    <div>CRM / Assinatura</div>
</div>

<div class="footer">
    Documento gerado em {data_emissao} - Plataforma OPME - Este documento contém informações médicas confidenciais
</div>

</body>
</html>"""


def build_guia_pdf(report: Report) -> bytes:
    """Gera PDF profissional do relatório médico."""
    html = _build_report_html(report)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes
    except ImportError:
        pass

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=2.5*cm, rightMargin=2.5*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []

        title_style = styles['Title']
        title_style.fontSize = 14
        title_style.textColor = '#2c5f2d'
        story.append(Paragraph("RELATÓRIO MÉDICO - JUSTIFICATIVA TÉCNICA", title_style))
        story.append(Paragraph("Solicitação de Material OPME", styles['Heading2']))
        story.append(Spacer(1, 12))

        paciente = getattr(report, 'paciente_nome', 'Não informado')
        data_emissao = (report.created_at or datetime.utcnow()).strftime("%d/%m/%Y")

        meta_lines = [
            f"<b>Paciente:</b> {paciente} | <b>Data:</b> {data_emissao}",
            f"<b>CID:</b> {report.cid or '-'} | <b>Procedimento:</b> {_truncate_word(report.surgery_description, 80)}",
            f"<b>Convênio:</b> {report.health_plan or '-'} | <b>Material:</b> {report.materials or '-'}",
        ]
        for line in meta_lines:
            story.append(Paragraph(line, styles['Normal']))

        story.append(Spacer(1, 20))

        justify_style = styles['Normal'].clone('justify')
        justify_style.alignment = TA_JUSTIFY
        justify_style.fontSize = 10
        justify_style.leading = 14

        story.append(Paragraph("<b>Justificativa Técnica</b>", styles['Heading3']))
        story.append(Spacer(1, 6))

        justificativa = getattr(report, 'justificativa_ia', '') or ''
        if not justificativa:
            justificativa = (
                f"Paciente com diagnóstico de {report.diagnosis or '[diagnóstico]'} "
                f"(CID {report.cid or '[CID]'}), necessitando {report.surgery_description or '[procedimento]'}."
            )

        for para in justificativa.split("\n"):
            if para.strip():
                story.append(Paragraph(para.strip(), justify_style))
                story.append(Spacer(1, 4))

        base_legal = getattr(report, 'base_legal_ans', '')
        if base_legal:
            story.append(Spacer(1, 12))
            story.append(Paragraph("<b>Fundamentação Legal</b>", styles['Heading3']))
            story.append(Paragraph(base_legal, justify_style))

        referencias = getattr(report, 'referencias_bib', []) or []
        if referencias:
            story.append(Spacer(1, 12))
            story.append(Paragraph("<b>Referências Bibliográficas</b>", styles['Heading3']))
            for i, ref in enumerate(referencias, 1):
                story.append(Paragraph(f"{i}. {_format_ref(ref)}", styles['Normal']))

        story.append(Spacer(1, 40))
        center_style = styles['Normal'].clone('center')
        center_style.alignment = TA_CENTER
        story.append(Paragraph("_" * 40, center_style))
        story.append(Paragraph("Médico Responsável / CRM", center_style))

        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    except ImportError:
        buffer = BytesIO()
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.units import cm

        c = pdf_canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 2 * cm
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(width / 2, y, "RELATÓRIO MÉDICO - JUSTIFICATIVA TÉCNICA")
        y -= 1.2 * cm
        c.setFont("Helvetica", 10)
        for label, value in [
            ("CID", report.cid or "-"),
            ("Diagnóstico", _truncate_word(report.diagnosis, 80)),
            ("Procedimento", _truncate_word(report.surgery_description, 80)),
            ("Material", _truncate_word(report.materials, 80)),
            ("Convênio", report.health_plan or "-"),
        ]:
            c.drawString(2 * cm, y, f"{label}: {value}")
            y -= 0.6 * cm
        c.save()
        buffer.seek(0)
        return buffer.read()
