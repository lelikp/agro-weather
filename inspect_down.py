#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inspect_grib.py — быстрая инспекция первого скачанного GRIB2.
Показывает, как cfgrib разбивает файл на наборы, какие переменные доступны, их shape/units/coords.
"""

import sys
from pathlib import Path
import cfgrib

CACHE_DIR = Path("data/cache")
grib_files = sorted(CACHE_DIR.glob("*.grib2"))

if not grib_files:
    print("❌ Нет GRIB2 файлов в data/cache/")
    sys.exit(1)

target = grib_files[0]
print(f"🔍 Инспекция: {target.name}\n")

try:
    datasets = cfgrib.open_datasets(str(target), backend_kwargs={"indexpath": ""})
except Exception as e:
    print(f"❌ Ошибка чтения cfgrib: {e}")
    sys.exit(1)

print(f"📦 Файл автоматически разбит на {len(datasets)} наборов (по уровням/typeOfLevel)\n")

for i, ds in enumerate(datasets):
    print(f"--- Набор {i+1} ---")
    print(f"📊 Переменные: {list(ds.data_vars)}")
    print(f"📍 Координаты: {list(ds.coords)}")
    for var in ds.data_vars:
        arr = ds[var]
        units = arr.attrs.get("units", "—")
        long_name = arr.attrs.get("longName", arr.attrs.get("GRIB_name", "—"))
        print(f"  🔹 {var:8} | shape={str(arr.shape):12} | dtype={arr.dtype} | units={units} | name={long_name}")
        if arr.ndim <= 2:
            sample = arr.values.flatten()[:3]
            print(f"        sample: {sample}")
    print()