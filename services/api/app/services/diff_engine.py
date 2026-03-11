"""
Motor de diff estruturado para captura de edições médicas.
Usa difflib para gerar diffs word-level com contexto.
"""
import difflib
import re


def compute_structured_diff(original: str, edited: str) -> dict:
    """
    Compara texto original (IA) com editado (médico).
    Retorna diff estruturado com tipo de edição dominante.
    """
    orig_words = original.split()
    edit_words = edited.split()

    matcher = difflib.SequenceMatcher(None, orig_words, edit_words)

    additions = []
    removals = []
    replacements = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            additions.append({
                "position": i1,
                "words": edit_words[j1:j2],
                "context": _get_context(orig_words, i1),
            })
        elif tag == "delete":
            removals.append({
                "position": i1,
                "words": orig_words[i1:i2],
                "context": _get_context(orig_words, i1),
            })
        elif tag == "replace":
            replacements.append({
                "position": i1,
                "original": orig_words[i1:i2],
                "replacement": edit_words[j1:j2],
                "context": _get_context(orig_words, i1),
            })

    changes_count = len(additions) + len(removals) + len(replacements)
    edit_type = _classify_edit(additions, removals, replacements)

    unified = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        edited.splitlines(keepends=True),
        fromfile="ia_original",
        tofile="medico_editado",
        lineterm="",
    ))

    return {
        "diff": {
            "additions": additions,
            "removals": removals,
            "replacements": replacements,
            "unified": unified[:100],
        },
        "edit_type": edit_type,
        "changes_count": changes_count,
    }


def _get_context(words: list[str], position: int, window: int = 3) -> str:
    start = max(0, position - window)
    end = min(len(words), position + window)
    return " ".join(words[start:end])


def _classify_edit(additions, removals, replacements) -> str:
    """Classifica o tipo dominante de edição."""
    if not additions and not removals and not replacements:
        return "none"

    if replacements and not additions and not removals:
        total_orig = sum(len(r["original"]) for r in replacements)
        total_repl = sum(len(r["replacement"]) for r in replacements)
        if abs(total_orig - total_repl) <= 2:
            return "terminology"

    if additions and not removals and not replacements:
        return "addition"

    if removals and not additions and not replacements:
        return "removal"

    if replacements:
        return "terminology"

    return "structure"
