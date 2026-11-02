---
name: morning-market-brief-slr
description: Maintains the Morning Market Brief – SLR, a daily overview of India's government debt market (G-Sec, T-bill and SDL borrowing and auctions, redemptions, curves from RBI auction cut-offs, borrowing maths, government cash, RBI liquidity and FX operations, MPC, data and tax calendar, market strip). Use when the user asks to update, run, refresh or open the Morning Market Brief, or for the Indian G-Sec/SDL market overview.
---

# Morning Market Brief – SLR

Created by **Aditya Kumar Singh**. Free software under AGPL-3.0 with additional attribution terms (see `ADDITIONAL-TERMS.md`).

The brief is one self-contained HTML page: `~/MorningMarketBrief/report.html` (override the folder with `MMB_HOME`). Your job is to bring it up to date from official releases. **Patch it; never rebuild it.**

## First run

1. `python scripts/mmb.py init`: copies `report/base_report.html` (the author's brief as of its "Data as of" date) to the user's folder.
2. Then do the daily update below. On a first run it covers every day since the base's "Data as of" date, so it is longer than a normal day. Work through the gap in date order. If the gap is more than about three weeks, tell the user the catch-up may be incomplete, and suggest downloading the newest base from the repository instead.

## Daily update

1. **Back up:** `python scripts/mmb.py backup`. Read `python scripts/mmb.py asof` to get the "Data as of" date (D).
2. **Read the page.** Open the working report and read the whole inline `<script>`. Everything lives there:
   - sources in the `SRC` object: one key per source, with title `t` and URL `u`;
   - events via `add(date,cat,title,{amt,detail,st,src})`;
   - specialised arrays: `OMO`, `FXS` (FX swaps), `MAT` (maturities), `MPCM` and the MPC outcome text, `SDLQ` (SDL quarters), `TB` (T-bill quarters), `CASH` (WSS net RBI credit to the Centre), `facts` (the facts strip), `MKT` (market strip), and the curve points `P`, `S13` and `S6` (in the curves block);
   - the borrowing-maths constants and the SDL-to-date table.
3. **Collect what is new since D.** Use only official releases:
   - **RBI press releases:** dated G-Sec, T-bill and SDL auction notices and results; OMO, VRR/VRRR and FX swap operations; buybacks and switches; new borrowing calendars; MPC statements and minutes; money-market operations; the WSS extract; SGB prices; FRB resets. Start at `https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx` and open each release (`BS_PressReleaseDisplay.aspx?prid=NNNNN`) for its figures.
   - **Optional helper, on the user's own machine:** `python -m mmb_feed digest --offline` (or without `--offline` to read RBI's feed) prints the latest auction results, notices, liquidity and WSS figures, parsed straight from RBI's tables. Use it to cross-check what you read.
   - **MoSPI, PIB, CGA, DEA:** for data releases and fiscal figures.
4. **Patch** with small targeted edits, such as a short Python string-replace on the file. For each new item:
   - add an event, or update the matching array;
   - add a `SRC` key for each new source;
   - tag it `st:"v"` (Verified: you read the primary release), `st:"s"` (Secondary: media or third party) or `st:"u"` (UNVERIFIED — CHECK MANUALLY);
   - when an auction completes, update its "notified" line to the result, and update the to-date totals, borrowing maths, curves and facts strip that depend on it;
   - when RBI publishes a new calendar (T-bill quarterly, SDL quarterly, dated securities half-yearly), replace any ESTIMATE block it supersedes.
5. **Market strip (`MKT`), every run.** For each series, append the latest closes since its last point and keep only the most recent ~6 points.
   - UST par yields come from the US Treasury daily par yield curve page (`st:"v"`).
   - Every other series is media or a data vendor (`st:"s"`). Keep each series' sampling consistent, and say in its `note` which days or snapshot times are used and which were missed.
   - If a series can't be refreshed, leave its points and note that it is stale as of its last date.
6. **Set `DATA_AS_OF`** to today's date in IST.
7. **Validate:** `python scripts/mmb.py validate`. If it fails, fix the problem. If you can't, run `python scripts/mmb.py restore` and report the failure. Never leave a failed page in place.
8. **Report** a short changelog: what changed, the market strip's latest date per series, and any new flags. If nothing new was found, still update the date and say so in one line.

## Hard rules

- **Data integrity.** Every figure comes from a primary source (RBI, MoSPI, PIB, CGA, DEA, US Treasury) or is labelled Secondary or UNVERIFIED — CHECK MANUALLY. Never present an estimate as data. Never fill a number from memory.
- **No CCIL-published SDL/SGS spreads.** The SDL curve uses RBI auction cut-offs only.
- **Attribution must stay.** Never remove or alter the `#mmb-attribution` footer, the author meta tag or the licence banner at the top of the script, and never reword "Morning Market Brief – SLR · by Aditya Kumar Singh". The licence requires them, and `validate` fails without them.
- **Describe, don't advise.** No views on rates, curve trades or positions.
- **Patch only what changed.** Don't restructure tabs, layout or design.
- If the page cannot be read or saved, report that and stop.

## Running it every morning

- **Claude Code on the user's computer:** schedule a weekday job that runs, from this folder,
  `claude -p "Run the Morning Market Brief – SLR daily update." --allowedTools "Bash,Read,Edit,Write,WebFetch,WebSearch"`.
  See README.md for Windows Task Scheduler and cron examples.
- **Claude app with scheduled tasks:** create a daily task whose prompt is "Run the Morning Market Brief – SLR daily update" with this skill enabled.
