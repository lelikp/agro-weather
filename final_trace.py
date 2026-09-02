import pandas as pd
import sqlite3
from pathlib import Path

print("🔍 ФИНАЛЬНАЯ ТРАССИРОВКА ДАННЫХ\n" + "="*60)

# 1. Проверка CSV
csv_files = list(Path("data/processed").glob("forecast_*.csv"))
if csv_files:
    csv_path = csv_files[-1]
    df = pd.read_csv(csv_path)
    params_csv = sorted(df['param'].unique().tolist())
    print(f"✅ CSV: {csv_path.name} ({len(df)} записей)")
    print(f"   Параметры ({len(params_csv)} шт.): {params_csv}")
else:
    print("❌ CSV файлов нет в data/processed/")

print("\n" + "="*60)

# 2. Проверка БД
db_path = Path("data/archive.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Берем самый последний прогон из БД
    cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        rd, rt = row
        # Безопасное преобразование типов (на случай BLOB)
        if isinstance(rd, bytes): rd = int.from_bytes(rd, 'little')
        if isinstance(rt, bytes): rt = int.from_bytes(rt, 'little')
        
        print(f"📅 БД: Последний прогон run_date={rd}, run_time={rt}")
        
        cursor.execute("SELECT DISTINCT param FROM forecasts_agg WHERE run_date=? AND run_time=?", (rd, rt))
        params_db = sorted([r[0] for r in cursor.fetchall()])
        print(f"   Параметры в БД ({len(params_db)} шт.): {params_db}")
        
        # Проверка наших целевых индексов
        targets = ['li_proxy', 'cape_proxy', 'tt_index', 'k_index', 'cin_proxy']
        missing = [t for t in targets if t not in params_db]
        
        print("\n" + "-"*60)
        if missing:
            print(f"⚠️ ПРОБЛЕМА: Этих индексов НЕТ в базе данных: {missing}")
            print("💡 Причина: Вы не запустили `python aggregate_and_save.py` после process_grib.py,")
            print("   либо скрипт завершился с ошибкой, либо параметры отфильтровались.")
        else:
            print("🎉 ОТЛИЧНО: Все целевые индексы успешно записаны в базу!")
            
            # Покажем живые значения
            print("\n📝 Живые значения из БД (пример):")
            cursor.execute("""
                SELECT step, param, stat_type, ROUND(value, 2) 
                FROM forecasts_agg 
                WHERE run_date=? AND run_time=? AND param IN ('li_proxy', 'cape_proxy') AND stat_type='max'
                ORDER BY step
                LIMIT 6
            """, (rd, rt))
            for r in cursor.fetchall():
                print(f"   Шаг +{r[0]:<3}ч | {r[1]:<12} | {r[2]:<4} | {r[3]}")
    else:
        print("❌ Таблица forecasts_agg абсолютно пуста!")
    conn.close()
else:
    print("❌ База данных data/archive.db не найдена!")

print("\n" + "="*60)
input("Нажмите Enter для выхода...")