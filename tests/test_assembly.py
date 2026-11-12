"""Integrity checks on the State Legislative Assembly tables."""
import gzip
import shutil
import sqlite3
import unittest
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "state_assemblies.db"


class AssemblyData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DB.exists():  # the repository ships it gzipped
            with gzip.open(str(DB) + ".gz", "rb") as fi, open(DB, "wb") as fo:
                shutil.copyfileobj(fi, fo)
        cls.con = sqlite3.connect(DB)

    def q(self, sql, *a):
        return self.con.execute(sql, a).fetchall()

    def test_coverage(self):
        n, states = self.q("SELECT COUNT(*), COUNT(DISTINCT state) FROM ae_summary")[0]
        self.assertGreaterEqual(n, 410)
        self.assertGreaterEqual(states, 40)

    def test_every_seat_has_its_winners(self):
        bad = self.q("""SELECT k.state, k.year, k.ac_name FROM ae_constituencies k
            JOIN ae_candidates c USING (year, state, ac_no, ac_name)
            GROUP BY k.state, k.year, k.ac_no, k.ac_name HAVING SUM(c.won) <> k.seats""")
        self.assertEqual(bad, [])

    def test_votes_reconcile_except_noted(self):
        bad = self.q("SELECT SUM(mismatched_acs) FROM ae_load_report")[0][0]
        self.assertLessEqual(bad, 5)  # each one is listed in ae_data_notes

    def test_known_results(self):
        cases = [("Uttar Pradesh", 2017, "BJP", 312), ("Uttar Pradesh", 2022, "BJP", 255),
                 ("West Bengal", 2011, "AITC", 184), ("Karnataka", 2023, "INC", 135),
                 ("Tamil Nadu", 2016, "ADMK", 134), ("Kerala", 1957, "CPI", 60),
                 ("Punjab", 2022, "AAP", 92), ("Delhi", 2015, "AAP", 67),
                 ("Gujarat", 2002, "BJP", 127), ("Andhra Pradesh", 2024, "TDP", 135),
                 ("Tamil Nadu", 1967, "DMK", 137), ("West Bengal", 1977, "CPM", 178),
                 ("Sikkim", 2004, "SDF", 31), ("Punjab", 1997, "SAD", 75)]
        for st, y, p, won in cases:
            got = self.q("SELECT won FROM ae_party_trends WHERE state=? AND year=? AND party=?", st, y, p)
            self.assertEqual(got and got[0][0], won, (st, y, p))

    def test_no_duplicate_elections(self):
        self.assertEqual(self.q("SELECT state, year FROM ae_summary WHERE state IN ('Madras', 'Mysore') AND year > 1951"), [])


if __name__ == "__main__":
    unittest.main()
