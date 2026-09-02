import sqlite3

print("🔍 ПРЯМАЯ ПРОВЕРКА СОДЕРЖИМОГО БД\n" + "="*50)

conn = sqlite3.connect("data/archive.db")
cursor = conn.cursor()

# 1. Берем самую последнюю запись, не делая предположений о типах данных
cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
row = cursor.fetchone()

if not row:
    print("❌ Таблица `forecasts_agg` абсолютно пуста!")
    print("💡 Вы точно запустили `python aggregate_and_save.py` после создания CSV?")
    conn.close()
    input("\nНажмите Enter для выхода...")
    exit()

rd, rt = row
print(f"📌 Последний прогон в БД: run_date={rd} (тип: {type(rd).__name__}), run_time={rt} (тип: {type(rt).__name__})\n")

# 2. Смотрим, какие параметры вообще записаны для этого прогона
cursor.execute("SELECT DISTINCT param FROM forecasts_agg WHERE run_date=? AND run_time=?", (rd, rt))
params_in_db = [r[0] for r in cursor.fetchall()]

print(f"📋 Параметры в БД для этого прогона ({len(params_in_db)} шт.):")
print(params_in_db)

# 3. Проверяем наличие наших новых индексов
target_indices = ['li_proxy', 'cape_proxy', 'tt_index', 'k_index', 'shear_0_3km']
found = [p for p in target_indices if p in params_in_db]
missing = [p for p in target_indices if p not in params_in_db]

print("\n" + "="*50)
if missing:
    print(f"⚠️ ПРОБЛЕМА: Этих индексов НЕТ в базе: {missing}")
    print("💡 Значит, aggregate_and_save.py их отфильтровал или не смог записать.")
else:
    print("🎉 ОТЛИЧНО: Все целевые индексы успешно записаны в базу!")
    
    # 4. Покажем живые примеры данных
    print("\n📝 Примеры данных из БД (первые 10 строк):")
    cursor.execute("""
        SELECT step, param, stat_type, ROUND(value, 2) 
        FROM forecasts_agg 
        WHERE run_date=? AND run_time=? AND param IN ('li_proxy', 'cape_proxy', '2t')
        ORDER BY step, param
        LIMIT 10
    """, (rd, rt))
    
    rows = cursor.fetchall()
    if not rows:
        print("  (Нет данных для li_proxy, cape_proxy, 2t)")
    else:
        for r in rows:
            print(f"  step={r[0]:<4} | param={r[1]:<12} | stat={r[2]:<8} | val={r[3]}")

conn.close()
print("\n" + "="*50)
input("Нажмите Enter для выхода...")