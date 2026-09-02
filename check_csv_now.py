import pandas as pd
from pathlib import Path

print("🔍 ПРОВЕРКА ТЕКУЩЕГО CSV\n" + "="*60)

csv_files = list(Path("data/processed").glob("forecast_*.csv"))
if not csv_files:
    print("❌ CSV файлов нет в data/processed/")
else:
    csv_path = csv_files[-1]
    print(f"📂 Файл: {csv_path.name}\n")
    
    df = pd.read_csv(csv_path)
    params = sorted(df['param'].unique().tolist())
    
    print(f"📋 Параметры в CSV ({len(params)} шт.):")
    print(params)
    
    target = ['li_proxy', 'cape_proxy', 'tt_index', 'k_index', 'cin_proxy', 'shear_0_3km']
    found = [p for p in target if p in params]
    missing = [p for p in target if p not in params]
    
    print("\n" + "="*60)
    if found:
        print(f"✅ Найдены: {found}")
    if missing:
        print(f"❌ Отсутствуют: {missing}")
    
    # Показываем примеры значений для найденных индексов
    if found:
        print("\n📝 Примеры значений:")
        for param in found[:3]:  # Первые 3 найденных
            subset = df[df['param'] == param]['value']
            print(f"  {param}: min={subset.min():.2f}, max={subset.max():.2f}, mean={subset.mean():.2f}")

print("\n" + "="*60)
input("Нажмите Enter для выхода...")