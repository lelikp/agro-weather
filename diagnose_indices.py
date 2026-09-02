import sqlite3
from pathlib import Path

def safe_int(val):
    if isinstance(val, bytes):
        return int.from_bytes(val, byteorder='little', signed=False)
    return int(val)

print("🔬 ДИАГНОСТИКА ФИЗИЧЕСКИХ ИНДЕКСОВ\n" + "="*70)

conn = sqlite3.connect("data/archive.db")
cursor = conn.cursor()

# Находим последний прогон
cursor.execute("SELECT run_date, run_time FROM forecasts_agg ORDER BY rowid DESC LIMIT 1")
row = cursor.fetchone()
if not row:
    print("❌ База данных пуста!")
    exit()

rd_raw, rt_raw = row
rd = safe_int(rd_raw)
rt = safe_int(rt_raw)
print(f"📅 Прогон: {rd} в {rt:02d}:00 UTC\n")

# Ключевые индексы для диагностики
indices = {
    'li_proxy': ('min', 'LI (Lifted Index): <0 нестабильно, <-2 гроза'),
    'cape_proxy': ('max', 'CAPE (Дж/кг): >500 слабая, >1000 сильная конвекция'),
    'tt_index': ('max', 'Total Totals: >44 гроза, >47 град'),
    'k_index': ('max', 'K-Index: >20 влажно, >30 гроза'),
    'shear_0_3km': ('max', 'Shear 0-3км (м/с): >12 хороший сдвиг'),
    'moisture_avail': ('mean', 'Влага (кг/м²): >25 достаточно для гроз'),
    '2t': ('mean', 'Температура 2м (°C)'),
    'tp': ('max', 'Осадки (мм/6ч)')
}

print(f"{'ШАГ':<6} | {'ИНДЕКС':<18} | {'MIN':<8} | {'MAX':<8} | {'MEAN':<8} | {'ИНТЕРПРЕТАЦИЯ'}")
print("-" * 100)

current_step = None
for step in range(18, 85, 6):
    step_header_printed = False
    
    for param, (stat_type, description) in indices.items():
        # Запрашиваем статистику для этого параметра и шага
        cursor.execute("""
            SELECT MIN(value), MAX(value), AVG(value)
            FROM forecasts_agg
            WHERE run_date=? AND run_time=? AND step=? AND param=?
        """, (rd, rt, step, param))
        
        result = cursor.fetchone()
        if not result or result[0] is None:
            continue
        
        min_val, max_val, mean_val = result
        
        if not step_header_printed:
            print(f"\n▶ Шаг +{step}ч")
            step_header_printed = True
        
        # Форматируем значения
        min_str = f"{min_val:.2f}" if min_val is not None else "N/A"
        max_str = f"{max_val:.2f}" if max_val is not None else "N/A"
        mean_str = f"{mean_val:.2f}" if mean_val is not None else "N/A"
        
        # Добавляем интерпретацию для ключевых индексов
        interp = ""
        if param == 'li_proxy' and max_val is not None:
            if max_val < -2:
                interp = "⚠️ СИЛЬНАЯ НЕУСТОЙЧИВОСТЬ"
            elif max_val < 0:
                interp = "⚡ Умеренная неустойчивость"
            elif max_val < 2:
                interp = "🟡 Пограничное состояние"
            else:
                interp = "✅ Стабильно"
        elif param == 'cape_proxy' and max_val is not None:
            if max_val > 2500:
                interp = "🔴 Экстремальная конвекция"
            elif max_val > 1000:
                interp = "⚠️ Сильная конвекция"
            elif max_val > 500:
                interp = "⚡ Слабая конвекция"
            else:
                interp = "✅ Конвекция маловероятна"
        elif param == 'tt_index' and max_val is not None:
            if max_val > 47:
                interp = "🔴 Высокий риск града"
            elif max_val > 44:
                interp = "⚠️ Риск гроз"
            else:
                interp = "✅ Без града"
        elif param == 'tp' and max_val is not None:
            if max_val > 15:
                interp = "🔴 Сильные осадки"
            elif max_val > 5:
                interp = "⚡ Умеренные осадки"
            elif max_val > 0.1:
                interp = "🌧 Слабые осадки"
            else:
                interp = "✅ Сухо"
        
        print(f"{'':<6} | {param:<18} | {min_str:<8} | {max_str:<8} | {mean_str:<8} | {interp}")

conn.close()
print("\n" + "="*70)
print("✅ Диагностика завершена.")
input("\nНажмите Enter для выхода...")