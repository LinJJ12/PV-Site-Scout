"""Central path constants for the backend layout."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

DATA_DIR = BACKEND_ROOT / "data"
DATA_CPVPD = DATA_DIR / "cpvpd"
DATA_SOLAR = DATA_DIR / "solar"
MODELS_DIR = BACKEND_ROOT / "models"
RESOURCE_DIR = BACKEND_ROOT / "resource"
LOGS_DIR = RESOURCE_DIR / "logs"

FRONTEND_DIR = REPO_ROOT / "frontend"
FRONTEND_PUBLIC_DATA = FRONTEND_DIR / "public" / "data"
FRONTEND_DIST_DATA = FRONTEND_DIR / "dist" / "data"

STATION_SCORED_CSV = DATA_SOLAR / "pv_stations_mcdm_scored.csv"
GAT_GBDT_MODEL = MODELS_DIR / "model_gat_gbdt_pvssi.pkl"
GBDT_RUNTIME_MODEL = MODELS_DIR / "model_gbdt_runtime.pkl"
