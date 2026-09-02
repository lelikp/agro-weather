#!/usr/bin/env python
import requests
import time
from pathlib import Path

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Гарантированно доступный запуск (вчера 18z)
BASE = "https://data.ecmwf.int/forecasts/20260512/18z"

# Файлы для теста
FILES = [
    f"{BASE}/aifs-single/0p25/oper/20260512180000-0h-oper-fc.grib2",
    # IFS почва (для сравнения, если AIFS не отдаёт vsw)
    f"{BASE}/ifs/0p25/oper/20260512180000-0h-oper-fc.grib2" 
]

print("📥 Скачиваем тестовые файлы...")
for url in FILES:
    fname = url.split("/")[-1]
    dest = CACHE_DIR / fname
    if dest.exists() and dest.stat().st_size > 1024:
        print(f"♻️ Уже есть: {fname} ({dest.stat().st_size/1024:.0f} KB)")
        continue
        
    try:
        print(f"⬇️ {fname}...")
        r = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        print(f"✅ {fname} ({dest.stat().st_size/1024:.0f} KB)")
    except Exception as e:
        print(f"❌ Ошибка {fname}: {e}")
    
    time.sleep(30)  # защита от 429

print("\n📁 Файлы сохранены в data/cache/")