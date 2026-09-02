from datetime import datetime

from pathlib import Path
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
DB_PATH = BASE_DIR / "data" / "archive.db"
OUTPUT_DIR = BASE_DIR / "output"

def get_active_phases(date_str, crops_cfg):
    dt = datetime.strptime(date_str, "%Y%m%d")
    current_md = dt.strftime("%m-%d")
    phases = {}
    for crop, cfg in crops_cfg.items():
        phases[crop] = "off_season"
        for phase, rng in cfg.items():
            start, end = rng["start"], rng["end"]
            if start > end:
                if current_md >= start or current_md <= end:
                    phases[crop] = phase; break
            else:
                if start <= current_md <= end:
                    phases[crop] = phase; break
    return phases