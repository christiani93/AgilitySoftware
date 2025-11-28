# apply_move_patches.py
# Verschiebt Patch-Skripte in patches_applied/
from pathlib import Path
import shutil, fnmatch

ROOT = Path(__file__).parent
DST = ROOT / "patches_applied"
DST.mkdir(exist_ok=True)

PATTERNS = ["apply_fix_*.py", "apply_create_*.py"]
moved = 0

for pat in PATTERNS:
    for p in ROOT.glob(pat):
        # sich selbst nicht verschieben
        if p.name == Path(__file__).name: 
            continue
        target = DST / p.name
        print(f"[MOVE] {p.name} -> {target}")
        shutil.move(str(p), str(target))
        moved += 1

print(f"[DONE] {moved} Datei(en) verschoben.")
