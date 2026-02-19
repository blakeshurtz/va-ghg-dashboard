"""CLI entrypoint for the VA GHG dashboard map render."""

from __future__ import annotations

import argparse

from scripts.config import load_yaml_config, validate_config
from scripts.render import render_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the VA GHG dashboard map")
    parser.add_argument("--config", default="config.yml", help="Path to YAML config")
    args = parser.parse_args()

    try:
        cfg = load_yaml_config(args.config)
        validate_config(cfg)
        print(f"[OK] Loaded and validated config: {args.config}")

        output_path = render_map(cfg)
        print(f"[OK] Rendered map: {output_path}")

        print("[OK] Build finished.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] Build failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
