import sys, yaml
from pathlib import Path

def find_project_root():
    cur = Path(__file__).resolve().parent
    while cur != cur.parent:
        if (cur / "config").exists():
            return cur
        cur = cur.parent
    return Path(__file__).resolve().parent

BASE_DIR = find_project_root()
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_loader import load_latest_forecast
from engine import evaluate_alerts
from alert_formatter import format_output

def main():
    cfg_dir = BASE_DIR / "config"
    
    with open(cfg_dir / "rules.yaml", encoding="utf-8") as f:
        rules = yaml.safe_load(f)["alerts"]
    with open(cfg_dir / "crops.yaml", encoding="utf-8") as f:
        crops = yaml.safe_load(f)["crops"]

    df = load_latest_forecast()
    if df.empty:
        print("❌ Нет данных в БД. Запустите aggregate_and_save.py")
        return

    run_date = str(df["run_date"].iloc[0])
    run_time = int(df["run_time"].iloc[0])
    
    alerts = evaluate_alerts(df, rules, crops)
    
    j, t = format_output(alerts, run_date, run_time, out_dir=str(BASE_DIR / "output"))
    
    if alerts:
        print(f"✅ Сгенерировано {len(alerts)} алертов\n📄 JSON: {j}\n📄 TXT:  {t}")
    else:
        print(f"✅ Алертов нет, но отчёт создан\n📄 JSON: {j}\n📄 TXT:  {t}")

if __name__ == "__main__":
    main()