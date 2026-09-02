import sqlite3

def safe_int(val):
    if isinstance(val, bytes):
        return int.from_bytes(val, byteorder='little', signed=False)
    return int(val)

conn = sqlite3.connect("data/archive.db")
cursor = conn.cursor()

# 1. Находим последний прогон
cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY run_date DESC, run_time DESC LIMIT 1")
rd_raw, rt_raw = cursor.fetchone()
rd = safe_int(rd_raw)
rt = safe_int(rt_raw)
print(f"📅 Проверка индексов для прогона: {rd} в {rt:02d}:00 UTC\n")

# 2. Запрашиваем мин, макс и среднее по региону для новых индексов
params = ("li_proxy", "cape_proxy", "tt_index", "k_index", "shear_0_3km")
placeholders = ",".join("?" * len(params))

query = f"""
    SELECT step, param, 
           ROUND(MIN(value), 2) as min_val, 
           ROUND(MAX(value), 2) as max_val,
           ROUND(AVG(value), 2) as mean_val
    FROM forecasts_agg 
    WHERE run_date=? AND run_time=? AND param IN ({placeholders})
    GROUP BY step, param
    ORDER BY step, param
"""
cursor.execute(query, (rd, rt) + params)
rows = cursor.fetchall()

print(f"{'ШАГ':<6} | {'ПАРАМЕТР':<15} | {'MIN':<8} | {'MAX':<8} | {'MEAN':<8} | {'ИНТЕРПРЕТАЦИЯ'}")
print("-" * 90)

current_step = None
for row in rows:
    step, param, min_v, max_v, mean_v = row
    if step != current_step:
        print(f"\n--- Прогноз на +{step} часов ---")
        current_step = step
    
    # Добавляем метеорологический контекст
    if param == "li_proxy":
        context = "LI > 0: стабильно | LI < -2: гроза"
    elif param == "cape_proxy":
        context = "CAPE < 500: слабо | CAPE > 1000: гроза"
    elif param == "tt_index":
        context = "TT < 45: без града | TT > 45: риск града"
    elif param == "k_index":
        context = "K < 20: сухо | K > 30: влажно/гроза"
    elif param == "shear_0_3km":
        context = "Shear > 12 м/с: хороший сдвиг для гроз"
    else:
        context = ""
        
    print(f"{'':<6} | {param:<15} | {min_v:<8} | {max_v:<8} | {mean_v:<8} | {context}")

conn.close()
print("\n✅ Проверка завершена.")