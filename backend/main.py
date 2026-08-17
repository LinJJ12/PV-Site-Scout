"""Backend entrypoint.

用法（在 backend/ 目录）：
  python main.py                 # 默认启动完整模型 API
  python main.py --mode full     # GAT+GBDT
  python main.py --mode simple   # 简化公式（独立 app）
  python main.py --mode base     # 基础 API（api/app.py）
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="PV site prediction API server")
    parser.add_argument(
        "--mode",
        choices=("full", "simple", "base"),
        default="full",
        help="API 模式：full=完整模型，simple/base=简化公式",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.mode == "full":
        from src.api.app_full import app
    elif args.mode == "simple":
        from src.api.app_simple import app
    else:
        from src.api.app import app

    # full 默认关闭 debug；simple/base 保持原先的 debug=True 行为
    debug = args.debug if args.mode == "full" else True
    app.run(host=args.host, port=args.port, debug=debug)


if __name__ == "__main__":
    main()
