"""完整预测服务。

默认优先加载 GBDT 运行包（model_gbdt_runtime.pkl）：推理快、不依赖 torch。
仅当运行包缺失时才回退到 GAT+GBDT 完整包，并按需惰性导入 torch。
"""

import logging
import os
import pickle

import numpy as np
from flask import Flask, jsonify, request
from scipy.spatial import cKDTree

from src.api.app import (
    classify_pvpi,
    get_nasa_solar_data,
    get_real_solar_data,
    parse_lat_lon,
    predict_simple_value,
    rate_limited,
    _classify_error_response,
)
from src.lib.paths import GAT_GBDT_MODEL, GBDT_RUNTIME_MODEL

try:
    from flask_cors import CORS
except ImportError:
    def CORS(app):
        return app

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

model_package = None
gat_model = None
use_full_model = False

# torch / torch_geometric 惰性导入：常规 GBDT 推理完全不需要 torch，
# 只有加载 GAT 完整包时才会真正 import，避免无谓的启动开销。
TORCH_AVAILABLE = False
torch = None
F = None


def _try_import_torch():
    """按需导入 torch/torch_geometric，成功时返回 True。"""
    global TORCH_AVAILABLE, torch, F
    if TORCH_AVAILABLE:
        return True
    try:
        import torch as _torch
        import torch.nn.functional as _F
        from torch_geometric.data import Data  # noqa: F401
        from torch_geometric.nn import GATConv  # noqa: F401

        torch = _torch
        F = _F
        TORCH_AVAILABLE = True
    except ImportError:
        TORCH_AVAILABLE = False
    return TORCH_AVAILABLE


def _build_gat_model(package):
    """从完整包构建 GAT 模型；torch 不可用或参数缺失时返回 None。"""
    global gat_model
    if not _try_import_torch():
        return None
    from torch_geometric.nn import GATConv

    class GATModel(torch.nn.Module):
        def __init__(self, in_channels, hidden_channels=64, heads=4, dropout=0.25, num_classes=3):
            super().__init__()
            self.dropout = dropout
            self.conv1 = GATConv(in_channels, hidden_channels, heads=heads, dropout=dropout)
            self.conv2 = GATConv(hidden_channels * heads, hidden_channels, heads=1, concat=False, dropout=dropout)
            self.norm = torch.nn.LayerNorm(hidden_channels)
            self.reg_head = torch.nn.Sequential(
                torch.nn.Linear(hidden_channels, hidden_channels // 2),
                torch.nn.ReLU(),
                torch.nn.Dropout(dropout),
                torch.nn.Linear(hidden_channels // 2, 1),
            )
            self.cls_head = torch.nn.Sequential(
                torch.nn.Linear(hidden_channels, hidden_channels // 2),
                torch.nn.ReLU(),
                torch.nn.Dropout(dropout),
                torch.nn.Linear(hidden_channels // 2, num_classes),
            )
            self.skip_reg = torch.nn.Linear(in_channels, 1)

        def forward(self, x, edge_index):
            h = F.elu(self.conv1(x, edge_index))
            h = F.dropout(h, p=self.dropout, training=self.training)
            h = F.elu(self.conv2(h, edge_index))
            h = self.norm(h)
            reg = self.reg_head(h).squeeze(-1) + 0.15 * self.skip_reg(x).squeeze(-1)
            logits = self.cls_head(h)
            return reg, logits

    try:
        params = package["gat_params"]
        model = GATModel(
            in_channels=params["in_channels"],
            hidden_channels=params["hidden_channels"],
            heads=params["heads"],
            dropout=params["dropout"],
            num_classes=params["num_classes"],
        )
        model.load_state_dict(package["gat_state_dict"], strict=True)
        model.eval()
        gat_model = model
        return model
    except Exception as exc:
        logger.warning("GAT 模型构建失败，将仅使用 GBDT 推理: %s", exc)
        return None


K_NEIGHBORS = 10
MODEL_LEVEL_LABELS = {
    "low": "约束区",
    "medium": "备选区",
    "high": "适宜区",
}
MODEL_LEVEL_COLORS = {
    "约束区": "#ff6b6b",
    "备选区": "#f3df54",
    "适宜区": "#27e7f3",
    "优选区": "#00ff88",
}
MODEL_LEVEL_SUITABILITY = {
    "约束区": "低",
    "备选区": "中等",
    "适宜区": "高",
    "优选区": "极高",
}


def load_full_model():
    """加载模型包：优先 GBDT 运行包，缺失时回退 GAT 完整包。"""
    global model_package, gat_model, use_full_model

    if GBDT_RUNTIME_MODEL.exists():
        model_path = GBDT_RUNTIME_MODEL
    elif GAT_GBDT_MODEL.exists():
        model_path = GAT_GBDT_MODEL
    else:
        logger.warning("未找到模型包（%s / %s），将只提供简化公式", GBDT_RUNTIME_MODEL.name, GAT_GBDT_MODEL.name)
        return False

    try:
        with open(model_path, "rb") as f:
            model_package = pickle.load(f)
    except Exception as exc:
        logger.exception("模型包加载失败 %s: %s", model_path, exc)
        model_package = None
        gat_model = None
        use_full_model = False
        return False

    use_full_model = "gbdt_models" in model_package
    if use_full_model and "gat_state_dict" in model_package:
        _build_gat_model(model_package)

    if use_full_model:
        logger.info("已加载模型包 %s（%s）", model_path.name, _model_type_label())
    return use_full_model


def _iter_gbdt_models(gbdt_models):
    if isinstance(gbdt_models, dict):
        gbdt_models = list(gbdt_models.values())
    for item in gbdt_models:
        if isinstance(item, tuple) and len(item) >= 2:
            yield item[1]
        else:
            yield item


def transform_with_fitted_gbdt(X, scaler, gbdt_models):
    X_sc = scaler.transform(X)
    preds = [model.predict(X_sc).reshape(-1, 1) for model in _iter_gbdt_models(gbdt_models)]
    return np.column_stack([X_sc] + preds).astype(np.float32)


def build_knn_edge_index(xy, k=K_NEIGHBORS):
    if not TORCH_AVAILABLE:
        raise RuntimeError("torch 未加载，无法构建 GAT 推理图")
    tree = cKDTree(xy)
    k_eff = min(k + 1, len(xy))
    _, indices = tree.query(xy, k=k_eff)
    src, dst = [], []
    for i in range(len(xy)):
        for j in np.atleast_1d(indices[i])[1:]:
            src.extend([i, int(j)])
            dst.extend([int(j), i])
    return torch.tensor([src, dst], dtype=torch.long)


def _build_spatial_features(lat, lon, solar_data, model_package):
    ghi_mean = float(solar_data["ghi_annual_mean"])
    ghi_std = float(solar_data["ghi_annual_std"])
    temp_mean = float(solar_data["temp_annual_mean"])
    temp_std = float(solar_data["temp_annual_std"])
    precip_annual = float(solar_data["precip_annual_mean"])

    x_m = (lon - 105) * 111000 * np.cos(np.radians(lat))
    y_m = (lat - 35) * 111000

    train_xy = model_package["train_xy"]
    tree = cKDTree(train_xy)
    agglomeration = len(tree.query_ball_point([x_m, y_m], r=50000))
    dist_m, _ = tree.query([x_m, y_m], k=1)
    nearest_station_km = float(dist_m) / 1000.0

    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    pos_x = float(np.cos(lat_rad) * np.cos(lon_rad))
    pos_y = float(np.cos(lat_rad) * np.sin(lon_rad))
    pos_z = float(np.sin(lat_rad))
    log_area = float(np.log1p(model_package["train_df_minimal"]["area_km2"].median()))

    feature_values = [
        lon,
        lat,
        pos_x,
        pos_y,
        pos_z,
        log_area,
        ghi_mean,
        ghi_std,
        temp_mean,
        temp_std,
        max(0, precip_annual),
        float(agglomeration),
        nearest_station_km,
    ]
    return {
        "feature_values": feature_values,
        "x_m": x_m,
        "y_m": y_m,
        "agglomeration": agglomeration,
        "ghi_mean": ghi_mean,
        "ghi_std": ghi_std,
        "temp_mean": temp_mean,
        "temp_std": temp_std,
        "precip_annual": precip_annual,
    }


INFERENCE_VERSION = "v3-nasa-gat-reg"


def _model_type_label():
    if not use_full_model or model_package is None:
        return "简化公式"
    if gat_model is not None:
        return "GAT+GBDT集成模型"
    return "GBDT模型"


load_full_model()


def _pvssi_to_pvpi(pvssi_value):
    pvssi_clipped = float(np.clip(pvssi_value, 0.0, 100.0))
    return max(0.1, min(0.99, pvssi_clipped / 100.0))


def predict_simple(lat, lon):
    # 与基础模式保持一致：NASA 不可用时回退最近站点，保证离线可用
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


def _full_prediction(lat, lon):
    if model_package is None:
        raise RuntimeError("完整模型未加载，请确认 backend/models/model_gbdt_runtime.pkl 存在")

    solar_data = get_nasa_solar_data(lat, lon)
    for key in ("ghi_annual_mean", "ghi_annual_std", "temp_annual_mean", "temp_annual_std", "precip_annual_mean"):
        if not np.isfinite(float(solar_data[key])):
            raise ValueError(f"气候数据无效: {key}")
    spatial = _build_spatial_features(lat, lon, solar_data, model_package)
    feature_values = spatial["feature_values"]
    X_cand = np.array([feature_values], dtype=np.float32)

    gbdt_models = model_package["gbdt_models"]
    x_scaler = model_package["x_scaler"]
    y_scaler = model_package["y_scaler"]

    gbdt_scaled_preds = [float(m.predict(x_scaler.transform(X_cand))[0]) for m in _iter_gbdt_models(gbdt_models)]
    gbdt_pred_mean = float(np.mean(gbdt_scaled_preds))

    pvssi_model = gbdt_pred_mean
    pvpi_source = "gbdt"
    gat_probs = None

    if TORCH_AVAILABLE and gat_model is not None and "train_aug_features" in model_package:
        from torch_geometric.data import Data

        import torch as _torch

        X_train = model_package["train_features"].astype(np.float32)
        X_combined = np.vstack([X_train, X_cand])
        X_aug_combined = transform_with_fitted_gbdt(X_combined, x_scaler, gbdt_models)

        xy_combined = np.vstack([
            model_package["train_xy"],
            np.array([[spatial["x_m"], spatial["y_m"]]], dtype=float),
        ])
        edge_index = build_knn_edge_index(xy_combined, k=K_NEIGHBORS)
        new_idx = len(X_train)

        data = Data(
            x=_torch.tensor(X_aug_combined, dtype=_torch.float32),
            edge_index=edge_index,
        )
        with _torch.no_grad():
            reg_out, cls_out = gat_model(data.x, data.edge_index)
            reg_value = reg_out[new_idx]
            if hasattr(reg_value, "dim") and reg_value.dim() > 0:
                reg_value = reg_value.squeeze()
            pvssi_model = float(
                y_scaler.inverse_transform(reg_value.detach().cpu().numpy().reshape(-1, 1))[0, 0]
            )
            pvpi_source = "gat_reg"
            gat_probs = F.softmax(cls_out[new_idx], dim=0).cpu().numpy()

    pvpi = _pvssi_to_pvpi(pvssi_model)
    if not np.isfinite(pvpi):
        raise ValueError("模型输出无效（NaN/Inf）")
    level, level_color, suitability = classify_pvpi(pvpi)

    result = {
        "lat": lat,
        "lon": lon,
        "pvpi": round(pvpi, 4),
        "pvssi": round(pvpi, 4),
        "pvssi_model": round(float(np.clip(pvssi_model, 0.0, 100.0)), 4),
        "level": level,
        "level_color": level_color,
        "suitability": suitability,
        "model_type": _model_type_label(),
        "inference_version": INFERENCE_VERSION,
        "pvpi_source": pvpi_source,
        "gbdt_pred": round(gbdt_pred_mean, 4),
        "agglomeration": spatial["agglomeration"],
        "solar_data": {
            "ghi_annual_mean": round(spatial["ghi_mean"], 2),
            "ghi_annual_std": round(spatial["ghi_std"], 2),
            "temp_annual_mean": round(spatial["temp_mean"], 2),
            "temp_annual_std": round(spatial["temp_std"], 2),
            "precip_annual_mean": round(max(0, spatial["precip_annual"]), 2),
            "source": solar_data.get("source", "unknown"),
        },
    }
    if gat_probs is not None:
        result["gat_probs"] = [round(float(p), 4) for p in gat_probs]
    return result


@app.route("/api/predict", methods=["GET"])
@rate_limited
def predict():
    try:
        lat, lon = parse_lat_lon(request.args)
        mode = request.args.get("mode", "simple")
        if mode == "full" and model_package is None:
            return jsonify({"error": "完整模型未加载"}), 503
        result = _full_prediction(lat, lon) if mode == "full" else predict_simple(lat, lon)
        return jsonify(result)
    except Exception as exc:
        return _classify_error_response(exc)


@app.route("/api/status", methods=["GET"])
def status():
    y_min = float(model_package["train_df_minimal"]["PVSSI_rule"].min()) if model_package else None
    y_max = float(model_package["train_df_minimal"]["PVSSI_rule"].max()) if model_package else None
    return jsonify({
        "model_loaded": model_package is not None,
        "model_type": _model_type_label(),
        "torch_available": TORCH_AVAILABLE,
        "inference_version": INFERENCE_VERSION,
        "feature_cols": model_package["feature_cols"] if model_package else None,
        "levels": model_package["id_to_level"] if model_package else None,
        "y_min": y_min,
        "y_max": y_max,
        "gbdt_models_type": type(model_package["gbdt_models"]).__name__ if model_package else None
    })


if os.environ.get("PV_ENABLE_DEBUG_ENDPOINTS", "").lower() in {"1", "true", "yes"}:

    @app.route("/api/debug_model", methods=["GET"])
    def debug_model():
        """调试端点：默认关闭，需设置 PV_ENABLE_DEBUG_ENDPOINTS=1 才启用。"""
        try:
            lat, lon = parse_lat_lon({
                "lat": request.args.get("lat", 31.23),
                "lon": request.args.get("lon", 121.47),
            })
            result = _full_prediction(lat, lon)
            return jsonify({
                "input_lat": lat,
                "input_lon": lon,
                "feature_cols": model_package["feature_cols"],
                "pvpi": result["pvpi"],
                "pvssi_model": result.get("pvssi_model"),
                "gbdt_pred": result.get("gbdt_pred"),
                "level": result.get("level"),
                "gat_probs": result.get("gat_probs"),
                "solar_data": result.get("solar_data"),
            })
        except Exception as exc:
            return _classify_error_response(exc)


@app.route("/api/toggle_mode", methods=["POST"])
def toggle_mode():
    global use_full_model
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "simple")
    if mode == "full":
        use_full_model = model_package is not None or load_full_model()
    else:
        use_full_model = False
    return jsonify({
        "success": True,
        "mode": "full" if use_full_model else "simple",
        "model_type": _model_type_label(),
        "torch_available": TORCH_AVAILABLE,
        "message": f'已切换到 {_model_type_label()}',
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
