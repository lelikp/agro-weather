import json
import sqlite3
import pandas as pd
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# ----------------------------------------------------------------------
# Словари испанской локализации
# ----------------------------------------------------------------------
ALERT_ES = {
    "thunderstorm": "Actividad de tormentas", "hail": "Granizo",
    "heatwave": "Ola de calor", "coldwave": "Ola de frío",
    "frost": "Heladas", "snow": "Nieve", "strong_wind": "Viento fuerte",
    "drought": "Sequía", "heavy_rain": "Exceso de lluvias",
    "soil_moisture": "Humedad del suelo", "wind_dir": "Dirección del viento",
}
CROP_ES = {"soy": "soja", "corn": "maíz", "wheat": "trigo", "sunflower": "girasol"}
PHASE_ES = {
    "emergence": "emergencia", "vegetative": "vegetativo", "tillering": "macollaje",
    "heading": "encañazón", "flowering": "floración", "grain_fill": "llenado de grano",
    "harvest": "cosecha", "off_season": "fuera de temporada",
}
PARAM_ES = {
    ("2t", "mean"): "T media", ("2t", "min"): "T mín", ("2t", "max"): "T máx",
    ("2d", "mean"): "Td media", ("2d", "min"): "Td mín", ("2d", "max"): "Td máx",
    ("li_proxy", "min"): "LI(mín)", ("cape_proxy", "max"): "CAPE(máx)",
    ("tt_index", "max"): "TT(máx)", ("shear_0_3km", "max"): "ciz. 0-3 km(máx)",
    ("moisture_avail", "mean"): "humedad(media)", ("wind_speed", "max"): "viento(máx)",
    ("tp", "delta_6h"): "Δlluvia 6h", ("vsw1", "mean"): "hum. suelo(media)",
}
REGION_NAMES = {
    "norte_ba": "Norte BA",
    "sur_ba_la_pampa": "Sur BA / La Pampa",
    "entre_rios": "Entre Ríos",
    "santa_fe": "Santa Fe",
    "cordoba": "Córdoba",
}
REGION_ORDER = ["cordoba", "santa_fe", "entre_rios", "norte_ba", "sur_ba_la_pampa"]


def build_background(db_path):
    """Фоновая сводка по регионам из БД."""
    if not Path(db_path).exists():
        return {}

    conn = sqlite3.connect(db_path)
    latest = pd.read_sql(
        "SELECT DISTINCT run_date, run_time FROM forecasts_agg WHERE region != 'pampa_umeda'",
        conn
    )
    if latest.empty:
        conn.close()
        return {}

    def safe_int(v):
        if isinstance(v, bytes):
            return int.from_bytes(v, byteorder='little', signed=False)
        return int(v)

    latest["_rd"] = latest["run_date"].apply(safe_int)
    latest["_rt"] = latest["run_time"].apply(safe_int)
    best = latest.sort_values(["_rd", "_rt"], ascending=False).iloc[0]

    df = pd.read_sql(
        "SELECT * FROM forecasts_agg WHERE run_date=? AND run_time=? AND region != 'pampa_umeda'",
        conn, params=(best["run_date"], best["run_time"])
    )
    conn.close()

    bg = {}
    for interval, g_int in df.groupby("interval_start"):
        parts = []
        for region_id in REGION_ORDER:
            g_reg = g_int[g_int["region"] == region_id]
            if g_reg.empty:
                continue

            def get(p, s):
                r = g_reg[(g_reg["param"] == p) & (g_reg["stat_type"] == s)]
                return float(r["value"].iloc[0]) if len(r) else None

            tmax, tmin = get("2t", "max"), get("2t", "min")
            u, v = get("10u", "mean"), get("10v", "mean")
            ws = int(round((u * u + v * v) ** 0.5)) if u is not None and v is not None else None
            tp = get("tp", "delta_6h")

            name = REGION_NAMES.get(region_id, region_id)
            line_parts = [f"{name}:"]
            if tmax is not None and tmin is not None:
                line_parts.append(f"🌡 de {int(round(tmin))}° a {int(round(tmax))}°")
            if ws is not None:
                #line_parts.append(f"🌬 ~{ws} m/s")
                line_parts.append("🌬 calma" if ws == 0 else f"🌬 ~{ws} m/s")
            if tp is not None:
                line_parts.append("💧 sin lluvia" if tp <= 0.5 else f"💧 ~{int(round(tp))} mm")
            parts.append(" ".join(line_parts))
        bg[interval] = "\n   ".join(parts)
    return bg


def format_output(alerts, run_date, run_time, out_dir="output"):
    Path(out_dir).mkdir(exist_ok=True)
    db_path = Path(out_dir).parent / "data" / "archive.db"
    background = build_background(db_path)

    # Все 12 интервалов (+18 ... +84)
    launch_utc = datetime.strptime(f"{run_date} {run_time:02d}:00", "%Y%m%d %H:%M")
    all_intervals = []
    for step in range(18, 85, 6):
        start_utc = launch_utc + timedelta(hours=step - 6)
        start_local = start_utc + timedelta(hours=-3)
        all_intervals.append(start_local.strftime('%Y-%m-%d %H:%M'))

    sev_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda x: (sev_order.get(x["severity"], 3), x["interval"], x["alert_id"]))

    grouped = defaultdict(list)
    for a in alerts:
        key = (a["interval"], a["alert_id"], a["name"], a["severity"])
        grouped[key].append({
            "crop": a["crop"], "phase": a["phase"],
            "conditions": a.get("conditions", [])
        })

    alerts_by_interval = defaultdict(list)
    for (interval, alert_id, name, severity), crops in grouped.items():
        alerts_by_interval[interval].append((alert_id, name, severity, crops))

    # 1. JSON
    j_path = Path(out_dir) / "alerts_latest.json"
    json_output = []
    for interval in all_intervals:
        if interval in alerts_by_interval:
            for alert_id, name, severity, crops in alerts_by_interval[interval]:
                json_output.append({
                    "interval": interval,
                    "alert_id": alert_id,
                    "name": ALERT_ES.get(alert_id, name),
                    "severity": severity,
                    "crops": crops
                })
        else:
            json_output.append({
                "interval": interval,
                "status": "clear",
                "message": "Sin fenómenos peligrosos"
            })
    with open(j_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, ensure_ascii=False, indent=2)

    # 2. TXT
    t_path = Path(out_dir) / "alerts_latest.txt"
    with open(t_path, "w", encoding="utf-8") as f:
        f.write("📊 ALERTAS AGROMETEOROLÓGICAS (Pampa Húmeda)\n" + "=" * 45 + "\n")

        for interval in all_intervals:
            f.write(f"\n🕒 {interval}\n" + "-" * 40 + "\n")

            # Сводка по регионам — всегда под шапкой
            if interval in background:
                f.write(f"   {background[interval]}\n")

            if interval in alerts_by_interval:
                for alert_id, name, severity, crops in alerts_by_interval[interval]:
                    em = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(severity, "⚪")
                    # Только активные культуры (без off_season)
                    active = [c for c in crops if c["phase"] != "off_season"]
                    conds = crops[0].get("conditions", [])

                    f.write(f"{em} {ALERT_ES.get(alert_id, name)}\n")
                    if active:
                        crops_str = ", ".join(
                            f"{CROP_ES.get(c['crop'], c['crop'])} ({PHASE_ES.get(c['phase'], c['phase'])})"
                            for c in active
                        )
                        f.write(f"   Cultivos en campo: {crops_str}\n")
                    else:
                        f.write("   Cultivos: fuera de temporada\n")

                    if conds:
                        cond_str_parts = []
                        for c in conds:
                            if c.get('is_context'):
                                val = int(c['value'])
                                prob = int(c.get('prob', 0))

                                if val > 15:
                                    intensity = "fuertes"
                                elif val > 5:
                                    intensity = "moderadas"
                                elif val > 0:
                                    intensity = "débiles"
                                else:
                                    intensity = "sin lluvias significativas"

                                if prob == 0:
                                    coverage_text = "no se esperan lluvias"
                                elif prob < 15:
                                    coverage_text = (
                                        f"carácter aislado, ≤{prob}% del territorio; "
                                        f"mayormente seco"
                                    )
                                elif prob <= 70:
                                    coverage_text = (
                                        f"carácter disperso (~{prob}% del territorio); "
                                        f"verifique el pronóstico local"
                                    )
                                else:
                                    coverage_text = (
                                        f"lluvias generalizadas, {prob}% del territorio"
                                    )
                                cond_str_parts.append(
                                    f"💧 ~{val} mm, {intensity}; {coverage_text}"
                                )
                            else:
                                label = PARAM_ES.get(
                                    (c['param'], c['stat']),
                                    f"{c['param']}({c['stat']})"
                                )
                                cond_str_parts.append(
                                    f"{label}={c['value']} {c['op']} {c['threshold']}"
                                )
                        f.write(f"   Parámetros: {'; '.join(cond_str_parts)}\n\n")
                    else:
                        f.write("   Parámetros: sin datos\n\n")
            else:
                f.write("✅ Sin fenómenos peligrosos\n\n")

    return j_path, t_path