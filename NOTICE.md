# Data sources and disclaimer

Morning Market Brief – SLR · created by Aditya Kumar Singh

## What the repository contains

- Code: the update procedure (`SKILL.md`), the scripts, and the RBI feed helper (`mmb_feed`).
- `report/base_report.html`: the brief as of its "Data as of" date. It compiles **facts** from public official releases, each tagged and linked to its source, plus the author's computations (labelled Computed) and estimates (labelled ESTIMATE / UNVERIFIED).
- Media-sourced market levels are **not** included in the base. Each user's own run fetches them.
- Test files use invented numbers.

## Sources

| Source | Used for |
|---|---|
| Reserve Bank of India: press releases, issuance calendars, auction results, money-market operations, Weekly Statistical Supplement, list of outstanding securities | Auctions, calendars, curves, liquidity, borrowing maths, government cash |
| Ministry of Finance / DEA, PIB | Budget and borrowing-plan figures |
| MoSPI | Data-release calendar and releases |
| CCIL (Rakshitra, outstanding government debt) | Outstanding-stock figures, tagged Secondary. **CCIL-published SDL/SGS spreads are not used.** |
| US Treasury, daily par yield curve | UST yields |
| Media and data vendors (named in each series' note) | Brent, gold, USD/INR, India 10Y and 5Y, Baltic Dry: Secondary |

All source content belongs to its publishers. The brief links each figure to its source.

## Disclaimer

Independent project, not affiliated with or endorsed by any body named above. The brief is maintained by an AI assistant following the documented procedure and may contain errors. It is not investment, legal or tax advice. Check every figure against its linked source before relying on it.
