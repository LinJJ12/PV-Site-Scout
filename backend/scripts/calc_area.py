import _bootstrap  # noqa: F401

import pandas as pd

from src.lib.paths import FRONTEND_PUBLIC_DATA

df = pd.read_csv(FRONTEND_PUBLIC_DATA / "provincial_statistics.csv")
total_area = df["Total_Area_km2"].sum()
total_count = df["Count"].sum()
print(f"Total Area: {total_area:.2f} km2")
print(f"Total Stations: {total_count}")
