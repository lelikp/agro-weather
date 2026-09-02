#!/usr/bin/env python3
import pandas as pd
df = pd.read_csv("data/processed/forecast_20260514_12z.csv")
# Фильтр по точке и параметрам
point = df[(df.lat == -37.5) & (df.lon == -58.25) & (df.param.isin(["cp", "tp"]))]
print(point[["step", "param", "value"]].sort_values(["param", "step"]))