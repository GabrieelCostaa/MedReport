"""
Checklist de saída obrigatório.
O relatório só é "Aprovado para PDF" se contiver todos os 6 itens.
"""

REQUIRED_SECTIONS = {
    "diagnostico": "Diagnóstico do paciente",
    "justificativa_tecnica": "Justificativa técnica com diferenciais do material",
    "falha_terapeutica": "Falha terapêutica prévia (tratamentos anteriores)",
    "risco_nao_realizacao": "Risco da não realização do procedimento",
    "base_legal_ans": "Base legal ANS (RN 395, 424, 428, 465)",
    "referencia_bibliografica": "Referência bibliográfica científica",
}


class ReportChecklist:
    """Avalia se um relatório está completo para gerar PDF."""

    @staticmethod
    def evaluate(report) -> dict:
        """Retorna status de cada item do checklist."""
        text = (report.justificativa_ia or "").lower()

        return {
            "diagnostico": {
                "ok": bool(report.diagnosis and len(report.diagnosis.strip()) > 5),
                "label": REQUIRED_SECTIONS["diagnostico"],
            },
            "justificativa_tecnica": {
                "ok": bool(report.justificativa_ia and len(report.justificativa_ia.strip()) > 100),
                "label": REQUIRED_SECTIONS["justificativa_tecnica"],
            },
            "falha_terapeutica": {
                "ok": bool(report.falha_terapeutica and len(report.falha_terapeutica.strip()) > 5),
                "label": REQUIRED_SECTIONS["falha_terapeutica"],
            },
            "risco_nao_realizacao": {
                "ok": bool(report.risco_nao_realizacao and len(report.risco_nao_realizacao.strip()) > 5),
                "label": REQUIRED_SECTIONS["risco_nao_realizacao"],
            },
            "base_legal_ans": {
                "ok": bool(report.base_legal_ans) or "rn 395" in text or "resolução" in text,
                "label": REQUIRED_SECTIONS["base_legal_ans"],
            },
            "referencia_bibliografica": {
                "ok": bool(report.referencias_bib and len(report.referencias_bib) > 0),
                "label": REQUIRED_SECTIONS["referencia_bibliografica"],
            },
        }

    @staticmethod
    def is_approved(report) -> bool:
        """Verifica se todos os 6 itens estão OK."""
        checklist = ReportChecklist.evaluate(report)
        return all(item["ok"] for item in checklist.values())

    @staticmethod
    def missing_items(report) -> list[str]:
        """Retorna lista de itens faltantes."""
        checklist = ReportChecklist.evaluate(report)
        return [
            item["label"]
            for key, item in checklist.items()
            if not item["ok"]
        ]
