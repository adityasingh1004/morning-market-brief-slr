# Morning Market Brief – SLR
# Copyright (C) 2026 Aditya Kumar Singh
# SPDX-License-Identifier: AGPL-3.0-only (with additional attribution terms, see ADDITIONAL-TERMS.md)
"""One-page daily digest: calendar plus what RBI actually published. Plain text and HTML."""
from __future__ import annotations

import html
from datetime import date, timedelta

from .engine import fmt_cr

CAT_NAME = {"gsec": "G-Sec", "tbill": "T-bill", "sdl": "SDL", "mat": "Redemption", "mpc": "RBI",
            "data": "Data", "tax": "Tax", "fiscal": "Fiscal", "other": "Other"}
DISCLAIMER = ("Compiled automatically from publicly available releases of the Reserve Bank of India and other "
              "Government of India bodies, which remain the property of their publishers. This digest is not affiliated "
              "with or endorsed by any of them, is not investment advice, and may contain parsing errors: verify every "
              "figure against the linked source before relying on it.")
STATIC_SOURCES = [
    ("RBI press releases (auction notices and results, money market operations, WSS extract)",
     "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"),
    ("RBI issuance calendars for dated securities, T-bills and SDLs", "https://www.rbi.org.in/"),
    ("RBI MPC meeting schedule", "https://www.rbi.org.in/"),
    ("MoSPI Advance Release Calendar", "https://www.mospi.gov.in/"),
    ("RBI holiday matrix", "https://rbi.org.in/Scripts/HolidayMatrixDisplay.aspx"),
]
PRIORITY = ["gsec", "tbill", "sdl", "mat", "mpc", "tax", "data", "fiscal", "other"]


# ------------------------------------------------------------ helpers
def _sel(events, d0: date, days: int):
    d1 = d0 + timedelta(days)
    return [e for e in events if d0.isoformat() <= e.date <= d1.isoformat()]


def _sort(evs):
    return sorted(evs, key=lambda e: (e.date, PRIORITY.index(e.cat), e.title))


def week_supply(evs):
    tot = {}
    for e in evs:
        if e.cat in ("gsec", "tbill", "sdl") and e.amount_cr and "settlement" not in e.title.lower():
            tot[e.cat] = tot.get(e.cat, 0) + e.amount_cr
        if e.cat == "mat" and e.amount_cr:
            tot["mat"] = tot.get("mat", 0) + e.amount_cr
    return tot


def latest(rbi, kind, since: date | None = None):
    for r in rbi:  # newest first
        if r.get("data") and r["data"].get("kind") == kind:
            if since and r.get("date") and r["date"] < since.isoformat():
                return None
            return r
    return None


def _d2(s):
    """'September 30, 2026' or 'Oct. 15, 2026' -> ISO, else unchanged."""
    from datetime import datetime
    for f in ("%B %d, %Y", "%b. %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(str(s), f).date().isoformat()
        except ValueError:
            pass
    return s


def fd(s):
    """2026-10-30 -> 30 Oct 2026; leaves other text alone."""
    try:
        return date.fromisoformat(str(s)).strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return str(s)


def pct(x, dp=4):
    return "-" if x is None else f"{x:.{dp}f}%"


def bn(usd_mn):
    return "-" if usd_mn is None else f"${usd_mn / 1000:,.2f} bn"


def chg_bn(usd_mn):
    return "-" if usd_mn is None else f"{'+' if usd_mn >= 0 else '−'}${abs(usd_mn) / 1000:,.2f} bn"


def lakh(cr):
    """₹ cr in lakh crore with sign, for liquidity lines."""
    return "-" if cr is None else f"{'+' if cr >= 0 else '−'}₹{abs(cr) / 100000:,.2f} lakh cr"


def _ref(r):
    return f"RBI PR {r['pr']}" if r.get("pr") else "RBI"


# ------------------------------------------------------------ sections (shared by text + html)
def sections(events, rbi, today: date):
    """Returns a list of (heading, [lines]) with plain strings; html escapes them later."""
    S = []
    look = today - timedelta(4)  # covers a weekend + holiday

    # 1. results
    res = []
    for kind, label in (("gsec_result", "G-Sec"), ("tbill_result", "T-bill"), ("sdl_result", "SDL")):
        r = latest(rbi, kind, look)
        if not r:
            continue
        d = r["data"]
        if kind == "sdl_result":
            res.append(f"SDL ({r['date']}): {d['n']} securities, cut-offs {pct(d['yield_min'], 2)} to "
                       f"{pct(d['yield_max'], 2)} · {_ref(r)}")
            continue
        for x in d["items"]:
            bc = f" · bid-cover {x['bid_cover']:.2f}x" if x.get("bid_cover") else ""
            dev = f" · devolvement {x['devolvement']}" if x.get("devolvement") else ""
            way = f" (WAY {pct(x['way'])})" if x.get("way") else ""
            res.append(f"{label} {x['security']}: cut-off {pct(x['cutoff_yield'])}{way}"
                       f" · {fmt_cr(x['notified_cr'])}{bc}{dev}")
        res.append(f"  Source: {_ref(r)}, {r['date']}")
    if res:
        S.append(("LATEST AUCTION RESULTS", res))

    # 2. notified for the coming days
    nt = []
    r = latest(rbi, "sdl_notice", look)
    if r:
        d = r["data"]
        top = ", ".join(f"{k} {fmt_cr(v)}" for k, v in list(d["states"].items())[:5])
        nt.append(f"SDL {d.get('auction') or ''}: {fmt_cr(d['total_cr'])} from {len(d['states'])} states/UTs, "
                  f"{d['n_securities']} securities. Largest: {top} · {_ref(r)}")
    r = latest(rbi, "tbill_notice", look)
    if r:
        d = r["data"]
        sp = ", ".join(f"{k} {fmt_cr(v)}" for k, v in d["split"].items())
        nt.append(f"T-bills {d.get('auction') or ''}: {fmt_cr(d['total_cr'])} ({sp}), settles {d.get('settle')} · {_ref(r)}")
    if nt:
        S.append(("NOTIFIED BY RBI", nt))

    # 3. liquidity
    r = latest(rbi, "mmo")
    if r:
        d = r["data"]
        li = [f"As on {d.get('as_on')}: net liquidity {lakh(d.get('net_liquidity_cr'))} "
              f"(+ injection / − absorption)",
              f"SDF {fmt_cr(d.get('sdf_cr'))} · MSF {fmt_cr(d.get('msf_cr'))}",
              f"Call WAR {pct(d.get('call_war'), 2)} (range {d.get('call_range')}) · "
              f"overnight WAR {pct(d.get('overnight_war'), 2)} · TREPS {pct(d.get('triparty_war'), 2)}"]
        if d.get("cash_balances_cr") and d.get("crr_requirement_cr"):
            li.append(f"Banks' cash with RBI {fmt_cr(d['cash_balances_cr'])} vs CRR requirement "
                      f"{fmt_cr(d['crr_requirement_cr'])}")
        if d.get("durable_liquidity_cr") is not None:
            li.append(f"Durable liquidity {lakh(d['durable_liquidity_cr'])} as on {d.get('durable_as_on')}")
        li.append(f"Source: {_ref(r)}")
        S.append(("LIQUIDITY", li))

    # 4. WSS
    r = latest(rbi, "wss")
    if r:
        d = r["data"]
        w = [f"Forex reserves {bn(d.get('fx_total_usd_mn'))} as on {d.get('fx_as_on')}, "
             f"{chg_bn(d.get('fx_week_chg_usd_mn'))} on the week "
             f"(FCA {chg_bn(d.get('fca_week_chg_usd_mn'))}, gold {chg_bn(d.get('gold_week_chg_usd_mn'))})"]
        if d.get("credit_yoy_pct") is not None:
            w.append(f"Bank credit {d['credit_yoy_pct']}% y/y · deposits {d.get('deposit_yoy_pct')}% y/y "
                     f"· M3 {d.get('m3_yoy_pct')}% y/y (as on {d.get('banks_as_on')})")
        if d.get("rbi_credit_govt_cr") is not None:
            w.append(f"Net RBI credit to Government {fmt_cr(d['rbi_credit_govt_cr'])}, "
                     f"fortnight change {fmt_cr(d.get('rbi_credit_govt_fortnight_chg_cr'))}")
        w.append(f"Source: {_ref(r)}, {r['date']}")
        S.append(("RBI WSS", w))

    # 5. other
    r = latest(rbi, "sgb", look)
    oth = []
    if r:
        oth.append(f"{r['data']['series']} premature redemption price ₹{r['data']['price']:,.0f}/unit · {_ref(r)}")
    shown = {"gsec_result", "tbill_result", "sdl_result", "sdl_notice", "tbill_notice", "mmo", "wss", "sgb"}
    for x in rbi:
        if x.get("date") and x["date"] >= look.isoformat() and not (x.get("data") and x["data"]["kind"] in shown):
            oth.append(f"{x['date']}: {x['title']}" + (f" · {_ref(x)}" if x.get('pr') else ""))
    if oth:
        S.append(("OTHER RBI RELEASES", oth))
    return S


def source_list(rbi):
    """Static sources plus every RBI release actually used in this digest."""
    used = []
    for kind in ("gsec_result", "tbill_result", "sdl_result", "sdl_notice", "tbill_notice", "mmo", "wss", "sgb"):
        r = latest(rbi, kind)
        if r and r.get("link"):
            used.append((f"RBI PR {r.get('pr') or ''}: {r['title']} ({r.get('date')})", r["link"]))
    return used + STATIC_SOURCES


def _line(e) -> str:
    amt = f" · {fmt_cr(e.amount_cr)}" if e.amount_cr else ""
    st = "" if e.state == "scheduled" else f" [{e.state.upper()}]"
    return f"  [{e.status}] {CAT_NAME[e.cat]}: {e.title}{amt}{st}"


# ------------------------------------------------------------ text
def text(events, today: date, rbi=None) -> str:
    rbi = rbi or []
    L = [f"TREASURY DIGEST · {today.strftime('%a %d %b %Y')}", "Compiled from public official releases", ""]
    for head, lines in sections(events, rbi, today):
        L += [head] + [f"  {x}" for x in lines] + [""]
    L.append("TODAY")
    L += [_line(e) for e in _sort(_sel(events, today, 0))] or ["  Nothing scheduled."]
    L += ["", "NEXT 7 DAYS"]
    cur = None
    for e in _sort(_sel(events, today + timedelta(1), 6)):
        if e.date != cur:
            cur = e.date
            L.append(f" {date.fromisoformat(cur).strftime('%a %d %b')}")
        L.append(_line(e))
    sup = week_supply(_sel(events, today, 6))
    L += ["", "SUPPLY, TODAY + 6 DAYS",
          f"  Dated G-Sec {fmt_cr(sup.get('gsec'))} · T-bills {fmt_cr(sup.get('tbill'))}"
          f" · SDL notified {fmt_cr(sup.get('sdl'))} · Redemptions {fmt_cr(sup.get('mat'))}"]
    fl = [e for e in _sel(events, today, 30) if e.flags]
    if fl:
        L += ["", "FLAGS (next 30 days)"] + [f"  {e.date} {e.title}: {'; '.join(e.flags)}" for e in _sort(fl)]
    L += ["", "Calendar status: V verified from primary release · S secondary · U rule-based, check manually.",
          "", "SOURCES"] + [f"  {t}: {u}" for t, u in source_list(rbi)] + ["", DISCLAIMER]
    return "\n".join(L)


# ------------------------------------------------------------ html
def html_page(events, today: date, rbi=None) -> str:
    rbi = rbi or []
    esc = html.escape
    look = today - timedelta(4)

    def src(r):
        if not r:
            return ""
        t = esc(_ref(r)) + (f", {esc(fd(r.get('date')))}" if r.get("date") else "")
        return f'<p class="src">Source: <a href="{esc(r.get("link") or "#")}">{t}</a></p>'

    def kpi(label, value, sub=""):
        return f'<div class="kpi"><span>{esc(label)}</span><b>{value}</b><em>{esc(sub)}</em></div>'

    blocks = []

    # ---- auction results
    rows, srcs = [], []
    for kind, label in (("gsec_result", "G-Sec"), ("tbill_result", "T-bill")):
        r = latest(rbi, kind, look)
        if not r:
            continue
        srcs.append(src(r))
        for x in r["data"]["items"]:
            bc = f"{x['bid_cover']:.2f}x" if x.get("bid_cover") else "-"
            rows.append(f"<tr><td>{label}</td><td class=sec>{esc(x['security'])}</td>"
                        f"<td class=n><b>{pct(x.get('cutoff_yield'))}</b></td><td class=n>{pct(x.get('way'))}</td>"
                        f"<td class=n>{fmt_cr(x.get('notified_cr'))}</td><td class=n>{bc}</td>"
                        f"<td>{esc(x.get('devolvement') or '-')}</td></tr>")
    r = latest(rbi, "sdl_result", look)
    if r:
        d = r["data"]
        srcs.append(src(r))
        rows.append(f"<tr><td>SDL</td><td class=sec>{d['n']} securities</td>"
                    f"<td class=n colspan=2><b>{pct(d['yield_min'], 2)} – {pct(d['yield_max'], 2)}</b></td>"
                    f"<td colspan=3></td></tr>")
    if rows:
        blocks.append(("results", "Latest auction results",
                       "<div class=tw><table class=grid><thead><tr><th></th><th>Security</th><th class=n>Cut-off</th>"
                       "<th class=n>WAY</th><th class=n>Notified</th><th class=n>Bid-cover</th><th>Devolvement</th>"
                       "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>" + "".join(srcs)))

    # ---- notified
    parts = []
    r = latest(rbi, "sdl_notice", look)
    if r:
        d = r["data"]
        mx = max(d["states"].values()) or 1
        bars = "".join(f'<div class=bar><span class=lab>{esc(k)}</span><span class=track><i style="width:{v / mx * 100:.1f}%"></i></span>'
                       f'<span class=val>{fmt_cr(v)}</span></div>' for k, v in d["states"].items())
        when = date.fromisoformat(d["auction"]).strftime("%a %d %b") if d.get("auction") else ""
        parts.append(f'<div class=sub><h3>SDL auction {esc(when)} · <b>{fmt_cr(d["total_cr"])}</b> · '
                     f'{len(d["states"])} states/UTs · {d["n_securities"]} securities</h3>{bars}{src(r)}</div>')
    r = latest(rbi, "tbill_notice", look)
    if r:
        d = r["data"]
        when = date.fromisoformat(d["auction"]).strftime("%a %d %b") if d.get("auction") else ""
        sp = "".join(kpi(k, fmt_cr(v)) for k, v in d["split"].items())
        parts.append(f'<div class=sub><h3>T-bill auction {esc(when)} · <b>{fmt_cr(d["total_cr"])}</b> · '
                     f'settles {esc(fd(d.get("settle")))}</h3><div class=kpis>{sp}</div>{src(r)}</div>')
    if parts:
        blocks.append(("notified", "Notified by RBI", "".join(parts)))

    # ---- liquidity
    r = latest(rbi, "mmo")
    if r:
        d = r["data"]
        nl = d.get("net_liquidity_cr")
        cls = ""
        k = [kpi("Net liquidity", f'<span class="{cls}">{lakh(nl)}</span>',
                 "net absorption by RBI (system in surplus)" if (nl or 0) < 0 else "net injection by RBI (system in deficit)"),
             kpi("SDF", fmt_cr(d.get("sdf_cr"))), kpi("MSF", fmt_cr(d.get("msf_cr"))),
             kpi("Call WAR", pct(d.get("call_war"), 2), d.get("call_range") or ""),
             kpi("Overnight WAR", pct(d.get("overnight_war"), 2)), kpi("TREPS WAR", pct(d.get("triparty_war"), 2))]
        if d.get("cash_balances_cr"):
            k.append(kpi("Banks' cash with RBI", fmt_cr(d["cash_balances_cr"]),
                         f"CRR requirement {fmt_cr(d.get('crr_requirement_cr'))}"))
        if d.get("durable_liquidity_cr") is not None:
            k.append(kpi("Durable liquidity", lakh(d["durable_liquidity_cr"]), f"as on {fd(_d2(d.get('durable_as_on')))}"))
        blocks.append(("liquidity", f"Liquidity · as on {fd(d.get('as_on'))}", f"<div class=kpis>{''.join(k)}</div>{src(r)}"))

    # ---- WSS
    r = latest(rbi, "wss")
    if r:
        d = r["data"]
        k = [kpi("Forex reserves", bn(d.get("fx_total_usd_mn")), f"{chg_bn(d.get('fx_week_chg_usd_mn'))} on the week · as on {fd(d.get('fx_as_on'))}"),
             kpi("Foreign currency assets", bn(d.get("fca_usd_mn")), f"{chg_bn(d.get('fca_week_chg_usd_mn'))} on the week"),
             kpi("Gold", bn(d.get("gold_usd_mn")), f"{chg_bn(d.get('gold_week_chg_usd_mn'))} on the week")]
        if d.get("credit_yoy_pct") is not None:
            k += [kpi("Bank credit", f"{d['credit_yoy_pct']}% y/y", f"as on {fd(_d2(d.get('banks_as_on')))}"),
                  kpi("Deposits", f"{d.get('deposit_yoy_pct')}% y/y"), kpi("M3", f"{d.get('m3_yoy_pct')}% y/y")]
        if d.get("rbi_credit_govt_cr") is not None:
            k.append(kpi("Net RBI credit to Govt", fmt_cr(d["rbi_credit_govt_cr"]),
                         f"fortnight {fmt_cr(d.get('rbi_credit_govt_fortnight_chg_cr'))}"))
        blocks.append(("wss", "RBI Weekly Statistical Supplement", f"<div class=kpis>{''.join(k)}</div>{src(r)}"))

    # ---- other releases
    oth = []
    r = latest(rbi, "sgb", look)
    if r:
        oth.append(f"<li>{esc(r['data']['series'] or 'SGB')} premature redemption price "
                   f"<b>₹{r['data']['price']:,.0f}</b>/unit · <a href=\"{esc(r.get('link') or '#')}\">{esc(_ref(r))}</a></li>")
    shown = {"gsec_result", "tbill_result", "sdl_result", "sdl_notice", "tbill_notice", "mmo", "wss", "sgb"}
    for x in rbi:
        if x.get("date") and x["date"] >= look.isoformat() and not (x.get("data") and x["data"]["kind"] in shown):
            oth.append(f"<li><a href=\"{esc(x.get('link') or '#')}\">{esc(x['title'])}</a> · {esc(str(x['date']))}</li>")
    if oth:
        blocks.append(("other", "Other RBI releases", "<ul class=plain>" + "".join(oth) + "</ul>"))

    # ---- calendar
    def rows_cal(evs):
        out = []
        for e in _sort(evs):
            amt = fmt_cr(e.amount_cr) if e.amount_cr else ""
            st = f' <span class="st">{e.state}</span>' if e.state != "scheduled" else ""
            fl = f'<div class="fl">{esc("; ".join(e.flags))}</div>' if e.flags else ""
            out.append(f"<tr><td class=d>{date.fromisoformat(e.date).strftime('%a %d %b')}</td>"
                       f"<td><span class='cat {e.cat}'>{CAT_NAME[e.cat]}</span></td>"
                       f"<td>{esc(e.title)}{st}{fl}</td><td class=n>{amt}</td>"
                       f"<td class=n><span class='b {e.status}'>{e.status}</span></td></tr>")
        return "".join(out) or '<tr><td colspan=5>Nothing scheduled.</td></tr>'

    sup = week_supply(_sel(events, today, 6))
    cal = (f"<div class=kpis>{kpi('Dated G-Sec', fmt_cr(sup.get('gsec')))}{kpi('T-bills', fmt_cr(sup.get('tbill')))}"
           f"{kpi('SDL notified', fmt_cr(sup.get('sdl')))}{kpi('Redemptions', fmt_cr(sup.get('mat')))}</div>"
           f"<div class=tw><table class=grid><tbody>{rows_cal(_sel(events, today, 7))}</tbody></table></div>"
           f"<p class=src>V = verified from the primary release · S = secondary · U = rule-based, check manually.</p>")
    blocks.append(("calendar", "Calendar · today and next 7 days", cal))

    body = "".join(f'<section class=card id="{bid}"><h2>{esc(h)}</h2>{b}</section>' for bid, h, b in blocks)
    srcs_html = "".join(f'<li><a href="{esc(u)}">{esc(t)}</a></li>' for t, u in source_list(rbi))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Treasury Digest {today}</title>
<style>
:root{{--ink:#14213A;--mut:#5C6878;--rule:#DDE2DA;--bg:#F2F4EF;--card:#fff;--soft:#EEF1EC;--acc:#1F6B57;--neg:#B3283B;--pos:#1F6B57;
--v:#1F6B57;--s:#9A6A12;--u:#B3283B;--bar:#2E7D68}}
@media(prefers-color-scheme:dark){{:root{{--ink:#E6EAF0;--mut:#9BA7B6;--rule:#2A3950;--bg:#0E1521;--card:#152031;--soft:#1B2A3F;--acc:#62B58D;--neg:#F06A7C;--pos:#62B58D;--v:#62B58D;--s:#E3A64A;--u:#F06A7C;--bar:#62B58D}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif;font-variant-numeric:tabular-nums}}
.w{{max-width:1040px;margin:0 auto;padding:22px 16px 40px}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:14px;border-bottom:3px solid var(--acc);padding-bottom:10px}}
header h1{{font-size:28px;margin:0;letter-spacing:-.01em}} header p{{margin:2px 0 0;color:var(--mut)}}
header .date{{font-size:15px;font-weight:600;text-align:right}}
.card{{background:var(--card);border:1px solid var(--rule);border-radius:12px;padding:14px 16px;margin:0 0 14px}}
.card h2{{font-size:13px;margin:0 0 10px;color:var(--acc);text-transform:uppercase;letter-spacing:.06em}}
.sub+.sub{{margin-top:14px;padding-top:12px;border-top:1px dashed var(--rule)}}
h3{{font-size:15px;font-weight:600;margin:0 0 8px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px}}
.kpi{{background:var(--soft);border-radius:8px;padding:9px 11px;min-width:0}}
.kpi>span{{display:block;font-size:12.5px;color:var(--mut)}} .kpi b{{display:block;font-size:20px;font-weight:700;margin-top:1px}}
.kpi em{{display:block;font-style:normal;font-size:12px;color:var(--mut)}}
.neg{{color:var(--neg)}} .pos{{color:var(--pos)}}
.tw{{overflow-x:auto}} table.grid{{border-collapse:collapse;width:100%;font-size:14px}}
.grid th{{font-size:12px;color:var(--mut);font-weight:600;text-align:left;padding:6px 8px;border-bottom:1px solid var(--rule)}}
.grid td{{padding:7px 8px;border-bottom:1px solid var(--rule);vertical-align:top}} .grid tr:last-child td{{border-bottom:0}}
.n{{text-align:right!important;white-space:nowrap}} td.d{{white-space:nowrap;color:var(--mut)}} td.sec{{font-weight:600}}
.bar{{display:grid;grid-template-columns:150px 1fr 110px;gap:10px;align-items:center;font-size:14px;margin:3px 0}}
.bar .track{{background:var(--soft);border-radius:4px;height:12px;overflow:hidden}} .bar i{{display:block;height:100%;background:var(--bar)}}
.bar .val{{text-align:right}}
.src{{font-size:12px;color:var(--mut);margin:8px 0 0}} .src a,a{{color:inherit}}
.b{{font-size:11px;font-weight:700;border:1px solid;border-radius:4px;padding:0 5px}}
.b.V{{color:var(--v)}} .b.S{{color:var(--s)}} .b.U{{color:#fff;background:var(--u);border-color:var(--u)}}
.cat{{font-size:12px;font-weight:600;color:var(--mut)}} .st{{font-size:11px;text-transform:uppercase;color:var(--v);font-weight:700;margin-left:4px}}
.fl{{font-size:12.5px;color:var(--s)}} ul.plain{{margin:0;padding-left:18px}} ul.plain li{{margin:3px 0}}
footer{{font-size:12px;color:var(--mut)}} .attr{{font-size:12.5px;color:var(--mut);margin:4px 2px 12px}} footer ul{{padding-left:18px}}
@media(max-width:560px){{.bar{{grid-template-columns:100px 1fr 90px}}}}
</style></head><body><div class="w">
<header><div><h1>Treasury Digest · India</h1><p>Compiled automatically from public official releases</p></div>
<div class="date">{today.strftime('%A')}<br>{today.strftime('%d %B %Y')}</div></header>
{body}
<p class="attr">Data: Reserve Bank of India press releases and official calendars, linked on each figure. Independent tool, not affiliated with RBI. Verify against the source.</p>
<footer><h2 style="font-size:13px;color:var(--acc);text-transform:uppercase;letter-spacing:.06em">Sources</h2><ul>{srcs_html}</ul>
<p>{esc(DISCLAIMER)}</p></footer>
</div></body></html>"""
