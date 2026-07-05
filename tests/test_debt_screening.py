"""Ported from debt_exposure_monitor/tests/test_screening.py --
orchestration, with the three checkers mocked so this test doesn't hit
the network."""
from __future__ import annotations

from unittest.mock import patch

import engines.debt_bis_checker as bis_checker
import engines.debt_foreign_state_lender_checker as foreign_state_lender_checker
import shared.ofac_checker as ofac_checker
from engines.debt_screening import screen_lenders


class _FakeOFACHit:
    def __init__(self, entity_name, sdn_name, score, sdn_program, sdn_type):
        self.entity_name, self.sdn_name, self.score = entity_name, sdn_name, score
        self.sdn_program, self.sdn_type = sdn_program, sdn_type


class _FakeBISHit:
    def __init__(self, entity_name, matched_name, score, source_list):
        self.entity_name, self.matched_name, self.score, self.source_list = entity_name, matched_name, score, source_list


class _FakeStateLenderHit:
    def __init__(self, entity_name, matched_name, score, country, basis, citation):
        self.entity_name, self.matched_name, self.score = entity_name, matched_name, score
        self.country, self.basis, self.citation = country, basis, citation


class TestScreenLenders:
    def test_combines_all_three_checkers(self):
        with patch.object(ofac_checker, "screen_entities", return_value=[_FakeOFACHit("VTB Bank", "VTB BANK", 100, "RUSSIA", "entity")]), \
             patch.object(bis_checker, "screen_entities", return_value=[_FakeBISHit("Huawei", "Huawei Technologies", 95, "Entity List (EL) - Bureau of Industry and Security")]), \
             patch.object(foreign_state_lender_checker, "screen_entities", return_value=[_FakeStateLenderHit("China Development Bank", "China Development Bank", 100, "China", "Policy bank", "cite")]):
            hits = screen_lenders(["VTB Bank", "Huawei", "China Development Bank"])
        list_names = {h.list_name for h in hits}
        assert list_names == {"OFAC SDN", "BIS Export Control List", "Foreign State-Connected Lender"}
        assert len(hits) == 3

    def test_no_hits_from_any_checker(self):
        with patch.object(ofac_checker, "screen_entities", return_value=[]), \
             patch.object(bis_checker, "screen_entities", return_value=[]), \
             patch.object(foreign_state_lender_checker, "screen_entities", return_value=[]):
            hits = screen_lenders(["JPMorgan Chase Bank, N.A."])
        assert hits == []

    def test_every_hit_carries_a_citation(self):
        with patch.object(ofac_checker, "screen_entities", return_value=[_FakeOFACHit("VTB Bank", "VTB BANK", 100, "RUSSIA", "entity")]), \
             patch.object(bis_checker, "screen_entities", return_value=[]), \
             patch.object(foreign_state_lender_checker, "screen_entities", return_value=[]):
            hits = screen_lenders(["VTB Bank"])
        assert all(h.citation for h in hits)
