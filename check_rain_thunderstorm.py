import sqlite3

conn = sqlite3.connect("data/archive.db")
cursor = conn.cursor()

# Ищем осадки для шага, где сработала гроза (2026-06-05 03:00)
# Это шаг +63ч от прогона 20260602_12z, но у нас шаги 60 и 66
print("🌧 ОСАДКИ В ПЕРИОД ГРОЗОВОЙ АКТИВНОСТИ\n" + "="*60)

# Берём последний прогон
cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
rd, rt = cursor.fetchone()

# Смотрим шаги 54, 60, 66, 72 (вокруг времени алерта)
for step in [54, 60, 66, 72]:
    cursor.execute("""
        SELECT stat_type, ROUND(value, 3)
        FROM forecasts_agg
        WHERE run_date=? AND run_time=? AND step=? AND param='tp'
    """, (rd, rt, step))
    
    results = cursor.fetchall()
    if results:
        stats = {stat: val for stat, val in results}
        delta = stats.get('delta_6h', 0)
        print(f"Шаг +{step}ч: tp(delta_6h) = {delta:.2f} мм", end="")
        if delta > 15:
            print(" 🔴 Сильные осадки")
        elif delta > 5:
            print(" ⚡ Умеренные осадки")
        elif delta > 0.1:
            print(" 🌧 Слабые осадки")
        else:
            print(" ✅ Сухо")
    else:
        print(f"Шаг +{step}ч: данных нет")

conn.close()
print("\n" + "="*60)
input("Нажмите Enter для выхода...")