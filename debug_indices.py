import pandas as pd
import sqlite3
from pathlib import Path

print("🔍 ПРОВЕРКА ПОТЕРИ ДАННЫХ ИНДЕКСОВ\n" + "="*50)

# 1. Проверка CSV
csv_path = Path("data/processed/forecast_20260601_12z.csv")
if csv_path.exists():
    df = pd.read_csv(csv_path)
    params_in_csv = df['param'].unique().tolist()
    print(f"✅ CSV найден. Всего записей: {len(df)}")
    print(f"📋 Параметры в CSV: {params_in_csv}")
    
    # Проверяем, есть ли наши новые индексы
    new_indices = ['li_proxy', 'cape_proxy', 'tt_index', 'k_index', 'shear_0_3km']
    missing_in_csv = [idx for idx in new_indices if idx not in params_in_csv]
    if missing_in_csv:
        print(f"❌ В CSV НЕТ следующих индексов: {missing_in_csv}")
    else:
        print("✅ Все новые индексы успешно записаны в CSV!")
else:
    print(f"❌ CSV файл не найден по пути: {csv_path}")

print("\n" + "="*50)

# 2. Проверка БД
db_path = Path("data/archive.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Ищем последний run_date (учитывая возможный BLOB)
    cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        rd, rt = row
        # Безопасное преобразование, если это BLOB
        if isinstance(rd, bytes): rd = int.from_bytes(rd, 'little')
        if isinstance(rt, bytes): rt = int.from_bytes(rt, 'little')
        
        print(f"📅 Последний прогон в БД: run_date={rd}, run_time={rt}")
        
        cursor.execute("SELECT DISTINCT param FROM forecasts_agg WHERE run_date=?", (rd,))
        params_in_db = [r[0] for r in cursor.fetchall()]
        print(f"📋 Параметры в БД для этого прогона: {params_in_db}")
        
        new_indices = ['li_proxy', 'cape_proxy', 'tt_index', 'k_index', 'shear_0_3km']
        missing_in_db = [idx for idx in new_indices if idx not in params_in_db]
        if missing_in_db:
            print(f"❌ В БД НЕТ следующих индексов: {missing_in_db}")
        else:
            print("✅ Все новые индексы успешно записаны в БД!")
    else:
        print("❌ В таблице forecasts_agg нет записей.")
    conn.close()
else:
    print(f"❌ База данных не найдена по пути: {db_path}")

print("\n" + "="*50)
input("Для продолжения нажмите Enter...")