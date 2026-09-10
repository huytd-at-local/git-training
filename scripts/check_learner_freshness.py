"""Fail the independent freshness check without blocking Reading deployment."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(sys.argv[1])
target = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d")
stale = []
for mode in ("learner", "learner-responsive"):
    folder = root / "breviary/en" / mode
    page = folder / target / "index.html"
    if not page.is_file() or "var CIPHERTEXT" not in page.read_text():
        stale.append(mode)
    print(f"{mode}: requested {target}; dates {[p.name for p in folder.glob('????-??-??') if p.is_dir()]}")
if stale:
    raise SystemExit(f"Learner stale for {target}: {', '.join(stale)}")
