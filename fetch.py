#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_aifs.py — загрузка прогнозов AIFS из AWS S3 зеркала ECMWF.
- Прогон: последний доступный 12 UTC
- Сроки: +12 ... +84 часов (13 файлов)
- Формат: полные GRIB2 (~90 МБ), все параметры
- Зависимости: requests
"""

import sys
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta

import time

import os

# На GitHub (CI=true) не печатаем прогресс-бар: каждый тик становится отдельной строкой лога
QUIET = os.environ.get("CI") == "true"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Конфигурация
BASE_URL = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_latest_12z_run():
    """Возвращает (date, time) последнего доступного запуска 12 UTC."""
    now_utc = datetime.utcnow()
    if now_utc.hour >= 19:
        return now_utc.strftime("%Y%m%d"), 12
    else:
        return (now_utc - timedelta(days=1)).strftime("%Y%m%d"), 12

def download_step(run_date: str, run_time: int, step: int, max_retries: int = 5) -> bool:
    """Скачивает один шаг прогноза с поддержкой повторов при 503."""
    url = (f"{BASE_URL}/{run_date}/{run_time:02d}z/"
           f"aifs-single/0p25/oper/"
           f"{run_date}{run_time:02d}0000-{step}h-oper-fc.grib2")
    
    filename = f"aifs_single_fc_{run_date}_{run_time}z_step{step}.grib2"
    filepath = CACHE_DIR / filename

    if filepath.exists() and filepath.stat().st_size > 50_000_000:
        logger.info(f"♻️ Уже есть: {filename} ({filepath.stat().st_size/1024/1024:.1f} MB)")
        return True

    logger.info(f"📥 Скачиваю: {filename}...")
    
    # 🔑 Повторы с экспоненциальной задержкой для обработки 503
    for attempt in range(max_retries + 1):
        try:
            with requests.get(url, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get('content-length', 0))
                downloaded = 0
                
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0 and not QUIET:
                                pct = downloaded / total * 100
                                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                                sys.stdout.write(f"\r   📥 [{bar}] {pct:5.1f}% ({downloaded/1024/1024:.1f}/{total/1024/1024:.1f} MB)")
                                sys.stdout.flush()
                sys.stdout.write("\n")
                
            size_mb = filepath.stat().st_size / 1024 / 1024
            logger.info(f"✅ Готово: {filename} ({size_mb:.1f} MB)")
            return True
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 503 and attempt < max_retries:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                logger.warning(f"⚠️ 503 Slow Down — ждём {wait}с и пробуем ещё раз (попытка {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            logger.error(f"❌ Ошибка загрузки +{step}ч: {e}")
            if filepath.exists():
                filepath.unlink(missing_ok=True)
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сети +{step}ч: {e}")
            if filepath.exists():
                filepath.unlink(missing_ok=True)
            return False
    
    return False

def main():
    logger.info("🚀 Запуск fetch_aifs.py")
    
    run_date, run_time = get_latest_12z_run()
    logger.info(f"📅 Выбран прогон: {run_date} 12:00 UTC")
    
    steps = list(range(12, 85, 6))  # +12, +18, ..., +84 (13 файлов)
    logger.info(f"📋 Планируется скачать {len(steps)} файлов")
    
    success = 0
    for step in steps:
        if download_step(run_date, run_time, step):
            success += 1
            
    logger.info(f"🏁 Завершено: {success}/{len(steps)} файлов скачано успешно.")
    
    if success < len(steps):
        logger.warning("⚠️ Не все файлы загружены. Проверьте лог выше.")
        exit(1)
    exit(0)

if __name__ == "__main__":
    main()