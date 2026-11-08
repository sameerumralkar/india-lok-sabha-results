"""Integrity checks on data/lok_sabha.db against ECI's published figures."""
import sqlite3
import unittest
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "lok_sabha.db"


class LokSabhaData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = sqlite3.connect(DB)

    def one(self, sql, *args):
        return self.con.execute(sql, args).fetchone()

    def test_every_seat_has_its_winners(self):
        bad = self.con.execute("""
            SELECT k.year, k.state, k.pc_name, k.seats, SUM(c.won)
            FROM constituencies k JOIN candidates c USING (year, state, pc_no, pc_name)
            GROUP BY k.year, k.state, k.pc_no, k.pc_name HAVING SUM(c.won) <> k.seats""").fetchall()
        self.assertEqual(bad, [])

    def test_votes_add_up_to_valid_votes(self):
        bad = self.con.execute("""
            SELECT k.year, k.state, k.pc_name
            FROM constituencies k JOIN candidates c USING (year, state, pc_no, pc_name)
            WHERE c.party <> 'NOTA'
            GROUP BY k.year, k.state, k.pc_no, k.pc_name HAVING SUM(c.votes) <> k.valid_votes""").fetchall()
        self.assertEqual(bad, [])

    def test_seat_totals(self):
        seats = dict(self.con.execute("SELECT year, seats FROM election_summary"))
        expected = {1951: 489, 1957: 494, 1962: 494, 1971: 518, 1977: 542, 1980: 529, 1984: 541,
                    1989: 529, 1991: 534, 1996: 543, 2004: 543, 2014: 543, 2019: 543, 2024: 543}
        for year, n in expected.items():
            self.assertEqual(seats[year], n, year)

    def test_candidate_counts_match_eci(self):
        counts = dict(self.con.execute("SELECT year, candidates FROM election_summary"))
        for year, n in {1989: 6160, 1996: 13952, 2009: 8070, 2014: 8251, 2019: 8054, 2024: 8360}.items():
            self.assertEqual(counts[year], n, year)

    def test_national_results_match_eci(self):
        cases = [  # year, party, seats, vote share (ECI, NOTA excluded from valid votes)
            (1951, "INC", 364, 44.99), (1957, "INC", 371, 47.78), (1977, "BLD", 295, 41.32),
            (1980, "INC", 353, 42.69), (1989, "BJP", 85, 11.36), (2009, "INC", 206, 28.55),
            (2014, "BJP", 282, 31.34), (2014, "INC", 44, 19.52), (2019, "BJP", 303, None),
            (2024, "BJP", 240, None), (2024, "INC", 99, None)]
        for year, party, won, share in cases:
            row = self.one("SELECT won, vote_share FROM national_party_trends WHERE year=? AND party=?",
                           year, party)
            self.assertEqual(row[0], won, (year, party))
            if share is not None:
                self.assertAlmostEqual(row[1], share, delta=0.01, msg=(year, party))

    def test_no_parse_debris_in_names(self):
        n = self.one("SELECT COUNT(*) FROM constituencies WHERE pc_name LIKE '%Electors%' "
                     "OR pc_name LIKE '%GENERAL POSTAL%'")[0]
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
