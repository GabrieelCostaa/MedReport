"""
Simulação realista: Médico usando a API do Hugo para gerar relatórios OPME.

Simula o fluxo completo via HTTP API como se fosse o frontend:
1. Login
2. Listar produtos
3. Para cada cenário: start-report → answer questions → receber relatório
4. Salvar relatórios para análise

Uso: cd services/api && python3 scripts/simulate_doctor.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = os.getenv("API_URL", "http://localhost:8000")
OUTPUT_DIR = Path("scripts/test_output_doctor_sim")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Cenários realistas: mínimo de input do médico (como na vida real)
# ============================================================================

SCENARIOS = [
    # --- ORTOPEDIA ---
    {
        "id": "01_viscossuplementacao_joelho",
        "descricao": "Viscossuplementação — Gonartrose grau III",
        "product_keyword": "Kit EC2 - Linha Opus",
        "paciente_nome": "José Ricardo Mendes",
        "cid": "M17.1",
        "diagnostico": "Gonartrose primária unilateral joelho D, grau III KL, dor crônica 2 anos",
        "especialidade": "Ortopedia",
        "health_plan": "Unimed",
        # Médico NÃO preenche falha terapêutica nem risco (pipeline deve perguntar)
    },
    {
        "id": "02_parafuso_lca",
        "descricao": "Parafuso bioabsorvível — Reconstrução de LCA",
        "product_keyword": "Parafuso de Interferência Bioabsorvível",
        "paciente_nome": "Lucas Andrade Ferreira",
        "cid": "S83.5",
        "diagnostico": "Ruptura de LCA joelho esquerdo, instabilidade anterior grau III, RM confirmando lesão completa",
        "especialidade": "Ortopedia",
        "health_plan": "Bradesco Saúde",
    },
    {
        "id": "03_biossilex_osteomielite",
        "descricao": "Biossilex — Defeito ósseo pós-osteomielite",
        "product_keyword": "Biossilex",
        "paciente_nome": "Antonio Carlos da Silva",
        "cid": "M86.6",
        "diagnostico": "Osteomielite crônica de tíbia proximal com defeito ósseo segmentar após 2 desbridamentos",
        "especialidade": "Ortopedia",
        "health_plan": "Cassi",
    },
    {
        "id": "04_vitagraft_pseudoartrose",
        "descricao": "Vitagraft — Pseudoartrose de úmero",
        "product_keyword": "Vitagraft",
        "paciente_nome": "Maria Helena Souza",
        "cid": "M84.1",
        "diagnostico": "Pseudoartrose de diáfise de úmero D, 9 meses sem consolidação pós-fratura",
        "especialidade": "Ortopedia",
        "health_plan": "SulAmérica",
    },
    # --- CIRURGIA GERAL ---
    {
        "id": "05_tela_hernia_incisional",
        "descricao": "Tela — Hérnia incisional recidivada",
        "product_keyword": "Tela de Polipropileno",
        "paciente_nome": "Francisco Oliveira Neto",
        "cid": "K43.1",
        "diagnostico": "Hérnia incisional recidivada, defeito de 8cm, 2a recidiva após reparo primário",
        "especialidade": "Cirurgia Geral",
        "health_plan": "Amil",
    },
    {
        "id": "06_adhesion_lise_aderencias",
        "descricao": "Adhesion STP+ — Lise de aderências abdominais",
        "product_keyword": "Adhesion STP+",
        "paciente_nome": "Claudia Regina Santos",
        "cid": "K66.0",
        "diagnostico": "Aderências peritoneais pós-operatórias com suboclusão intestinal recorrente, 3 episódios em 6 meses",
        "especialidade": "Cirurgia Geral",
        "health_plan": "Porto Seguro",
    },
    # --- UROLOGIA ---
    {
        "id": "07_enxerto_peyronie",
        "descricao": "Enxerto Composto — Doença de Peyronie (fora do Rol)",
        "product_keyword": "Kit EC2 - Enxerto Composto",
        "paciente_nome": "Roberto Augusto Lima",
        "cid": "N48.6",
        "diagnostico": "Doença de Peyronie com curvatura peniana >60 graus, placa estável, disfunção erétil",
        "especialidade": "Urologia",
        "health_plan": "Unimed",
    },
    # --- ORL ---
    {
        "id": "08_laser_turbinectomia",
        "descricao": "Laser — Turbinoplastia por hipertrofia de cornetos",
        "product_keyword": "Kit FO - Laser Cirúrgico",
        "paciente_nome": "Fernanda Costa Ribeiro",
        "cid": "J34.3",
        "diagnostico": "Hipertrofia de cornetos inferiores bilateral, obstrução nasal crônica refratária a tratamento clínico 10 meses",
        "especialidade": "Otorrinolaringologia",
        "health_plan": "Bradesco Saúde",
    },
]

# Respostas que o médico daria para as perguntas do pipeline
# (mínimo esforço — seleciona a primeira opção ou dá resposta curta)
DEFAULT_ANSWERS = {
    "falha_terapeutica": "Tratamento conservador por mais de 6 meses sem melhora significativa",
    "risco_nao_realizacao": "Progressão da doença com piora funcional e necessidade de procedimento de maior porte",
    "surgery_description": "Procedimento cirúrgico programado conforme indicação",
}


async def login(client: httpx.AsyncClient) -> str:
    """Login e retorna token."""
    resp = await client.post(
        f"{BASE_URL}/auth/token",
        data={"username": "medico@opme.com", "password": "senha123"},
    )
    if resp.status_code != 200:
        print(f"  ERRO login: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()["access_token"]


async def list_products(client: httpx.AsyncClient, headers: dict) -> list:
    """Lista produtos disponíveis."""
    resp = await client.get(f"{BASE_URL}/api/products", headers=headers)
    resp.raise_for_status()
    return resp.json().get("items", resp.json()) if isinstance(resp.json(), dict) else resp.json()


async def find_product(products: list, keyword: str) -> dict | None:
    """Busca produto por keyword no nome."""
    for p in products:
        if keyword.lower() in p["nome"].lower():
            return p
    return None


async def start_report(client: httpx.AsyncClient, headers: dict, product: dict, scenario: dict) -> dict:
    """Inicia geração de relatório."""
    payload = {
        "product_id": product["id"],
        "paciente_nome": scenario["paciente_nome"],
        "cid": scenario["cid"],
        "diagnostico": scenario["diagnostico"],
        "especialidade": scenario.get("especialidade", ""),
        "health_plan": scenario.get("health_plan", ""),
    }
    resp = await client.post(
        f"{BASE_URL}/api/ai/start-report",
        json=payload,
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


async def answer_questions(client: httpx.AsyncClient, headers: dict, session_id: str, questions: list) -> dict:
    """Responde perguntas do pipeline (simula médico escolhendo opções)."""
    answers = {}
    for q in questions:
        secao = q["secao"]
        opcoes = q.get("opcoes", [])
        if secao in DEFAULT_ANSWERS:
            answers[secao] = DEFAULT_ANSWERS[secao]
        elif opcoes:
            # Médico seleciona a primeira opção (mínimo esforço)
            opt = opcoes[0]
            answers[secao] = opt["texto"] if isinstance(opt, dict) else str(opt)
        else:
            answers[secao] = "Conforme avaliação clínica"

    resp = await client.post(
        f"{BASE_URL}/api/ai/answer",
        json={"session_id": session_id, "answers": answers},
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def analyze_report(result: dict, scenario: dict) -> list[str]:
    """Analisa criticamente o relatório gerado, buscando problemas."""
    issues = []
    text = result.get("justificativa", "")
    text_lower = text.lower()

    # 1. Verificação básica
    if not text or len(text) < 200:
        issues.append("CRÍTICO: Relatório muito curto ou vazio")

    word_count = len(text.split())
    if word_count < 150:
        issues.append(f"ALERTA: Apenas {word_count} palavras (mínimo esperado: ~200)")
    if word_count > 500:
        issues.append(f"ALERTA: {word_count} palavras — pode estar prolixo")

    # 2. Checklist
    checklist = result.get("checklist", {})
    missing = [k for k, v in checklist.items() if not v]
    if missing:
        issues.append(f"CRÍTICO: Checklist incompleto — faltam: {', '.join(missing)}")

    # 3. Dados do paciente devem estar presentes
    paciente = scenario["paciente_nome"].split()[0].lower()
    if paciente not in text_lower:
        issues.append(f"ALERTA: Nome do paciente '{scenario['paciente_nome']}' não aparece no texto")

    cid = scenario["cid"]
    if cid.lower() not in text_lower:
        issues.append(f"ALERTA: CID {cid} não mencionado no texto")

    # 4. RNs não devem estar no corpo (Bug 5 fix)
    import re
    rn_matches = re.findall(r'\bRN\s*\d{3}\b', text, re.IGNORECASE)
    if rn_matches:
        issues.append(f"ALERTA: RNs encontradas no corpo da justificativa: {rn_matches} (devem ficar na base_legal)")

    # 5. Base legal deve existir separadamente
    base_legal = result.get("base_legal", "")
    if not base_legal or len(base_legal) < 20:
        issues.append("ALERTA: Campo base_legal ausente ou muito curto")

    # 6. Referências devem existir e ter fontes verificáveis
    refs = result.get("referencias", [])
    if not refs:
        issues.append("CRÍTICO: Nenhuma referência bibliográfica")
    else:
        internal_only = all(r.get("source") == "internal" for r in refs)
        if internal_only and len(refs) < 2:
            issues.append("ALERTA: Apenas referências internas — sem PubMed")
        for ref in refs:
            ref_text = ref.get("texto", "") if isinstance(ref, dict) else str(ref)
            # Valid formats: "Author et al., Year", "Author, Year", "Author (Year)", "Author and Author, Year"
            import re as _re
            has_author_year = bool(_re.search(r"[A-Za-z]+.*\d{4}", ref_text))
            if not has_author_year:
                issues.append(f"ALERTA: Referência com formato duvidoso: {ref_text[:60]}")

    # 7. Detecção de possíveis alucinações
    hallucination_markers = [
        "100%", "garantia de", "cura definitiva", "elimina completamente",
        "aprovado pela FDA", "gold standard mundial", "único produto",
    ]
    for marker in hallucination_markers:
        if marker.lower() in text_lower:
            issues.append(f"POSSÍVEL ALUCINAÇÃO: '{marker}' encontrado no texto")

    # 8. Valores numéricos inventados (percentuais precisos sem evidência)
    precise_pct = re.findall(r'\b(\d{2,3})[,.]?\d*\s*%', text)
    for pct in precise_pct:
        val = int(pct)
        if val > 50 and val not in (93, 95, 100):  # 93% é de Diamond 1996, valores comuns
            issues.append(f"VERIFICAR: Percentual {val}% no texto — confirmar se tem evidência")

    # 9. Custos inventados
    cost_matches = re.findall(r'R\$\s*[\d.]+', text)
    if cost_matches:
        issues.append(f"VERIFICAR: Valores monetários no texto: {cost_matches} — confirmar se são reais")

    # 10. Audit log
    audit_log = result.get("audit_log", [])
    corrections = [a for a in audit_log if a.get("tipo") == "correcao"]
    removals = [a for a in audit_log if a.get("tipo") == "remocao"]
    hard_vals = [a for a in audit_log if a.get("tipo") == "hard_validation"]
    if hard_vals:
        for hv in hard_vals:
            issues.append(f"CORREÇÃO HARD: {hv.get('campo')}: {hv.get('motivo')}")
    if removals:
        for rm in removals:
            issues.append(f"DADO REMOVIDO PELO AUDITOR: {rm.get('campo')}: {rm.get('motivo')}")

    # 11. Compliance
    score = result.get("approval_score", 0)
    if score < 60:
        issues.append(f"CRÍTICO: Score de compliance baixo ({score}/100)")
    elif score < 75:
        issues.append(f"ALERTA: Score de compliance médio ({score}/100)")

    mode = result.get("compliance_mode", "")
    gaps = result.get("approval_gaps", [])
    if gaps:
        for g in gaps:
            issues.append(f"GAP: {g}")

    # 12. Motivos de bloqueio
    bloqueio = result.get("motivo_bloqueio")
    if bloqueio:
        for m in bloqueio:
            issues.append(f"BLOQUEIO: {m}")

    return issues


def format_report_output(scenario: dict, result: dict, issues: list, elapsed: float) -> str:
    """Formata output legível do relatório + análise."""
    lines = []
    sep = "=" * 80

    lines.append(sep)
    lines.append(f"CENÁRIO: {scenario['descricao']}")
    lines.append(sep)
    lines.append(f"ID: {scenario['id']}")
    lines.append(f"PRODUTO: {scenario['product_keyword']}")
    lines.append(f"PACIENTE: {scenario['paciente_nome']}")
    lines.append(f"CID: {scenario['cid']}")
    lines.append(f"DIAGNÓSTICO: {scenario['diagnostico']}")
    lines.append(f"CONVÊNIO: {scenario.get('health_plan', 'N/A')}")
    lines.append(f"ESPECIALIDADE: {scenario.get('especialidade', 'N/A')}")
    lines.append("")

    # Resultado
    aprovado = result.get("aprovado", False)
    checklist = result.get("checklist", {})
    ck_count = sum(1 for v in checklist.values() if v)
    ck_total = len(checklist)
    word_count = len((result.get("justificativa", "")).split())
    score = result.get("approval_score", 0)
    nivel = result.get("approval_nivel", "?")
    mode = result.get("compliance_mode", "?")

    lines.append("--- RESULTADOS ---")
    lines.append(f"APROVADO: {aprovado}")
    lines.append(f"CHECKLIST: {ck_count}/{ck_total}")
    lines.append(f"PALAVRAS: {word_count}")
    lines.append(f"SCORE: {score}/100 ({nivel})")
    lines.append(f"MODO: {mode}")
    lines.append(f"TEMPO: {elapsed:.1f}s")

    # Score components breakdown
    componentes = result.get("approval_componentes", {})
    if componentes:
        lines.append(f"COMPONENTES: DUT={componentes.get('aderencia_dut', '?')}/40 | "
                      f"TUSS/TISS={componentes.get('completude_tiss_tuss', '?')}/30 | "
                      f"Justificativa={componentes.get('qualidade_justificativa', '?')}/20 | "
                      f"Evidência={componentes.get('robustez_evidencia', '?')}/10")
    gaps = result.get("approval_gaps", [])
    if gaps:
        lines.append(f"GAPS: {'; '.join(gaps)}")
    lines.append("")

    # Relatório gerado
    lines.append("--- RELATÓRIO GERADO ---")
    lines.append(result.get("justificativa", "(vazio)"))
    lines.append("")

    # Base legal
    base_legal = result.get("base_legal", "")
    if base_legal:
        lines.append("--- BASE LEGAL ---")
        lines.append(base_legal)
        lines.append("")

    # Referências
    refs = result.get("referencias", [])
    if refs:
        lines.append("--- REFERÊNCIAS ---")
        for i, ref in enumerate(refs, 1):
            if isinstance(ref, dict):
                txt = ref.get("texto", "")
                src = ref.get("source", "?")
                link = ref.get("link", "")
                lines.append(f"  {i}. {txt} [{src}]" + (f" — {link}" if link else ""))
            else:
                lines.append(f"  {i}. {ref}")
        lines.append("")

    # Audit log
    audit_log = result.get("audit_log", [])
    if audit_log:
        lines.append("--- AUDIT LOG ---")
        for a in audit_log:
            lines.append(f"  [{a.get('tipo')}] {a.get('campo')}: {a.get('motivo')}")
        lines.append("")

    # Análise crítica
    lines.append("--- ANÁLISE CRÍTICA ---")
    if not issues:
        lines.append("  ✓ Nenhum problema detectado")
    else:
        for issue in issues:
            prefix = "✗" if "CRÍTICO" in issue else "⚠" if "ALERTA" in issue else "?"
            lines.append(f"  {prefix} {issue}")
    lines.append("")

    return "\n".join(lines)


async def run_simulation():
    """Executa simulação completa."""
    print(f"\n{'='*80}")
    print("  SIMULAÇÃO: MÉDICO USANDO API DO HUGO")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    async with httpx.AsyncClient(timeout=180) as client:
        # 1. Login
        print("[1] Fazendo login como medico@opme.com...")
        token = await login(client)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"    Token obtido: {token[:20]}...\n")

        # 2. Listar produtos
        print("[2] Listando produtos disponíveis...")
        products = await list_products(client, headers)
        print(f"    {len(products)} produtos encontrados:")
        for p in products:
            print(f"      - {p['nome']} (TUSS: {p.get('codigo_tuss_sugerido', 'N/A')})")
        print()

        # 3. Gerar relatórios
        all_results = []
        total_issues = 0

        for i, scenario in enumerate(SCENARIOS, 1):
            print(f"[{i}/{len(SCENARIOS)}] {scenario['descricao']}")
            print(f"    Paciente: {scenario['paciente_nome']} | CID: {scenario['cid']}")

            product = await find_product(products, scenario["product_keyword"])
            if not product:
                print(f"    ✗ ERRO: Produto '{scenario['product_keyword']}' não encontrado\n")
                continue

            print(f"    Produto: {product['nome']} (ID: {product['id'][:8]}...)")

            t0 = time.time()

            # Start report
            try:
                result = await start_report(client, headers, product, scenario)
            except Exception as e:
                print(f"    ✗ ERRO ao iniciar: {e}\n")
                continue

            # Answer questions if needed
            rounds = 0
            while result.get("step") == "questions":
                questions = result.get("questions", [])
                q_labels = [q["secao"] for q in questions]
                print(f"    Pipeline pergunta: {q_labels}")

                try:
                    result = await answer_questions(
                        client, headers, result["session_id"], questions
                    )
                except Exception as e:
                    print(f"    ✗ ERRO ao responder: {e}")
                    break
                rounds += 1
                if rounds > 5:
                    print("    ✗ ERRO: Loop infinito de perguntas")
                    break

            elapsed = time.time() - t0

            if result.get("step") != "done":
                print(f"    ✗ Pipeline não completou: step={result.get('step')}\n")
                continue

            # Analyze
            issues = analyze_report(result, scenario)
            total_issues += len(issues)

            ck = result.get("checklist", {})
            ck_ok = sum(1 for v in ck.values() if v)
            score = result.get("approval_score", 0)
            mode = result.get("compliance_mode", "?")
            word_count = len((result.get("justificativa", "")).split())
            issue_str = f" | {len(issues)} problema(s)" if issues else ""

            print(f"    ✓ OK | {word_count} palavras | checklist {ck_ok}/{len(ck)} | "
                  f"score {score}/100 | {mode} | {elapsed:.1f}s{issue_str}")

            # Save output
            output = format_report_output(scenario, result, issues, elapsed)
            out_file = OUTPUT_DIR / f"{scenario['id']}.txt"
            out_file.write_text(output, encoding="utf-8")
            print(f"    Salvo: {out_file}")
            print()

            all_results.append({
                "id": scenario["id"],
                "descricao": scenario["descricao"],
                "product": product["nome"],
                "aprovado": result.get("aprovado"),
                "checklist_ok": ck_ok,
                "checklist_total": len(ck),
                "word_count": word_count,
                "score": score,
                "nivel": result.get("approval_nivel", "?"),
                "mode": mode,
                "issues_count": len(issues),
                "issues": issues,
                "elapsed": round(elapsed, 1),
            })

        # 4. Resumo final
        print(f"\n{'='*80}")
        print("  RESUMO DA SIMULAÇÃO")
        print(f"{'='*80}\n")

        for r in all_results:
            icon = "✓" if not r["issues"] else "⚠" if r["issues_count"] <= 2 else "✗"
            print(f"  {icon} {r['id']}: score {r['score']}/100 ({r['mode']}) | "
                  f"{r['issues_count']} problema(s) | {r['elapsed']}s")
            for issue in r["issues"]:
                print(f"      → {issue}")

        print(f"\n  Total: {len(all_results)} relatórios | "
              f"{sum(1 for r in all_results if not r['issues'])} sem problemas | "
              f"{total_issues} problemas encontrados")

        # Save summary JSON
        summary_file = OUTPUT_DIR / "resumo_simulacao.json"
        summary_file.write_text(
            json.dumps(all_results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Resumo JSON: {summary_file}")
        print(f"  Outputs em: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    asyncio.run(run_simulation())
