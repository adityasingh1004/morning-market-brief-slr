"""Reads the content of RBI press releases carried in the RSS feed.

Every number comes straight out of RBI's own HTML tables. Nothing is estimated.
If a table layout changes, the parser returns None for that release and the
digest falls back to the title and link, so a layout change never produces a wrong number.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path


# ------------------------------------------------------------ html tables
class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._stack, self._cell, self.text = [], [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack:
            if not self._stack[-1]:
                self._stack[-1].append([])
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack:
            self._stack[-1][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        self.text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def tables(html: str):
    p = _Tables()
    p.feed(html or "")
    return p.tables, " ".join(" ".join(p.text).split())


def num(s):
    if s is None:
        return None
    s = s.replace(",", "").replace("₹", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m and s not in ("-", "") else None


def pr_no(text):
    m = re.search(r"Press Release:\s*(\d{4}-\d{4}/\d+)", text)
    return m.group(1) if m else None


# ------------------------------------------------------------ parsers
def p_gsec_result(tbls, text):
    """Government Stock - Full Auction Results."""
    for t in tbls:
        hdr = next((r for r in t if r and r[0].startswith("Auction Results")), None)
        if not hdr:
            continue
        secs = hdr[1:]
        n = len(secs)

        def row(label):
            for i, r in enumerate(t):
                if any(label in c for c in r):
                    return i, r[-n:]
            return None, None

        out = [{"security": s} for s in secs]
        _, notified = row("Notified Amount")
        i_bids, _ = row("Competitive Bids Received")
        i_cut, cut = row("Cut-off price")
        i_way, way = row("Weighted Average Price")
        _, dev = row("Devolvement")
        _, pa = row("Partial Allotment Percentage of Competitive")
        bids = t[i_bids + 2][-n:] if i_bids is not None else [None] * n
        ytm = t[i_cut + 1][-n:] if i_cut is not None else [None] * n
        wy = t[i_way + 1][-n:] if i_way is not None else [None] * n
        for k, o in enumerate(out):
            o["notified_cr"] = num(notified[k]) if notified else None
            o["bids_cr"] = num(bids[k])
            o["cutoff_price"] = num(cut[k]) if cut else None
            o["cutoff_yield"] = num(ytm[k])
            o["way"] = num(wy[k])
            o["devolvement"] = dev[k] if dev else None
            o["partial_allotment"] = pa[k] if pa else None
            if o["notified_cr"] and o["bids_cr"]:
                o["bid_cover"] = round(o["bids_cr"] / o["notified_cr"], 2)
        return {"kind": "gsec_result", "items": out}
    return None


def p_tbill_result(tbls, text):
    """Treasury Bills: Full Auction Result (layout mirrors the G-Sec results table)."""
    for t in tbls:
        hdr = next((r for r in t if r and any("Day" in c for c in r[1:]) and len(r) >= 3), None)
        if not hdr or not any("Cut-off" in " ".join(r) for r in t):
            continue
        secs = [c for c in hdr if "Day" in c]
        n = len(secs)

        def find(label, offset=0):
            for i, r in enumerate(t):
                if any(label in c for c in r):
                    return t[i + offset][-n:] if i + offset < len(t) else None
            return None

        notified = find("Notified Amount")
        cut = find("Cut-off")
        bids_row = None
        for i, r in enumerate(t):
            if any("Competitive Bids Received" in c for c in r):
                bids_row = t[i + 2][-n:] if i + 2 < len(t) else None
                break
        ytm = None
        for i, r in enumerate(t):
            if any("Cut-off" in c for c in r):
                ytm = t[i + 1][-n:] if i + 1 < len(t) else None
                break
        out = []
        for k, s in enumerate(secs):
            o = {"security": s,
                 "notified_cr": num(notified[k]) if notified else None,
                 "cutoff_price": num(cut[k]) if cut else None,
                 "cutoff_yield": num(ytm[k]) if ytm and "%" in (ytm[k] or "") else None,
                 "bids_cr": num(bids_row[k]) if bids_row else None}
            if o["notified_cr"] and o["bids_cr"]:
                o["bid_cover"] = round(o["bids_cr"] / o["notified_cr"], 2)
            out.append(o)
        return {"kind": "tbill_result", "items": out}
    return None


def p_tbill_notice(tbls, text):
    m = re.search(r"Total\s+([\d,]+)", text)
    d = re.search(r"Notified Amount.*?(\w+ \d{1,2}, \d{4}) \((\w+)\)\s+(\w+ \d{1,2}, \d{4})", text)
    parts = re.findall(r"(91|182|364)-Day\s+([\d,]+)", text)
    if not parts:
        return None
    return {"kind": "tbill_notice", "total_cr": num(m.group(1)) if m else None,
            "auction": _d(d.group(1)) if d else None, "settle": _d(d.group(3)) if d else None,
            "split": {f"{a}D": num(b) for a, b in parts}}


def p_sdl_notice(tbls, text):
    agg = re.search(r"aggregate amount of ₹\s*([\d,]+)\s*Crore", text)
    dt = re.search(r"auction.*?on (\w+ \d{1,2}, \d{4})", text[text.find("Total"):] if "Total" in text else text)
    for t in tbls:
        if not t or not any("State/UT" in c for c in t[0]):
            continue
        states, cur = {}, None
        for r in t[1:]:
            if len(r) >= 6 and r[0].rstrip(".").isdigit():
                cur = r[1]
                amt = num(r[2])
            elif len(r) >= 4 and cur:
                amt = num(r[0])
            else:
                continue
            states[cur] = states.get(cur, 0) + (amt or 0)
        return {"kind": "sdl_notice", "total_cr": num(agg.group(1)) if agg else sum(states.values()),
                "states": dict(sorted(states.items(), key=lambda x: -x[1])),
                "n_securities": sum(1 for r in t[1:] if (len(r) >= 6 and r[0].rstrip(".").isdigit()) or (4 <= len(r) < 6)),
                "auction": _d(dt.group(1)) if dt else None}
    return None


def p_sdl_result(tbls, text):
    """Result of the auction of State Government Securities: cut-off yields by state."""
    rows = []
    for t in tbls:
        hdr = next((r for r in t if any("Cut" in c and "Yield" in c for c in r)), None)
        if not hdr:
            continue
        for r in t:
            ys = [c for c in r if re.fullmatch(r"\d{1,2}\.\d{2,4}", c or "")]
            if ys and len(r) >= 4:
                rows.append({"row": r, "cutoff_yield": float(ys[-1])})
    if not rows:
        return None
    ylds = [x["cutoff_yield"] for x in rows if 4 < x["cutoff_yield"] < 12]
    return {"kind": "sdl_result", "n": len(rows), "yield_min": min(ylds) if ylds else None,
            "yield_max": max(ylds) if ylds else None, "rows": rows}


def p_mmo(tbls, text, title=""):
    out = {"kind": "mmo"}
    m = re.search(r"as on (\w+ \d{1,2}, \d{4})", title)
    out["as_on"] = _d(m.group(1)) if m else None
    for t in tbls:
        for r in t:
            lab = r[0] if r else ""
            if lab.startswith("A. Overnight Segment"):
                out["overnight_war"] = num(r[2]); out["overnight_vol_cr"] = num(r[1])
            elif lab.startswith("I. Call Money"):
                out["call_war"] = num(r[2]); out["call_range"] = r[3]
            elif lab.startswith("II. Triparty Repo") and "triparty_war" not in out:
                out["triparty_war"] = num(r[2])
            elif lab.startswith("F. Net liquidity injected"):
                out["net_liquidity_cr"] = num(next((c for c in reversed(r) if c), None))
            elif lab.startswith("(i) Cash balances with RBI"):
                out["cash_balances_cr"] = num(r[-1])
            elif lab.startswith("(ii) Average daily cash reserve"):
                out["crr_requirement_cr"] = num(r[-1])
            elif lab.startswith("I. Net durable liquidity"):
                out["durable_liquidity_cr"] = num(r[-1]); out["durable_as_on"] = r[1] if len(r) > 2 else None
            elif lab.startswith("4. SDF") and len(r) >= 6:
                out["sdf_cr"] = (out.get("sdf_cr") or 0) + (num(r[4]) or 0)
            elif lab.startswith("3. MSF") and len(r) >= 6:
                out["msf_cr"] = (out.get("msf_cr") or 0) + (num(r[4]) or 0)
        # continuation rows under SDF/MSF have no label: count them
        cur = None
        for r in t:
            lab = r[0] if r else ""
            if lab.startswith("3. MSF"):
                cur = "msf_cr"
            elif lab.startswith("4. SDF"):
                cur = "sdf_cr"
            elif lab.startswith("5.") or lab.startswith("II."):
                cur = None
            elif cur and len(r) == 5 and re.match(r"\w{3}, \d\d/", lab):
                out[cur] = (out.get(cur) or 0) + (num(r[3]) or 0)
    return out if "net_liquidity_cr" in out or "call_war" in out else None


def p_wss(tbls, text):
    out = {"kind": "wss"}
    for t in tbls:
        if t and t[0] and t[0][0].startswith("2. Foreign Exchange Reserves"):
            asof = re.search(r"As on (\w+ \d{1,2}, \d{4})", " ".join(t[1]))
            out["fx_as_on"] = _d(asof.group(1)) if asof else None
            for r in t:
                if r and r[0].startswith("1 Total Reserves"):
                    out["fx_total_usd_mn"] = num(r[2]); out["fx_week_chg_usd_mn"] = num(r[4])
                elif r and r[0].startswith("1.1 Foreign Currency"):
                    out["fca_usd_mn"] = num(r[2]); out["fca_week_chg_usd_mn"] = num(r[4])
                elif r and r[0].startswith("1.2 Gold"):
                    out["gold_usd_mn"] = num(r[2]); out["gold_week_chg_usd_mn"] = num(r[4])
        if t and t[0] and t[0][0].startswith("4. Scheduled Commercial Banks"):
            for r in t:
                if r and r[0].startswith("2.1a Growth"):
                    out["deposit_yoy_pct"] = num(r[-1])
                elif r and r[0].startswith("7.1a Growth"):
                    out["credit_yoy_pct"] = num(r[-1])
            hd = next((" ".join(r) for r in t if r and "Outstanding as on" in " ".join(r)), "")
            m = re.search(r"as on (\w+\.? \d{1,2}, \d{4})", hd)
            out["banks_as_on"] = m.group(1) if m else None
        if t and t[0] and t[0][0].startswith("6. Money Stock"):
            for r in t:
                if r and r[0] == "M3":
                    out["m3_yoy_pct"] = num(r[-1])
                elif r and r[0].startswith("2.1.1 Reserve Bank"):
                    out["rbi_credit_govt_cr"] = num(r[2]); out["rbi_credit_govt_fortnight_chg_cr"] = num(r[3])
        if t and t[0] and t[0][0].startswith("8. Liquidity Operations"):
            days = [r for r in t if r and re.match(r"\d{2}-\w{3}-\d{2}", r[0])]
            out["liquidity_days"] = [(r[0], num(r[-1])) for r in days]
    return out if len(out) > 1 else None


def p_sgb(tbls, text):
    m = re.search(r"redemption price .*?shall be ₹\s*([\d,]+)", text)
    s = re.search(r"(SGB \d{4}-\d{2} Series [IVX]+)", text)
    return {"kind": "sgb", "series": s.group(1) if s else None, "price": num(m.group(1))} if m else None


def _d(s):
    for f in ("%B %d, %Y", "%b %d, %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(s.strip(), f).date().isoformat()
        except (ValueError, AttributeError):
            pass
    return None


ROUTES = [
    (r"^government stock - full auction result", p_gsec_result),
    (r"treasury bills?.*full auction result", p_tbill_result),
    (r"^auction of .*treasury bills", p_tbill_notice),
    (r"^result of .*state government securities|state government securities.*result", p_sdl_result),
    (r"^auction of state government securities", p_sdl_notice),
    (r"^money market operations", p_mmo),
    (r"weekly statistical supplement", p_wss),
    (r"sovereign gold bond.*redemption price", p_sgb),
]


def parse_item(item: dict) -> dict:
    title = item["title"]
    tbls, text = tables(item.get("html", ""))
    out = {"title": title, "link": item.get("link"), "date": item.get("date"), "pr": pr_no(text), "data": None}
    for rx, fn in ROUTES:
        if re.search(rx, title.lower()):
            try:
                out["data"] = fn(tbls, text, title) if fn is p_mmo else fn(tbls, text)
            except Exception as ex:  # never let one release break the digest
                out["error"] = f"{ex.__class__.__name__}: {ex}"
            break
    return out


# ------------------------------------------------------------ archive
def archive(items, folder: Path) -> list[dict]:
    """The feed only holds the latest ~10 releases, so every run keeps a copy.
    Returns all archived releases, newest first."""
    folder.mkdir(parents=True, exist_ok=True)
    for it in items:
        m = re.search(r"prid=(\d+)", it.get("link") or "")
        key = m.group(1) if m else re.sub(r"\W+", "_", it["title"])[:60]
        p = folder / f"{key}.json"
        if not p.exists():
            rec = dict(it)
            rec["date"] = it["date"].isoformat() if it.get("date") else None
            p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*.json")]
    return sorted(recs, key=lambda r: (r.get("date") or "", r.get("link") or ""), reverse=True)
