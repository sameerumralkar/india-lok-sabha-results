-- Lok Sabha general election results, 1951-2024, from ECI statistical reports.

CREATE TABLE elections (
    year        INTEGER PRIMARY KEY,   -- year of poll as ECI labels the report
    lok_sabha   INTEGER NOT NULL,      -- 1st ... 18th Lok Sabha
    cycle       INTEGER NOT NULL       -- general-election cycle; deferred polls (1985, 1992) roll up into 1984, 1991
);

CREATE TABLE parties (
    year        INTEGER NOT NULL,
    party       TEXT NOT NULL,         -- normalised abbreviation (used everywhere else)
    party_raw   TEXT NOT NULL,         -- abbreviation exactly as printed by ECI that year
    name        TEXT,                  -- full name from ECI's list of participating parties
    party_type  TEXT,                  -- National / State / Registered (unrecognised) / Independent
    family      TEXT,                  -- lineage used for long-run trend lines (see reference.py)
    PRIMARY KEY (year, party_raw)
);

CREATE TABLE constituencies (
    year        INTEGER NOT NULL,
    state       TEXT NOT NULL,         -- normalised state / UT name
    state_raw   TEXT NOT NULL,         -- as printed by ECI
    pc_no       INTEGER NOT NULL,
    pc_name     TEXT NOT NULL,
    reserved    TEXT,                  -- GEN / SC / ST
    seats       INTEGER NOT NULL,      -- 2 or 3 for some 1951/1957 multi-member seats
    electors    INTEGER,
    voters      INTEGER,
    valid_votes INTEGER,
    turnout     REAL,                  -- voters / electors, %
    source      TEXT,
    PRIMARY KEY (year, state, pc_no, pc_name)
);

CREATE TABLE candidates (
    id          INTEGER PRIMARY KEY,
    year        INTEGER NOT NULL,
    state       TEXT NOT NULL,
    pc_no       INTEGER NOT NULL,
    pc_name     TEXT NOT NULL,
    candidate   TEXT NOT NULL,
    sex         TEXT,
    age         INTEGER,
    category    TEXT,
    party       TEXT NOT NULL,
    party_raw   TEXT NOT NULL,
    party_family TEXT NOT NULL,
    votes       INTEGER NOT NULL,
    postal      INTEGER,
    vote_share  REAL,                  -- % of valid votes in the constituency
    rank        INTEGER NOT NULL,
    won         INTEGER NOT NULL,      -- 1 if elected
    uncontested INTEGER NOT NULL DEFAULT 0,
    source      TEXT
);
CREATE INDEX ix_cand_year_party ON candidates (year, party);
CREATE INDEX ix_cand_year_state ON candidates (year, state);

CREATE TABLE data_notes (note TEXT);
