import sqlite3
from pathlib import Path

print("🔬 УПРОЩЁННАЯ ДИАГНОСТИКА (БЕЗ ФИЛЬТРОВ)\n" + "="*70)

conn = sqlite3.connect("data/archive.db")
cursor = conn.cursor()

# 1. Смотрим ВСЕ записи из БД (без фильтров)
cursor.execute("SELECT run_date, run_time, step, param, stat_type, ROUND(value, 2) FROM forecasts_agg ORDER BY rowid DESC LIMIT 20")
rows = cursor.fetchall()

if not rows:
    print("❌ Таблица forecasts_agg пуста!")
    conn.close()
    exit()

print(f"📊 Последние 20 записей из БД:\n")
print(f"{'run_date':<15} | {'run_time':<8} | {'step':<5} | {'param':<15} | {'stat':<6} | {'value':<8}")
print("-" * 70)

for row in rows:
    rd, rt, step, param, stat, val = row
    # Безопасное преобразование типов
    if isinstance(rd, bytes): rd = int.from_bytes(rd, 'little')
    if isinstance(rt, bytes): rt = int.from_bytes(rt, 'little')
    print(f"{rd:<15} | {rt:<8} | {step:<5} | {param:<15} | {stat:<6} | {val:<8}")

# 2. Берём самый свежий прогон
cursor.execute("SELECT DISTINCT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
latest = cursor.fetchone()
rd_raw, rt_raw = latest

if isinstance(rd_raw, bytes): rd = int.from_bytes(rd_raw, 'little')
else: rd = rd_raw

if isinstance(rt_raw, bytes): rt = int.from_bytes(rt_raw, 'little')
else: rt = rt_raw

print(f"\n📅 Самый свежий прогон: run_date={rd}, run_time={rt}")

# 3. Смотрим все шаги для этого прогона
cursor.execute("SELECT DISTINCT step FROM forecasts_agg WHERE run_date=? AND run_time=? ORDER BY step", (rd_raw, rt_raw))
steps = [row[0] for row in cursor.fetchall()]
print(f"🔢 Доступные шаги: {steps}")

# 4. Смотрим все параметры для шага 18
cursor.execute("SELECT DISTINCT param FROM forecasts_agg WHERE run_date=? AND run_time=? AND step=18", (rd_raw, rt_raw))
params = [row[0] for row in cursor.fetchall()]
print(f"📋 Параметры для шага +18ч: {params}")

# 5. Показываем реальные значения индексов для шага 18
print(f"\n📊 Значения индексов для шага +18ч:")
print("-" * 70)

target_params = ['li_proxy', 'cape_proxy', 'tt_index', 'k_index', 'shear_0_3km', '2t', 'tp']
for param in target_params:
    cursor.execute("""
        SELECT stat_type, ROUND(value, 2) 
        FROM forecasts_agg 
        WHERE run_date=? AND run_time=? AND step=18 AND param=?
    """, (rd_raw, rt_raw, param))
    
    results = cursor.fetchall()
    if results:
        stats = {stat: val for stat, val in results}
        print(f"  {param:<15} | min={stats.get('min', 'N/A'):<8} | max={stats.get('max', 'N/A'):<8} | mean={stats.get('mean', 'N/A'):<8}")
    else:
        print(f"  {param:<15} | ❌ Не найдено")

conn.close()
print("\n" + "="*70)
print("✅ Диагностика завершена.")
input("\nНажмите Enter для выхода...")