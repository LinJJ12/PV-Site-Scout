"""Regression harness for post-restructure backend hazards."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import app_full
from src.api.app import predict_simple_value
from src.lib.paths import DATA_SOLAR, FRONTEND_PUBLIC_DATA, GBDT_RUNTIME_MODEL


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


def main() -> None:
    c = app_full.app.test_client()

    check("model loaded", app_full.use_full_model and app_full.model_package is not None)
    check("gbdt runtime exists", GBDT_RUNTIME_MODEL.exists())
    check("scored csv", (DATA_SOLAR / "pv_stations_mcdm_scored.csv").exists())
    check("frontend public data dir", FRONTEND_PUBLIC_DATA.exists())

    bad = c.get("/api/predict", query_string={"lat": "abc", "lon": 121})
    check("invalid lat -> 400", bad.status_code == 400, bad.get_data(as_text=True)[:120])

    missing = c.get("/api/predict")
    check("missing coords -> 400", missing.status_code == 400)

    oob = c.get("/api/predict", query_string={"lat": 100, "lon": 0, "mode": "simple"})
    check("lat out of range -> 400", oob.status_code == 400)

    try:
        predict_simple_value(
            {
                "ghi_annual_mean": float("nan"),
                "ghi_annual_std": 1,
                "temp_annual_mean": 1,
                "temp_annual_std": 1,
                "precip_annual_mean": 1,
            }
        )
        check("nan climate rejected", False)
    except ValueError:
        check("nan climate rejected", True)

    dbg = c.get("/api/debug_model", query_string={"lat": 31.23, "lon": 121.47})
    body = dbg.get_json() or {}
    check("debug_model no traceback leak", "traceback" not in body, str(body.keys()))

    import src.api.app_full as full_mod

    fake = {
        "ghi_annual_mean": 4.2,
        "ghi_annual_std": 1.5,
        "temp_annual_mean": 16.0,
        "temp_annual_std": 8.0,
        "precip_annual_mean": 900.0,
        "source": "NASA POWER 2020-2023",
    }
    original = full_mod.get_nasa_solar_data
    full_mod.get_nasa_solar_data = lambda lat, lon, retries=3: dict(fake)
    try:
        r = c.get("/api/predict", query_string={"lat": 31.23, "lon": 121.47, "mode": "full"})
        body = r.get_json() or {}
        check("full predict 200", r.status_code == 200, json.dumps(body, ensure_ascii=False)[:200])
        check("full has NASA source", "NASA" in str(body.get("solar_data", {}).get("source", "")))
        check("full has inference_version", body.get("inference_version") == "v3-nasa-gat-reg")
        check("model_type is GBDT without torch", body.get("model_type") == "GBDT模型", body.get("model_type"))
        pvpi = float(body.get("pvpi", -1))
        check("pvpi in range", 0.1 <= pvpi <= 0.99, str(pvpi))
        check("not stuck at 1.0", pvpi < 0.999, str(pvpi))

        for lat, lon in [(0, 0), (90, 180), (-90, -180), (35.0, 105.0)]:
            rr = c.get("/api/predict", query_string={"lat": lat, "lon": lon, "mode": "full"})
            bb = rr.get_json() or {}
            check(f"full predict ({lat},{lon})", rr.status_code == 200 and "pvpi" in bb, bb.get("error"))
    finally:
        full_mod.get_nasa_solar_data = original

    st = c.get("/api/status").get_json()
    check("status model_loaded", st.get("model_loaded") is True)
    check("status model_type GBDT", st.get("model_type") == "GBDT模型", st.get("model_type"))
    check("levels is dict", isinstance(st.get("levels"), dict), str(type(st.get("levels"))))

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
