"""从完整 GAT+GBDT pickle 导出无 torch 依赖的运行时包。

在有 torch 的环境执行一次：
  python scripts/export_gbdt_runtime.py
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.lib.paths import GAT_GBDT_MODEL, MODELS_DIR

KEEP_KEYS = (
    "gbdt_models",
    "x_scaler",
    "y_scaler",
    "feature_cols",
    "train_xy",
    "train_df_minimal",
    "train_features",
    "id_to_level",
)

OUT_PATH = MODELS_DIR / "model_gbdt_runtime.pkl"


def main() -> None:
    if not GAT_GBDT_MODEL.exists():
        raise SystemExit(f"missing source model: {GAT_GBDT_MODEL}")

    with open(GAT_GBDT_MODEL, "rb") as f:
        full = pickle.load(f)

    slim = {k: full[k] for k in KEEP_KEYS if k in full}
    missing = [k for k in KEEP_KEYS if k not in slim]
    if missing:
        raise SystemExit(f"source model missing keys: {missing}")

    with open(OUT_PATH, "wb") as f:
        pickle.dump(slim, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"wrote {OUT_PATH}")
    print("keys:", sorted(slim.keys()))


if __name__ == "__main__":
    main()
