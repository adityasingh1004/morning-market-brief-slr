"""Housekeeping for the Morning Market Brief - SLR report. Standard library only.

    python scripts/mmb.py init [--force]   copy the base report to your folder (first run)
    python scripts/mmb.py path             print where your working report is
    python scripts/mmb.py asof             print the report's "Data as of" date
    python scripts/mmb.py backup           save a dated copy before editing
    python scripts/mmb.py validate [FILE]  check the report before it is saved for the day
    python scripts/mmb.py restore          put back the latest backup (if validation fails)
    python scripts/mmb.py open             open the report in the browser

Your folder is ~/MorningMarketBrief (override with MMB_HOME).

Morning Market Brief - SLR. Copyright (C) 2026 Aditya Kumar Singh.
AGPL-3.0 with additional attribution terms (see ADDITIONAL-TERMS.md).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "report" / "base_report.html"
AUTHOR = "Aditya Kumar Singh"
NAME = "Morning Market Brief – SLR"
ATTR_ID = "mmb-attribution"
IST = timezone(timedelta(hours=5, minutes=30))


def home() -> Path:
    h = os.environ.get("MMB_HOME")
    return Path(h).expanduser() if h else Path.home() / "MorningMarketBrief"


def report_path() -> Path:
    return home() / "report.html"


def asof(text: str) -> str | None:
    m = re.search(r'const DATA_AS_OF="(\d{4}-\d{2}-\d{2})"', text)
    return m.group(1) if m else None


# ------------------------------------------------------------------ validation
def validate(text: str) -> list[str]:
    """Returns a list of problems; empty means the report may be saved."""
    errs = []
    # attribution (licence term: must be preserved)
    if f'id="{ATTR_ID}"' not in text or AUTHOR not in text or NAME not in text:
        errs.append("Attribution footer or author name missing (required by the licence terms).")
    if f'name="author" content="{AUTHOR}"' not in text:
        errs.append("Author meta tag missing.")
    # as-of date
    d = asof(text)
    today = datetime.now(IST).date()
    if not d:
        errs.append('DATA_AS_OF not found or not in "YYYY-MM-DD" form.')
    elif date.fromisoformat(d) > today:
        errs.append(f"DATA_AS_OF {d} is in the future.")
    # script must exist and be syntactically valid (Node, if installed)
    m = re.search(r"<script>(.*?)</script>", text, re.S)
    if not m or "const SRC={" not in m.group(1):
        errs.append("Main script or SRC sources object missing.")
        return errs
    js = m.group(1)
    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(js)
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        os.unlink(f.name)
        if r.returncode:
            errs.append("JavaScript syntax error: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    # status tags
    bad = sorted(set(re.findall(r'\bst:"([^"]*)"', js)) - {"v", "s", "u", "c"})
    if bad:
        errs.append(f"Unknown status tags {bad}: use v (Verified), s (Secondary), u (UNVERIFIED).")
    # every cited source exists
    a = js.find("const SRC={")
    b = js.find("\n};", a)
    keys = set(re.findall(r"^\s*([A-Za-z_][\w]*)\s*:\s*\{", js[a:b], re.M))
    used = set(re.findall(r'\bsrc:"([^"]+)"', js)) - {"none"}
    missing = sorted(used - keys)
    if missing:
        errs.append(f"Sources cited but not defined in SRC: {missing[:10]}{' …' if len(missing) > 10 else ''}")
    return errs


def warnings(text: str) -> list[str]:
    """Things worth a look that do not block saving."""
    w = []
    js = (re.search(r"<script>(.*?)</script>", text, re.S) or [None, ""])[1]
    for m in re.finditer(r'add\("(\d{4}-\d{2}-\d{2})","(\w+)","([^"]{0,60})[^"]*",\{[^}]*?st:"v",src:"none"', js):
        if "Quarter-end" not in m.group(3):
            w.append(f"{m.group(1)} {m.group(3)}: tagged Verified but cites no source.")
    return w


# ------------------------------------------------------------------ commands
def cmd_init(force=False):
    dst = report_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not force:
        print(f"Working report already exists: {dst} (Data as of {asof(dst.read_text(encoding='utf-8'))}).")
        print("Use --force to start again from the base report.")
        return
    shutil.copy2(BASE, dst)
    print(f"Copied the base report to {dst}. Data as of {asof(dst.read_text(encoding='utf-8'))}.")
    print("Next: run the daily update to bring it to today.")


def cmd_backup():
    src = report_path()
    if not src.exists():
        sys.exit("No working report yet: run `python scripts/mmb.py init` first.")
    hist = home() / "history"
    hist.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y%m%d-%H%M%S")
    dst = hist / f"report_{asof(src.read_text(encoding='utf-8'))}_{stamp}.html"
    shutil.copy2(src, dst)
    print(f"Backup saved: {dst}")


def cmd_restore():
    hist = sorted((home() / "history").glob("report_*.html"))
    if not hist:
        sys.exit("No backups found.")
    shutil.copy2(hist[-1], report_path())
    print(f"Restored {hist[-1].name} to {report_path()}")


def cmd_validate(path=None):
    p = Path(path) if path else report_path()
    errs = validate(p.read_text(encoding="utf-8"))
    if errs:
        print("VALIDATION FAILED:")
        for e in errs:
            print("  - " + e)
        sys.exit(1)
    for x in warnings(p.read_text(encoding="utf-8")):
        print("  note: " + x)
    print(f"OK: {p} passes all checks (Data as of {asof(p.read_text(encoding='utf-8'))}).")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "path"
    if cmd == "init":
        cmd_init("--force" in argv)
    elif cmd == "path":
        print(report_path())
    elif cmd == "asof":
        print(asof(report_path().read_text(encoding="utf-8")))
    elif cmd == "backup":
        cmd_backup()
    elif cmd == "restore":
        cmd_restore()
    elif cmd == "validate":
        cmd_validate(argv[1] if len(argv) > 1 else None)
    elif cmd == "open":
        webbrowser.open(report_path().resolve().as_uri())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
