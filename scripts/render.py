"""Orchestrates layout-aware rendering targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from scripts.io import (
    emissions_to_gdf,
    ensure_crs,
    load_emissions_csv,
    load_va_boundary,
)
from scripts.layout import apply_dark_theme, create_canvas
from scripts.map_base import draw_boundary, set_extent_to_boundary
from scripts.points import draw_points

TARGET_CRS = "EPSG:3857"


def _prepare_paths(cfg: dict[str, Any]) -> dict[str, Path]:
    render_cfg = cfg["render"]
    output_dir = Path(render_cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = render_cfg["outputs"]
    return {
        "output_dir": output_dir,
        "base_png": output_dir / outputs["base_png"],
        "points_png": output_dir / outputs["points_png"],
    }


def _load_boundary_3857(cfg: dict[str, Any]):
    boundary = load_va_boundary(cfg["paths"]["va_boundary"])
    return ensure_crs(boundary, TARGET_CRS)


def _save_figure(fig, path: Path, dpi: int) -> None:
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def render_layout_base(cfg: dict[str, Any]) -> Path:
    """Render layout base map with boundary and blank panel."""
    paths = _prepare_paths(cfg)
    boundary = _load_boundary_3857(cfg)

    fig, map_ax, panel_ax = create_canvas(cfg)
    apply_dark_theme(fig, map_ax, panel_ax, cfg)
    draw_boundary(map_ax, boundary, cfg)
    set_extent_to_boundary(map_ax, boundary, padding_pct=float(cfg["style"].get("padding_pct", 0.02)))

    _save_figure(fig, paths["base_png"], int(cfg["render"]["dpi"]))
    return paths["base_png"]


def render_layout_points(cfg: dict[str, Any]) -> Path:
    """Render layout with boundary plus emissions points."""
    emissions_csv = cfg["paths"].get("emissions_csv")
    if not emissions_csv:
        raise ValueError("paths.emissions_csv is not set; cannot render points target.")

    paths = _prepare_paths(cfg)
    boundary = _load_boundary_3857(cfg)

    points_df = load_emissions_csv(emissions_csv)
    lat_col = cfg["paths"].get("emissions_lat_col", "latitude")
    lon_col = cfg["paths"].get("emissions_lon_col", "longitude")
    points = emissions_to_gdf(points_df, lat_col=lat_col, lon_col=lon_col)
    points = ensure_crs(points, TARGET_CRS)

    fig, map_ax, panel_ax = create_canvas(cfg)
    apply_dark_theme(fig, map_ax, panel_ax, cfg)
    draw_boundary(map_ax, boundary, cfg)
    draw_points(map_ax, points, cfg)
    set_extent_to_boundary(map_ax, boundary, padding_pct=float(cfg["style"].get("padding_pct", 0.02)))

    _save_figure(fig, paths["points_png"], int(cfg["render"]["dpi"]))
    return paths["points_png"]
