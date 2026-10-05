import logging
import math
import os
import threading
import time
from collections import defaultdict, deque
from functools import wraps

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from scipy.spatial import cKDTree

from src.lib.paths import DATA_SOLAR, FRONTEND_DIST_DATA, FRONTEND_PUBLIC_DATA
from src.lib.solar_data import SolarRadiationAPI

try:
    from flask_cors import CORS
except ImportError:
    def CORS(app):
        return app

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
nasa_api = SolarRadiationAPI()
station_data = None
station_tree = None
_station_lock = threading.Lock()

# ---------------------------------------------------------------------------
# NASA POWER 结果缓存
#
# NASA POWER 数据为 0.5°×0.5° 网格的历史数据（不会变化），官方文档明确提示
# “对同一位置持续重复请求可能被限制”。因此这里按 0.5° 网格单元缓存响应：
# 相邻点击命中同一网格时无需重复出网请求。
# 可用环境变量 PV_NASA_CACHE_TTL（秒，默认 24h）调整。
# ---------------------------------------------------------------------------
NASA_CACHE_TTL = float(os.environ.get("PV_NASA_CACHE_TTL", 24 * 3600))
NASA_CACHE_MAX = 2048
_nasa_cache = {}
_nasa_cache_lock = threading.Lock()


def _grid_cell(lat, lon):
    """将经纬度映射到 0.5° 网格单元（NASA POWER 数据分辨率）。"""
    return (round(math.floor(lat * 2) / 2.0, 1), round(math.floor(lon * 2) / 2.0, 1))


def _cache_get(key):
    entry = _nasa_cache.get(key)
    if entry is None:
        return None
    value, ts = entry
    if time.monotonic() - ts > NASA_CACHE_TTL:
        with _nasa_cache_lock:
            _nasa_cache.pop(key, None)
        return None
    return value


def _cache_put(key, value):
    with _nasa_cache_lock:
        if len(_nasa_cache) >= NASA_CACHE_MAX:
            # 淘汰最早写入的条目，避免缓存无限膨胀
            oldest = min(_nasa_cache, key=lambda k: _nasa_cache[k][1])
            _nasa_cache.pop(oldest, None)
        _nasa_cache[key] = (value, time.monotonic())


# ---------------------------------------------------------------------------
# 轻量级接口限流（每 IP 滑动窗口）
#
# /api/predict 会触发对 NASA POWER 的出网请求，限流用于防止滥用拖垮服务
# 或导致本机 IP 被 NASA 限制。默认 60 次/分钟，可用 PV_RATE_LIMIT_PER_MIN
# 覆盖（<=0 表示关闭）。
# ---------------------------------------------------------------------------
RATE_LIMIT_PER_MIN = int(os.environ.get("PV_RATE_LIMIT_PER_MIN", 60))
_rate_lock = threading.Lock()
_rate_buckets = defaultdict(deque)


def rate_limited(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if RATE_LIMIT_PER_MIN > 0:
            ip = request.remote_addr or "unknown"
            now = time.monotonic()
            with _rate_lock:
                bucket = _rate_buckets[ip]
                while bucket and now - bucket[0] > 60:
                    bucket.popleft()
                if len(bucket) >= RATE_LIMIT_PER_MIN:
                    return jsonify({"error": "请求过于频繁，请稍后再试"}), 429
                bucket.append(now)
                if len(_rate_buckets) > 10000:
                    stale = [k for k, v in _rate_buckets.items() if not v or now - v[-1] > 3600]
                    for k in stale:
                        _rate_buckets.pop(k, None)
        return view(*args, **kwargs)

    return wrapper


def parse_lat_lon(args):
    """Parse and validate lat/lon from query args. Raises ValueError on bad input."""
    if args.get("lat") is None or args.get("lon") is None:
        raise ValueError("缺少参数 lat 或 lon")
    try:
        lat = float(args.get("lat"))
        lon = float(args.get("lon"))
    except (TypeError, ValueError) as exc:
        raise ValueError("lat/lon 必须为数字") from exc
    if not (np.isfinite(lat) and np.isfinite(lon)):
        raise ValueError("lat/lon 不能为 NaN/Inf")
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("lat 必须在 [-90, 90] 范围内")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("lon 必须在 [-180, 180] 范围内")
    return lat, lon


def _require_finite_solar(solar_data):
    required = (
        "ghi_annual_mean",
        "ghi_annual_std",
        "temp_annual_mean",
        "temp_annual_std",
        "precip_annual_mean",
    )
    for key in required:
        value = float(solar_data[key])
        if not np.isfinite(value):
            raise ValueError(f"气候数据无效: {key}={value}")
    return solar_data


def load_station_data():
    global station_data, station_tree
    if station_data is not None:
        return station_data, station_tree

    with _station_lock:
        if station_data is not None:
            return station_data, station_tree

        possible_paths = [
            DATA_SOLAR / "pv_stations_mcdm_scored.csv",
            FRONTEND_PUBLIC_DATA / "pv_stations_mcdm_scored.csv",
            FRONTEND_DIST_DATA / "pv_stations_mcdm_scored.csv",
        ]

        data_path = None
        for path in possible_paths:
            if path.exists():
                data_path = path
                break

        if data_path is None:
            raise FileNotFoundError(f"无法找到光伏电站数据文件。已搜索路径: {possible_paths}")

        loaded = pd.read_csv(data_path)
        loaded_tree = cKDTree(loaded[["lon", "lat"]].to_numpy())
        station_data = loaded
        station_tree = loaded_tree
        return station_data, station_tree


def get_nasa_solar_data(lat, lon, retries=3):
    """获取 NASA POWER 气候数据（带 0.5° 网格缓存与重试）。"""
    key = _grid_cell(lat, lon)
    cached = _cache_get(key)
    if cached is not None:
        result = dict(cached)
        result["source"] = "NASA POWER 2020-2023 (cached)"
        return result

    last_error = None
    for attempt in range(retries):
        solar_data = nasa_api.get_solar_data(lat, lon, start_year=2020, end_year=2023)
        if solar_data is not None:
            _cache_put(key, dict(solar_data))
            solar_data["source"] = "NASA POWER 2020-2023"
            return solar_data
        last_error = f"NASA POWER 第 {attempt + 1} 次请求无数据"
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(
        f"无法从 NASA POWER 获取 ({lat}, {lon}) 的气候数据，请检查网络后重试。{last_error or ''}"
    )


def get_real_solar_data(lat, lon):
    try:
        solar_data = get_nasa_solar_data(lat, lon)
        solar_data["source"] = solar_data.get("source", "NASA POWER 2020-2023")
        return solar_data
    except RuntimeError:
        logger.warning("NASA POWER 不可用，回退到最近站点气候数据 (%.4f, %.4f)", lat, lon)

    stations, tree = load_station_data()
    distance, index = tree.query([lon, lat], k=1)
    row = stations.iloc[int(index)]
    return {
        "ghi_annual_mean": row["ghi_mean"],
        "ghi_annual_std": row["ghi_std"],
        "temp_annual_mean": row["temp_mean"],
        "temp_annual_std": row["temp_std"],
        "precip_annual_mean": row["precip_annual"],
        "source": f'nearest real station: {row["province"]} #{int(row["index"])}',
        "nearest_station_distance_deg": float(distance),
    }


def classify_pvpi(pvpi):
    if pvpi >= 0.8:
        return "优选区", "#00ff88", "极高"
    if pvpi >= 0.6:
        return "适宜区", "#27e7f3", "高"
    if pvpi >= 0.4:
        return "备选区", "#f3df54", "中等"
    return "约束区", "#ff6b6b", "低"


def predict_simple_value(solar_data):
    _require_finite_solar(solar_data)
    ghi = round(float(solar_data["ghi_annual_mean"]), 2)
    temp = round(float(solar_data["temp_annual_mean"]), 2)
    temp_std = round(float(solar_data["temp_annual_std"]), 2)
    precip = round(float(solar_data["precip_annual_mean"]), 2)

    ghi_score = min(ghi / 6, 1)
    temp_score = min(max((25 - abs(temp - 15)) / 25, 0), 1)
    precip_score = min(max((1000 - precip) / 1000, 0), 1)
    stability_score = min(max((10 - temp_std) / 10, 0), 1)
    score = 0.3 * ghi_score + 0.2 * temp_score + 0.25 * precip_score + 0.25 * stability_score
    if not np.isfinite(score):
        raise ValueError("简化公式计算结果无效")
    return max(0.1, min(0.95, round(float(score), 4)))


def predict_simple(lat, lon):
    solar_data = get_real_solar_data(lat, lon)
    pvpi = predict_simple_value(solar_data)
    level, level_color, suitability = classify_pvpi(pvpi)
    return {
        "lat": lat,
        "lon": lon,
        "pvpi": pvpi,
        "pvssi": pvpi,
        "level": level,
        "level_color": level_color,
        "suitability": suitability,
        "model_type": "简化公式",
        "solar_data": {
            "ghi_annual_mean": round(float(solar_data["ghi_annual_mean"]), 2),
            "ghi_annual_std": round(float(solar_data["ghi_annual_std"]), 2),
            "temp_annual_mean": round(float(solar_data["temp_annual_mean"]), 2),
            "temp_annual_std": round(float(solar_data["temp_annual_std"]), 2),
            "precip_annual_mean": round(max(0, float(solar_data["precip_annual_mean"])), 2),
            "source": solar_data.get("source", "unknown"),
        },
    }


def _classify_error_response(exc):
    """按异常类型决定响应码与对外消息，避免泄露内部细节。"""
    if isinstance(exc, ValueError):
        # 校验类错误消息由本项目产生，可安全返回
        return jsonify({"error": str(exc)}), 400
    if isinstance(exc, RuntimeError):
        # NASA/网络等可预期错误，消息可读且安全
        return jsonify({"error": str(exc)}), 503
    logger.exception("接口处理异常: %s", exc)
    return jsonify({"error": "服务器内部错误，请稍后重试"}), 500


@app.route("/api/predict", methods=["GET"])
@rate_limited
def predict():
    try:
        lat, lon = parse_lat_lon(request.args)
        solar_data = get_real_solar_data(lat, lon)
        pvpi = predict_simple_value(solar_data)
        level, level_color, suitability = classify_pvpi(pvpi)

        return jsonify({
            "lat": lat,
            "lon": lon,
            "pvpi": pvpi,
            "pvssi": pvpi,
            "level": level,
            "level_color": level_color,
            "suitability": suitability,
            "model_type": "简化公式",
            "solar_data": {
                "ghi_annual_mean": round(float(solar_data["ghi_annual_mean"]), 2),
                "ghi_annual_std": round(float(solar_data["ghi_annual_std"]), 2),
                "temp_annual_mean": round(float(solar_data["temp_annual_mean"]), 2),
                "temp_annual_std": round(float(solar_data["temp_annual_std"]), 2),
                "precip_annual_mean": round(max(0, float(solar_data["precip_annual_mean"])), 2),
                "source": solar_data.get("source", "unknown"),
            },
        })
    except Exception as exc:
        return _classify_error_response(exc)


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({"model_loaded": False, "model_type": "简化公式"})


@app.route("/api/toggle_mode", methods=["POST"])
def toggle_mode():
    return jsonify({"success": True, "mode": "simple", "message": "已切换到 简化公式"})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
