"""Reference tables: Lok Sabha numbering, state-name normalisation, party aliases
and party families used for long-run trend lines."""

LOK_SABHA_NO = {1951: 1, 1957: 2, 1962: 3, 1967: 4, 1971: 5, 1977: 6, 1980: 7, 1984: 8,
                1985: 8, 1989: 9, 1991: 10, 1992: 10, 1996: 11, 1998: 12, 1999: 13,
                2004: 14, 2009: 15, 2014: 16, 2019: 17, 2024: 18}

# Deferred polls belong to the general election of the same Lok Sabha:
# Assam & Punjab voted in 1985 (8th LS), Punjab in 1992 (10th LS).
CYCLE = {1985: 1984, 1992: 1991}

# Renames and spelling variants only. Historic units that were split or merged
# (Bombay, Hyderabad, Madhya Bharat, PEPSU, Travancore-Cochin, Goa Daman & Diu...)
# are kept as reported, because they do not map onto one modern state.
STATE_RENAMES = {
    "A And N Islands": "Andaman & Nicobar Islands",
    "Andaman And Nicobar Islands": "Andaman & Nicobar Islands",
    "Chattisgarh": "Chhattisgarh",
    "D And N Haveli": "Dadra & Nagar Haveli",
    "Dadra And Nagar Haveli": "Dadra & Nagar Haveli",
    "National Capital Territory Of Delhi": "Delhi",
    "NCT OF Delhi": "Delhi",
    "Goa Daman & Diu": "Goa, Daman & Diu",
    "Goa, Daman And Diu": "Goa, Daman & Diu",
    "Gujrat": "Gujarat",
    "Kerla": "Kerala",
    "Jammu And Kashmir": "Jammu & Kashmir",
    "Jammu and Kashmir": "Jammu & Kashmir",
    "L M And A Islands": "Lakshadweep",
    "Laccadive, Minicoy And Amindivi Islands": "Lakshadweep",
    "Orissa": "Odisha",
    "Orrisa": "Odisha",
    "Pondicherry": "Puducherry",
    "Uttaranchal": "Uttarakhand",
    "Patiala And East Punjab States Union": "PEPSU",
    "Travancore Cochin": "Travancore-Cochin",
}


def canonical_state(raw: str, year: int) -> str:
    s = STATE_RENAMES.get(raw.strip(), raw.strip())
    # Same territory, renamed later: Madras -> Tamil Nadu (1969), Mysore -> Karnataka (1973).
    # In 1951 both had different (pre-1956) boundaries, so keep the old name.
    if s == "Madras" and year >= 1957:
        return "Tamil Nadu"
    if s == "Mysore" and year >= 1957:
        return "Karnataka"
    return s


# Same party, different abbreviation in different reports. Keys are either
# 'ABBR' or (year, 'ABBR').
PARTY_ALIASES = {
    "CPI(M)": "CPM", "CPIM": "CPM",
    "ADK": "ADMK", "AIADMK": "ADMK",
    "FBL": "AIFB", "FB": "AIFB",
    "MUL": "IUML", "ML": "IUML",
    "WBTC": "AITC",
    "AUDF": "AIUDF",
    "AAAP": "AAP",
    "JnP": "JSP",            # Jana Sena Party (2019+); distinct from Janata Party (JNP)
    (1980, "INC(I)"): "INC",  # Congress (Indira) was the INC in 1980
}

# Lineages used for the 'family' trend lines. Anything not listed is its own family.
PARTY_FAMILY = {
    "INC": "Congress",
    "BJS": "BJS / BJP", "BJP": "BJS / BJP",
    # Janata parivar: the 1977 Janata Party contested on the BLD symbol.
    "BLD": "Janata parivar", "JNP": "Janata parivar", "JNP(S)": "Janata parivar",
    "LKD": "Janata parivar", "JD": "Janata parivar", "SJP(R)": "Janata parivar",
    "SJP": "Janata parivar", "JP": "Janata parivar", "SAP": "Janata parivar",
    "JD(U)": "Janata parivar", "JD(S)": "Janata parivar", "RJD": "Janata parivar",
    "JD(G)": "Janata parivar", "BKD": "Janata parivar",
    "CPI": "Left", "CPM": "Left", "RSP": "Left", "AIFB": "Left", "CPI(ML)(L)": "Left",
    "ADMK": "AIADMK", "DMK": "DMK",
    "TRS": "TRS / BRS", "BRS": "TRS / BRS",
    "LJP": "LJP", "LJPRV": "LJP",
    "SHS": "Shiv Sena", "SHSUBT": "Shiv Sena",
    "NCP": "NCP", "NCPSP": "NCP",
    "IND": "Independents",
    "NOTA": "NOTA",
}

# Full names for seat-winning parties whose year's ECI party list we do not have
# (2009, 2014 and 2019 reports were downloaded without that table).
EXTRA_PARTY_NAMES = {
    "LJP": "Lok Jan Shakti Party",
    "BLSP": "Rashtriya Lok Samta Party",
    "AIUDF": "All India United Democratic Front",
    "HJCBL": "Haryana Janhit Congress (BL)",
    "JVM": "Jharkhand Vikas Morcha (Prajatantrik)",
    "AINRC": "All India N.R. Congress",
}
