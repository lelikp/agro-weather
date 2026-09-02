import sys
import logging
from pathlib import Path
from datetime import datetime

import sqlite3
import json

from ecmwf.opendata import Client

import xarray as xr      
import pandas as pd      
import numpy as np 

# 1. Определяем корень проекта (на 1 уровень выше папки src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 2. Создаём нужные папки, если их ещё нет
(PROJECT_ROOT / "logs").mkdir(exist_ok=True)
(PROJECT_ROOT / "data").mkdir(exist_ok=True)
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 3. Настраиваем логирование: дублируем в консоль и в файл
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "logs" / "fetch_aifs.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Границы региона (N/W/S/E) для запроса AIFS
BBOX = {"north": -30.0, "west": -64.5, "south": -38.5, "east": -57.0}

def get_forecast_params():
    """Возвращает дату запуска, время и список шагов прогноза."""
    now_utc = datetime.utcnow()
    
    # Привязка к синоптическим срокам ECMWF: 00, 06, 12, 18
    run_hour = (now_utc.hour // 6) * 6
    run_date = now_utc.strftime("%Y%m%d")
    
    # Шаги: 0, 6, 12, ... 120 (всего 21 временной срез)
    steps = list(range(0, 121, 6))
    
    logger.info(f"📅 Прогноз: {run_date} {run_hour:02d} UTC | шагов: {len(steps)}")
    return run_date, run_hour, steps

# Путь к БД
DB_PATH = PROJECT_ROOT / "data" / "archive.db"

def init_db():
    """Создаёт таблицу для прогнозов, если её ещё нет."""
    schema = """
    CREATE TABLE IF NOT EXISTS forecast_grid (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT NOT NULL,
        run_time INTEGER NOT NULL,
        step_hours INTEGER NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        param TEXT NOT NULL DEFAULT '2t',
        value REAL,
        source TEXT DEFAULT 'aifs',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_run ON forecast_grid(run_date, run_time, step_hours);
    CREATE INDEX IF NOT EXISTS idx_point ON forecast_grid(lat, lon);
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(schema)
    logger.info(f"💾 БД готова: {DB_PATH}")

def download_aifs_mock(lat: float, lon: float, run_date: str, run_time: int, steps: list[int]) -> dict:
    """
    Тестовая заглушка: генерирует правдоподобные данные без реального API.
    Позволяет отладить весь пайплайн до записи в БД.
    """
    # Простая модель: температура растёт днём, падает ночью + случайный шум
    forecast = {}
    base_temp = 15.0  # базовая температура, °C
    
    for step in steps:
        # Суточный ход: минимум в 06 UTC (03 ART), максимум в 18 UTC (15 ART)
        hour_local = (run_time + step - 3) % 24  # сдвиг на UTC-3
        diurnal = -5 * (1 if 0 <= hour_local < 6 else -1 if 12 <= hour_local < 18 else 0)
        noise = (hash(f"{lat}{lon}{step}") % 100) / 50 - 1  # детерминированный "шум" ±1°
        forecast[str(step)] = round(base_temp + diurnal + step * 0.02 + noise, 1)
    
    return {
        "lat": lat, "lon": lon, "run_date": run_date, "run_time": run_time,
        "steps": steps, "forecast": forecast, "source": "aifs_mock"
    }

def save_to_db(data: dict):
    """Сохраняет прогноз в таблицу forecast_grid."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for step_str, value in data["forecast"].items():
            cursor.execute("""
                INSERT INTO forecast_grid 
                (run_date, run_time, step_hours, lat, lon, param, value, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["run_date"], data["run_time"], int(step_str),
                data["lat"], data["lon"], "2t", value, data["source"]
            ))
        conn.commit()
    logger.info(f"📥 Записано {len(data['forecast'])} значений в БД")

def download_aifs_real(run_date: str, run_time: int, steps: list[int], cache_dir: Path, param: str = "2t", publication_lag_hours: int = 7) -> list[Path]:
    """
    Скачивает AIFS single run: один файл на шаг.
    Учитывает лаг публикации: пробует запуск, который уже должен быть доступен.
    """
    from ecmwf.opendata import Client
    from datetime import datetime, timedelta
    import time
    
    # Вычисляем, какой запуск должен быть доступен сейчас
    now_utc = datetime.utcnow()
    latest_available_utc = now_utc - timedelta(hours=publication_lag_hours)
    
    # Привязываем к синоптическим срокам (0, 6, 12, 18)
    available_run_hour = (latest_available_utc.hour // 6) * 6
    available_run_date = latest_available_utc.strftime("%Y%m%d")
    
    # Список запусков для перебора: от наиболее свежего к старому
    attempts = []
    base_dt = datetime.strptime(f"{available_run_date}{available_run_hour:02d}", "%Y%m%d%H")
    for i in range(4):  # пробуем 4 последних запуска
        attempt_dt = base_dt - timedelta(hours=6*i)
        attempts.append((attempt_dt.strftime("%Y%m%d"), attempt_dt.hour))
    
    logger.info(f"🔍 Доступные запуски: {[f'{d}{t:02d}z' for d,t in attempts]}")
    
    downloaded_files = []
    
    for step in steps:
        step_downloaded = False
        
        for attempt_date, attempt_time in attempts:
            filename = cache_dir / f"aifs_single_fc_{param}_{attempt_date}_{attempt_time}z_step{step}.grib2"
            
            # Проверяем кэш
            if filename.exists() and filename.stat().st_size > 1024:
                logger.debug(f"♻️ В кэше: {filename.name}")
                downloaded_files.append(filename)
                step_downloaded = True
                break
            
            try:
                client = Client(source="ecmwf", model="aifs-single", resol="0p25")
                
                request = {
                    "date": attempt_date,
                    "time": attempt_time,
                    "type": "fc",
                    "step": step,
                    "param": param,
                }
                
                client.retrieve(request, str(filename))
                
                if filename.exists() and filename.stat().st_size > 1024:
                    size_kb = filename.stat().st_size / 1024
                    logger.info(f"✅ Шаг {step}ч ({attempt_date}{attempt_time:02d}z): {size_kb:.0f} KB")
                    downloaded_files.append(filename)
                    step_downloaded = True
                    break
                else:
                    if filename.exists():
                        filename.unlink()
                        
            except Exception as e:
                err_str = str(e).lower()
                if "404" in err_str or "not found" in err_str:
                    continue  # пробуем следующий запуск
                elif "403" in err_str or "forbidden" in err_str:
                    logger.error(f"❌ Доступ запрещён: проверьте лицензию")
                    break
                else:
                    logger.warning(f"⚠️ Ошибка: {e}")
                    continue
            
            time.sleep(0.3)
        
        if not step_downloaded:
            logger.warning(f"⚠️ Не удалось скачать шаг {step}ч")
    
    logger.info(f"📦 Скачано: {len(downloaded_files)}/{len(steps)} файлов")
    return downloaded_files

def parse_grib_and_save_single(grib_path: Path, run_date: str, run_time: int, step: int, bbox: dict):
    """
    Парсит ОДИН GRIB2-файл (один шаг), фильтрует по bbox, записывает в БД.
    Возвращает кол-во записанных строк.
    """
    logger.debug(f"🔍 Парсинг: {grib_path.name}")
    
    ds = xr.open_dataset(grib_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    
    # Фильтр по bbox
    mask_lat = (lats >= bbox["south"]) & (lats <= bbox["north"])
    mask_lon = (lons >= bbox["west"]) & (lons <= bbox["east"])
    
    lat_idx = np.where(mask_lat)[0]
    lon_idx = np.where(mask_lon)[0]
    
    if len(lat_idx) == 0 or len(lon_idx) == 0:
        logger.warning(f"⚠️ Нет точек в bbox для {grib_path.name}")
        return 0
    
    temp_c = ds["t2m"].values - 273.15  # K → °C
    
    records = []
    for li in lat_idx:
        for lo in lon_idx:
            val = temp_c[li, lo]
            if pd.isna(val):
                continue
            records.append((
                run_date, run_time, step,
                float(lats[li]), float(lons[lo]),
                "2t", float(val), "aifs"
            ))
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany("""
            INSERT INTO forecast_grid 
            (run_date, run_time, step_hours, lat, lon, param, value, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
    
    return len(records)

if __name__ == "__main__":
    logger.info("🚀 Запуск fetch_aifs.py (с учётом лага публикации)")
    
    init_db()
    
    # Динамическое вычисление параметров (как было изначально)
    run_date, run_time, steps = get_forecast_params()
    
    try:
        grib_files = download_aifs_real(run_date, run_time, steps, CACHE_DIR, param="2t")
        
        if not grib_files:
            logger.error("❌ Не скачано ни одного файла")
            sys.exit(1)
        
        total_records = 0
        for grib_file in grib_files:
            step = int(grib_file.stem.split("_step")[-1])
            count = parse_grib_and_save_single(grib_file, run_date, run_time, step, BBOX)
            total_records += count
        
        logger.info(f"✅ Всего записано: {total_records} значений")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        sys.exit(1)