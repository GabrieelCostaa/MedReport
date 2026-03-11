"""
Serviço de geração de PDF para relatórios OPME.
Usa Jinja2 + WeasyPrint para converter HTML template em PDF profissional.
"""
import base64
import io
import os
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


def _generate_qr_base64(url: str) -> str:
    """Gera QR code em base64 PNG para uma URL."""
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=4, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        logger.warning("qrcode library not installed, skipping QR generation")
        return ""
    except Exception as e:
        logger.warning("QR generation failed: %s", e)
        return ""


def _prepare_references_for_pdf(referencias: list) -> list:
    """Prepara referências com QR codes para o template PDF."""
    if not referencias:
        return []
    prepared = []
    for ref in referencias:
        if isinstance(ref, dict):
            item = dict(ref)
            if item.get("link"):
                item["qr_base64"] = _generate_qr_base64(item["link"])
            prepared.append(item)
        else:
            prepared.append(ref)
    return prepared


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
) -> bytes:
    """
    Gera PDF em bytes a partir do relatório.

    Returns:
        bytes do PDF gerado.
    """
    import weasyprint

    template = _jinja_env.get_template("report_pdf.html")

    protocolo = f"OPME-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    watermark = None if aprovado else "RASCUNHO"

    html_content = template.render(
        paciente_nome=paciente_nome or "Não informado",
        cid=cid or "",
        diagnostico_resumo=diagnostico_resumo or "",
        produto_nome=produto_nome or "",
        convenio=convenio or "Não informado",
        especialidade=especialidade or "",
        codigo_tuss=codigo_tuss or "",
        justificativa_paragrafos=_split_paragraphs(justificativa),
        referencias=_prepare_references_for_pdf(referencias or []),
        checklist=checklist,
        medico_nome=medico_nome,
        medico_crm=medico_crm,
        data_emissao=datetime.now().strftime("%d/%m/%Y"),
        protocolo=protocolo,
        watermark=watermark,
    )

    pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()

    logger.info(
        "PDF gerado: paciente=%s, produto=%s, %d bytes, protocolo=%s",
        paciente_nome, produto_nome, len(pdf_bytes), protocolo,
    )

    return pdf_bytes


def generate_pdf_file(output_path: str, **kwargs) -> str:
    """Gera PDF e salva em disco. Retorna o caminho do arquivo."""
    pdf_bytes = generate_pdf_bytes(**kwargs)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)
    return output_path
