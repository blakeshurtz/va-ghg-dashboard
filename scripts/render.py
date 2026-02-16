"""Orchestrates layout-aware rendering targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import rasterio
from rasterio.warp import transform_bounds

from scripts.io import (
    emissions_to_gdf,
    ensure_crs,
    load_emissions_csv,
    load_va_boundary,
    load_vector_collection,
)
from scripts.layout import apply_dark_theme, create_canvas
from scripts.map_base import draw_boundary, draw_pipelines, draw_reference_layer, set_extent_to_boundary
from scripts.points import draw_points_with_facility_icons

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


def _load_pipelines_3857(cfg: dict[str, Any]):
    pipelines_path = cfg["paths"].get("pipelines")
    if not pipelines_path:
        return None

    layer = cfg["paths"].get("pipelines_layer")
    pipelines = load_vector_collection(pipelines_path, layer=layer)
    return ensure_crs(pipelines, TARGET_CRS)


def _load_reference_layers_3857(cfg: dict[str, Any]) -> dict[str, Any]:
    path_keys = {
        "railroads": "railroads",
        "primary_roads": "primary_roads",
        "incorporated_places": "incorporated_places",
        "principal_ports": "principal_ports",
    }

    layers: dict[str, Any] = {}
    for layer_name, path_key in path_keys.items():
        source_path = cfg["paths"].get(path_key)
        if not source_path:
            continue
        layer = load_vector_collection(source_path)
        layers[layer_name] = ensure_crs(layer, TARGET_CRS)

    return layers


def _draw_reference_layers(map_ax, boundary, cfg: dict[str, Any], layers: dict[str, Any]) -> None:
    style = cfg.get("style", {})
    for layer_name, layer_gdf in layers.items():
        draw_reference_layer(
            map_ax,
            layer_gdf,
            boundary,
            color=style.get(f"{layer_name}_color", "#546e7a"),
            linewidth=float(style.get(f"{layer_name}_linewidth", 0.35)),
            alpha=float(style.get(f"{layer_name}_alpha", 0.35)),
            zorder=float(style.get(f"{layer_name}_zorder", 1.5)),
            marker_size=float(style.get(f"{layer_name}_marker_size", 6.0)),
        )


def _save_figure(fig, path: Path, dpi: int) -> None:
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def _draw_terrain_overlay(map_ax, cfg: dict[str, Any]) -> None:
    """Draw terrain tint PNG aligned to the map CRS when terrain outputs are available."""
    paths_cfg = cfg.get("paths", {})
    terrain_processed_dir = Path(paths_cfg.get("terrain_processed_dir", "layers/terrain/processed"))
    terrain_tint_name = paths_cfg.get("terrain_tint_png", "terrain_tint_va.png")
    terrain_dem_name = paths_cfg.get("terrain_dem_tif", "dem_va_clipped.tif")

    tint_path = terrain_processed_dir / terrain_tint_name
    dem_path = terrain_processed_dir / terrain_dem_name
    if not tint_path.exists() or not dem_path.exists():
        return

    terrain_img = plt.imread(tint_path)
    with rasterio.open(dem_path) as dem:
        if dem.crs is None:
            return
        minx, miny, maxx, maxy = transform_bounds(dem.crs, TARGET_CRS, *dem.bounds, densify_pts=21)

    map_ax.imshow(
        terrain_img,
        extent=(minx, maxx, miny, maxy),
        origin="upper",
        interpolation="bilinear",
        zorder=float(cfg.get("style", {}).get("terrain_zorder", 0.5)),
    )


def render_layout_base(cfg: dict[str, Any]) -> Path:
    """Render layout base map with boundary and blank panel."""
    paths = _prepare_paths(cfg)
    boundary = _load_boundary_3857(cfg)
    pipelines = _load_pipelines_3857(cfg)
    reference_layers = _load_reference_layers_3857(cfg)

    fig, map_ax, panel_ax = create_canvas(cfg)
    apply_dark_theme(fig, map_ax, panel_ax, cfg)
    _draw_terrain_overlay(map_ax, cfg)
    draw_boundary(map_ax, boundary, cfg)
    if pipelines is not None:
        draw_pipelines(map_ax, pipelines, boundary, cfg)
    _draw_reference_layers(map_ax, boundary, cfg, reference_layers)
    set_extent_to_boundary(map_ax, boundary, padding_pct=float(cfg["style"].get("padding_pct", 0.02)))

    _save_figure(fig, paths["base_png"], int(cfg["render"]["dpi"]))
    return paths["base_png"]


def render_layout_points(cfg: dict[str, Any]) -> Path:
    """Render 2023 layout with top-20 icons and subpart labels for other facilities."""
    emissions_csv = cfg["paths"].get("emissions_csv")
    if not emissions_csv:
        raise ValueError("paths.emissions_csv is not set; cannot render points target.")

    paths = _prepare_paths(cfg)
    boundary = _load_boundary_3857(cfg)
    pipelines = _load_pipelines_3857(cfg)
    reference_layers = _load_reference_layers_3857(cfg)

    points_df = load_emissions_csv(emissions_csv)
    if "reporting_year" in points_df.columns:
        points_df = points_df[points_df["reporting_year"] == 2023]
    lat_col = cfg["paths"].get("emissions_lat_col", "latitude")
    lon_col = cfg["paths"].get("emissions_lon_col", "longitude")
    points = emissions_to_gdf(points_df, lat_col=lat_col, lon_col=lon_col)
    points = ensure_crs(points, TARGET_CRS)

    top20_csv = cfg["paths"].get("top20_csv")
    top20_names: set[str] = set()
    if top20_csv:
        top20_df = load_emissions_csv(top20_csv)
        if "facility_name" in top20_df.columns:
            top20_names = {
                str(name).strip().casefold()
                for name in top20_df["facility_name"].dropna().tolist()
                if str(name).strip()
            }

    if "facility_name" in points.columns and top20_names:
        points["_is_top20"] = (
            points["facility_name"].astype(str).str.strip().str.casefold().isin(top20_names)
        )
    else:
        points["_is_top20"] = False

    fig, map_ax, panel_ax = create_canvas(cfg)
    apply_dark_theme(fig, map_ax, panel_ax, cfg)
    _draw_terrain_overlay(map_ax, cfg)
    draw_boundary(map_ax, boundary, cfg)
    if pipelines is not None:
        draw_pipelines(map_ax, pipelines, boundary, cfg)
    _draw_reference_layers(map_ax, boundary, cfg, reference_layers)
    draw_points_with_facility_icons(map_ax, points, cfg)
    set_extent_to_boundary(map_ax, boundary, padding_pct=float(cfg["style"].get("padding_pct", 0.02)))

    _save_figure(fig, paths["points_png"], int(cfg["render"]["dpi"]))
    return paths["points_png"]
