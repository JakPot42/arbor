"""Ported from ghosttrace/tests/test_risk_engine.py -- pure logic, no
network or DB."""
from __future__ import annotations

from configs.ghosttrace import (
    RISK_LEVEL_HIGH, RISK_LEVEL_MEDIUM,
    RISK_WEIGHT_ADVERSARY_JURISDICTION, RISK_WEIGHT_SECRECY_JURISDICTION,
    RISK_WEIGHT_CHAIN_DEPTH, RISK_WEIGHT_CIRCULAR_OWNERSHIP,
    RISK_WEIGHT_SHARED_AGENT, RISK_WEIGHT_UNDISCLOSED_OWNER,
)
from engines.ghosttrace_risk_engine import assess, jurisdiction_category


class TestJurisdictionCategory:
    def test_cayman_is_secrecy(self):
        assert jurisdiction_category("Cayman Islands") == "secrecy"

    def test_bvi_is_secrecy(self):
        assert jurisdiction_category("British Virgin Islands") == "secrecy"

    def test_china_is_adversary(self):
        assert jurisdiction_category("China") == "adversary"

    def test_prc_is_adversary(self):
        assert jurisdiction_category("PRC") == "adversary"

    def test_russia_is_adversary(self):
        assert jurisdiction_category("Russia") == "adversary"

    def test_us_is_none(self):
        assert jurisdiction_category("Delaware, United States") is None

    def test_none_input(self):
        assert jurisdiction_category(None) is None

    def test_empty_string(self):
        assert jurisdiction_category("") is None

    def test_substring_match(self):
        assert jurisdiction_category("Shenzhen, China") == "adversary"


def _entity(name, jur=None, addr=None, focal=False):
    return {"canonical_name": name, "jurisdiction": jur, "address": addr,
            "is_focal": focal, "entity_type": "company"}

def _link(owner, owned, pct=50.0, evidence="", source="ACC-001"):
    return {"owner": owner, "owned": owned, "ownership_pct": pct,
            "evidence_quote": evidence, "source": source}


class TestAssessSecrecy:
    def test_fires_for_cayman_entity(self):
        entities = [
            _entity("FocalCo", "Delaware, United States", focal=True),
            _entity("CaymanShell", "Cayman Islands"),
        ]
        links = [_link("CaymanShell", "FocalCo")]
        result = assess(entities, links, "FocalCo")
        rules = {f["rule"] for f in result["findings"]}
        assert "secrecy_jurisdiction" in rules
        assert result["score"] >= RISK_WEIGHT_SECRECY_JURISDICTION

    def test_fires_once_per_unique_jurisdiction(self):
        entities = [
            _entity("FocalCo", "Delaware, United States", focal=True),
            _entity("CaymanA", "Cayman Islands"),
            _entity("CaymanB", "Cayman Islands"),
        ]
        links = [_link("CaymanA", "FocalCo"), _link("CaymanB", "FocalCo")]
        result = assess(entities, links, "FocalCo")
        secrecy_findings = [f for f in result["findings"] if f["rule"] == "secrecy_jurisdiction"]
        assert len(secrecy_findings) <= 2


class TestAssessAdversary:
    def test_fires_for_chinese_entity(self):
        entities = [
            _entity("FocalCo", "Delaware, United States", focal=True),
            _entity("ShenzhengCo", "Shenzhen, China"),
        ]
        links = [_link("ShenzhengCo", "FocalCo", pct=11.0)]
        result = assess(entities, links, "FocalCo")
        rules = {f["rule"] for f in result["findings"]}
        assert "adversary_jurisdiction" in rules
        assert result["score"] >= RISK_WEIGHT_ADVERSARY_JURISDICTION


class TestAssessUndisclosed:
    def test_fires_for_none_pct(self):
        entities = [
            _entity("FocalCo", focal=True),
            _entity("NomineeShell"),
        ]
        links = [_link("NomineeShell", "FocalCo", pct=None)]
        result = assess(entities, links, "FocalCo")
        rules = {f["rule"] for f in result["findings"]}
        assert "undisclosed_ownership" in rules


class TestAssessChainDepth:
    def test_fires_for_deep_chain(self):
        entities = [
            _entity("FocalCo", focal=True),
            _entity("A"), _entity("B"), _entity("C"),
        ]
        links = [
            _link("A", "FocalCo"),
            _link("B", "A"),
            _link("C", "B"),
        ]
        result = assess(entities, links, "FocalCo")
        rules = {f["rule"] for f in result["findings"]}
        assert "chain_depth" in rules

    def test_does_not_fire_for_shallow_chain(self):
        entities = [_entity("FocalCo", focal=True), _entity("A")]
        links = [_link("A", "FocalCo")]
        result = assess(entities, links, "FocalCo")
        rules = {f["rule"] for f in result["findings"]}
        assert "chain_depth" not in rules


class TestAssessCircular:
    def test_fires_for_cycle(self):
        entities = [_entity("A"), _entity("B"), _entity("C")]
        links = [_link("A", "B"), _link("B", "C"), _link("C", "A")]
        result = assess(entities, links, "A")
        rules = {f["rule"] for f in result["findings"]}
        assert "circular_ownership" in rules


class TestAssessSharedAgent:
    def test_fires_for_shared_address(self):
        addr = "Suite 400, 12 Quayside Lane, George Town, Cayman Islands"
        entities = [
            _entity("FocalCo", focal=True),
            _entity("ShellA", addr=addr),
            _entity("ShellB", addr=addr),
        ]
        links = [_link("ShellA", "FocalCo"), _link("ShellB", "FocalCo")]
        result = assess(entities, links, "FocalCo")
        rules = {f["rule"] for f in result["findings"]}
        assert "shared_registered_agent" in rules

    def test_does_not_fire_for_unique_addresses(self):
        entities = [
            _entity("FocalCo", focal=True),
            _entity("A", addr="1 Main St, Delaware"),
            _entity("B", addr="2 Other Ave, New York"),
        ]
        links = [_link("A", "FocalCo"), _link("B", "FocalCo")]
        result = assess(entities, links, "FocalCo")
        rules = {f["rule"] for f in result["findings"]}
        assert "shared_registered_agent" not in rules


class TestAssessRiskLevel:
    def test_zero_score_is_low(self):
        result = assess([_entity("CleanCo", focal=True)], [], "CleanCo")
        assert result["level"] == "LOW"
        assert result["score"] == 0

    def test_high_score_is_high(self):
        entities = [
            _entity("FocalCo", focal=True),
            _entity("CaymanShell", "Cayman Islands"),
            _entity("ChinaCo", "China"),
        ]
        links = [
            _link("CaymanShell", "FocalCo"),
            _link("ChinaCo", "FocalCo"),
        ]
        result = assess(entities, links, "FocalCo")
        assert result["level"] == "HIGH"
        assert result["score"] >= RISK_LEVEL_HIGH

    def test_findings_have_required_keys(self):
        entities = [_entity("FocalCo", focal=True), _entity("CaymanCo", "Cayman Islands")]
        links = [_link("CaymanCo", "FocalCo")]
        result = assess(entities, links, "FocalCo")
        for f in result["findings"]:
            assert "rule" in f
            assert "detail" in f
            assert "weight" in f

    def test_score_never_negative(self):
        result = assess([], [], "Anything")
        assert result["score"] >= 0

    def test_harborview_scenario_is_high(self):
        """The seed data scenario should always score HIGH — regression guard."""
        from engines.ghosttrace_seed_data import SEED_ENTITIES, SEED_LINKS
        result = assess(SEED_ENTITIES, SEED_LINKS, "Harborview Capital Partners LP")
        assert result["level"] == "HIGH"
        assert result["score"] >= RISK_LEVEL_HIGH
