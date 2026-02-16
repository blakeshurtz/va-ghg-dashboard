"""CLI entrypoint for layout-aware dashboard renders."""

from __future__ import annotations

import argparse

from scripts.config import load_yaml_config, validate_config
from scripts.render import render_layout_base, render_layout_points


TARGET_CHOICES = ("base", "points", "all")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build VA GHG render artifacts")
    parser.add_argument("--config", default="config.yml", help="Path to YAML config")
    parser.add_argument(
        "--target",
        default="all",
        choices=TARGET_CHOICES,
        help="Render target: base, points, or all",
    )
    args = parser.parse_args()

    try:
        cfg = load_yaml_config(args.config)
        validate_config(cfg)
        print(f"[OK] Loaded and validated config: {args.config}")

        if args.target in ("base", "all"):
            base_path = render_layout_base(cfg)
            print(f"[OK] Rendered base layout PNG: {base_path}")

        if args.target in ("points", "all"):
            points_path = render_layout_points(cfg)
            print(f"[OK] Rendered points layout PNG: {points_path}")

        print("[OK] Build finished.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] Build failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
