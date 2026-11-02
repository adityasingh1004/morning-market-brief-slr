"""Calendar engine: turns the official-calendar seed plus date rules into dated events.

Standard library only, so it installs on a locked-down treasury PC with plain Python 3.9+.
Status codes follow the FY27 dashboard:
  V = read from the primary release itself
  S = secondary / media source
  U = rule-based expectation, estimate, or not yet released
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path

from .paths import data_file

WEEKDAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4}


@dataclass
class Event:
    date: str
    cat: str            # gsec, tbill, sdl, mat, mpc, data, tax, fiscal, other
    title: str
    status: str = "U"   # V / S / U
    src: str = "rule"
    amount_cr: float | None = None
    detail: str = ""
    state: str = "scheduled"   # scheduled / notified / done
    flags: list = field(default_factory=list)
    evidence: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.date}|{self.cat}|{self.title}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key
        return d


# ---------------------------------------------------------------- dates
class Cal:
    def __init__(self, holidays: dict[str, str]):
        self.hol = holidays

    def working(self, d: date) -> bool:
        return d.weekday() < 5 and d.isoformat() not in self.hol

    def next_working(self, d: date) -> date:
        while not self.working(d):
            d += timedelta(1)
        return d

    def prev_working(self, d: date) -> date:
        while not self.working(d):
            d -= timedelta(1)
        return d

    def after(self, d: date) -> date:
        return self.next_working(d + timedelta(1))

    def last_working_of_month(self, y: int, m: int) -> date:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        return self.prev_working(nxt - timedelta(1))

    def nth_weekday(self, y: int, m: int, wd: int, n: int) -> date:
        d = date(y, m, 1)
        d += timedelta((wd - d.weekday()) % 7)
        return d + timedelta(7 * (n - 1))

    def holiday_name(self, d: date) -> str | None:
        if d.weekday() >= 5:
            return d.strftime("%A")
        return self.hol.get(d.isoformat())


def D(s: str) -> date:
    return date.fromisoformat(s)


def months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + (m == 12), m % 12 + 1)


def fmt_cr(x) -> str:
    if x is None:
        return "-"
    if x < 0:
        return "−" + fmt_cr(-x)
    s = f"{int(round(x)):d}"
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return "₹" + ",".join(parts + [tail]) + " cr" if parts else "₹" + tail + " cr"


# ---------------------------------------------------------------- builder
def _f(name: str, data_dir: Path | None) -> Path:
    return (data_dir / name) if data_dir else data_file(name)


def load_inputs(data_dir: Path | None = None):
    seed = json.loads(_f("seed_fy27_h2.json", data_dir).read_text(encoding="utf-8"))
    hol = json.loads(_f("holidays_mumbai.json", data_dir).read_text(encoding="utf-8"))["holidays"]
    secs = []
    p = _f("securities_due.csv", data_dir)
    if p.exists():
        with p.open(encoding="utf-8") as f:
            secs = [r for r in csv.DictReader(f) if r.get("maturity")]
    return seed, hol, secs


def build(start: str, end: str, data_dir: Path | None = None) -> list[Event]:
    seed, hol, secs = load_inputs(data_dir)
    cal = Cal(hol)
    s, e = D(start), D(end)
    src = seed["sources"]
    ev: list[Event] = []

    def add(d: date, *a, **k):
        if s <= d <= e:
            ev.append(Event(d.isoformat(), *a, **k))

    # --- dated G-Secs (primary issuance calendar)
    for w in seed["gsec_weeks"]:
        fri = D(w["week_end"])
        tot = sum(w["alloc"].values())
        tenors = ", ".join(w["alloc"])
        det = "; ".join(f"{t} {fmt_cr(a)}" for t, a in w["alloc"].items())
        flags = []
        st = src[w["src"]]["status"]
        if not cal.working(fri):
            flags.append(f"Friday is {cal.holiday_name(fri)}: auction day will be set by RBI notification")
        add(fri, "gsec", f"G-Sec auction · {tenors}", status=st, src=w["src"], amount_cr=tot,
            detail=f"Week {w['week_start']} to {w['week_end']}: {det}. Greenshoe up to "
                   f"{fmt_cr(seed['gsec_rules']['greenshoe_per_security_cr'])} per security.",
            flags=flags)
        add(cal.after(fri), "gsec", "G-Sec settlement (T+1)", status="U", src="rule", amount_cr=tot,
            detail="Settlement assumed next working day after the auction; confirm in RBI notification.")

    # --- switch auctions: third Monday, fourth if holiday
    for y, m in months(s, e):
        d = cal.nth_weekday(y, m, 0, 3)
        if not cal.working(d):
            d = cal.nth_weekday(y, m, 0, 4)
        if D("2026-10-01") <= d <= D("2027-03-31"):
            add(d, "mpc", "Switch auction slot (third Monday)", status="V", src="rbi_gsec_h2",
                detail="Per issuance calendar note; held only if RBI notifies.")

    # --- T-bills
    for t in seed["tbills"]:
        tot = t["91D"] + t["182D"] + t["364D"]
        add(D(t["auction"]), "tbill", "T-bill auction · 91D/182D/364D", status=src[t["src"]]["status"],
            src=t["src"], amount_cr=tot,
            detail=f"91D {fmt_cr(t['91D'])}, 182D {fmt_cr(t['182D'])}, 364D {fmt_cr(t['364D'])}; "
                   f"settlement {t['settle']}.")
    last_tb = max(D(t["auction"]) for t in seed["tbills"])
    add(cal.prev_working(last_tb - timedelta(2)), "tbill",
        "Next quarter's T-bill calendar expected", status="U", src="rule",
        detail="Usually released in the last week of the quarter.")

    # --- SDLs: quarter totals verified, weekly amounts come from RBI each week
    for q in seed["sdl_quarters"]:
        qs, qe = D(q["start"]), D(q["end"])
        d = qs + timedelta((WEEKDAYS[seed["sdl_rules"]["auction_weekday"]] - qs.weekday()) % 7)
        while d <= qe:
            flags = [] if cal.working(d) else [f"Tuesday is {cal.holiday_name(d)}: check RBI notice"]
            qt = f"quarter total {fmt_cr(q['total_cr'])} ({src[q['src']]['status']})" if q["total_cr"] \
                else "quarterly calendar not yet released"
            add(d, "sdl", "SDL auction (Tuesday slot)", status="U", src="rule",
                detail=f"{q['quarter']}: {qt}. Weekly amount confirmed by RBI notice 2–3 days before.",
                flags=flags)
            d += timedelta(7)
        if q["total_cr"] is None:
            add(qs, "sdl", f"SDL indicative calendar {q['quarter']} expected", status="U", src="rule")

    # --- MPC
    for i, m in enumerate(seed["mpc_meetings"], 1):
        a, b = D(m["start"]), D(m["end"])
        add(a, "mpc", f"MPC meeting begins ({i} of 6)", status="V", src=m["src"])
        add(b, "mpc", f"MPC decision ({i} of 6)", status="V", src=m["src"])
        add(b + timedelta(14), "mpc", f"MPC minutes ({i} of 6), expected", status="U", src="rule",
            detail="Minutes are usually published on the 14th day after the decision.")

    # --- redemptions (from securities_due.csv, user-maintained from RBI outstanding list)
    for r in secs:
        m = D(r["maturity"])
        pay = cal.prev_working(m)
        flags = [] if pay == m else [f"Maturity {m} is a {cal.holiday_name(m)}: "
                                     f"rule pays on preceding working day {pay}; confirm"]
        add(pay, "mat", f"Redemption · {r['security']}", status=r.get("status") or "U",
            src=r.get("source") or "rule", amount_cr=float(r["outstanding_cr"] or 0) or None, flags=flags)

    # --- data releases (rule-based expectations; replace with MoSPI ARC when loaded)
    for y, m in months(s, e):
        nw = lambda day: cal.next_working(date(y, m, day))
        add(nw(12), "data", "CPI inflation", detail="Rule: 12th, next working day if holiday.")
        add(nw(28), "data", "IIP (industrial production)", detail="Rule: 28th, next working day if holiday.")
        add(nw(15), "data", "PLFS monthly bulletin", detail="Rule: 15th, next working day if holiday.")
        if m in (2, 5, 8, 11):
            add(nw(10), "data", "PLFS quarterly bulletin", detail="Rule: 10th of Feb/May/Aug/Nov.")
            add(cal.last_working_of_month(y, m), "data", "GDP quarterly estimate",
                detail="Rule: last working day of Feb/May/Aug/Nov.")
        add(cal.last_working_of_month(y, m), "other", "CGA monthly accounts (Union Govt)",
            detail="Rule: last working day of the month.")
        add(nw(14), "other", "WPI inflation (DPIIT)", detail="Rule: 14th, next working day.")
        add(nw(15), "other", "Merchandise trade data", detail="Rule: around the 15th.")
        add(nw(20), "other", "Eight core industries index", detail="Rule: around the 20th.")
        # tax
        add(nw(7), "tax", "TDS/TCS deposit", detail="Rule: 7th, next working day.")
        add(nw(20), "tax", "GST payment + GSTR-3B (monthly filers)", detail="Rule: 20th, next working day.")
        if m in (6, 9, 12, 3):
            n = {6: 1, 9: 2, 12: 3, 3: 4}[m]
            add(nw(15), "tax", f"Advance tax instalment {n} of 4",
                detail="15 Jun/Sep/Dec/Mar; confirm dates under the Income-tax Act, 2025.")
        if m in (3, 6, 9, 12):
            add(date(y, m, 30 if m in (6, 9) else 31), "fiscal", "Quarter-end", status="V", src="rule")
        if m in (1, 4, 7, 10):
            add(nw(22), "tax", "GSTR-3B quarterly (QRMP), Category X states", detail="Rule: 22nd after quarter-end.")
            add(nw(24), "tax", "GSTR-3B quarterly (QRMP), Category Y states", detail="Rule: 24th after quarter-end.")
    # one-off dated events carried in the seed
    for o in seed.get("one_offs", []):
        add(D(o["date"]), o["cat"], o["title"], status=src[o["src"]]["status"], src=o["src"],
            detail=o.get("detail", src[o["src"]]["title"]))
    # WSS every Friday
    d = s + timedelta((4 - s.weekday()) % 7)
    while d <= e:
        add(d, "other", "RBI WSS release",
            flags=[] if cal.working(d) else [f"Friday is {cal.holiday_name(d)}"],
            detail="Weekly Statistical Supplement, Friday.")
        d += timedelta(7)

    ev.sort(key=lambda x: (x.date, x.cat, x.title))
    return ev
