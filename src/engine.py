import numpy as np
import pandas as pd
from phenology import get_active_phases

def nice(x):
    """7.0 → 7, -3.0 → -3, 13.79 → 13.79"""
    x = float(x)
    return int(x) if x == int(x) else round(x, 2)

def evaluate_alerts(df, rules, crops_cfg):
    """Проверяет правила против данных из БД и возвращает список алертов."""
    if df.empty:
        return []

    # ------------------------------------------------------------------
    # 1. Вычисляем производные параметры, если их нет в БД
    # ------------------------------------------------------------------
    if "10u" in df["param"].values and "10v" in df["param"].values:
        u = df[df["param"] == "10u"].set_index("stat_type")["value"]
        v = df[df["param"] == "10v"].set_index("stat_type")["value"]
        ws = np.sqrt(u ** 2 + v ** 2)
        ws.name = "wind_speed"
        df_ws = ws.reset_index().rename(columns={0: "value"})
        df_ws["param"] = "wind_speed"
        df = pd.concat([df, df_ws], ignore_index=True)

    # ------------------------------------------------------------------
    # 2. Pivot для быстрого доступа: index=interval_start,
    #    columns="param_stat_type", values=mean/max/min
    # ------------------------------------------------------------------
    pivot = df.pivot_table(
        index="interval_start",
        columns=["param", "stat_type"],
        values="value"
    )
    pivot.columns = [f"{p}_{s}" for p, s in pivot.columns]
    # Температуры — до целых: точность прогноза не оправдывает десятые
    temp_cols = [c for c in pivot.columns if c.startswith(("2t_", "2d_"))]
    pivot[temp_cols] = pivot[temp_cols].round(0)

    # ------------------------------------------------------------------
    # 3. Определяем фазы культур на дату прогона
    # ------------------------------------------------------------------
    run_date = str(int(df["run_date"].iloc[0]))
    phases = get_active_phases(run_date, crops_cfg)

    alerts = []

    # ------------------------------------------------------------------
    # 4. Проход по интервалам и правилам
    # ------------------------------------------------------------------
    for interval, row in pivot.iterrows():
        for alert_id, rule in rules.items():
            triggered = True
            for param_name, cond in rule.get("conditions", {}).items():
                col = f"{param_name}_{cond['stat']}"
                val = row.get(col, np.nan)
                if pd.isna(val):
                    triggered = False
                    break
                op = cond["op"]
                th = cond["threshold"]
                if op == ">" and not (val > th):
                    triggered = False
                elif op == "<" and not (val < th):
                    triggered = False
                elif op == ">=" and not (val >= th):
                    triggered = False
                elif op == "<=" and not (val <= th):
                    triggered = False
                if not triggered:
                    break

            if not triggered:
                continue

            # ----------------------------------------------------------
            # 4а. Собираем ВСЕ условия правила (для наглядности в выводе)
            # ----------------------------------------------------------
            conditions_met = []
            for param_name, cond in rule.get("conditions", {}).items():
                col = f"{param_name}_{cond['stat']}"
                val = row.get(col, float('nan'))
                if pd.isna(val):
                    continue
                conditions_met.append({
                    "param": param_name,
                    "stat": cond['stat'],
#                    "value": round(float(val), 2),
#                    "threshold": float(cond['threshold']),
                    "value": nice(val),
                    "threshold": nice(cond['threshold']),
                    "op": cond['op']
                })

            # === НОВОЕ: Добавляем контекст об осадках для гроз ===
            if alert_id in ['thunderstorm', 'hail', 'heavy_rain']:
                # Берем значения из pivot-таблицы
                tp_val = row.get('tp_delta_6h', np.nan)
                tp_prob = row.get('tp_prob', np.nan) 
                
                if not pd.isna(tp_val):
                    conditions_met.append({
                        "param": "Осадки",
                        "stat": "прогноз",
                        "value": round(float(tp_val), 2),
                        "prob": int(tp_prob) if not pd.isna(tp_prob) else 0, # <-- ВОТ ЭТО КЛЮЧЕВОЕ ДОБАВЛЕНИЕ
                        "threshold": 0.0,
                        "op": "",
                        "is_context": True
                    })
            # ========================================================

            #impact = "; ".join(
            #    f"{c['param']}({c['stat']})={c['value']} {c['op']} {c['threshold']}"
            #    for c in conditions_met if not c.get('is_context')
            #)
            impact = "; ".join(
                f"{c['param']}({c['stat']})={c['value']:g} {c['op']} {c['threshold']:g}"
                for c in conditions_met if not c.get('is_context')
            )

            # ----------------------------------------------------------
            # 4б. Модуляция severity по фазам каждой культуры
            # ----------------------------------------------------------
            for crop, phase in phases.items():
                sev_map = rule.get("phases", {})
                severity = sev_map.get(phase, rule.get("base_severity", "info"))

                alerts.append({
                    "interval": interval,
                    "alert_id": alert_id,
                    "name": rule["name"],
                    "crop": crop,
                    "phase": phase,
                    "severity": severity,
                    "impact": impact,
                    "conditions": conditions_met
                })

    return alerts