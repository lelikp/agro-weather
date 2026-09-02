#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_full.py — Полный отчёт по последнему прогону.
Показывает min, max, mean, std для всех параметров по каждому шагу.
"""
import sqlite3
from pathlib import Path
from collections import defaultdict

# Группировка параметров для красивого вывода
PARAM_GROUPS = {
    "🌡 ТЕМПЕРАТУРА И ВЛАГА": ['2t', '2d', 'tcc', 'tcw', 'moisture_avail'],
    "💨 ВЕТЕР": ['10u', '10v', 'shear_0_3km', 'sp'],
    "🌧 ОСАДКИ": ['tp', 'cp'],
    "☀️ РАДИАЦИЯ": ['ssrd'],
    "⚡ ИНДЕКСЫ ГРОЗЫ": ['li_proxy', 'cape_proxy', 'cin_proxy', 'tt_index', 'k_index'],
    "🌱 ПОЧВА": ['vsw1', 'vsw2', 'sot1', 'sot2'],
}

# Единицы измерения
UNITS = {
    '2t': '°C', '2d': '°C', 'tcc': '%', 'tcw': 'кг/м²', 'moisture_avail': 'кг/м²',
    '10u': 'м/с', '10v': 'м/с', 'shear_0_3km': 'м/с', 'sp': 'гПа',
    'tp': 'мм', 'cp': 'мм', 'ssrd': 'МДж/м²',
    'li_proxy': '°C', 'cape_proxy': 'Дж/кг', 'cin_proxy': 'Дж/кг',
    'tt_index': '', 'k_index': '',
    'vsw1': '%', 'vsw2': '%', 'sot1': '°C', 'sot2': '°C',
}

def safe_int(val):
    if isinstance(val, bytes):
        return int.from_bytes(val, byteorder='little', signed=False)
    return int(val)

def fmt(val, width=7):
    if val is None:
        return " " * (width - 3) + "N/A"
    return f"{val:>{width}.2f}"

def main():
    db_path = Path("data/archive.db")
    if not db_path.exists():
        print("❌ База данных не найдена!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Находим последний прогон
    cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        print("❌ БД пуста!")
        return
    
    rd_raw, rt_raw = row
    rd = safe_int(rd_raw)
    rt = safe_int(rt_raw)
    
    print("=" * 110)
    print(f"📊 ПОЛНЫЙ ОТЧЁТ ПО ПРОГНОЗУ")
    print(f"📅 Прогон: {rd} в {rt:02d}:00 UTC")
    print(f"🌎 Регион: Pampa-Умеда (bbox: -38.5..-30.0°S, -64.5..-57.0°W)")
    print("=" * 110)
    
    # Получаем все шаги
    cursor.execute("""
        SELECT DISTINCT step FROM forecasts_agg 
        WHERE run_date=? AND run_time=? ORDER BY step
    """, (rd_raw, rt_raw))
    steps = [safe_int(r[0]) for r in cursor.fetchall()]
    
    # Для каждого шага выводим отчёт
    for step in steps:
        # Время интервала (UTC-3)
        from datetime import datetime, timedelta
        launch_utc = datetime.strptime(f"{rd} {rt:02d}:00", "%Y%m%d %H:%M")
        end_utc = launch_utc + timedelta(hours=step)
        end_arg = end_utc + timedelta(hours=-3)
        
        print(f"\n{'─' * 110}")
        print(f"▶ ШАГ +{step}ч  |  Интервал (ARG): до {end_arg.strftime('%d.%m %H:%M')}  |  (UTC): до {end_utc.strftime('%d.%m %H:%M')}")
        print(f"{'─' * 110}")
        print(f"{'ПАРАМЕТР':<18} | {'ЕД.':<6} | {'MIN':>8} | {'MAX':>8} | {'MEAN':>8} | {'СКО':>8} | {'РАЗБРОС':>8}")
        print(f"{'─' * 18} | {'─' * 6} | {'─' * 8} | {'─' * 8} | {'─' * 8} | {'─' * 8} | {'─' * 8}")
        
        for group_name, params in PARAM_GROUPS.items():
            print(f"\n  {group_name}")
            
            for param in params:
                # Для tp/cp используем delta_6h, для остальных — mean/max/min/std
                if param in ['tp', 'cp']:
                    stat_filter = "stat_type = 'delta_6h'"
                else:
                    stat_filter = "stat_type IN ('mean', 'max', 'min', 'std')"
                
                cursor.execute(f"""
                    SELECT stat_type, value FROM forecasts_agg
                    WHERE run_date=? AND run_time=? AND step=? AND param=? AND ({stat_filter})
                """, (rd_raw, rt_raw, step, param))
                
                stats = {r[0]: r[1] for r in cursor.fetchall()}
                
                if not stats:
                    print(f"    {param:<16} | {'':<6} | {'N/A':>8} | {'N/A':>8} | {'N/A':>8} | {'N/A':>8} | {'— нет данных —'}")
                    continue
                
                unit = UNITS.get(param, '')
                
                if param in ['tp', 'cp']:
                    # Для осадков показываем только delta_6h
                    delta = stats.get('delta_6h', 0)
                    print(f"    {param:<16} | {unit:<6} | {'':>8} | {'':>8} | {fmt(delta):>8} | {'':>8} | (дельта за 6ч)")
                else:
                    min_v = stats.get('min')
                    max_v = stats.get('max')
                    mean_v = stats.get('mean')
                    std_v = stats.get('std', 0)
                    
                    # Разброс (max - min) как дополнительная информация
                    if min_v is not None and max_v is not None:
                        spread = max_v - min_v
                        spread_str = fmt(spread)
                    else:
                        spread_str = "N/A"
                    
                    print(f"    {param:<16} | {unit:<6} | {fmt(min_v)} | {fmt(max_v)} | {fmt(mean_v)} | {fmt(std_v)} | {spread_str}")
    
    conn.close()
    
    print("\n" + "=" * 110)
    print("✅ Отчёт завершён.")
    print("\n📖 Как читать:")
    print("   • MIN/MAX — экстремумы по региону (в одной точке сетки)")
    print("   • MEAN — среднее по всем точкам bbox")
    print("   • СКО — стандартное отклонение (насколько неоднородно поле)")
    print("   • РАЗБРОС — разница MAX-MIN (амплитуда вариаций)")
    print("=" * 110)
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()