"""Backend entrypoint.

用法（在 backend/ 目录）：
  python main.py                 # 默认启动完整模型 API（GBDT 运行包优先）
  python main.py --mode full     # GAT+GBDT（仅在缺少运行包时才走 GAT，需 torch）
  python main.py --mode simple   # 简化公式（独立 app）
  python main.py --mode base     # 基础 API（api/app.py）

环境变量：
  PV_RATE_LIMIT_PER_MIN        /api/predict 每 IP 限流（默认 60，<=0 关闭）
  PV_NASA_CACHE_TTL            NASA POWER 结果缓存时长（秒，默认 24h）
  PV_ENABLE_DEBUG_ENDPOINTS    设为 1 时启用 /api/debug_model 调试端点
"""

from __future__ import annotations

import argparse
import logging


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="PV site prediction API server")
    parser.add_argument(
        "--mode",
        choices=("full", "simple", "base"),
        default="full",
        help="API 模式：full=完整模型（GBDT 优先），simple/base=简化公式",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启 Flask 调试模式（仅本地开发使用；调试器存在代码执行风险，勿对外网开放）",
    )
    args = parser.parse_args()

    if args.mode == "full":
        from src.api.app_full import app
    elif args.mode == "simple":
        from src.api.app_simple import app
    else:
        from src.api.app import app

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
