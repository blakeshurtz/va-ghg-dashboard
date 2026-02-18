"""Base-map rendering helpers."""

from __future__ import annotations

import warnings
from typing import Any

import geopandas as gpd
import numpy as np

from scripts.geometry_utils import repair_geometry


def _repair_geometry_frame(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    repaired = gdf[gdf.geometry.notna()].copy()
    if repaired.empty:
        return repaired

    repaired["geometry"] = [repair_geometry(geom) for geom in repaired.geometry]
    return repaired[repaired.geometry.notna() & ~repaired.geometry.is_empty].copy()


def _keep_plottable_geometries(gdf: gpd.GeoDataFrame, *, label: str) -> gpd.GeoDataFrame:
    """Filter to geometry types that geopandas can render without error.

    Clipping can produce GeometryCollections or LinearRings that cause
    geopandas.plot() to raise.  This helper keeps only Point, MultiPoint,
    LineString, and MultiLineString features, which are the types expected
    for overlay layers.
    """
    plottable_types = {"Point", "MultiPoint", "LineString", "MultiLineString",
                       "Polygon", "MultiPolygon"}
    mask = gdf.geometry.geom_type.isin(plottable_types)
    dropped = int((~mask).sum())
    if dropped:
        bad_types = gdf.loc[~mask, "geometry"].geom_type.value_counts().to_dict()
        warnings.warn(
            f"{label}: dropped {dropped} non-plottable feature(s) "
            f"with types {bad_types}",
            RuntimeWarning,
            stacklevel=2,
        )
    return gdf[mask].copy()


def _has_finite_bounds(gdf: gpd.GeoDataFrame) -> bool:
    if gdf.empty:
        return False
    bounds = gdf.total_bounds
    return bool(np.isfinite(bounds).all())


def _safe_clip(
    layer_gdf: gpd.GeoDataFrame,
    boundary_gdf: gpd.GeoDataFrame,
    *,
    label: str = "layer",
) -> gpd.GeoDataFrame:
    if layer_gdf.empty:
        warnings.warn(f"{label}: layer is empty before clip", RuntimeWarning, stacklevel=2)
        return layer_gdf
    if boundary_gdf.empty:
        warnings.warn(f"{label}: boundary is empty before clip", RuntimeWarning, stacklevel=2)
        return layer_gdf.iloc[0:0]

    if not _has_finite_bounds(layer_gdf):
        warnings.warn(
            f"{label}: non-finite layer bounds detected ({tuple(layer_gdf.total_bounds)}) — skipping clip",
            RuntimeWarning,
            stacklevel=2,
        )
        return layer_gdf.iloc[0:0]

    if not _has_finite_bounds(boundary_gdf):
        warnings.warn(
            f"{label}: non-finite boundary bounds detected ({tuple(boundary_gdf.total_bounds)}) — skipping clip",
            RuntimeWarning,
            stacklevel=2,
        )
        return layer_gdf.iloc[0:0]

    # Ensure CRS alignment — mismatched CRS silently produces empty clips.
    if layer_gdf.crs is not None and boundary_gdf.crs is not None:
        if not layer_gdf.crs.equals(boundary_gdf.crs):
            warnings.warn(
                f"{label}: CRS mismatch — layer={layer_gdf.crs}, "
                f"boundary={boundary_gdf.crs}; reprojecting layer to match boundary",
                RuntimeWarning,
                stacklevel=2,
            )
            layer_gdf = layer_gdf.to_crs(boundary_gdf.crs)

    if not _has_finite_bounds(layer_gdf):
        warnings.warn(
            f"{label}: non-finite bounds after reprojection ({tuple(layer_gdf.total_bounds)}) — skipping clip",
            RuntimeWarning,
            stacklevel=2,
        )
        return layer_gdf.iloc[0:0]

    try:
        result = gpd.clip(layer_gdf, boundary_gdf)
        if result.empty:
            warnings.warn(
                f"{label}: gpd.clip returned 0 features "
                f"(layer: {len(layer_gdf)} features, CRS={layer_gdf.crs}, "
                f"bounds={tuple(round(v, 1) for v in layer_gdf.total_bounds)}; "
                f"boundary: CRS={boundary_gdf.crs}, "
                f"bounds={tuple(round(v, 1) for v in boundary_gdf.total_bounds)})",
                RuntimeWarning,
                stacklevel=2,
            )
        return result
    except Exception as first_exc:
        warnings.warn(
            f"{label}: primary clip failed ({first_exc!r}), trying repaired inputs",
            RuntimeWarning,
            stacklevel=2,
        )
        layer_fixed = _repair_geometry_frame(layer_gdf)
        boundary_fixed = _repair_geometry_frame(boundary_gdf)
        if layer_fixed.empty or boundary_fixed.empty:
            warnings.warn(
                f"{label}: no usable geometries after repair — layer will be empty",
                RuntimeWarning,
                stacklevel=2,
            )
            return layer_fixed.iloc[0:0]
        try:
            result = gpd.clip(layer_fixed, boundary_fixed)
            return result
        except Exception as second_exc:
            warnings.warn(
                f"{label}: repaired clip also failed ({second_exc!r}), "
                "falling back to bounding-box filter",
                RuntimeWarning,
                stacklevel=2,
            )
            minx, miny, maxx, maxy = boundary_fixed.total_bounds
            return layer_fixed.cx[minx:maxx, miny:maxy]


def draw_boundary(map_ax, boundary_gdf: gpd.GeoDataFrame, cfg: dict[str, Any]) -> None:
    """Draw boundary outline and optional fill on the map axis."""
    style = cfg["style"]
    fill_color = style.get("boundary_fill")

    boundary_gdf.plot(
        ax=map_ax,
        facecolor=fill_color if fill_color else "none",
        edgecolor=style.get("boundary_edgecolor", "#9fb3c8"),
        linewidth=float(style["boundary_linewidth"]),
        alpha=float(style["boundary_alpha"]),
    )


def draw_pipelines(
    map_ax,
    pipelines_gdf: gpd.GeoDataFrame,
    boundary_gdf: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> None:
    """Draw natural gas pipelines clipped to the boundary extent."""
    style = cfg["style"]
    clipped = _safe_clip(pipelines_gdf, boundary_gdf, label="pipelines")
    if clipped.empty:
        warnings.warn("Pipelines: empty after clip — nothing to draw", RuntimeWarning, stacklevel=2)
        return

    clipped = _keep_plottable_geometries(clipped, label="pipelines")
    if clipped.empty:
        warnings.warn("Pipelines: no plottable geometries after filtering", RuntimeWarning, stacklevel=2)
        return

    # On high-resolution exports, sub-1pt strokes can become nearly imperceptible.
    linewidth = max(float(style.get("pipelines_linewidth", 0.4)), 1.0)

    clipped.plot(
        ax=map_ax,
        color=style.get("pipelines_color", "#4ba3c7"),
        linewidth=linewidth,
        alpha=float(style.get("pipelines_alpha", 0.5)),
        zorder=float(style.get("pipelines_zorder", 2)),
    )


def draw_reference_layer(
    map_ax,
    layer_gdf: gpd.GeoDataFrame,
    boundary_gdf: gpd.GeoDataFrame,
    *,
    color: str,
    linewidth: float,
    alpha: float,
    zorder: float,
    label: str = "reference",
    marker_size: float = 6.0,
) -> None:
    """Draw a reference vector layer clipped to the boundary extent."""
    clipped = _safe_clip(layer_gdf, boundary_gdf, label=label)
    if clipped.empty:
        warnings.warn(f"{label}: empty after clip — nothing to draw", RuntimeWarning, stacklevel=2)
        return

    clipped = _keep_plottable_geometries(clipped, label=label)
    if clipped.empty:
        warnings.warn(f"{label}: no plottable geometries after filtering", RuntimeWarning, stacklevel=2)
        return

    # Keep line references readable at dashboard export size.
    visible_linewidth = max(float(linewidth), 0.9)

    geom_types = {str(geom_type) for geom_type in clipped.geometry.geom_type.unique()}
    if geom_types <= {"Point", "MultiPoint"}:
        clipped.plot(
            ax=map_ax,
            color=color,
            alpha=alpha,
            zorder=zorder,
            markersize=marker_size,
        )
        return

    clipped.plot(
        ax=map_ax,
        color=color,
        linewidth=visible_linewidth,
        alpha=alpha,
        zorder=zorder,
    )


def set_extent_to_boundary(
    map_ax,
    boundary_gdf: gpd.GeoDataFrame,
    padding_pct: float,
) -> None:
    """Set axis extent to boundary total bounds with optional padding."""
    minx, miny, maxx, maxy = boundary_gdf.total_bounds
    pad_x = (maxx - minx) * float(padding_pct)
    pad_y = (maxy - miny) * float(padding_pct)

    map_ax.set_xlim(minx - pad_x, maxx + pad_x)
    map_ax.set_ylim(miny - pad_y, maxy + pad_y)
    map_ax.set_aspect("equal", adjustable="box")
    map_ax.set_axis_off()
