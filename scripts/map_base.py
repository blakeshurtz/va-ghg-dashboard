"""Base-map rendering helpers."""

from __future__ import annotations

from typing import Any

import geopandas as gpd


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
