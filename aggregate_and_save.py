#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggregate_and_save.py — Агрегация сетки, расчет дельт, запись в SQLite.
- Группирует 253k точек -> ~700 агрегатов/запуск
- Считает delta_6h для tp, cp (пропускает шаг +12 ТОЛЬКО для осадков)
- Конвертирует время в UTC-3 (Аргентина)
- Атомарно обновляет data/archive.db, удаляет сырой CSV
"""

import logging
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

PROCESSED_DIR = Path("data/processed")
DB_PATH = Path("data/archive.db")
REGION = "pampa_umedа"
TZ_ARGENTINA = -3  # UTC-3

# === НОВОЕ: Загрузка регионов из stations.yaml ===
STATIONS_PATH = Path("config/stations.yaml")
with open(STATIONS_PATH, encoding="utf-8") as f:
    stations_cfg = yaml.safe_load(f)

all_stations = []
for region_id, region in stations_cfg.get("regions", {}).items():
    for st in region.get("stations", []):
        all_stations.append({
            "region": region_id,
            "lat": st["lat"],
            "lon": st["lon"],
        })

def assign_region(lat, lon):
    """Находит регион по ближайшей станции."""
    min_dist = float("inf")
    best_region = "pampa_umeda"
    for st in all_stations:
        d = (lat - st["lat"])**2 + (lon - st["lon"])**2
        if d < min_dist:
            min_dist = d
            best_region = st["region"]
    return best_region

def main():
    csv_files = sorted(PROCESSED_DIR.glob("forecast_*.csv"))
    if not csv_files:
        logger.warning("❌ Нет CSV файлов в data/processed/")
        return

    csv_path = csv_files[-1]
    logger.info(f"📊 Агрегация: {csv_path.name}")
    df = pd.read_csv(csv_path)

    # === НОВОЕ: Присваиваем region каждой точке ===
    df['region'] = df.apply(lambda r: assign_region(r['lat'], r['lon']), axis=1)

    # Агрегация по всему bbox (для алертов)
    agg_all = df.groupby(['run_date', 'run_time', 'step', 'param'])['value'].agg(['mean', 'max', 'min', 'std']).reset_index()
    agg_all['region'] = 'pampa_umeda'

    # Агрегация по регионам (для сводки)
    agg_regions = df.groupby(['run_date', 'run_time', 'step', 'param', 'region'])['value'].agg(['mean', 'max', 'min', 'std']).reset_index()

    # Объединяем
    agg = pd.concat([agg_all, agg_regions], ignore_index=True)
    
    # Диагностика: какие шаги есть в CSV
    unique_steps = sorted(df['step'].unique())
    logger.info(f"🔢 Уникальные шаги в CSV: {unique_steps}")
    logger.info(f"📋 Уникальные параметры: {sorted(df['param'].unique())}")

    # 1. Агрегация по шагу и параметру (mean, max, min по bbox)
    # agg = df.groupby(['run_date', 'run_time', 'step', 'param'])['value'].agg(['mean', 'max', 'min']).reset_index()
    # agg = df.groupby(['run_date', 'run_time', 'step', 'param'])['value'].agg(['mean', 'max', 'min', 'std']).reset_index()

    run_date = agg['run_date'].iloc[0]
    run_time = agg['run_time'].iloc[0]
    launch_utc = datetime.strptime(f"{run_date} {run_time:02d}:00", "%Y%m%d %H:%M")

    records = []
    skipped_steps = set()
    
    for _, row in agg.iterrows():
        step = row['step']
        param = row['param']

        # Пропускаем базовый срез +12ч ТОЛЬКО для осадков (tp, cp), потому что они кумулятивные
        if step == 12 and param in ['tp', 'cp']:
            skipped_steps.add(step)
            continue

        # Временные интервалы прогноза (Аргентина UTC-3)
        start_utc = launch_utc + timedelta(hours=step - 6)
        end_utc   = launch_utc + timedelta(hours=step)
        start_arg = start_utc + timedelta(hours=TZ_ARGENTINA)
        end_arg   = end_utc   + timedelta(hours=TZ_ARGENTINA)

        if param in ['tp', 'cp']:
            # 1. Дельта за 6 часов (разность средних значений по региону)
            prev_mean = agg[(agg['param'] == param) & (agg['step'] == step - 6) & (agg['region'] == row['region'])]['mean']
            delta = row['mean'] - prev_mean.iloc[0] if not prev_mean.empty else row['mean']
            records.append((run_date, run_time, step,
                            start_arg.strftime('%Y-%m-%d %H:%M'),
                            end_arg.strftime('%Y-%m-%d %H:%M'),
                            row['region'], param, 'delta_6h', round(delta, 3)))

            # 2. НОВОЕ: Вероятность по методу окрестностей (Neighborhood Method)
            step_data = df[(df['step'] == step) & (df['param'] == param) & (df['region'] == row['region'])].copy()
            
            if not step_data.empty and param == 'tp':
                # Радиус ~40-45 км. На широте 35°S, 0.4 градуса ≈ 44 км по меридиану 
                # и ≈ 36 км по параллели. Это идеальный размер "коробки" для сглаживания 
                # пространственной ошибки AIFS на 72 часа.
                bin_size = 0.4
                step_data['lat_bin'] = (step_data['lat'] / bin_size).round() * bin_size
                step_data['lon_bin'] = (step_data['lon'] / bin_size).round() * bin_size
                
                # Общее количество уникальных "коробок" (окрестностей) в нашем bbox
                total_bins = step_data.drop_duplicates(subset=['lat_bin', 'lon_bin']).shape[0]
                
                # Находим точки с осадками > 0.1 мм
                wet_points = step_data[step_data['value'] > 0.1]
                
                # Считаем уникальные "коробки", в которых есть хотя бы одна "мокрая" точка
                wet_bins = wet_points.drop_duplicates(subset=['lat_bin', 'lon_bin']).shape[0]
                
                # Вероятность = доля "мокрых" окрестностей от общего числа окрестностей
                prob = (wet_bins / total_bins) * 100 if total_bins > 0 else 0.0
            else:
                prob = 0.0
                
            records.append((run_date, run_time, step,
                            start_arg.strftime('%Y-%m-%d %H:%M'),
                            end_arg.strftime('%Y-%m-%d %H:%M'),
                            row['region'], param, 'prob', int(round(prob)))) # Сохраняем как целое число

        # else:
        #     # Для остальных параметров сохраняем mean, max, min
        #     for stat in ['mean', 'max', 'min']:
        #         records.append((run_date, run_time, step,
        #                         start_arg.strftime('%Y-%m-%d %H:%M'),
        #                         end_arg.strftime('%Y-%m-%d %H:%M'),
        #                         REGION, param, stat, round(row[stat], 3)))
        else:
            # Для остальных параметров сохраняем mean, max, min, std
            for stat in ['mean', 'max', 'min', 'std']:
                val = row[stat]
                if pd.isna(val): val = 0.0  # std может быть NaN если все значения одинаковы
                records.append((run_date, run_time, step,
                                start_arg.strftime('%Y-%m-%d %H:%M'),
                                end_arg.strftime('%Y-%m-%d %H:%M'),
                                row['region'], param, stat, round(val, 3)))

    if skipped_steps:
        logger.info(f"⏭️ Пропущены шаги {skipped_steps} для tp/cp (базовый срез)")

    # 2. Запись в SQLite (UPSERT)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # conn.execute("""CREATE TABLE IF NOT EXISTS forecasts_agg (
    #     id INTEGER PRIMARY KEY,
    #     run_date TEXT, run_time INT, step INT,
    #     interval_start TEXT, interval_end TEXT,
    #     region TEXT, param TEXT, stat_type TEXT, value REAL,
    #     UNIQUE(run_date, run_time, step, param, stat_type))""")

    conn.execute("""CREATE TABLE IF NOT EXISTS forecasts_agg (
                 id INTEGER PRIMARY KEY,
                 run_date TEXT, run_time INT, step INT,
                 interval_start TEXT, interval_end TEXT,
                 region TEXT, param TEXT, stat_type TEXT, value REAL,
                 UNIQUE(run_date, run_time, step, param, stat_type, region))""")

    conn.executemany("""INSERT OR REPLACE INTO forecasts_agg
        (run_date, run_time, step, interval_start, interval_end, region, param, stat_type, value)
        VALUES (?,?,?,?,?,?,?,?,?)""", records)
    conn.commit()

    logger.info(f"💾 Записано {len(records)} агрегатов в {DB_PATH.name}")
    
    if len(records) == 0:
        logger.warning("⚠️ ВНИМАНИЕ: Записано 0 агрегатов! Проверьте, есть ли в CSV шаги кроме 12.")
    
    logger.info("🧹 Удаляю исходный CSV...")
    csv_path.unlink(missing_ok=True)
    logger.info("✅ Пайплайн завершен. Данные готовы к алертам.")

if __name__ == "__main__":
    main()