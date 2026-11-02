# Morning Market Brief – SLR
# Copyright (C) 2026 Aditya Kumar Singh
# SPDX-License-Identifier: AGPL-3.0-only (with additional attribution terms, see ADDITIONAL-TERMS.md)
"""Daily scheduling: Windows Task Scheduler, or cron on macOS/Linux.

Weekdays only. Default 09:15 local time, because RBI posts the previous day's
money market operations at about 09:00 IST.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from .paths import out_dir

TASK_NAME = "Morning Market Brief SLR - feed"
CRON_TAG = "# morning-market-brief-slr"
PKG_PARENT = Path(__file__).resolve().parent.parent


def _python(windowless: bool) -> str:
    exe = Path(sys.executable)
    if windowless and os.name == "nt":
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(exe)


def windows_xml(hhmm: str, open_browser: bool = True) -> str:
    args = "-m mmb_feed digest" + (" --open" if open_browser else "")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Builds the Morning Market Brief – SLR (RBI feed helper) from public RBI releases on weekday mornings.</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{date.today().isoformat()}T{hhmm}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek><Monday/><Tuesday/><Wednesday/><Thursday/><Friday/></DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(_python(windowless=True))}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(PKG_PARENT))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def cron_line(hhmm: str) -> str:
    h, m = hhmm.split(":")
    log = out_dir() / "scheduled.log"
    return (f'{int(m)} {int(h)} * * 1-5 cd "{PKG_PARENT}" && "{_python(False)}" -m mmb_feed digest '
            f'>> "{log}" 2>&1 {CRON_TAG}')


def install(hhmm: str = "09:15", open_browser: bool = True) -> str:
    if not (len(hhmm) == 5 and hhmm[2] == ":" and hhmm.replace(":", "").isdigit()):
        raise ValueError("Time must be HH:MM, e.g. 09:15")
    if os.name == "nt":
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
            f.write(windows_xml(hhmm, open_browser))
            xml = f.name
        try:
            r = subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml, "/F"],
                               capture_output=True, text=True)
        finally:
            os.unlink(xml)
        if r.returncode:
            raise RuntimeError(r.stderr.strip() or r.stdout.strip())
        return (f"Scheduled '{TASK_NAME}' for {hhmm} on weekdays. If the laptop is off or asleep then, "
                f"it runs as soon as it wakes. Manage it in Task Scheduler.")
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    lines = [ln for ln in current.splitlines() if CRON_TAG not in ln] + [cron_line(hhmm)]
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    return f"Added a cron entry for {hhmm} on weekdays. Output goes to {out_dir()}."


def remove() -> str:
    if os.name == "nt":
        r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
        return "Removed the scheduled task." if r.returncode == 0 else (r.stderr.strip() or "No task found.")
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    keep = [ln for ln in current.splitlines() if CRON_TAG not in ln]
    subprocess.run(["crontab", "-"], input="\n".join(keep) + ("\n" if keep else ""), text=True, check=True)
    return "Removed the cron entry."
