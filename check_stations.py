# check_stations.py
from pathlib import Path
import yaml

cfg_path = Path("config/stations.yaml")
if not cfg_path.exists():
    print("❌ Файл config/stations.yaml не найден!")
    exit(1)

c = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
count = sum(len(r["stations"]) for r in c["regions"].values())
print(f"✅ OK: {count} станций по {len(c['regions'])} регионам")