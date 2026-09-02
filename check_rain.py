import sqlite3

conn = sqlite3.connect("data/archive.db")
cursor = conn.cursor()

# 1. Находим последний прогон
cursor.execute("""
    SELECT run_date, run_time FROM forecasts_agg 
    ORDER BY run_date DESC, run_time DESC LIMIT 1
""")
rd, rt = cursor.fetchone()
print(f"📅 Последний прогон: run_date={rd}, run_time={rt}\n")

# 2. Смотрим осадки только этого прогона
cursor.execute("""
    SELECT step, param, stat_type, ROUND(value, 3) as val 
    FROM forecasts_agg 
    WHERE run_date=? AND run_time=? AND param IN ('tp', 'cp')
    ORDER BY step, param, stat_type
""", (rd, rt))
rows = cursor.fetchall()

print(f"Найдено записей: {len(rows)}\n")
print(f"{'ШАГ':<5} | {'ПАР':<4} | {'СТАТ':<10} | {'ЗНАЧЕНИЕ (мм)'}")
print("-" * 40)

for row in rows:
    print(f"{row[0]:<5} | {row[1]:<4} | {row[2]:<10} | {row[3]}")

# 3. Проверяем, сработало бы правило heavy_rain (tp_delta_6h > 15)
print("\n" + "="*40)
print("ПРОВЕРКА ПОРОГА heavy_rain (tp delta_6h > 15 мм):")
cursor.execute("""
    SELECT step, MAX(value) as max_val
    FROM forecasts_agg 
    WHERE run_date=? AND run_time=? AND param='tp' AND stat_type='delta_6h'
    GROUP BY step
""", (rd, rt))
for step, max_val in cursor.fetchall():
    flag = "⚠️ АЛЕРТ" if max_val > 15 else "✅ тихо"
    print(f"  Шаг +{step}ч: max delta = {max_val:.2f} мм  {flag}")

conn.close()