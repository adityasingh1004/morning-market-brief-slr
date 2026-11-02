# Morning Market Brief – SLR
# Copyright (C) 2026 Aditya Kumar Singh
# SPDX-License-Identifier: AGPL-3.0-only (with additional attribution terms, see ADDITIONAL-TERMS.md)
"""Command line for the Morning Market Brief – SLR (RBI feed helper).

  treasury-digest                     build today's digest (same as `digest`)
  treasury-digest digest [--date YYYY-MM-DD] [--offline] [--feed-file PATH] [--open]
  treasury-digest schedule [--time HH:MM] [--no-open]   run every weekday morning
  treasury-digest unschedule
  treasury-digest init                copy the editable data files to your folder
  treasury-digest where               show where files are kept
  treasury-digest export --start YYYY-MM-DD --end YYYY-MM-DD
  treasury-digest crosscheck --report events.json --start ... --end ...

`python -m mmb_feed ...` works the same way.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import __version__, digest, engine, feed, rbi_parse, schedule
from .crosscheck import compare, load_report, summary_rows
from .paths import data_file, home, init_user_data, out_dir

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> date:
    return datetime.now(IST).date()


def run_digest(day: date, feed_file=None, offline=False, open_browser=False, quiet=False) -> Path:
    OUT = out_dir()
    evs = engine.build((day - timedelta(10)).isoformat(), (day + timedelta(35)).isoformat())
    log, items = [], []
    if feed_file:
        items = feed.parse(Path(feed_file).read_bytes())
    elif not offline:
        try:
            items = feed.parse(feed.fetch(feed.DEFAULT_FEED, OUT / "rbi_feed_cache.xml"))
        except Exception as ex:  # network blocked, feed moved, etc. The digest still goes out.
            log = [f"RBI feed not read ({ex.__class__.__name__}: {ex}); showing archived releases only."]
    arch = rbi_parse.archive(items, OUT / "rbi_archive")
    recs = [rbi_parse.parse_item(r) for r in arch]
    for r in arch:
        if r.get("date"):
            r["date"] = date.fromisoformat(r["date"])
    log += feed.confirm(evs, [r for r in arch if r.get("date")])
    log += feed.apply_notices(evs, recs)
    txt = digest.text(evs, day, recs)
    (OUT / f"digest_{day}.txt").write_text(txt + ("\n\nFEED LOG\n" + "\n".join(log) if log else ""), encoding="utf-8")
    page = digest.html_page(evs, day, recs)
    html_path = OUT / f"digest_{day}.html"
    html_path.write_text(page, encoding="utf-8")
    (OUT / "digest_latest.html").write_text(page, encoding="utf-8")
    if not quiet:
        print(txt)
        if log:
            print("\nFEED LOG\n" + "\n".join(log))
        print(f"\nSaved: {html_path}\n       {OUT / f'digest_{day}.txt'}")
    if open_browser:
        webbrowser.open(html_path.resolve().as_uri())
    return html_path


def main(argv=None):
    p = argparse.ArgumentParser(prog="mmb-feed", description="Morning Market Brief – SLR (RBI feed helper) from public RBI releases.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd")
    d = sub.add_parser("digest", help="build the digest")
    d.add_argument("--date")
    d.add_argument("--feed-file")
    d.add_argument("--offline", action="store_true")
    d.add_argument("--open", action="store_true", help="open the HTML digest in the browser")
    s = sub.add_parser("schedule", help="run every weekday morning")
    s.add_argument("--time", default="09:15")
    s.add_argument("--no-open", action="store_true")
    sub.add_parser("unschedule", help="remove the daily run")
    i = sub.add_parser("init", help="copy editable data files to your folder")
    i.add_argument("--force", action="store_true")
    sub.add_parser("where", help="show where files are kept")
    x = sub.add_parser("export")
    x.add_argument("--start", required=True)
    x.add_argument("--end", required=True)
    c = sub.add_parser("crosscheck")
    c.add_argument("--report", required=True)
    c.add_argument("--start", required=True)
    c.add_argument("--end", required=True)
    a = p.parse_args(argv)
    cmd = a.cmd or "digest"

    if cmd == "digest":
        day = date.fromisoformat(a.date) if getattr(a, "date", None) else today_ist()
        quiet = sys.stdout is None  # pythonw (scheduled run) has no console
        try:
            run_digest(day, getattr(a, "feed_file", None), getattr(a, "offline", False),
                       getattr(a, "open", False), quiet)
        except Exception:
            (out_dir() / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            raise

    elif cmd == "schedule":
        print(schedule.install(a.time, not a.no_open))

    elif cmd == "unschedule":
        print(schedule.remove())

    elif cmd == "init":
        done = init_user_data(a.force)
        print("Copied:\n  " + "\n  ".join(done) if done else "Your data files already exist (use --force to reset).")
        print(f"Edit them in {home() / 'data'}. Your copies are used instead of the defaults.")

    elif cmd == "where":
        print(f"Home folder : {home()}")
        print(f"Digests     : {out_dir()}")
        for f in ("seed_fy27_h2.json", "holidays_mumbai.json", "securities_due.csv"):
            print(f"Using       : {data_file(f)}")

    elif cmd == "export":
        evs = engine.build(a.start, a.end)
        path = out_dir() / f"events_{a.start}_{a.end}.json"
        path.write_text(json.dumps([e.to_dict() for e in evs], indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{len(evs)} events -> {path}")

    elif cmd == "crosscheck":
        evs = engine.build(a.start, a.end)
        res = compare(evs, load_report(Path(a.report), a.start, a.end))
        print(f"{'family':14} match datediff amtdiff only_report only_engine")
        for row in summary_rows(res):
            print(f"{row[0]:14} {row[1]:5} {row[2]:8} {row[3]:7} {row[4]:11} {row[5]:11}")
        return res


if __name__ == "__main__":
    main()
