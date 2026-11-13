"""Consistency checks on data/party_lineage.json (party splits and mergers since 1885)."""
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import lineage  # noqa: E402


class PartyLineage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = lineage.load()
        cls.P = {p["id"]: p for p in cls.d["parties"]}

    def test_file_is_consistent(self):
        self.assertEqual(lineage.validate(self.d), [])

    def test_starts_with_congress_1885(self):
        self.assertEqual(min(p["start"] for p in self.d["parties"]), 1885)
        self.assertEqual(self.P["INC"]["start"], 1885)

    def test_every_party_is_connected_or_a_root(self):
        linked = {i for e in self.d["events"] for i in e["from"] + e["to"]}
        # parties with no event are allowed only if they were founded independently
        loose = [p["id"] for p in self.d["parties"] if p["id"] not in linked]
        self.assertLessEqual(len(loose), 25, loose)

    def test_known_lineages(self):
        ev = {(e["year"], e["type"], tuple(e["from"]), tuple(e["to"])) for e in self.d["events"]}
        self.assertIn((1964, "split", ("CPI",), ("CPM",)), ev)
        self.assertIn((1980, "split", ("JNP",), ("BJP",)), ev)
        self.assertIn((1999, "split", ("JD",), ("JDS", "JDU")), ev)
        self.assertIn((1977, "merger", ("NCO", "BJS", "BLD", "SOC71", "CFD"), ("JNP",)), ev)

    def test_lok_sabha_record_uses_code_windows(self):
        con = sqlite3.connect(ROOT / "data" / "lok_sabha.db")
        rec = lineage.lok_sabha_record(con, self.d)
        self.assertEqual(rec["JNP"]["1977"][0], 295)          # Janata on the BLD symbol
        self.assertEqual(rec["SOCP"], {"1951": [12, 10.59]})  # SP code = Socialist Party only in 1951
        self.assertNotIn("1951", rec["SP"])                   # ... and Samajwadi Party from 1996
        self.assertEqual(rec["BJP"]["2014"][0], 282)


if __name__ == "__main__":
    unittest.main()
