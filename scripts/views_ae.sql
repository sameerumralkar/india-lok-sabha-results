-- Assembly trend views. Vote shares are over valid votes excluding NOTA.
CREATE VIEW ae_summary AS
SELECT k.state, k.year, SUM(k.seats) AS seats, COUNT(*) AS constituencies,
       (SELECT COUNT(*) FROM ae_candidates c WHERE c.state = k.state AND c.year = k.year AND c.party <> 'NOTA') AS candidates,
       SUM(k.electors) AS electors, SUM(k.voters) AS voters, SUM(k.valid_votes) AS valid_votes,
       ROUND(100.0 * SUM(CASE WHEN k.voters IS NOT NULL AND k.electors IS NOT NULL THEN k.voters END)
             / SUM(CASE WHEN k.voters IS NOT NULL AND k.electors IS NOT NULL THEN k.electors END), 2) AS turnout,
       (SELECT c.party FROM ae_candidates c WHERE c.state = k.state AND c.year = k.year
        GROUP BY c.party ORDER BY SUM(c.won) DESC, SUM(c.votes) DESC LIMIT 1) AS largest_party
FROM ae_constituencies k GROUP BY k.state, k.year ORDER BY k.state, k.year;

CREATE VIEW ae_party_trends AS
WITH tot AS (SELECT state, year, SUM(CASE WHEN party <> 'NOTA' THEN votes END) AS v, SUM(won) AS s
             FROM ae_candidates GROUP BY state, year)
SELECT c.state, c.year, c.party, MAX(c.party_family) AS family,
       COUNT(*) AS contested, SUM(c.won) AS won, t.s AS seats, SUM(c.votes) AS votes,
       ROUND(100.0 * SUM(c.votes) / NULLIF(t.v, 0), 2) AS vote_share,
       ROUND(100.0 * SUM(c.won) / NULLIF(t.s, 0), 2) AS seat_share,
       CASE WHEN 2 * SUM(c.won) > t.s THEN 1 ELSE 0 END AS majority
FROM ae_candidates c JOIN tot t ON t.state = c.state AND t.year = c.year
GROUP BY c.state, c.year, c.party ORDER BY c.state, c.year, won DESC, votes DESC;

CREATE VIEW ae_family_trends AS
WITH tot AS (SELECT state, year, SUM(CASE WHEN party <> 'NOTA' THEN votes END) AS v, SUM(won) AS s
             FROM ae_candidates GROUP BY state, year)
SELECT c.state, c.year, c.party_family AS family,
       COUNT(*) AS contested, SUM(c.won) AS won, t.s AS seats, SUM(c.votes) AS votes,
       ROUND(100.0 * SUM(c.votes) / NULLIF(t.v, 0), 2) AS vote_share
FROM ae_candidates c JOIN tot t ON t.state = c.state AND t.year = c.year
GROUP BY c.state, c.year, c.party_family ORDER BY c.state, c.year, won DESC, votes DESC;
