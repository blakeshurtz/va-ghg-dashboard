"""Point rendering utilities."""

from __future__ import annotations

from typing import Any

import geopandas as gpd


def draw_points(map_ax, points_gdf: gpd.GeoDataFrame, cfg: dict[str, Any]) -> None:
    """Draw emissions points as simple dots for validation."""
    style = cfg["style"]
    points_gdf.plot(
        ax=map_ax,
        markersize=float(style["points_size"]),
        color=style.get("points_color", "#ff8c42"),
        alpha=float(style["points_alpha"]),
        linewidth=0,
    )
