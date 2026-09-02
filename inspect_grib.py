import cfgrib
import xarray as xr
from pathlib import Path

print("🔍 ИНСПЕКЦИЯ GRIB2 ФАЙЛА\n" + "="*50)

cache_dir = Path("data/cache")
grib_files = list(cache_dir.glob("aifs_single_fc_*.grib2"))

if not grib_files:
    print("❌ Нет GRIB2 файлов в data/cache/. Сначала запустите fetch_aifs.py")
else:
    file_path = grib_files[0]
    print(f"📂 Анализируем: {file_path.name}\n")
    
    try:
        # Открываем только метаданные, чтобы не грузить всю память
        ds = cfgrib.open_dataset(str(file_path), backend_kwargs={"indexpath": ""})
        
        print("🌡 Доступные уровни (isobaricInhPa) для температуры (t):")
        if "isobaricInhPa" in ds.coords and "t" in ds:
            levels_t = sorted(ds["t"].coords["isobaricInhPa"].values.tolist())
            print(f"   {levels_t}")
        else:
            print("   ❌ Уровень isobaricInhPa или переменная 't' не найдены!")
            
        print("\n💧 Доступные уровни (isobaricInhPa) для влажности (q):")
        if "isobaricInhPa" in ds.coords and "q" in ds:
            levels_q = sorted(ds["q"].coords["isobaricInhPa"].values.tolist())
            print(f"   {levels_q}")
        else:
            print("   ❌ Уровень isobaricInhPa или переменная 'q' не найдены!")
            
        print("\n💨 Доступные уровни (isobaricInhPa) для ветра (u, v):")
        if "isobaricInhPa" in ds.coords and "u" in ds:
            levels_u = sorted(ds["u"].coords["isobaricInhPa"].values.tolist())
            print(f"   {levels_u}")
        else:
            print("   ❌ Уровень isobaricInhPa или переменная 'u' не найдены!")
            
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")

print("\n" + "="*50)
input("Нажмите Enter для выхода...")