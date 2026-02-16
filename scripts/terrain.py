"""Terrain mosaic, reprojection, clipping, hillshade, and tint generation."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, reproject


@dataclass(frozen=True)
class TerrainOutputs:
    dem_path: Path
    hillshade_path: Path
    tint_png_path: Path


def run_terrain_pipeline(cfg: dict[str, Any]) -> TerrainOutputs | None:
    """Run terrain preprocessing if DEM tiles are available."""
    paths_cfg = cfg.get("paths", {})
    terrain_cfg = cfg.get("terrain", {})
    crs_cfg = cfg.get("crs", {})

    raw_dir = Path(paths_cfg.get("terrain_raw_dir", "data/terrain/raw"))
    processed_dir = Path(paths_cfg.get("terrain_processed_dir", "data/terrain/processed"))
    boundary_path = Path(paths_cfg.get("va_boundary_path", paths_cfg.get("va_boundary", "")))

    map_crs = str(crs_cfg.get("map_crs", "EPSG:3857"))
    nodata = float(terrain_cfg.get("nodata_value", -9999))
    azimuth = float(terrain_cfg.get("hillshade_azimuth", 315.0))
    altitude = float(terrain_cfg.get("hillshade_altitude", 45.0))
    vertical_exaggeration = float(terrain_cfg.get("vertical_exaggeration", 1.0))
    tint_strength = float(terrain_cfg.get("tint_strength", 0.25))
    dem_resample = _parse_resampling(str(terrain_cfg.get("dem_resample", "bilinear")))
    output_resolution = terrain_cfg.get("output_resolution")
    if output_resolution is not None:
        output_resolution = float(output_resolution)
        if output_resolution <= 0:
            raise ValueError("Config key 'terrain.output_resolution' must be > 0 when provided.")

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    tif_paths = sorted(raw_dir.glob("*.tif")) + sorted(raw_dir.glob("*.tiff"))
    if not tif_paths:
        print(f"[WARN] No DEM tiles found in {raw_dir.as_posix()} — skipping terrain step.")
        return None

    print(f"[OK] Found {len(tif_paths)} DEM tile(s) in {raw_dir.as_posix()}.")

    dem_array, dem_transform, dem_crs = _mosaic_tiles(tif_paths, nodata)
    reproj_array, reproj_transform = _reproject_dem(
        dem_array=dem_array,
        src_transform=dem_transform,
        src_crs=dem_crs,
        dst_crs=map_crs,
        nodata=nodata,
        resampling=dem_resample,
        output_resolution=output_resolution,
    )

    clipped_array, clipped_transform = _clip_to_boundary(
        dem_array=reproj_array,
        dem_transform=reproj_transform,
        dem_crs=map_crs,
        nodata=nodata,
        boundary_path=boundary_path,
    )

    dem_output_path = processed_dir / "dem_va_clipped.tif"
    _write_dem_tif(
        path=dem_output_path,
        dem_array=clipped_array,
        transform=clipped_transform,
        crs=map_crs,
        nodata=nodata,
    )

    hillshade = _compute_hillshade(
        dem_array=clipped_array,
        transform=clipped_transform,
        nodata=nodata,
        azimuth_deg=azimuth,
        altitude_deg=altitude,
        vertical_exaggeration=vertical_exaggeration,
    )

    hillshade_path = processed_dir / "hillshade_va.tif"
    _write_hillshade_tif(hillshade_path, hillshade, clipped_transform, map_crs)

    tint_path = processed_dir / "terrain_tint_va.png"
    _write_terrain_tint_png(
        png_path=tint_path,
        hillshade=hillshade,
        nodata_mask=(clipped_array == nodata) | ~np.isfinite(clipped_array),
        tint_strength=tint_strength,
    )

    return TerrainOutputs(
        dem_path=dem_output_path,
        hillshade_path=hillshade_path,
        tint_png_path=tint_path,
    )


def _mosaic_tiles(tif_paths: list[Path], nodata: float) -> tuple[np.ndarray, Affine, Any]:
    with ExitStack() as stack:
        datasets = [stack.enter_context(rasterio.open(path)) for path in tif_paths]
        mosaic, transform = merge(datasets, nodata=nodata)
        crs = datasets[0].crs

    dem = mosaic[0].astype("float32", copy=False)
    dem[~np.isfinite(dem)] = nodata
    return dem, transform, crs


def _reproject_dem(
    dem_array: np.ndarray,
    src_transform: Affine,
    src_crs: Any,
    dst_crs: str,
    nodata: float,
    resampling: Resampling,
    output_resolution: float | None,
) -> tuple[np.ndarray, Affine]:
    src_height, src_width = dem_array.shape
    left, bottom, right, top = rasterio.transform.array_bounds(src_height, src_width, src_transform)

    transform_kwargs: dict[str, float] = {}
    if output_resolution is not None:
        transform_kwargs["resolution"] = output_resolution

    dst_transform, dst_width, dst_height = calculate_default_transform(
        src_crs,
        dst_crs,
        src_width,
        src_height,
        left,
        bottom,
        right,
        top,
        **transform_kwargs,
    )

    dst_array = np.full((dst_height, dst_width), nodata, dtype="float32")
    reproject(
        source=dem_array,
        destination=dst_array,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=nodata,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_nodata=nodata,
        resampling=resampling,
    )
    return dst_array, dst_transform


def _clip_to_boundary(
    dem_array: np.ndarray,
    dem_transform: Affine,
    dem_crs: str,
    nodata: float,
    boundary_path: Path,
) -> tuple[np.ndarray, Affine]:
    va_boundary = gpd.read_file(boundary_path)
    if va_boundary.empty:
        raise ValueError(f"Boundary file is empty: {boundary_path}")
    if va_boundary.crs is None:
        raise ValueError(f"Boundary file has no CRS: {boundary_path}")

    va_boundary = va_boundary.to_crs(dem_crs)
    geometry = [va_boundary.geometry.union_all().__geo_interface__]

    profile = {
        "driver": "GTiff",
        "height": dem_array.shape[0],
        "width": dem_array.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": dem_crs,
        "transform": dem_transform,
        "nodata": nodata,
    }

    with MemoryFile() as mem_file:
        with mem_file.open(**profile) as dataset:
            dataset.write(dem_array, 1)
            clipped, clipped_transform = mask(dataset, geometry, crop=True, nodata=nodata, filled=True)

    clipped_dem = clipped[0].astype("float32", copy=False)
    clipped_dem[~np.isfinite(clipped_dem)] = nodata
    return clipped_dem, clipped_transform


def _compute_hillshade(
    dem_array: np.ndarray,
    transform: Affine,
    nodata: float,
    azimuth_deg: float,
    altitude_deg: float,
    vertical_exaggeration: float,
) -> np.ndarray:
    invalid = (dem_array == nodata) | ~np.isfinite(dem_array)

    dem = dem_array.astype("float32", copy=True)
    if np.any(~invalid):
        fill_value = float(np.nanmean(dem[~invalid]))
    else:
        fill_value = 0.0
    dem[invalid] = fill_value

    x_res = abs(transform.a)
    y_res = abs(transform.e)

    grad_y, grad_x = np.gradient(dem * vertical_exaggeration, y_res, x_res)
    slope = np.pi / 2.0 - np.arctan(np.sqrt(grad_x * grad_x + grad_y * grad_y))
    aspect = np.arctan2(-grad_x, grad_y)

    azimuth = np.deg2rad(azimuth_deg)
    altitude = np.deg2rad(altitude_deg)

    shaded = (
        np.sin(altitude) * np.sin(slope)
        + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    )
    shaded = np.clip(shaded, 0.0, 1.0)

    hillshade = np.round(shaded * 255.0).astype("uint8")
    hillshade[invalid] = 0
    return hillshade


def _write_dem_tif(path: Path, dem_array: np.ndarray, transform: Affine, crs: str, nodata: float) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=dem_array.shape[0],
        width=dem_array.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="lzw",
    ) as dst:
        dst.write(dem_array.astype("float32"), 1)


def _write_hillshade_tif(path: Path, hillshade: np.ndarray, transform: Affine, crs: str) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=hillshade.shape[0],
        width=hillshade.shape[1],
        count=1,
        dtype="uint8",
        crs=crs,
        transform=transform,
        nodata=0,
        compress="lzw",
    ) as dst:
        dst.write(hillshade, 1)


def _write_terrain_tint_png(
    png_path: Path,
    hillshade: np.ndarray,
    nodata_mask: np.ndarray,
    tint_strength: float,
) -> None:
    hs_norm = hillshade.astype("float32") / 255.0
    rgba = np.zeros((hillshade.shape[0], hillshade.shape[1], 4), dtype="uint8")

    base_gray = np.clip(150 + hs_norm * 50, 0, 255).astype("uint8")
    alpha = np.clip(hs_norm * float(np.clip(tint_strength, 0.0, 1.0)) * 255.0, 0, 255).astype("uint8")

    valid = ~nodata_mask
    rgba[..., 0][valid] = base_gray[valid]
    rgba[..., 1][valid] = base_gray[valid]
    rgba[..., 2][valid] = base_gray[valid]
    rgba[..., 3][valid] = alpha[valid]

    plt.imsave(png_path, rgba)


def _parse_resampling(name: str) -> Resampling:
    normalized = name.strip().lower()
    mapping = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
        "average": Resampling.average,
    }
    if normalized not in mapping:
        valid = ", ".join(sorted(mapping))
        raise ValueError(f"Unsupported terrain.dem_resample '{name}'. Valid options: {valid}")
    return mapping[normalized]
