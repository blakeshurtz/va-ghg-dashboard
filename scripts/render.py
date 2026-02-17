"""Orchestrates layout-aware rendering targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import warnings

import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch
import numpy as np
import rasterio
from shapely.geometry import MultiPolygon, Polygon
from rasterio.transform import array_bounds
from rasterio.warp import calculate_default_transform, reproject, transform_bounds

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
from scripts.geometry_utils import repair_geometry

TARGET_CRS = "EPSG:3857"


def _target_crs(cfg: dict[str, Any]) -> str:
    return str(cfg.get("crs", {}).get("map_crs", TARGET_CRS))


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
    return ensure_crs(boundary, _target_crs(cfg))


def _load_pipelines_3857(cfg: dict[str, Any]):
    pipelines_path = cfg["paths"].get("pipelines")
    if not pipelines_path:
        return None

    layer = cfg["paths"].get("pipelines_layer")
    pipelines = load_vector_collection(pipelines_path, layer=layer)
    return ensure_crs(pipelines, _target_crs(cfg))


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
        layers[layer_name] = ensure_crs(layer, _target_crs(cfg))

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
    valid_boundary = boundary[boundary.geometry.notna()].copy()
    if valid_boundary.empty:
        return None

    valid_boundary["geometry"] = [repair_geometry(geom) for geom in valid_boundary.geometry]
    valid_boundary = valid_boundary[valid_boundary.geometry.notna() & ~valid_boundary.geometry.is_empty].copy()
    if valid_boundary.empty:
        return None

    try:
        geometry = valid_boundary.geometry.union_all()
    except Exception:
        # As a final fallback, attempt to repair all geometries before unioning.
        repaired = valid_boundary.copy()
        repaired["geometry"] = [repair_geometry(geom) for geom in repaired.geometry]
        repaired = repaired[repaired.geometry.notna() & ~repaired.geometry.is_empty].copy()
        if repaired.empty:
            return None
        geometry = repaired.geometry.union_all()

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
    """Draw terrain tint PNG aligned to the map CRS and clipped to the VA boundary."""
    paths_cfg = cfg.get("paths", {})
    terrain_processed_dir = Path(paths_cfg.get("terrain_processed_dir", "layers/terrain/processed"))
    terrain_tint_name = paths_cfg.get("terrain_tint_png", "terrain_tint_va.png")
    terrain_dem_name = paths_cfg.get("terrain_dem_tif", "dem_va_clipped.tif")

    tint_path = terrain_processed_dir / terrain_tint_name
    dem_path = terrain_processed_dir / terrain_dem_name
    if not tint_path.exists() or not dem_path.exists():
        return

    terrain_img = plt.imread(tint_path)
    target_crs = _target_crs(cfg)
    with rasterio.open(dem_path) as dem:
        if dem.crs is None:
            return

        terrain_height, terrain_width = terrain_img.shape[:2]
        source_transform = dem.transform
        if (terrain_width, terrain_height) != (dem.width, dem.height):
            mismatch_message = (
                "Terrain tint dimensions do not match DEM grid dimensions; "
                f"terrain_tint={terrain_width}x{terrain_height}, dem={dem.width}x{dem.height}. "
                "Using DEM bounds to derive src_transform for reprojection. "
                "Regenerate terrain_tint_va.png from the same DEM grid to avoid potential misalignment."
            )
            warnings.warn(mismatch_message, RuntimeWarning, stacklevel=2)
            source_transform = rasterio.transform.from_bounds(
                dem.bounds.left,
                dem.bounds.bottom,
                dem.bounds.right,
                dem.bounds.top,
                terrain_width,
                terrain_height,
            )

        if dem.crs == target_crs:
            minx, miny, maxx, maxy = transform_bounds(dem.crs, target_crs, *dem.bounds, densify_pts=21)
        else:
            dst_transform, dst_width, dst_height = calculate_default_transform(
                dem.crs,
                target_crs,
                dem.width,
                dem.height,
                *dem.bounds,
            )

            if terrain_img.ndim == 2:
                src_bands = terrain_img[np.newaxis, ...]
            else:
                src_bands = np.moveaxis(terrain_img, -1, 0)

            reprojected = np.zeros((src_bands.shape[0], dst_height, dst_width), dtype=np.float32)
            for band_idx in range(src_bands.shape[0]):
                is_alpha_band = src_bands.shape[0] == 4 and band_idx == 3
                reproject(
                    source=src_bands[band_idx],
                    destination=reprojected[band_idx],
                    src_transform=source_transform,
                    src_crs=dem.crs,
                    dst_transform=dst_transform,
                    dst_crs=target_crs,
                    src_nodata=0.0,
                    dst_nodata=0.0,
                    resampling=(rasterio.enums.Resampling.nearest if is_alpha_band else rasterio.enums.Resampling.bilinear),
                )

            terrain_img = reprojected[0] if reprojected.shape[0] == 1 else np.moveaxis(reprojected, 0, -1)
            minx, miny, maxx, maxy = array_bounds(dst_height, dst_width, dst_transform)

    image_artist = map_ax.imshow(
        terrain_img,
        extent=(minx, maxx, miny, maxy),
        origin="upper",
        interpolation="bilinear",
        zorder=float(cfg.get("style", {}).get("terrain_zorder", 0.5)),
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
    points = ensure_crs(points, _target_crs(cfg))

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
