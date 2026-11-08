-- Vote shares use ECI's definition of valid votes, which excludes NOTA (2014+).
-- The NOTA row's share is therefore relative to valid votes, as ECI also reports it.
-- Trend views. Everything is grouped by election cycle so the deferred
-- 1985 (Assam, Punjab) and 1992 (Punjab) polls count with 1984 and 1991.

CREATE VIEW cand AS
SELECT c.*, e.cycle, e.lok_sabha FROM candidates c JOIN elections e USING (year);

CREATE VIEW pcs AS
SELECT p.*, e.cycle, e.lok_sabha FROM constituencies p JOIN elections e USING (year);

CREATE VIEW election_summary AS
SELECT cycle AS year, MIN(lok_sabha) AS lok_sabha,
       SUM(seats) AS seats, COUNT(*) AS constituencies,
       (SELECT COUNT(*) FROM cand c WHERE c.cycle = p.cycle AND c.party <> 'NOTA') AS candidates,
       SUM(electors) AS electors, SUM(voters) AS voters, SUM(valid_votes) AS valid_votes,
       ROUND(100.0 * SUM(CASE WHEN voters IS NOT NULL AND electors IS NOT NULL THEN voters END)
             / SUM(CASE WHEN voters IS NOT NULL AND electors IS NOT NULL THEN electors END), 2) AS turnout
FROM pcs p GROUP BY cycle ORDER BY cycle;

CREATE VIEW state_summary AS
SELECT cycle AS year, state, SUM(seats) AS seats, COUNT(*) AS constituencies,
       SUM(electors) AS electors, SUM(voters) AS voters, SUM(valid_votes) AS valid_votes,
       ROUND(100.0 * SUM(CASE WHEN voters IS NOT NULL AND electors IS NOT NULL THEN voters END)
             / SUM(CASE WHEN voters IS NOT NULL AND electors IS NOT NULL THEN electors END), 2) AS turnout
FROM pcs GROUP BY cycle, state ORDER BY cycle, state;

CREATE VIEW national_party_trends AS
WITH tot AS (SELECT cycle, SUM(CASE WHEN party <> 'NOTA' THEN votes END) AS v, SUM(won) AS s FROM cand GROUP BY cycle),
     agg AS (SELECT cycle, party, MAX(party_family) AS family, COUNT(*) AS contested,
                    SUM(won) AS won, SUM(votes) AS votes, ROUND(AVG(vote_share), 2) AS avg_share
             FROM cand GROUP BY cycle, party)
SELECT a.cycle AS year, a.party,
       COALESCE(py.name, pn.name) AS party_name,
       a.family, a.contested, a.won, a.votes,
       ROUND(100.0 * a.votes / t.v, 2) AS vote_share,
       ROUND(100.0 * a.won / t.s, 2) AS seat_share,
       a.avg_share AS avg_share_where_contested
FROM agg a JOIN tot t ON t.cycle = a.cycle
LEFT JOIN (SELECT year, party, MAX(name) AS name FROM parties WHERE name IS NOT NULL
           GROUP BY year, party) py ON py.year = a.cycle AND py.party = a.party
LEFT JOIN (SELECT party, name, MAX(year) FROM parties WHERE name IS NOT NULL
           GROUP BY party) pn ON pn.party = a.party
ORDER BY a.cycle, a.won DESC, a.votes DESC;

CREATE VIEW state_party_trends AS
WITH tot AS (SELECT cycle, state, SUM(CASE WHEN party <> 'NOTA' THEN votes END) AS v, SUM(won) AS s FROM cand GROUP BY cycle, state)
SELECT c.cycle AS year, c.state, c.party, MAX(c.party_family) AS family,
       COUNT(*) AS contested, SUM(c.won) AS won, tot.s AS state_seats, SUM(c.votes) AS votes,
       ROUND(100.0 * SUM(c.votes) / NULLIF(tot.v, 0), 2) AS vote_share
FROM cand c JOIN tot USING (cycle, state)
GROUP BY c.cycle, c.state, c.party ORDER BY c.cycle, c.state, won DESC, votes DESC;

CREATE VIEW national_family_trends AS
WITH tot AS (SELECT cycle, SUM(CASE WHEN party <> 'NOTA' THEN votes END) AS v, SUM(won) AS s FROM cand GROUP BY cycle)
SELECT c.cycle AS year, c.party_family AS family,
       COUNT(*) AS contested, SUM(c.won) AS won, SUM(c.votes) AS votes,
       ROUND(100.0 * SUM(c.votes) / tot.v, 2) AS vote_share,
       ROUND(100.0 * SUM(c.won) / tot.s, 2) AS seat_share
FROM cand c JOIN tot USING (cycle)
GROUP BY c.cycle, c.party_family ORDER BY c.cycle, won DESC, votes DESC;

CREATE VIEW state_family_trends AS
WITH tot AS (SELECT cycle, state, SUM(CASE WHEN party <> 'NOTA' THEN votes END) AS v, SUM(won) AS s FROM cand GROUP BY cycle, state)
SELECT c.cycle AS year, c.state, c.party_family AS family,
       COUNT(*) AS contested, SUM(c.won) AS won, tot.s AS state_seats, SUM(c.votes) AS votes,
       ROUND(100.0 * SUM(c.votes) / NULLIF(tot.v, 0), 2) AS vote_share
FROM cand c JOIN tot USING (cycle, state)
GROUP BY c.cycle, c.state, c.party_family ORDER BY c.cycle, c.state, won DESC, votes DESC;
