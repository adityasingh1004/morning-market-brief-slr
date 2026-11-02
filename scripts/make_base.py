"""Builds the public base report from the author's live report.

    python scripts/make_base.py SOURCE.html [--out report/base_report.html]

What it does (and nothing else):
  * strips the hosting wrapper, if present, so the file opens on its own;
  * replaces the private "Prepared for ..." line with the public byline;
  * adds the author / licence attribution (title, meta tags, script banner, footer);
  * empties media-sourced (Secondary) market-strip series, so each user's first
    update fills them from their own sources; official series (US Treasury) stay;
  * makes the market strip render an empty series gracefully.

Morning Market Brief - SLR. Copyright (C) 2026 Aditya Kumar Singh.
Licensed under AGPL-3.0 with additional attribution terms (see ADDITIONAL-TERMS.md).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NAME = "Morning Market Brief – SLR"
AUTHOR = "Aditya Kumar Singh"
REPO = "https://github.com/{account}/morning-market-brief-slr"
ATTR_ID = "mmb-attribution"
BANNER = (f"/* {NAME} — created by {AUTHOR}. AGPL-3.0 with attribution terms "
          f"(ADDITIONAL-TERMS.md): this notice and the #{ATTR_ID} footer must be kept. */")


def footer(repo: str) -> str:
    return (f'<footer id="{ATTR_ID}" data-author="{AUTHOR}" style="max-width:1100px;margin:0 auto;padding:14px 16px 28px;'
            f'font-size:12.5px;color:var(--muted,#5E6A78);border-top:1px solid var(--rule,#D6DCD4)">'
            f'<b>{NAME}</b> · created by <b>{AUTHOR}</b> · '
            f'<a href="{repo}" style="color:inherit">{repo.replace("https://", "")}</a> · '
            f'Free software under AGPL-3.0 with attribution terms. Figures are tagged Verified / Secondary / '
            f'UNVERIFIED against their sources; check the source before relying on any figure. Not investment advice.</footer>')


def make_base(src: str, account: str = "YOUR-GITHUB-ACCOUNT") -> str:
    s = src
    # 1. hosting wrapper: keep the real document only
    i = s.find("<!DOCTYPE html>")
    if i > 0:
        s = s[i:]
    j = s.find("</html>")
    if j != -1:
        s = s[:j + len("</html>")] + "\n"

    # 2. byline
    s = re.sub(r"Prepared for [^.<]+\.", f"{NAME} · by {AUTHOR}.", s)

    # 3. attribution: title, meta, banner, footer (idempotent)
    s = re.sub(r"<title>.*?</title>", f"<title>{NAME} · FY 2026-27</title>", s, count=1, flags=re.S)
    if 'name="author"' not in s:
        s = s.replace('<meta charset="utf-8">',
                      f'<meta charset="utf-8">\n<meta name="author" content="{AUTHOR}">\n'
                      f'<meta name="generator" content="{NAME}">\n<meta name="license" content="AGPL-3.0 with attribution terms">', 1)
    if BANNER not in s:
        s = re.sub(r"<script>\s*\(function\(\)\{", lambda m: "<script>\n" + BANNER + "\n(function(){", s, count=1)
    repo = REPO.format(account=account)
    s = re.sub(rf'<footer id="{ATTR_ID}".*?</footer>\n?', "", s, flags=re.S)
    s = s.replace("</body>", footer(repo) + "\n</body>", 1)

    # 4. empty media-sourced market series
    a = s.find("const MKT=[")
    b = s.find("\n];", a)
    if a != -1 and b != -1:
        block = s[a:b]
        out = []
        for line in block.split("\n"):
            if 'st:"s"' in line and "pts:[" in line:
                line = re.sub(r"pts:\[\[.*?\]\]", "pts:[]", line)
                line = re.sub(r'note:"(?:[^"\\]|\\.)*"',
                              'note:"Not captured yet: filled by your first update run (media or vendor source, Secondary)."', line)
            out.append(line)
        s = s[:a] + "\n".join(out) + s[b:]

    # 5. render empty series gracefully
    guard = ('if(!o.pts.length)return `<div class="mk" title="${esc(o.note)}"><div class="nm">${esc(o.n)}</div>'
             '<div class="val">—</div><div class="dt">Filled on your first update run</div></div>`;\n    ')
    if guard not in s:
        s = s.replace("const n=o.pts.length,[d1,v1]=o.pts[n-1];", guard + "const n=o.pts.length,[d1,v1]=o.pts[n-1];", 1)
    return s


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "report" / "base_report.html"))
    p.add_argument("--account", default="YOUR-GITHUB-ACCOUNT", help="GitHub account that hosts the repo")
    a = p.parse_args(argv)
    out = make_base(Path(a.source).read_text(encoding="utf-8"), a.account)
    Path(a.out).write_text(out, encoding="utf-8")
    print(f"Base report written: {a.out} ({len(out):,} chars)")


if __name__ == "__main__":
    sys.exit(main())
