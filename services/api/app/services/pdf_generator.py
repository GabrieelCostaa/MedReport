"""
Serviço de geração de PDF para relatórios OPME.
Usa Jinja2 + WeasyPrint para converter HTML template em PDF profissional.
"""
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


def generate_pdf_bytes(
    justificativa: str,
    paciente_nome: str,
    cid: str,
    diagnostico_resumo: str,
    produto_nome: str,
    convenio: str = "",
    especialidade: str = "",
    codigo_tuss: str = "",
    referencias: list[str] = None,
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
        referencias=referencias or [],
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
