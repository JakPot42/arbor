"""Ported from cfius_screener/tests/test_m2.py -- AI intake, memo, and
PDF routes. All Claude calls are mocked -- no test makes a network
request. Patch targets updated to where routers/cfius.py actually
imported these names (not main.py, and not the engines module directly
for the route-level patches, since `from X import Y` binds a new name in
the importing module's namespace)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from database import SessionLocal
from engines.jurisdiction_engine import TransactionFacts
from engines.cfius_screening_service import run_and_store
from main import app
from models.cfius import Screening
from fastapi.testclient import TestClient


def _fake_parse_result(**overrides) -> dict:
    base = {
        "us_business_name": "Apex Photonics Inc",
        "us_business_description": "Makes laser rangefinders.",
        "acquirer_name": "Shenzhen Capital Group",
        "acquirer_country": "China",
        "foreign_govt_ownership_pct": 55.0,
        "voting_interest_pct": 30.0,
        "contractual_control_rights": False,
        "board_seat": True,
        "board_observer": False,
        "access_nonpublic_tech_info": True,
        "substantive_decision_role": False,
        "produces_critical_tech": True,
        "export_authorization_required": True,
        "critical_infrastructure": False,
        "sensitive_personal_data": False,
        "confidence_notes": "High confidence on acquirer country and stake size.",
    }
    base.update(overrides)
    return base


FAKE_MEMO = "This is a mock memorandum paragraph one.\n\nParagraph two."


# ---------------------------------------------------------------------------
# engines.cfius_claude_intake module
# ---------------------------------------------------------------------------

def test_parse_deal_description_success():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text='{"us_business_name":"X","us_business_description":"","acquirer_name":"Y","acquirer_country":"China","foreign_govt_ownership_pct":0.0,"voting_interest_pct":10.0,"contractual_control_rights":false,"board_seat":false,"board_observer":false,"access_nonpublic_tech_info":false,"substantive_decision_role":false,"produces_critical_tech":false,"export_authorization_required":false,"critical_infrastructure":false,"sensitive_personal_data":false,"confidence_notes":"OK"}')]

    with patch("engines.cfius_claude_intake.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = fake_response
        with patch("engines.cfius_claude_intake.ANTHROPIC_API_KEY", "sk-test"):
            from engines.cfius_claude_intake import parse_deal_description
            result = parse_deal_description("Some deal description.")

    assert result["us_business_name"] == "X"
    assert result["acquirer_country"] == "China"
    assert "confidence_notes" in result


def test_parse_deal_description_no_api_key():
    from engines.cfius_claude_intake import IntakeError, parse_deal_description
    with patch("engines.cfius_claude_intake.ANTHROPIC_API_KEY", ""):
        with pytest.raises(IntakeError, match="ANTHROPIC_API_KEY"):
            parse_deal_description("deal")


def test_parse_deal_description_bad_json():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="not json at all")]

    with patch("engines.cfius_claude_intake.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = fake_response
        with patch("engines.cfius_claude_intake.ANTHROPIC_API_KEY", "sk-test"):
            from engines.cfius_claude_intake import IntakeError, parse_deal_description
            with pytest.raises(IntakeError, match="non-JSON"):
                parse_deal_description("deal")


def test_parse_deal_description_api_error():
    with patch("engines.cfius_claude_intake.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = Exception("network error")
        with patch("engines.cfius_claude_intake.ANTHROPIC_API_KEY", "sk-test"):
            from engines.cfius_claude_intake import IntakeError, parse_deal_description
            with pytest.raises(IntakeError, match="Claude API error"):
                parse_deal_description("deal")


# ---------------------------------------------------------------------------
# engines.cfius_claude_memo module
# ---------------------------------------------------------------------------

def test_draft_memo_success():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="MemoTest Corp",
            acquirer_name="Foreign Buyer",
            acquirer_country="Russia",
            voting_interest_pct=60.0,
        ))
        fake_response = MagicMock()
        fake_response.content = [MagicMock(text=FAKE_MEMO)]

        with patch("engines.cfius_claude_memo.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = fake_response
            with patch("engines.cfius_claude_memo.ANTHROPIC_API_KEY", "sk-test"):
                from engines.cfius_claude_memo import draft_memo
                result = draft_memo(row)

        assert result == FAKE_MEMO
    finally:
        db.close()


def test_draft_memo_no_api_key():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="NokeyTest",
            acquirer_name="Buyer",
            acquirer_country="Germany",
            voting_interest_pct=10.0,
        ))
        with patch("engines.cfius_claude_memo.ANTHROPIC_API_KEY", ""):
            from engines.cfius_claude_memo import MemoError, draft_memo
            with pytest.raises(MemoError, match="ANTHROPIC_API_KEY"):
                draft_memo(row)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Web routes — now under /cfius
# ---------------------------------------------------------------------------

def test_intake_form_renders():
    with TestClient(app) as client:
        assert client.get("/cfius/intake").status_code == 200


def test_intake_post_calls_claude_and_shows_confirm():
    with patch("routers.cfius.parse_deal_description", return_value=_fake_parse_result()) as mock_parse:
        with TestClient(app) as client:
            resp = client.post("/cfius/intake", data={
                "description": "Apex Photonics being acquired by Shenzhen Capital for 30%."
            })
        assert resp.status_code == 200
        assert "Review Claude" in resp.text
        assert "Apex Photonics Inc" in resp.text
        assert "High confidence" in resp.text
        mock_parse.assert_called_once()


def test_intake_post_claude_error_rerenders_form():
    from engines.cfius_claude_intake import IntakeError
    with patch("routers.cfius.parse_deal_description", side_effect=IntakeError("API down")):
        with TestClient(app) as client:
            resp = client.post("/cfius/intake", data={"description": "some deal"})
    assert resp.status_code == 200
    assert "API down" in resp.text


def test_intake_confirm_runs_engine_and_redirects():
    with TestClient(app) as client:
        resp = client.post("/cfius/intake/confirm", data={
            "intake_description": "Apex being acquired by China firm for 30%.",
            "us_business_name": "Apex Photonics Inc",
            "us_business_description": "Makes laser rangefinders.",
            "acquirer_name": "Shenzhen Capital Group",
            "acquirer_country": "China",
            "foreign_govt_ownership_pct": "55",
            "voting_interest_pct": "30",
            "board_seat": "on",
            "produces_critical_tech": "on",
            "export_authorization_required": "on",
        }, follow_redirects=False)
    assert resp.status_code == 303
    assert "/cfius/screening/" in resp.headers["location"]


def test_intake_confirm_stores_intake_description():
    with TestClient(app) as client:
        resp = client.post("/cfius/intake/confirm", data={
            "intake_description": "Original plain-English description here.",
            "us_business_name": "StorageTest LLC",
            "us_business_description": "",
            "acquirer_name": "Foreign Co",
            "acquirer_country": "France",
            "foreign_govt_ownership_pct": "0",
            "voting_interest_pct": "10",
        }, follow_redirects=False)
        screening_id = int(resp.headers["location"].split("/")[-1])

    db = SessionLocal()
    try:
        row = db.get(Screening, screening_id)
        assert row.intake_description == "Original plain-English description here."
    finally:
        db.close()


def test_generate_memo_stores_and_redirects():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="MemoRoute Corp",
            acquirer_name="Buyer Ltd",
            acquirer_country="China",
            voting_interest_pct=60.0,
        ))
        sid = row.id
    finally:
        db.close()

    with patch("routers.cfius.draft_memo", return_value=FAKE_MEMO):
        with TestClient(app) as client:
            resp = client.post(f"/cfius/screening/{sid}/memo", follow_redirects=False)

    assert resp.status_code == 303

    db = SessionLocal()
    try:
        row = db.get(Screening, sid)
        assert row.memo_text == FAKE_MEMO
    finally:
        db.close()


def test_generate_memo_claude_failure_redirects_with_error():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="FailMemo Inc",
            acquirer_name="Buyer",
            acquirer_country="China",
            voting_interest_pct=60.0,
        ))
        sid = row.id
    finally:
        db.close()

    from engines.cfius_claude_memo import MemoError
    with patch("routers.cfius.draft_memo", side_effect=MemoError("API down")):
        with TestClient(app) as client:
            resp = client.post(f"/cfius/screening/{sid}/memo", follow_redirects=False)

    assert resp.status_code == 303
    assert "memo_error=1" in resp.headers["location"]


def test_memo_pdf_returns_pdf():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="PDFTest Corp",
            acquirer_name="Buyer Ltd",
            acquirer_country="China",
            voting_interest_pct=60.0,
        ))
        row.memo_text = FAKE_MEMO
        db.commit()
        sid = row.id
    finally:
        db.close()

    with TestClient(app) as client:
        resp = client.get(f"/cfius/screening/{sid}/memo.pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_memo_pdf_404_when_no_memo():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="NoMemo Corp",
            acquirer_name="Buyer",
            acquirer_country="Germany",
            voting_interest_pct=10.0,
        ))
        sid = row.id
    finally:
        db.close()

    with TestClient(app) as client:
        resp = client.get(f"/cfius/screening/{sid}/memo.pdf")

    assert resp.status_code == 404


def test_result_page_shows_memo_when_present():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="MemoDisplay Corp",
            acquirer_name="Buyer",
            acquirer_country="China",
            voting_interest_pct=60.0,
        ))
        row.memo_text = FAKE_MEMO
        db.commit()
        sid = row.id
    finally:
        db.close()

    with TestClient(app) as client:
        resp = client.get(f"/cfius/screening/{sid}")

    assert resp.status_code == 200
    assert "mock memorandum" in resp.text
    assert "Download PDF" in resp.text


def test_result_page_shows_generate_button_when_no_memo():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="NoMemoYet Corp",
            acquirer_name="Buyer",
            acquirer_country="Germany",
            voting_interest_pct=10.0,
        ))
        sid = row.id
    finally:
        db.close()

    with TestClient(app) as client:
        resp = client.get(f"/cfius/screening/{sid}")

    assert resp.status_code == 200
    assert "Generate memo" in resp.text
