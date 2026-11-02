"""Where the tool keeps its files.

Default data ships inside the package. Users edit their own copies in the home
folder (default ~/MorningMarketBrief; override with MMB_HOME). If a user
copy exists it wins; otherwise the packaged default is used.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PKG_DATA = Path(__file__).resolve().parent / "data"
DATA_FILES = ("seed_fy27_h2.json", "holidays_mumbai.json", "securities_due.csv")


def home() -> Path:
    h = os.environ.get("MMB_HOME")
    return Path(h).expanduser() if h else Path.home() / "MorningMarketBrief"


def out_dir() -> Path:
    p = home() / "feed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_file(name: str) -> Path:
    user = home() / "data" / name
    return user if user.exists() else PKG_DATA / name


def init_user_data(force: bool = False) -> list[str]:
    """Copy the default data files into the home folder so the user can edit them."""
    dst = home() / "data"
    dst.mkdir(parents=True, exist_ok=True)
    done = []
    for f in DATA_FILES:
        t = dst / f
        if force or not t.exists():
            shutil.copy2(PKG_DATA / f, t)
            done.append(str(t))
    return done
