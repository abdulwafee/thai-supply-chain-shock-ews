# data/mapping

Small, hand-curated classification crosswalks. Unlike every other `data/` subfolder, this one
**is** committed to Git (see `.gitignore`) — these tables are closer to code/config than to bulk
data, and their diffs are what a reviewer needs to see when a classification decision changes.

- `industry_map.csv` — the 12 project-internal `industry_id`s, each mapped to its official TSIC
  2009 division numbers. Fully populated; see `docs/architecture/data_architecture.md` §4 for the
  identifier policy and §13 for the one open item (TSIC Division 12, tobacco).
- `hs_to_industry.csv`, `io_sector_to_industry.csv`, `commodity_to_industry.csv` — **schema only,
  intentionally empty.** Populating these requires official codes (Thai national HS, NESDC I-O
  sector codes, World Bank commodity labels) that are not yet verified per
  `docs/data_source_inventory.md`. Do not fill these with invented codes — see the
  project restriction against fabricating official classification mappings.
- `country_reference.csv` — ISO 3166-1 alpha-3 codes for Thailand and its major trading partners.
  This is a real, external, well-documented standard, safe to populate directly (unlike the three
  files above, which depend on unverified Thai-specific official sources).
