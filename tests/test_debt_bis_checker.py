"""Ported from debt_exposure_monitor/tests/test_bis_checker.py -- no
real HTTP call, network mocked. Uses engines.debt_bis_checker's new
reset_cache() instead of poking the private _bis_entries attribute
directly."""
from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock, patch

import engines.debt_bis_checker as bis_checker

_CSL_HEADER = ["source", "name"]
_CSL_ROWS = [
    ["Entity List (EL) - Bureau of Industry and Security", "Huawei Technologies Co., Ltd."],
    ["Specially Designated Nationals (SDN) - Treasury Department", "AEROCARIBBEAN AIRLINES"],
    ["Unverified List (UVL) - Bureau of Industry and Security", "Some Unverified Co"],
]


def _fake_csv_bytes() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSL_HEADER)
    writer.writerows(_CSL_ROWS)
    return buf.getvalue().encode("utf-8")


class TestScreenEntities:
    def setup_method(self):
        bis_checker.reset_cache()

    def teardown_method(self):
        bis_checker.reset_cache()

    def _mock_urlopen(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = _fake_csv_bytes()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        return patch("engines.debt_bis_checker.urllib.request.urlopen", return_value=mock_resp)

    def test_bis_entity_list_match_found(self):
        with self._mock_urlopen():
            hits = bis_checker.screen_entities(["Huawei Technologies"])
        assert len(hits) >= 1
        assert hits[0].source_list == "Entity List (EL) - Bureau of Industry and Security"

    def test_treasury_row_excluded_even_with_name_match(self):
        with self._mock_urlopen():
            hits = bis_checker.screen_entities(["Aerocaribbean Airlines"])
        assert hits == []  # SDN row, not a BIS source -- must not appear here

    def test_no_match_for_unrelated_name(self):
        with self._mock_urlopen():
            hits = bis_checker.screen_entities(["JPMorgan Chase Bank, N.A."])
        assert hits == []

    def test_unverified_list_included(self):
        with self._mock_urlopen():
            hits = bis_checker.screen_entities(["Some Unverified Co"])
        assert any("Unverified" in h.source_list for h in hits)

    def test_download_failure_returns_empty_not_crash(self):
        with patch("engines.debt_bis_checker.urllib.request.urlopen", side_effect=Exception("network down")):
            hits = bis_checker.screen_entities(["Huawei Technologies"])
        assert hits == []
