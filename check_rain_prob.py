import sqlite3

def safe_int(val):
    if isinstance(val, bytes):
        return int.from_bytes(val, byteorder='little', signed=False)
    return int(val)

conn = sqlite3.connect("data/archive.db")
cursor = conn.cursor()

# Берём последний прогон
cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
row = cursor.fetchone()
if not row:
    print("❌ База данных пуста!")
    exit()

rd_raw, rt_raw = row
rd = safe_int(rd_raw)
rt = safe_int(rt_raw)

print("🔍 ПРОВЕРКА ОСАДКОВ И ВЕРОЯТНОСТИ\n" + "="*60)
print(f"Прогон: {rd} в {rt:02d}:00 UTC\n")

# Смотрим шаг +24ч (интервал 03:00-09:00 ARG)
step = 24
cursor.execute("""
    SELECT param, stat_type, value 
    FROM forecasts_agg 
    WHERE run_date=? AND run_time=? AND step=? AND param='tp'
""", (rd_raw, rt_raw, step))

results = cursor.fetchall()
print(f"📊 Шаг +{step}ч (03:00-09:00 ARG):")
for param, stat, val in results:
    print(f"  {param} | {stat:<12} | {val}")

if not results:
    print("  ❌ Данных по tp нет!")
else:
    delta = next((v for p, s, v in results if s == 'delta_6h'), None)
    prob = next((v for p, s, v in results if s == 'prob'), None)
    
    print(f"\n📈 Анализ:")
    print(f"  delta_6h = {delta} мм")
    print(f"  prob = {prob}%")
    
    if delta and delta > 0 and (prob is None or prob == 0):
        print("\n⚠️ ПРОБЛЕМА: Осадки есть (delta > 0), но вероятность = 0!")
        print("  Это означает, что Neighborhood Method не нашёл 'мокрых' окрестностей.")
        print("  Возможные причины:")
        print("  1. В исходном CSV все точки имеют value <= 0.1 мм (но тогда среднее не могло быть 3 мм)")
        print("  2. Ошибка в расчёте lat_bin/lon_bin в aggregate_and_save.py")
        print("  3. Поля 'lat' или 'lon' отсутствуют в DataFrame при агрегации")

conn.close()
print("\n" + "="*60)
input("Нажмите Enter для выхода...")