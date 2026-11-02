"""Compares engine events with another calendar (e.g. the FY27 dashboard export) event by event."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

FAMILIES = [
    ("g-sec settlement", "gsec_settle"), ("asuse", "asuse"), ("first advance estimates", "gdp_ae"),
    ("plfs annual", "plfs_a"), ("union budget", "budget"), ("swap window", "fx_swap"),
    ("sgb", "sgb"), ("qrmp", "qrmp"), ("centre's net rbi credit", "wss_note"), ("g-sec auction", "gsec"), ("t-bill auction", "tbill"),
    ("t-bill calendar", "tbill_cal"), ("next quarter's t-bill", "tbill_cal"),
    ("sdl indicative calendar", "sdl_cal"), ("sdl", "sdl"), ("switch auction", "switch"),
    ("mpc decision", "mpc_dec"), ("mpc meeting begins", "mpc_begin"), ("minutes", "mpc_min"),
    ("redemption", "mat"), ("cpi", "cpi"), ("iip", "iip"), ("plfs monthly", "plfs_m"),
    ("plfs quarterly", "plfs_q"), ("gdp", "gdp"), ("cga", "cga"), ("wpi", "wpi"),
    ("merchandise trade", "trade"), ("eight core", "core"), ("tds", "tds"),
    ("gst payment", "gst"), ("advance tax", "advtax"), ("quarter-end", "qend"), ("wss", "wss"),
]


def family(title: str) -> str | None:
    t = title.lower()
    for k, f in FAMILIES:
        if k in t:
            return f
    return None


def load_report(path: Path, start: str, end: str) -> list[dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    evs = d["EV"] if isinstance(d, dict) else d
    return [e for e in evs if start <= e["date"] <= end]


def compare(engine_events, report_events) -> dict:
    eng = defaultdict(list)
    rep = defaultdict(list)
    for e in engine_events:
        f = family(e.title)
        if f:
            eng[f].append(e)
    for r in report_events:
        f = family(r["title"])
        if f:
            rep[f].append(r)
    out = {"match": [], "amount_diff": [], "status_diff": [], "date_diff": [],
           "only_report": [], "only_engine": [], "unmapped_report": []}
    out["unmapped_report"] = [r for r in report_events if not family(r["title"])]
    for f in sorted(set(eng) | set(rep)):
        E = sorted(eng.get(f, []), key=lambda x: x.date)
        R = sorted(rep.get(f, []), key=lambda x: x["date"])
        used = set()
        for e in E:
            hit = next((i for i, r in enumerate(R) if i not in used and r["date"] == e.date), None)
            if hit is None:
                # nearest same-family event within 5 days counts as a date difference
                cand = [(abs((date.fromisoformat(r["date"]) - date.fromisoformat(e.date)).days), i)
                        for i, r in enumerate(R) if i not in used]
                cand = [c for c in cand if c[0] <= 5]
                if cand:
                    _, i = min(cand)
                    used.add(i)
                    out["date_diff"].append((f, e, R[i]))
                else:
                    out["only_engine"].append((f, e))
                continue
            used.add(hit)
            r = R[hit]
            out["match"].append((f, e, r))
            ra = r.get("amt")
            if (e.amount_cr or ra) and round(e.amount_cr or 0, 2) != round(ra or 0, 2):
                out["amount_diff"].append((f, e, r))
            if e.status != r.get("st", "").upper():
                out["status_diff"].append((f, e, r))
        out["only_report"] += [(f, r) for i, r in enumerate(R) if i not in used]
    return out


def summary_rows(res) -> list[tuple]:
    by = defaultdict(lambda: [0, 0, 0, 0, 0])
    for f, *_ in res["match"]:
        by[f][0] += 1
    for f, *_ in res["date_diff"]:
        by[f][1] += 1
    for f, *_ in res["amount_diff"]:
        by[f][2] += 1
    for f, *_ in res["only_report"]:
        by[f][3] += 1
    for f, *_ in res["only_engine"]:
        by[f][4] += 1
    return sorted((f, *v) for f, v in by.items())
