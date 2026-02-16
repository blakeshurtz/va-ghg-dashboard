"""Configuration loading and validation utilities for render scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REQUIRED_RENDER_KEYS = {"width_px", "height_px", "dpi", "output_dir", "outputs", "theme"}
REQUIRED_OUTPUT_KEYS = {"base_png", "points_png"}
REQUIRED_LAYOUT_KEYS = {"map_frac", "panel_frac"}
REQUIRED_PATH_KEYS = {"va_boundary"}
REQUIRED_STYLE_KEYS = {
    "background",
    "boundary_linewidth",
    "boundary_alpha",
    "points_size",
    "points_alpha",
}


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file into a dictionary."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping/object.")

    return data


def _require_mapping(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    value = cfg.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{key}' must be a mapping/object.")
    return value


def validate_config(cfg: dict[str, Any]) -> None:
    """Validate required render settings and data paths with clear errors."""
    render = _require_mapping(cfg, "render")
    layout = _require_mapping(cfg, "layout")
    paths = _require_mapping(cfg, "paths")
    style = _require_mapping(cfg, "style")

    missing_render = REQUIRED_RENDER_KEYS - set(render)
    if missing_render:
        raise ValueError(f"Missing render keys: {sorted(missing_render)}")

    outputs = render.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("Config key 'render.outputs' must be a mapping/object.")

    missing_outputs = REQUIRED_OUTPUT_KEYS - set(outputs)
    if missing_outputs:
        raise ValueError(f"Missing render.outputs keys: {sorted(missing_outputs)}")

    missing_layout = REQUIRED_LAYOUT_KEYS - set(layout)
    if missing_layout:
        raise ValueError(f"Missing layout keys: {sorted(missing_layout)}")

    total_frac = float(layout["map_frac"]) + float(layout["panel_frac"])
    if abs(total_frac - 1.0) > 1e-6:
        raise ValueError("layout.map_frac + layout.panel_frac must equal 1.0")

    missing_paths = REQUIRED_PATH_KEYS - set(paths)
    if missing_paths:
        raise ValueError(f"Missing paths keys: {sorted(missing_paths)}")

    va_boundary_path = Path(str(paths["va_boundary"]))
    if not va_boundary_path.exists():
        raise FileNotFoundError(f"Boundary file not found: {va_boundary_path}")


    pipelines = paths.get("pipelines")
    if pipelines is not None and str(pipelines).strip():
        pipelines_path = Path(str(pipelines))
        if not pipelines_path.exists():
            raise FileNotFoundError(f"Configured pipelines file not found: {pipelines_path}")

    emissions_csv = paths.get("emissions_csv")
    if emissions_csv is not None and str(emissions_csv).strip():
        emissions_path = Path(str(emissions_csv))
        if not emissions_path.exists():
            raise FileNotFoundError(
                f"Configured emissions CSV not found: {emissions_path}. "
                "Set paths.emissions_csv to null/empty to skip points rendering."
            )


    top20_csv = paths.get("top20_csv")
    if top20_csv is not None and str(top20_csv).strip():
        top20_path = Path(str(top20_csv))
        if not top20_path.exists():
            raise FileNotFoundError(f"Configured top-20 CSV not found: {top20_path}")

    missing_style = REQUIRED_STYLE_KEYS - set(style)
    if missing_style:
        raise ValueError(f"Missing style keys: {sorted(missing_style)}")
