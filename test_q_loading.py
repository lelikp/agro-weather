import cfgrib
from pathlib import Path

print("🔍 ТЕСТ ЗАГРУЗКИ ВЛАЖНОСТИ (q) ИЗ GRIB2\n" + "="*60)

cache_dir = Path("data/cache")
grib_files = list(cache_dir.glob("aifs_single_fc_*.grib2"))

if not grib_files:
    print("❌ Нет GRIB2 файлов. Сначала запустите fetch_aifs.py")
else:
    file_path = grib_files[0]
    print(f"📂 Файл: {file_path.name}\n")
    
    # Способ 1: Стандартный (может не работать)
    print("🔸 Способ 1: Стандартный open_dataset")
    try:
        ds = cfgrib.open_dataset(str(file_path), backend_kwargs={"indexpath": ""})
        if "q" in ds:
            print(f"   ✅ q найден! Уровни: {sorted(ds['q'].coords['isobaricInhPa'].values)}")
        else:
            print("   ❌ q не найден")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    # Способ 2: С игнорированием конфликтов
    print("\n🔸 Способ 2: С ignore_keys")
    try:
        ds = cfgrib.open_dataset(
            str(file_path), 
            backend_kwargs={
                "indexpath": "",
                "ignore_keys": ["heightAboveGround", "stepType", "numberOfPoints"]
            }
        )
        if "q" in ds:
            print(f"   ✅ q найден! Уровни: {sorted(ds['q'].coords['isobaricInhPa'].values)}")
        else:
            print("   ❌ q не найден")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    # Способ 3: Загружаем ВСЕ датасеты и ищем q
    print("\n🔸 Способ 3: Перебор всех датасетов")
    try:
        datasets = cfgrib.open_datasets(
            str(file_path),
            backend_kwargs={"indexpath": ""}
        )
        print(f"   Найдено датасетов: {len(datasets)}")
        
        q_found = False
        for i, ds in enumerate(datasets):
            if "q" in ds:
                levels = sorted(ds['q'].coords['isobaricInhPa'].values)
                print(f"   ✅ Датасет #{i}: q найден! Уровни: {levels}")
                q_found = True
        
        if not q_found:
            print("   ❌ q не найден ни в одном датасете")
            print("\n📋 Все переменные во всех датасетах:")
            for i, ds in enumerate(datasets):
                vars_list = [v for v in ds.data_vars if v not in ['latitude', 'longitude', 'valid_time', 'step', 'number']]
                print(f"   Датасет #{i}: {vars_list}")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

print("\n" + "="*60)
input("Нажмите Enter для выхода...")