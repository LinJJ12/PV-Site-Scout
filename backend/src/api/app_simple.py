from flask import Flask, jsonify, request

from src.api.app import classify_pvpi, get_real_solar_data, parse_lat_lon, predict_simple_value

try:
    from flask_cors import CORS
except ImportError:
    def CORS(app):
        return app

app = Flask(__name__)
CORS(app)


@app.route("/api/predict", methods=["GET"])
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
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    app.run(host="127.0.0.1", port=5000, debug=True)
