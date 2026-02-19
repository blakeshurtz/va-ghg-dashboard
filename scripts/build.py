"""CLI entrypoint for layout-aware dashboard renders."""

from __future__ import annotations

import argparse

from scripts.config import load_yaml_config, validate_config
from scripts.render import render_layout_base, render_layout_points
from scripts.terrain import run_terrain_pipeline


TARGET_CHOICES = ("base", "points", "terrain", "layers", "all")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build VA GHG render artifacts")
    parser.add_argument("--config", default="config.yml", help="Path to YAML config")
    parser.add_argument(
        "--target",
        default="all",
        choices=TARGET_CHOICES,
        help="Render target: base, points, terrain, layers (base+points, no terrain), or all",
    )
    args = parser.parse_args()

    try:
        cfg = load_yaml_config(args.config)
        validate_config(cfg)
        print(f"[OK] Loaded and validated config: {args.config}")

        if args.target in ("terrain", "all"):
            print("[NEXT] Running terrain acquisition + preprocessing + tint generation...")
            terrain_result = run_terrain_pipeline(cfg)
            if terrain_result is None:
                print("[WARN] Terrain step skipped.")
            else:
                print(f"[OK] Terrain DEM clipped: {terrain_result.dem_path}")
                print(f"[OK] Terrain hillshade: {terrain_result.hillshade_path}")
                print(f"[OK] Terrain tint PNG: {terrain_result.tint_png_path}")

        if args.target in ("base", "layers", "all"):
            base_path = render_layout_base(cfg)
            print(f"[OK] Rendered base layout PNG: {base_path}")

        if args.target in ("points", "layers", "all"):
            points_path = render_layout_points(cfg)
            print(f"[OK] Rendered points layout PNG: {points_path}")

        print("[OK] Build finished.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] Build failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
