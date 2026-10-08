"""LabelDesk's background server on Windows (Startup folder + started by LabelDesk.pyw). No console window: output
goes to %LOCALAPPDATA%\\LabelDesk\\labeldesk.log (last ~1 MB kept)."""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "LabelDesk")
os.makedirs(log_dir, exist_ok=True)
log = os.path.join(log_dir, "labeldesk.log")
if os.path.exists(log) and os.path.getsize(log) > 1_000_000:
    os.replace(log, log + ".1")
sys.stdout = sys.stderr = open(log, "a", buffering=1, encoding="utf-8")
sys.path.insert(0, os.path.join(HERE, "server"))
os.chdir(HERE)
runpy.run_path(os.path.join(HERE, "server", "app.py"), run_name="__main__")
