import sqlite3
import pandas as pd
from pathlib import Path

def find_project_root():
    cur = Path(__file__).resolve().parent
    while cur != cur.parent:
        if (cur / "data").exists():
            return cur
        cur = cur.parent
    return Path(__file__).resolve().parent

DB_PATH = find_project_root() / "data" / "archive.db"

def safe_int(val):
    if isinstance(val, bytes):
        return int.from_bytes(val, byteorder='little', signed=False)
    return int(val)

def load_latest_forecast():
    conn = sqlite3.connect(DB_PATH)
    
    # === ИЗМЕНЕНО: фильтруем только pampa_umeda ===
    pairs = pd.read_sql(
        "SELECT DISTINCT run_date, run_time FROM forecasts_agg WHERE region='pampa_umeda'",
        conn
    )
    if pairs.empty:
        conn.close()
        return pd.DataFrame()

    pairs["_rd"] = pairs["run_date"].apply(safe_int)
    pairs["_rt"] = pairs["run_time"].apply(safe_int)
    best = pairs.sort_values(["_rd", "_rt"], ascending=False).iloc[0]

    # === ИЗМЕНЕНО: фильтруем только pampa_umeda ===
    df = pd.read_sql(
        "SELECT * FROM forecasts_agg WHERE run_date=? AND run_time=? AND region='pampa_umeda'",
        conn, params=(best["run_date"], best["run_time"])
    )
    conn.close()

    df['run_date'] = df['run_date'].apply(safe_int)
    df['run_time'] = df['run_time'].apply(safe_int)
    df['step']     = df['step'].apply(safe_int)
    return df