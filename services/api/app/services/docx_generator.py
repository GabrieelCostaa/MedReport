"""
Serviço de geração de DOCX para relatórios OPME.
Usa python-docx para gerar documento Word profissional.
"""
import os
import uuid
import logging
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

BLUE = RGBColor(0x1A, 0x4D, 0x8F)
DARK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x66, 0x66, 0x66)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x27, 0xAE, 0x60)


def _set_cell_shading(cell, color_hex: str):
    shading = cell._element.get_or_add_tcPr()
    shd = shading.makeelement(qn("w:shd"), {
        qn("w:fill"): color_hex,
        qn("w:val"): "clear",
    })
    shading.append(shd)


def _add_hyperlink(doc, paragraph, url, text):
    """Adds a clickable hyperlink to a paragraph in a docx document."""
    part = doc.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = paragraph._element.makeelement(qn("w:hyperlink"), {qn("r:id"): r_id})
    run_elem = paragraph._element.makeelement(qn("w:r"), {})
    rPr = run_elem.makeelement(qn("w:rPr"), {})
    rStyle = rPr.makeelement(qn("w:rStyle"), {qn("w:val"): "Hyperlink"})
    rPr.append(rStyle)
    color_elem = rPr.makeelement(qn("w:color"), {qn("w:val"): "1A4D8F"})
    rPr.append(color_elem)
    sz = rPr.makeelement(qn("w:sz"), {qn("w:val"): "16"})
    rPr.append(sz)
    run_elem.append(rPr)
    t_elem = run_elem.makeelement(qn("w:t"), {})
    t_elem.text = text
    run_elem.append(t_elem)
    hyperlink.append(run_elem)
    paragraph._element.append(hyperlink)


def _add_run(paragraph, text, bold=False, size=11, color=DARK, font_name="Calibri"):
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.name = font_name
    return run


def _split_paragraphs(text: str) -> list[str]:
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


def generate_docx_bytes(
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
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    style.font.color.rgb = DARK
    style.paragraph_format.space_after = Pt(4)
    style.paragraph_format.line_spacing = 1.15

    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.0)

    protocolo = f"OPME-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    # ── HEADER ──
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _add_run(p_title, "Relatório Médico Complementar", bold=True, size=16, color=BLUE)
    p_title.paragraph_format.space_after = Pt(2)

    p_sub = doc.add_paragraph()
    _add_run(p_sub, "Justificativa Técnica para Autorização de OPME", size=9, color=GRAY)
    p_sub.paragraph_format.space_after = Pt(2)

    p_proto = doc.add_paragraph()
    p_proto.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(p_proto, f"{datetime.now().strftime('%d/%m/%Y')}  |  Protocolo: {protocolo}", size=9, color=GRAY)
    p_proto.paragraph_format.space_after = Pt(8)

    # ── LINHA AZUL ──
    p_line = doc.add_paragraph()
    p_line.paragraph_format.space_after = Pt(12)
    border = p_line._element.get_or_add_pPr()
    pBdr = border.makeelement(qn("w:pBdr"), {})
    bottom = pBdr.makeelement(qn("w:bottom"), {
        qn("w:val"): "single",
        qn("w:sz"): "12",
        qn("w:color"): "1A4D8F",
        qn("w:space"): "1",
    })
    pBdr.append(bottom)
    border.append(pBdr)

    # ── META TABLE ──
    meta_items = [
        ("Paciente:", paciente_nome or "Não informado"),
        ("Convênio:", convenio or "Não informado"),
        ("Diagnóstico (CID):", f"{cid} — {diagnostico_resumo}"),
        ("Material OPME:", produto_nome),
    ]
    if especialidade:
        meta_items.append(("Especialidade:", especialidade))
    if codigo_tuss:
        meta_items.append(("Código TUSS:", codigo_tuss))

    rows_needed = (len(meta_items) + 1) // 2
    table = doc.add_table(rows=rows_needed, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, (label, value) in enumerate(meta_items):
        row_idx = i // 2
        col_offset = (i % 2) * 2
        cell_label = table.cell(row_idx, col_offset)
        cell_value = table.cell(row_idx, col_offset + 1)

        _set_cell_shading(cell_label, "F4F7FB")
        _set_cell_shading(cell_value, "F4F7FB")

        p_l = cell_label.paragraphs[0]
        _add_run(p_l, label, bold=True, size=10, color=BLUE)

        p_v = cell_value.paragraphs[0]
        _add_run(p_v, value, size=10, color=DARK)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # ── JUSTIFICATIVA ──
    paragraphs = _split_paragraphs(justificativa)

    section_map = {
        "Relatório Médico Complementar": True,
        "Quadro Clínico": True,
        "Falha Terapêutica": True,
        "Justificativa Técnica": True,
        "Superioridade do Material": True,
        "Risco da Não Realização": True,
        "Impacto Financeiro": True,
        "Fundamentação Legal": True,
        "Fechamento Checkmate": True,
        "Fechamento": True,
    }

    for para_text in paragraphs:
        is_section_header = False
        for key in section_map:
            if para_text.strip().lower().startswith(key.lower()) and len(para_text) < 80:
                is_section_header = True
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(12)
                p.paragraph_format.space_after = Pt(4)
                _add_run(p, para_text.upper(), bold=True, size=11, color=BLUE)
                break

        if not is_section_header:
            has_title = False
            if ":" in para_text[:80]:
                parts = para_text.split(":", 1)
                candidate = parts[0].strip()
                for key in section_map:
                    if key.lower() in candidate.lower():
                        has_title = True
                        p_heading = doc.add_paragraph()
                        p_heading.paragraph_format.space_before = Pt(12)
                        p_heading.paragraph_format.space_after = Pt(4)
                        _add_run(p_heading, candidate.upper(), bold=True, size=11, color=BLUE)

                        p_body = doc.add_paragraph()
                        p_body.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                        p_body.paragraph_format.space_after = Pt(6)
                        _add_run(p_body, parts[1].strip(), size=11)
                        break

            if not has_title:
                if "substituição deste material" in para_text.lower():
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p.paragraph_format.space_before = Pt(8)
                    p.paragraph_format.space_after = Pt(8)
                    _add_run(p, para_text, bold=True, size=10, color=RED)
                else:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    p.paragraph_format.space_after = Pt(6)
                    _add_run(p, para_text, size=11)

    # ── REFERÊNCIAS ──
    if referencias:
        p_ref_title = doc.add_paragraph()
        p_ref_title.paragraph_format.space_before = Pt(16)
        p_ref_title.paragraph_format.space_after = Pt(6)
        _add_run(p_ref_title, "REFERÊNCIAS BIBLIOGRÁFICAS", bold=True, size=10, color=BLUE)

        border_ref = p_ref_title._element.get_or_add_pPr()
        pBdr2 = border_ref.makeelement(qn("w:pBdr"), {})
        top2 = pBdr2.makeelement(qn("w:top"), {
            qn("w:val"): "single", qn("w:sz"): "4",
            qn("w:color"): "DDDDDD", qn("w:space"): "4",
        })
        pBdr2.append(top2)
        border_ref.append(pBdr2)

        for ref in referencias:
            p_ref = doc.add_paragraph()
            p_ref.paragraph_format.space_after = Pt(2)
            if isinstance(ref, dict):
                texto = ref.get("texto", str(ref))
                link = ref.get("link", "")
                _add_run(p_ref, f"■ {texto}", size=9, color=GRAY)
                if link:
                    _add_run(p_ref, f" ", size=9, color=GRAY)
                    _add_hyperlink(doc, p_ref, link, "[Verificar]")
            else:
                _add_run(p_ref, f"■ {ref}", size=9, color=GRAY)

    # ── CHECKLIST ──
    if checklist:
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
        p_ck_title = doc.add_paragraph()
        _add_run(p_ck_title, "CHECKLIST DE CONFORMIDADE", bold=True, size=10, color=BLUE)
        p_ck_title.paragraph_format.space_after = Pt(4)

        ck_table = doc.add_table(rows=len(checklist), cols=2)
        ck_table.alignment = WD_TABLE_ALIGNMENT.CENTER

        for i, (item, status) in enumerate(checklist.items()):
            cell_icon = ck_table.cell(i, 0)
            cell_name = ck_table.cell(i, 1)

            _set_cell_shading(cell_icon, "F0F8F0" if status else "FDF2F2")
            _set_cell_shading(cell_name, "F0F8F0" if status else "FDF2F2")

            p_icon = cell_icon.paragraphs[0]
            icon_color = GREEN if status else RED
            _add_run(p_icon, "✓" if status else "✗", bold=True, size=10, color=icon_color)

            p_name = cell_name.paragraphs[0]
            label = item.replace("_", " ").title()
            _add_run(p_name, label, size=10)

    # ── ASSINATURA ──
    doc.add_paragraph().paragraph_format.space_after = Pt(20)

    p_line2 = doc.add_paragraph()
    p_line2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(p_line2, "___________________________", size=11)

    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(p_name, medico_nome or "___________________________", bold=True, size=11)

    p_crm = doc.add_paragraph()
    p_crm.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(p_crm, medico_crm or "CRM: __________", size=9, color=GRAY)

    # ── WATERMARK (rascunho) ──
    if not aprovado:
        p_wm = doc.add_paragraph()
        p_wm.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p_wm, "\n\n[ RASCUNHO — PENDENTE DE APROVAÇÃO ]", bold=True, size=14, color=RGBColor(0xCC, 0xCC, 0xCC))

    import io
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def generate_docx_file(output_path: str, **kwargs) -> str:
    docx_bytes = generate_docx_bytes(**kwargs)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(docx_bytes)
    return output_path
