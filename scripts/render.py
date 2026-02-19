"""Orchestrates layout-aware rendering targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import contextily as ctx
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

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


def _polygon_to_mpl_path(polygon: Polygon) -> MplPath:
    vertices: list[tuple[float, float]] = []
    codes: list[int] = []

    def add_ring(coords) -> None:
        ring = list(coords)
        if len(ring) < 3:
            return
        for index, (x_coord, y_coord) in enumerate(ring):
            vertices.append((float(x_coord), float(y_coord)))
            if index == 0:
                codes.append(MplPath.MOVETO)
            elif index == len(ring) - 1:
                codes.append(MplPath.CLOSEPOLY)
            else:
                codes.append(MplPath.LINETO)

    add_ring(polygon.exterior.coords)
    for interior in polygon.interiors:
        add_ring(interior.coords)

    if not vertices:
        return MplPath(np.empty((0, 2), dtype=float), np.empty((0,), dtype=np.uint8))
    return MplPath(np.asarray(vertices, dtype=float), np.asarray(codes, dtype=np.uint8))


def _boundary_clip_patch(boundary) -> PathPatch | None:
    geometry = boundary.geometry.union_all()
    polygons: list[Polygon]
    if isinstance(geometry, Polygon):
        polygons = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    else:
        polygons = []

    paths = [_polygon_to_mpl_path(poly) for poly in polygons if not poly.is_empty]
    if not paths:
        return None

    clip_path = paths[0] if len(paths) == 1 else MplPath.make_compound_path(*paths)
    return PathPatch(clip_path, transform=None)


def _draw_terrain_overlay(map_ax, boundary, cfg: dict[str, Any]) -> None:
    """Draw terrain hillshade fetched via contextily tiles, clipped to the VA boundary.

    Tiles are natively in EPSG:3857 (matching the display CRS), which eliminates
    the CRS mismatch that caused terrain clipping artefacts with the old DEM-based
    pipeline.  No local DEM data is required.
    """
    terrain_cfg = cfg.get("terrain", {})
    style = cfg.get("style", {})
    tint_strength = float(terrain_cfg.get("tint_strength", 0.25))
    terrain_zorder = float(style.get("terrain_zorder", 0.5))
    tile_zoom = terrain_cfg.get("tile_zoom", "auto")

    # Boundary is already in EPSG:3857
    minx, miny, maxx, maxy = boundary.total_bounds

    try:
        img, (w, s, e, n) = ctx.bounds2img(
            minx, miny, maxx, maxy,
            source=ctx.providers.Esri.WorldShadedRelief,
            ll=False,
            zoom=tile_zoom,
        )
    except Exception as exc:
        print(f"[WARN] Could not fetch terrain tiles: {exc}")
        return

    # Convert to grayscale luminance (0-1)
    gray = np.mean(img[..., :3].astype(np.float32), axis=2) / 255.0

    # Build RGBA overlay matching the dark-theme tint formula:
    #   gray channel = 150 + luminance * 50  (out of 255)
    #   alpha = luminance * tint_strength
    h, w_px = gray.shape
    rgba = np.zeros((h, w_px, 4), dtype=np.float32)
    base_gray = (150.0 + gray * 50.0) / 255.0
    rgba[..., 0] = base_gray
    rgba[..., 1] = base_gray
    rgba[..., 2] = base_gray
    rgba[..., 3] = gray * tint_strength

    # extent for matplotlib imshow: (left, right, bottom, top)
    extent = (w, e, s, n)

    image_artist = map_ax.imshow(
        rgba,
        extent=extent,
        origin="upper",
        interpolation="bilinear",
        zorder=terrain_zorder,
    )

    clip_patch = _boundary_clip_patch(boundary)
    if clip_patch is not None:
        clip_patch.set_transform(map_ax.transData)
        image_artist.set_clip_path(clip_patch)


def render_layout_base(cfg: dict[str, Any]) -> Path:
    """Render layout base map with boundary and blank panel."""
    paths = _prepare_paths(cfg)
    boundary = _load_boundary_3857(cfg)
    pipelines = _load_pipelines_3857(cfg)
    reference_layers = _load_reference_layers_3857(cfg)

    fig, map_ax, panel_ax = create_canvas(cfg)
    apply_dark_theme(fig, map_ax, panel_ax, cfg)
    _draw_terrain_overlay(map_ax, boundary, cfg)
    draw_boundary(map_ax, boundary, cfg)
    if pipelines is not None:
        draw_pipelines(map_ax, pipelines, boundary, cfg)
    _draw_reference_layers(map_ax, boundary, cfg, reference_layers)
    set_extent_to_boundary(map_ax, boundary, padding_pct=float(cfg["style"].get("padding_pct", 0.02)))

    _save_figure(fig, paths["base_png"], int(cfg["render"]["dpi"]))
    return paths["base_png"]


def render_layout_points(cfg: dict[str, Any]) -> Path:
    """Render 2023 layout with facility icons scaled by GHG quantity."""
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

    fig, map_ax, panel_ax = create_canvas(cfg)
    apply_dark_theme(fig, map_ax, panel_ax, cfg)
    _draw_terrain_overlay(map_ax, boundary, cfg)
    draw_boundary(map_ax, boundary, cfg)
    if pipelines is not None:
        draw_pipelines(map_ax, pipelines, boundary, cfg)
    _draw_reference_layers(map_ax, boundary, cfg, reference_layers)
    draw_points_with_facility_icons(map_ax, points, cfg)
    set_extent_to_boundary(map_ax, boundary, padding_pct=float(cfg["style"].get("padding_pct", 0.02)))

    _save_figure(fig, paths["points_png"], int(cfg["render"]["dpi"]))
    return paths["points_png"]
