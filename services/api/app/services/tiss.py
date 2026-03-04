"""Geração de guias TISS (XML) e PDF."""
from io import BytesIO
import xml.etree.ElementTree as ET
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

from app.db.models import Report


def build_guia_solicitacao_xml(report: Report) -> str:
    """Monta XML da guia de solicitação conforme padrão TISS."""
    ns = "http://www.ans.gov.br/padroes/tiss/schemas"
    root = ET.Element("guiaSolicitacao", attrib={"xmlns": ns})
    header = ET.SubElement(root, "cabecalhoGuia")
    ET.SubElement(header, "numeroGuiaPrestador").text = str(report.id).replace("-", "")[:20]
    ET.SubElement(header, "dataEmissao").text = (report.created_at or datetime.utcnow()).strftime("%Y-%m-%d")
    body = ET.SubElement(root, "dadosSolicitacao")
    ET.SubElement(body, "cid").text = report.cid or ""
    ET.SubElement(body, "diagnostico").text = (report.diagnosis or "")[:500]
    ET.SubElement(body, "descricaoProcedimento").text = (report.surgery_description or "")[:500]
    ET.SubElement(body, "materiaisOPME").text = (report.materials or "")[:500]
    ET.SubElement(body, "operadora").text = (report.health_plan or "")[:100]
    rough = ET.tostring(root, encoding="unicode", default_namespace=ns)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + rough


def build_guia_pdf(report: Report) -> bytes:
    """Gera PDF da guia para visualização/impressão."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, y, "Guia de Solicitação de Cirurgia - TISS")
    y -= 1.2 * cm
    c.setFont("Helvetica", 10)
    for label, value in [
        ("CID", report.cid or "-"),
        ("Diagnóstico", (report.diagnosis or "-")[:80]),
        ("Descrição da cirurgia", (report.surgery_description or "-")[:80]),
        ("Materiais/OPME", (report.materials or "-")[:80]),
        ("Convênio", report.health_plan or "-"),
        ("Data emissão", (report.created_at or datetime.utcnow()).strftime("%d/%m/%Y")),
    ]:
        c.drawString(2 * cm, y, f"{label}: {value}")
        y -= 0.6 * cm
    c.save()
    buffer.seek(0)
    return buffer.read()
