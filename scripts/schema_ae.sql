-- State Legislative Assembly results, from ECI statistical reports.
DROP VIEW IF EXISTS ae_summary;
DROP VIEW IF EXISTS ae_party_trends;
DROP VIEW IF EXISTS ae_family_trends;
DROP VIEW IF EXISTS ae_cand;
DROP TABLE IF EXISTS ae_candidates;
DROP TABLE IF EXISTS ae_constituencies;
DROP TABLE IF EXISTS ae_data_notes;
DROP TABLE IF EXISTS ae_load_report;
DROP TABLE IF EXISTS ae_parties;

CREATE TABLE ae_parties (
    state TEXT, year INTEGER, party TEXT, party_raw TEXT, name TEXT, party_type TEXT,
    PRIMARY KEY (state, year, party_raw)
);

CREATE TABLE ae_constituencies (
    year        INTEGER NOT NULL,
    state       TEXT NOT NULL,         -- state as it existed at that election (Bombay, Madras, undivided Andhra Pradesh...)
    ac_no       INTEGER NOT NULL,
    ac_name     TEXT NOT NULL,
    reserved    TEXT,                  -- GEN / SC / ST
    seats       INTEGER NOT NULL,      -- 2 for some 1950s double-member seats
    electors    INTEGER,
    voters      INTEGER,
    valid_votes INTEGER,               -- excludes NOTA
    turnout     REAL,
    source      TEXT,
    PRIMARY KEY (year, state, ac_no, ac_name)
);

CREATE TABLE ae_candidates (
    id           INTEGER PRIMARY KEY,
    year         INTEGER NOT NULL,
    state        TEXT NOT NULL,
    ac_no        INTEGER NOT NULL,
    ac_name      TEXT NOT NULL,
    candidate    TEXT NOT NULL,
    sex          TEXT,
    age          INTEGER,
    category     TEXT,
    party        TEXT NOT NULL,
    party_raw    TEXT NOT NULL,
    party_family TEXT NOT NULL,
    votes        INTEGER NOT NULL,
    postal       INTEGER,
    vote_share   REAL,
    rank         INTEGER NOT NULL,
    won          INTEGER NOT NULL,
    uncontested  INTEGER NOT NULL DEFAULT 0,
    source       TEXT
);
CREATE INDEX ix_ae_state_year ON ae_candidates (state, year);

CREATE TABLE ae_data_notes (note TEXT);

CREATE TABLE ae_load_report (
    state TEXT, year INTEGER, source TEXT, acs INTEGER, seats INTEGER,
    candidates INTEGER, mismatched_acs INTEGER, missing_acs INTEGER, status TEXT
);
