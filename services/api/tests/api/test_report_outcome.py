"""Loop de prova de valor: marcar desfecho + estatística de aprovação (score×resultado)."""
import uuid

import pytest
import pytest_asyncio

from app.db.models import Report, GlosaMotivo


@pytest_asyncio.fixture
async def signed_report(db, test_user):
    r = Report(
        id=uuid.uuid4(), user_id=test_user.id, status="signed",
        diagnosis="Gonartrose", especialidade="Ortopedia",
        health_plan="Unimed", approval_score=88.0,
    )
    db.add(r)
    db.add(GlosaMotivo(codigo="2001", descricao="MATERIAL INVÁLIDO"))
    await db.commit()
    return r


class TestMarkOutcome:
    async def test_mark_aprovado(self, client, auth_headers, signed_report):
        r = await client.patch(f"/api/reports/{signed_report.id}/outcome",
                               json={"outcome": "aprovado"}, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["outcome"] == "aprovado"
        assert body["outcome_at"] is not None

    async def test_mark_glosado_with_valid_motivo(self, client, auth_headers, signed_report):
        r = await client.patch(f"/api/reports/{signed_report.id}/outcome",
                               json={"outcome": "glosado", "motivo_codigo": "2001"}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["outcome_motivo_codigo"] == "2001"

    async def test_invalid_motivo_rejected(self, client, auth_headers, signed_report):
        r = await client.patch(f"/api/reports/{signed_report.id}/outcome",
                               json={"outcome": "glosado", "motivo_codigo": "9999"}, headers=auth_headers)
        assert r.status_code == 422

    async def test_invalid_outcome_rejected(self, client, auth_headers, signed_report):
        r = await client.patch(f"/api/reports/{signed_report.id}/outcome",
                               json={"outcome": "talvez"}, headers=auth_headers)
        assert r.status_code == 422

    async def test_requires_auth(self, client, signed_report):
        r = await client.patch(f"/api/reports/{signed_report.id}/outcome", json={"outcome": "aprovado"})
        assert r.status_code in (401, 403)

    async def test_other_users_report_404(self, client, auth_headers, db):
        other = Report(id=uuid.uuid4(), user_id=uuid.uuid4(), status="signed")
        db.add(other)
        await db.commit()
        r = await client.patch(f"/api/reports/{other.id}/outcome",
                               json={"outcome": "aprovado"}, headers=auth_headers)
        assert r.status_code == 404


class TestApprovalStats:
    async def test_calibration_score_vs_outcome(self, client, auth_headers, db, test_user):
        # 3 laudos score alto → aprovados; 2 score baixo → glosados; 1 pendente
        for _ in range(3):
            db.add(Report(id=uuid.uuid4(), user_id=test_user.id, status="signed",
                          approval_score=90.0, especialidade="Ortopedia",
                          health_plan="Unimed", outcome="aprovado"))
        for _ in range(2):
            db.add(Report(id=uuid.uuid4(), user_id=test_user.id, status="signed",
                          approval_score=30.0, health_plan="Bradesco", outcome="glosado"))
        db.add(Report(id=uuid.uuid4(), user_id=test_user.id, status="signed",
                      approval_score=85.0, outcome="pendente"))
        await db.commit()

        r = await client.get("/api/reports/stats/approval", headers=auth_headers)
        assert r.status_code == 200
        s = r.json()
        assert s["total"] == 6
        assert s["com_desfecho"] == 5
        assert s["pendentes"] == 1
        assert s["aprovados"] == 3 and s["glosados"] == 2
        assert s["taxa_aprovacao"] == 0.6
        # calibração: faixa alta 100%, faixa crítica 0% (o número que vende)
        bandas = {c["faixa"]: c["taxa"] for c in s["calibracao_score"]}
        assert bandas["alto (80-100)"] == 1.0
        assert bandas["critico (0-39)"] == 0.0

    async def test_empty_stats(self, client, auth_headers):
        s = (await client.get("/api/reports/stats/approval", headers=auth_headers)).json()
        assert s["total"] == 0 and s["taxa_aprovacao"] is None
