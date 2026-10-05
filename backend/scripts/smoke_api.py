"""Regression harness for post-restructure backend hazards.

运行方式（在 backend/ 目录）：
  python scripts/smoke_api.py

覆盖项：模型加载（GBDT 运行包优先）、参数校验、气候数据有效性、
NASA 缓存、限流、离线回退、调试端点门控与信息泄露。
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# 调试端点默认关闭；冒烟测试需要验证其内容，因此先开启再导入
os.environ["PV_ENABLE_DEBUG_ENDPOINTS"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import app_full
from src.api import app as app_base
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
    expected_model_type = "GBDT模型" if GBDT_RUNTIME_MODEL.exists() else "GAT+GBDT集成模型"
    check("no torch imported for gbdt runtime", (GBDT_RUNTIME_MODEL.exists() and not app_full.TORCH_AVAILABLE) or not GBDT_RUNTIME_MODEL.exists(),
          f"torch_available={app_full.TORCH_AVAILABLE}")

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

    # --- NASA 网格缓存单元 ---
    gc = app_base._grid_cell
    check("grid cell 0.5deg", gc(31.23, 121.47) == (31.0, 121.0) and gc(31.7, 121.6) == (31.5, 121.5),
          str(gc(31.23, 121.47)))
    app_base._cache_put(("test", 0.0), {"a": 1})
    check("cache roundtrip", app_base._cache_get(("test", 0.0)) == {"a": 1})
    app_base._nasa_cache[("expired", 0.0)] = ({"a": 1}, time.monotonic() - 10 * 365 * 86400)
    check("cache ttl expiry", app_base._cache_get(("expired", 0.0)) is None)

    # --- 完整模式（mock NASA）---
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
        check("full predict 200", r.status_code == 200, str(body)[:200])
        check("full has NASA source", "NASA" in str(body.get("solar_data", {}).get("source", "")))
        check("full has inference_version", body.get("inference_version") == "v3-nasa-gat-reg")
        check("model_type matches loaded package", body.get("model_type") == expected_model_type, body.get("model_type"))
        pvpi = float(body.get("pvpi", -1))
        check("pvpi in range", 0.1 <= pvpi <= 0.99, str(pvpi))
        check("not stuck at 1.0", pvpi < 0.999, str(pvpi))

        for lat, lon in [(0, 0), (90, 180), (-90, -180), (35.0, 105.0)]:
            rr = c.get("/api/predict", query_string={"lat": lat, "lon": lon, "mode": "full"})
            bb = rr.get_json() or {}
            check(f"full predict ({lat},{lon})", rr.status_code == 200 and "pvpi" in bb, bb.get("error"))

        # 完整模式在 NASA 失败时应返回 503（明确报错而非静默给错误高分）
        def _raise(lat, lon, retries=3):
            raise RuntimeError("mock: NASA unavailable")

        full_mod.get_nasa_solar_data = _raise
        rf = c.get("/api/predict", query_string={"lat": 31.23, "lon": 121.47, "mode": "full"})
        check("full predict nasa failure -> 503", rf.status_code == 503, str(rf.status_code))
        full_mod.get_nasa_solar_data = lambda lat, lon, retries=3: dict(fake)
    finally:
        full_mod.get_nasa_solar_data = original

    # --- 简化模式离线回退：NASA 不可用时使用最近真实站点 ---
    original_base = app_base.get_nasa_solar_data

    def _raise_base(lat, lon, retries=3):
        raise RuntimeError("mock: NASA unavailable")

    app_base.get_nasa_solar_data = _raise_base
    try:
        rs = c.get("/api/predict", query_string={"lat": 31.23, "lon": 121.47, "mode": "simple"})
        bs = rs.get_json() or {}
        check("simple offline fallback 200", rs.status_code == 200, str(bs)[:160])
        check("fallback source nearest station", "nearest real station" in str(bs.get("solar_data", {}).get("source", "")),
              str(bs.get("solar_data", {}).get("source")))
    finally:
        app_base.get_nasa_solar_data = original_base

    # --- 限流：低阈值下第 N+1 次请求返回 429 ---
    original_limit = app_base.RATE_LIMIT_PER_MIN
    app_base._rate_buckets.clear()
    app_base.RATE_LIMIT_PER_MIN = 3
    full_mod.get_nasa_solar_data = lambda lat, lon, retries=3: dict(fake)
    try:
        codes = []
        for _ in range(4):
            resp = c.get("/api/predict", query_string={"lat": 31.23, "lon": 121.47, "mode": "full"})
            codes.append(resp.status_code)
        check("rate limit -> 429", codes[:3] == [200, 200, 200] and codes[3] == 429, str(codes))
    finally:
        app_base.RATE_LIMIT_PER_MIN = original_limit
        app_base._rate_buckets.clear()
        full_mod.get_nasa_solar_data = original

    st = c.get("/api/status").get_json()
    check("status model_loaded", st.get("model_loaded") is True)
    check("status model_type", st.get("model_type") == expected_model_type, st.get("model_type"))
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
