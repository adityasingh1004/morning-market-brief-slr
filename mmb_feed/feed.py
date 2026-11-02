"""Confirms scheduled events against RBI press releases (RSS feed).

Deterministic title matching only: no AI, no numbers parsed from prose.
A matched release moves an event to 'notified' or 'done', upgrades its date
status to V, and stores the release title + link as evidence.
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

# RBI press-release RSS feed (confirmed working Nov 2026). Listed at https://rbi.org.in/Scripts/rss.aspx
DEFAULT_FEED = "https://www.rbi.org.in/pressreleases_rss.xml"

# (category, new state, title regex, window: days before/after the event date the release may appear)
RULES = [
    ("gsec", "done", r"(government stock|dated securities).*(auction result|cut-off)|auction result.*government stock", (0, 1)),
    ("gsec", "notified", r"auction of government stocks?", (-6, 0)),
    ("gsec", "notified", r"auction of government of india dated securities|auction of government securities", (-6, 0)),
    ("tbill", "done", r"treasury bills?.*(auction result|cut-off)", (0, 1)),
    ("tbill", "notified", r"auction of .*treasury bills", (-6, 0)),
    ("sdl", "done", r"result of .*auction of state government securities", (0, 1)),
    ("sdl", "notified", r"auction of state government securities", (-4, 0)),
    ("mpc", "done", r"monetary policy statement", (0, 0)),
    ("mpc", "done", r"minutes of the monetary policy committee", (-3, 3)),
]
TITLE_HINT = {"gsec": "G-Sec auction", "tbill": "T-bill auction", "sdl": "SDL auction"}


def fetch(url: str = DEFAULT_FEED, cache: Path | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "indian-treasury-digest/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if cache:
        cache.write_bytes(raw)
    return raw


def parse(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        title = re.sub(r"<[^>]+>", "", (it.findtext("title") or "")).strip()
        title = " ".join(title.split())
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            d = parsedate_to_datetime(pub).date() if pub else None
        except (TypeError, ValueError):
            d = None
        out.append({"title": title, "link": link, "date": d, "pub": pub,
                    "html": it.findtext("description") or ""})
    return out


def confirm(events, items) -> list[str]:
    """Mutates events in place. Returns a log of what matched."""
    log = []
    for it in items:
        if not it["date"]:
            continue
        t = it["title"].lower()
        for cat, state, rx, (lo, hi) in RULES:
            if not re.search(rx, t):
                continue
            for e in events:
                if e.cat != cat:
                    continue
                if cat in TITLE_HINT and not e.title.startswith(TITLE_HINT[cat]):
                    continue
                if cat == "mpc":
                    want = "minutes" if "minutes" in t else "decision"
                    if want not in e.title.lower():
                        continue
                ed = date.fromisoformat(e.date)
                if ed + timedelta(lo) <= it["date"] <= ed + timedelta(hi):
                    order = {"scheduled": 0, "notified": 1, "done": 2}
                    if order[state] >= order[e.state]:
                        e.state = state
                        e.status = "V"
                        e.evidence.append({"title": it["title"], "link": it["link"], "date": it["date"].isoformat()})
                        log.append(f"{e.date} {e.title} -> {state} ({it['title']})")
            break
    return log


def apply_notices(events, recs) -> list[str]:
    """Copies amounts from parsed RBI notices onto the matching calendar event."""
    log = []
    for r in recs:
        d = r.get("data") or {}
        k = d.get("kind")
        if k == "sdl_notice" and d.get("auction"):
            for e in events:
                if e.cat == "sdl" and e.date == d["auction"] and e.title.startswith("SDL auction"):
                    e.amount_cr = d["total_cr"]
                    e.title = f"SDL auction · {len(d['states'])} states/UTs"
                    e.status = "V"
                    e.state = "notified" if e.state == "scheduled" else e.state
                    e.src = f"RBI PR {r.get('pr')}"
                    e.detail = ", ".join(f"{s} {int(v):,}" for s, v in d["states"].items()) + " (₹ cr)"
                    log.append(f"{e.date} SDL amount ₹{int(d['total_cr']):,} cr from RBI PR {r.get('pr')}")
        if k == "tbill_notice" and d.get("auction"):
            for e in events:
                if e.cat == "tbill" and e.date == d["auction"] and e.amount_cr:
                    if d.get("total_cr") and abs(d["total_cr"] - e.amount_cr) > 0.5:
                        e.flags.append(f"RBI notice says ₹{int(d['total_cr']):,} cr vs calendar ₹{int(e.amount_cr):,} cr")
                        e.amount_cr = d["total_cr"]
                    e.status = "V"
                    e.state = "notified" if e.state == "scheduled" else e.state
                    e.src = f"RBI PR {r.get('pr')}"
                    e.detail = f"Settles {d.get('settle')}; " + ", ".join(f"{a} ₹{int(b):,} cr" for a, b in d["split"].items())
                    log.append(f"{e.date} T-bill notice matches calendar (RBI PR {r.get('pr')})")
    return log
