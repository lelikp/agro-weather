#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_grib.py — извлечение параметров + 7 прокси-индексов гроз.
- Промежуточные логи на каждом этапе (видно прогресс)
- Оптимизирована сборка записей (в 3-5x быстрее)
- Индексы считаются на сетке ДО агрегации
"""

import logging
import numpy as np
import pandas as pd
import cfgrib
from pathlib import Path

import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")
OUTPUT_DIR = Path("data/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BBOX = {"lat": (-38.5, -30.0), "lon": (-64.5, -57.0)}

def parse_meta(parts):
    run_date = next(p for p in parts if re.fullmatch(r"\d{8}", p))
    run_time = int(next(p for p in parts if re.fullmatch(r"\d{1,2}z", p))[:-1])
    step = int(next(p for p in parts if p.startswith("step")).replace("step", "").split(".")[0])
    return {"run_date": run_date, "run_time": run_time, "step": step}

# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================
def q_to_td(q_kgkg, p_pa):
    """Быстрая аппроксимация точки росы по удельной влажности и давлению."""
    e = q_kgkg * p_pa / (0.62198 + q_kgkg)
    e = np.clip(e, 1.0, None)
    return 243.5 * np.log(e / 610.94) / (17.67 - np.log(e / 610.94))

def safe_select(ds, var, coord, target_val):
    """Безопасный выбор уровня."""
    if ds is None or var not in ds: return None
    if coord not in ds.coords: return ds[var].values if ds[var].ndim == 2 else None
    levels = ds[coord].values
    if target_val in levels:
        return ds[var].sel({coord: target_val}).values
    idx = np.argmin(np.abs(levels - target_val))
    return ds[var].isel({coord: idx}).values

# ==============================================================================
# ОСНОВНАЯ ОБРАБОТКА
# ==============================================================================
def process_file(filepath: Path) -> list[dict]:
    records = []
    # try:
    #     logger.info(f"  📖 Открытие GRIB2...")
    #     datasets = cfgrib.open_datasets(str(filepath), backend_kwargs={"indexpath": ""})
    # except Exception as e:
    #     logger.error(f"❌ Ошибка чтения {filepath.name}: {e}")
    #     return records

    # # Поиск датасетов по координатам
    # iso_ds = next((ds for ds in datasets if "isobaricInhPa" in ds.coords), None)
    # soil_ds = next((ds for ds in datasets if "soilLayer" in ds.coords), None)

    try:
        logger.info(f"  📖 Открытие GRIB2...")
        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: игнорируем конфликты метаданных AIFS
        datasets = cfgrib.open_datasets(
            str(filepath), 
            backend_kwargs={
                "indexpath": "",
                "ignore_keys": ["heightAboveGround", "stepType"]
            }
        )
    except Exception as e:
        logger.error(f"❌ Ошибка чтения {filepath.name}: {e}")
        return records

    # Поиск датасетов по координатам (теперь они загрузятся корректно)
    iso_ds = next((ds for ds in datasets if "isobaricInhPa" in ds.coords), None)
    soil_ds = next((ds for ds in datasets if "soilLayer" in ds.coords), None)

    # Маска BBOX
    lats = datasets[0].latitude.values
    lons = datasets[0].longitude.values
    lon_g, lat_g = np.meshgrid(lons, lats)
    mask = (lat_g >= BBOX["lat"][0]) & (lat_g <= BBOX["lat"][1]) & \
           (lon_g >= BBOX["lon"][0]) & (lon_g <= BBOX["lon"][1])
    
    lats_m, lons_m = lat_g[mask], lon_g[mask]
    logger.info(f"  🎯 BBOX применён: {mask.sum()} точек для обработки")

    # 1. Базовые параметры
    logger.info("  🔹 1/4 Извлечение базовых и приземных параметров...")
    def get_var(v):
        for ds in datasets:
            if ds == iso_ds or ds == soil_ds: continue
            if v in ds:
                return ds[v].values[mask] if ds[v].ndim == 2 else None
        return np.full(mask.sum(), np.nan)

    tcc  = get_var("tcc")
    tcw  = get_var("tcw")
    tp   = get_var("tp")
    cp   = get_var("cp")
    sp   = get_var("sp") / 100.0
    ssrd = get_var("ssrd") / 1e6
    t2m = get_var("t2m") - 273.15
    d2m = get_var("d2m") - 273.15
    u10 = get_var("u10")
    v10 = get_var("v10")

    # 2. Изобарические уровни (С ПОЛНОЙ ДИАГНОСТИКОЙ)
    logger.info("  🔹 2/4 Изобарические уровни (850/700/500 hPa)...")
    
    # Ищем датасеты явно по наличию переменных
    iso_ds = next((ds for ds in datasets if "isobaricInhPa" in ds.coords and "t" in ds), None)
    q_ds = next((ds for ds in datasets if "isobaricInhPa" in ds.coords and "q" in ds), None)
    
    if iso_ds is None:
        logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Не найден датасет с температурой (t)!")
    if q_ds is None:
        logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Не найден датасет с влажностью (q)! Индексы будут NaN.")
    else:
        logger.info(f"    ✅ Датасет с 'q' найден! Доступные уровни: {sorted(q_ds['isobaricInhPa'].values)}")

    # Извлекаем T
    t850 = safe_select(iso_ds, "t", "isobaricInhPa", 850.0) if iso_ds else None
    t700 = safe_select(iso_ds, "t", "isobaricInhPa", 700.0) if iso_ds else None
    t500 = safe_select(iso_ds, "t", "isobaricInhPa", 500.0) if iso_ds else None
    
    # Извлекаем Q
    q850 = safe_select(q_ds, "q", "isobaricInhPa", 850.0) if q_ds else None
    q700 = safe_select(q_ds, "q", "isobaricInhPa", 700.0) if q_ds else None
    q500 = safe_select(q_ds, "q", "isobaricInhPa", 500.0) if q_ds else None
    
    # Отладка: проверяем, загрузились ли данные Q до применения маски
    if q850 is not None:
        logger.info(f"    📊 q850 до маски: shape={q850.shape}, min={np.nanmin(q850):.5f}, max={np.nanmax(q850):.5f}")
    else:
        logger.warning("    ⚠️ q850 равен None!")

    # Извлекаем U, V
    u850 = safe_select(iso_ds, "u", "isobaricInhPa", 850.0) if iso_ds else None
    v850 = safe_select(iso_ds, "v", "isobaricInhPa", 850.0) if iso_ds else None
    u700 = safe_select(iso_ds, "u", "isobaricInhPa", 700.0) if iso_ds else None
    v700 = safe_select(iso_ds, "v", "isobaricInhPa", 700.0) if iso_ds else None

    # Функция применения маски с защитой от ошибок размерности
    def am(arr): 
        if arr is None: 
            return np.full(mask.sum(), np.nan)
        # Убедимся, что массив 2D и совпадает с формой маски
        if arr.shape == lat_g.shape:
            return arr[mask]
        else:
            logger.warning(f"    ⚠️ Размерность массива {arr.shape} не совпадает с маской {lat_g.shape}. Заполняю NaN.")
            return np.full(mask.sum(), np.nan)

    t850, t700, t500 = [am(a) - 273.15 if a is not None else np.full(mask.sum(), np.nan) for a in (t850, t700, t500)]
    q850, q700, q500, u850, v850, u700, v700 = [am(a) for a in (q850, q700, q500, u850, v850, u700, v700)]

    # # 3. Индексы
    # logger.info("  🔹 3/4 Расчет 7 прокси-индексов гроз...")
    # td850 = q_to_td(q850, 85000.0) if not np.all(np.isnan(q850)) else np.full_like(q850, np.nan)
    # td700 = q_to_td(q700, 70000.0) if not np.all(np.isnan(q700)) else np.full_like(q700, np.nan)
    # td500 = q_to_td(q500, 50000.0) if not np.all(np.isnan(q500)) else np.full_like(q500, np.nan)

    # li_proxy     = t2m - t500
    # k_index      = (t850 - t500) + td850 - (t700 - td700)
    # tt_index     = (t850 - t500) + (td850 - td500)
    # cape_proxy   = (t2m - t500) * q850 * 100.0
    # cin_proxy    = np.maximum(0, t850 - t2m) + (t2m - d2m)
    # shear_0_3km  = np.sqrt((u850 - u10)**2 + (v850 - v10)**2)
    # moisture_av  = tcw

        # 3. Индексы (Физически корректный упрощённый расчёт)
    logger.info("  🔹 3/4 Расчет метеорологических индексов (LI, CAPE, CIN, TT, K, Shear)...")
    
    # Точка росы на уровнях
    td850 = q_to_td(q850, 85000.0) if not np.all(np.isnan(q850)) else np.full_like(q850, np.nan)
    td700 = q_to_td(q700, 70000.0) if not np.all(np.isnan(q700)) else np.full_like(q700, np.nan)
    td500 = q_to_td(q500, 50000.0) if not np.all(np.isnan(q500)) else np.full_like(q500, np.nan)

    # --- A. Total Totals (TT) и K-Index (Точные формулы) ---
    tt_index = (t850 + td850) - 2.0 * t500
    k_index = (t850 - t500) + td850 - (t700 - td700)

    # --- B. Упрощённый расчёт подъёма частицы (Parcel Lift) от 850 гПа ---
    # Высота уровней (прибл.): 850=1450м, 700=3000м, 500=5500м
    # 1. Высота уровня конденсации (LCL) в метрах
    lcl_h = 125.0 * (t850 - td850)
    
    # 2. Температура частицы на LCL (сухоадиабатический подъём от 850 гПа)
    # Перепад высот от 850 гПа до LCL
    delta_h_to_lcl = np.maximum(0, lcl_h - 1450.0)
    t_lcl = t850 - 0.0098 * delta_h_to_lcl
    
    # 3. Температура частицы на 700 гПа (3000м) и 500 гПа (5500м)
    # Влажноадиабатический градиент ~5.5 °C / 1000 м
    delta_h_700 = np.maximum(0, 3000.0 - lcl_h)
    t_parcel_700 = t_lcl - 0.0055 * delta_h_700
    
    delta_h_500 = np.maximum(0, 5500.0 - lcl_h)
    t_parcel_500 = t_lcl - 0.0055 * delta_h_500

    # --- C. Lifted Index (LI) ---
    # LI = T_окружающей_среды_500 - T_частицы_500
    # Отрицательные значения = неустойчивость (гроза)
    li_proxy = t500 - t_parcel_500

    # --- D. CAPE (Доступная потенциальная энергия неустойчивости, Дж/кг) ---
    # Плавучесть (Buoyancy) на уровнях 700 и 500 гПа
    # B = g * (T_parcel - T_env) / T_env(K)
    b_700 = 9.81 * (t_parcel_700 - t700) / (t700 + 273.15)
    b_500 = 9.81 * (t_parcel_500 - t500) / (t500 + 273.15)
    
    # В CAPE идёт только положительная плавучесть
    b_700_pos = np.maximum(0, b_700)
    b_500_pos = np.maximum(0, b_500)
    
    # Интегрирование по слою (приближённо, толщина слоя 700-500 ~ 2500 м)
    cape_proxy = 0.5 * (b_700_pos + b_500_pos) * 2500.0
    cape_proxy = np.maximum(0, cape_proxy) # CAPE не может быть отрицательным

    # --- E. CIN (Энергия конвективного торможения, Дж/кг) ---
    # Отрицательная плавучесть ниже уровня свободной конвекции (LFC)
    b_700_neg = np.minimum(0, 9.81 * (t_parcel_700 - t700) / (t700 + 273.15))
    cin_proxy = np.abs(b_700_neg * 1500.0) # Приближённый слой 1500 м
    cin_proxy = np.minimum(cin_proxy, 300.0) # Ограничиваем разумным максимумом

    # --- F. Shear 0-3 км (м/с) ---
    # Используем 10м как поверхность и 700 гПа (~3000м) как верхнюю границу
    # Если есть 925 гПа, можно использовать его, но 10м+700 даёт хорошую оценку нижнего слоя
    shear_0_3km = np.sqrt((u700 - u10)**2 + (v700 - v10)**2)

    # 4. Почва
    logger.info("  🔹 4/4 Извлечение данных почвы...")
    vsw1 = (safe_select(soil_ds, "vsw", "soilLayer", 1)[mask] * 100) if soil_ds else np.full(mask.sum(), np.nan)
    vsw2 = (safe_select(soil_ds, "vsw", "soilLayer", 2)[mask] * 100) if soil_ds else np.full(mask.sum(), np.nan)
    sot1 = (safe_select(soil_ds, "sot", "soilLayer", 1)[mask] - 273.15) if soil_ds else np.full(mask.sum(), np.nan)
    sot2 = (safe_select(soil_ds, "sot", "soilLayer", 2)[mask] - 273.15) if soil_ds else np.full(mask.sum(), np.nan)

    # 5. Сборка записей
    logger.info("  💾 Сборка выходных записей...")
    vars_dict = {
        "tcc": tcc, "tcw": tcw, "tp": tp, "cp": cp, "sp": sp, "ssrd": ssrd,
        "2t": t2m, "2d": d2m, "10u": u10, "10v": v10,
        "li_proxy": li_proxy, "k_index": k_index, "tt_index": tt_index,
        "cape_proxy": cape_proxy, "cin_proxy": cin_proxy, "shear_0_3km": shear_0_3km,
        "moisture_avail": tcw, # moisture_av,
        "vsw1": vsw1, "vsw2": vsw2, "sot1": sot1, "sot2": sot2
    }

    total_valid = 0
    for param, vals in vars_dict.items():
        if vals is None or np.all(np.isnan(vals)): continue
        valid = ~np.isnan(vals)
        if not np.any(valid): continue
        count = int(valid.sum())
        total_valid += count
        # Быстрая генерация записей
        records.extend({"param": param, "lat": round(float(lat), 2), "lon": round(float(lon), 2), "value": round(float(val), 3)}
                       for lat, lon, val in zip(lats_m[valid], lons_m[valid], vals[valid]))
        
    logger.info(f"  📊 Итого собрано: {total_valid} валидных записей по {len(vars_dict)} параметрам")
    return records

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    logger.info("🚀 process_grib.py (INDICES MODE + LOGS)")
    grib_files = sorted(CACHE_DIR.glob("aifs_single_fc_*.grib2"))
    if not grib_files:
        logger.warning("❌ Нет GRIB2 файлов в data/cache/")
        return

    all_records = []
    last_meta = None

    for f in grib_files:
        parts = f.stem.split("_")
#        meta = {"run_date": parts[3], "run_time": int(parts[4].replace("z", "")), "step": int(parts[5].replace("step", ""))}
        meta = parse_meta(parts)
        last_meta = meta

        logger.info(f"\n📦 [ШАГ +{meta['step']}ч] Обработка: {f.name}")
        recs = process_file(f)
        for r in recs: r.update(meta)
        all_records.extend(recs)
        
        if len(recs) > 0:
            f.unlink()
            logger.info(f"✅ Файл удалён. Переход к следующему шагу.\n")
        else:
            logger.warning(f"⛔ 0 точек. Файл сохранён для проверки.\n")

    if all_records:
        df = pd.DataFrame(all_records)
        out_path = OUTPUT_DIR / f"forecast_{last_meta['run_date']}_{last_meta['run_time']:02d}z.csv"
        df = df[["run_date", "run_time", "step", "lat", "lon", "param", "value"]]
        df.to_csv(out_path, index=False)
        logger.info(f"💾 Сохранено {len(df)} записей в {out_path.name}")
    else:
        logger.warning("⚠️ Записей 0.")

if __name__ == "__main__":
    main()