"""Point rendering utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.image as mpimg
from matplotlib.offsetbox import AnnotationBbox, OffsetImage


_ICON_BY_SECTOR = {
    "power": "coal.jpg",
    "coal": "coal.jpg",
    "paper": "paper.jpg",
    "cement": "cement.jpg",
    "chemical": "chemical.jpg",
    "manufacturing": "manufacturing.jpg",
    "generation": "generation.jpg",
}


def _pick_icon_key(subparts: str) -> str:
    codes = {part.strip().upper() for part in str(subparts or "").split(",") if part.strip()}
    if "FF" in codes:
        return "coal"
    if "AA" in codes:
        return "paper"
    if "H" in codes:
        return "cement"
    if {"G", "PP"} & codes:
        return "chemical"
    if "D" in codes:
        return "power"
    if "TT" in codes:
        return "generation"
    return "manufacturing"


def _load_icon(path: Path):
    return mpimg.imread(path)


def _primary_subpart(subparts: str) -> str:
    parts = [part.strip().upper() for part in str(subparts or "").split(",") if part.strip()]
    return parts[0] if parts else "UNK"


def draw_points_with_facility_icons(
    map_ax,
    points_gdf: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> None:
    """Draw top-20 facilities with icons and label all others by primary subpart."""
    style = cfg["style"]
    if points_gdf.empty:
        return

    icon_dir = Path(cfg.get("paths", {}).get("icons_dir", "icons"))
    icon_zoom = float(style.get("top20_icon_zoom", 0.09))
    default_point_color = style.get("default_points_color", "#ffd84d")
    default_point_size = float(style.get("points_size", 8))
    default_point_alpha = float(style.get("points_alpha", 0.8))
    non_top20_label_size = float(style.get("non_top20_label_size", 5))
    non_top20_label_color = style.get("non_top20_label_color", "#dbe8f5")

    points = points_gdf.copy()
    if "subparts" not in points.columns:
        points["subparts"] = ""
    if "_is_top20" not in points.columns:
        points["_is_top20"] = False

    icon_cache: dict[str, Any] = {}
    fallback_x: list[float] = []
    fallback_y: list[float] = []

    for _, row in points.iterrows():
        if not bool(row.get("_is_top20", False)):
            map_ax.text(
                row.geometry.x,
                row.geometry.y,
                _primary_subpart(row["subparts"]),
                color=non_top20_label_color,
                fontsize=non_top20_label_size,
                ha="center",
                va="center",
                zorder=6,
            )
            continue

        subparts = row["subparts"]
        icon_key = _pick_icon_key(subparts)
        icon_name = _ICON_BY_SECTOR.get(icon_key, "manufacturing.jpg")
        icon_path = icon_dir / icon_name
        if not icon_path.exists():
            fallback_x.append(row.geometry.x)
            fallback_y.append(row.geometry.y)
            continue

        if icon_name not in icon_cache:
            icon_cache[icon_name] = _load_icon(icon_path)

        image = OffsetImage(icon_cache[icon_name], zoom=icon_zoom)
        marker = AnnotationBbox(
            image,
            (row.geometry.x, row.geometry.y),
            frameon=False,
            box_alignment=(0.5, 0.5),
            zorder=6,
        )
        map_ax.add_artist(marker)

    if fallback_x:
        map_ax.scatter(
            fallback_x,
            fallback_y,
            s=default_point_size,
            c=default_point_color,
            alpha=default_point_alpha,
            linewidths=0,
            zorder=4,
        )
