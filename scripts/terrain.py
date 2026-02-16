"""Terrain mosaic, reprojection, clipping, hillshade, and tint generation."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from rasterio.windows import Window, from_bounds, transform as window_transform


@dataclass(frozen=True)
class TerrainOutputs:
    dem_path: Path
    hillshade_path: Path
    tint_png_path: Path


@dataclass(frozen=True)
class RasterPlan:
    transform: Affine
    width: int
    height: int


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

    max_pixels = int(terrain_cfg.get("max_pixels", 120_000_000))
    max_memory_mb = float(terrain_cfg.get("max_memory_mb", 2500))
    window_size = int(terrain_cfg.get("processing_window_size", 1024))
    if window_size <= 0:
        raise ValueError("Config key 'terrain.processing_window_size' must be > 0 when provided.")

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    tif_paths = sorted(raw_dir.glob("*.tif")) + sorted(raw_dir.glob("*.tiff"))
    if not tif_paths:
        print(f"[WARN] No DEM tiles found in {raw_dir.as_posix()} — skipping terrain step.")
        return None

    print(f"[OK] Found {len(tif_paths)} DEM tile(s) in {raw_dir.as_posix()}.")

    va_boundary = _load_boundary(boundary_path)
    mosaic_path = processed_dir / "dem_va_mosaic.tif"
    _mosaic_tiles_to_tif(tif_paths, mosaic_path, nodata, boundary=va_boundary)

    cropped_path = processed_dir / "dem_va_mosaic_cropped.tif"
    _crop_dem_to_boundary_bounds(
        dem_path=mosaic_path,
        out_path=cropped_path,
        boundary=va_boundary,
        nodata=nodata,
        window_size=window_size,
    )

    reproj_path = processed_dir / "dem_va_reprojected.tif"
    _reproject_dem(
        src_path=cropped_path,
        dst_path=reproj_path,
        dst_crs=map_crs,
        nodata=nodata,
        resampling=dem_resample,
        output_resolution=output_resolution,
        max_pixels=max_pixels,
        max_memory_mb=max_memory_mb,
    )

    dem_output_path = processed_dir / "dem_va_clipped.tif"
    _clip_to_boundary(
        src_path=reproj_path,
        dst_path=dem_output_path,
        dem_crs=map_crs,
        nodata=nodata,
        boundary=va_boundary,
        window_size=window_size,
    )

    hillshade_path = processed_dir / "hillshade_va.tif"
    _compute_hillshade(
        dem_path=dem_output_path,
        hillshade_path=hillshade_path,
        nodata=nodata,
        azimuth_deg=azimuth,
        altitude_deg=altitude,
        vertical_exaggeration=vertical_exaggeration,
        window_size=window_size,
    )

    tint_path = processed_dir / "terrain_tint_va.png"
    _write_terrain_tint_png(
        png_path=tint_path,
        hillshade_path=hillshade_path,
        dem_path=dem_output_path,
        nodata=nodata,
        tint_strength=tint_strength,
        window_size=window_size,
    )

    return TerrainOutputs(
        dem_path=dem_output_path,
        hillshade_path=hillshade_path,
        tint_png_path=tint_path,
    )


def _load_boundary(boundary_path: Path) -> gpd.GeoDataFrame:
    boundary = gpd.read_file(boundary_path)
    if boundary.empty:
        raise ValueError(f"Boundary file is empty: {boundary_path}")
    if boundary.crs is None:
        raise ValueError(f"Boundary file has no CRS: {boundary_path}")
    print(f"[INFO] Boundary CRS={boundary.crs}, bounds={tuple(boundary.total_bounds)}")
    return boundary


def _mosaic_tiles_to_tif(
    tif_paths: list[Path],
    out_path: Path,
    nodata: float,
    boundary: gpd.GeoDataFrame,
) -> None:
    with ExitStack() as stack:
        datasets = [stack.enter_context(rasterio.open(path)) for path in tif_paths]
        bounds = transform_bounds(
            boundary.crs,
            datasets[0].crs,
            *boundary.total_bounds,
            densify_pts=21,
        )
        mosaic, transform = merge(datasets, nodata=nodata, bounds=bounds)
        crs = datasets[0].crs

    dem = mosaic[0].astype("float32", copy=False)
    np.nan_to_num(dem, copy=False, nan=nodata, posinf=nodata, neginf=nodata)

    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=dem.shape[0],
        width=dem.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="lzw",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    ) as dst:
        dst.write(dem, 1)

    _log_raster("Mosaic", out_path)


def _crop_dem_to_boundary_bounds(
    dem_path: Path,
    out_path: Path,
    boundary: gpd.GeoDataFrame,
    nodata: float,
    window_size: int,
) -> None:
    with rasterio.open(dem_path) as src:
        bounds = transform_bounds(
            boundary.crs,
            src.crs,
            *boundary.total_bounds,
            densify_pts=21,
        )

        crop_window = from_bounds(*bounds, transform=src.transform)
        full_window = Window(col_off=0, row_off=0, width=src.width, height=src.height)
        crop_window = crop_window.intersection(full_window).round_offsets().round_lengths()

        if crop_window.width <= 0 or crop_window.height <= 0:
            raise ValueError("Boundary does not overlap DEM extent.")

        profile = src.profile.copy()
        profile.update(
            {
                "height": int(crop_window.height),
                "width": int(crop_window.width),
                "transform": window_transform(crop_window, src.transform),
                "dtype": "float32",
                "nodata": nodata,
                "compress": "lzw",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
            }
        )

        with rasterio.open(out_path, "w", **profile) as dst:
            for window in _iter_windows(int(crop_window.width), int(crop_window.height), window_size):
                src_window = Window(
                    col_off=int(crop_window.col_off + window.col_off),
                    row_off=int(crop_window.row_off + window.row_off),
                    width=int(window.width),
                    height=int(window.height),
                )
                block = src.read(1, window=src_window).astype("float32", copy=False)
                block[~np.isfinite(block)] = nodata
                dst.write(block, 1, window=window)

    _log_raster("Cropped mosaic", out_path)


def _reproject_dem(
    src_path: Path,
    dst_path: Path,
    dst_crs: str,
    nodata: float,
    resampling: Resampling,
    output_resolution: float | None,
    max_pixels: int,
    max_memory_mb: float,
) -> None:
    with rasterio.open(src_path) as src:
        plan = _plan_reprojection(src, dst_crs, output_resolution)
        _preflight_raster_size(plan, max_pixels, max_memory_mb)

        profile = src.profile.copy()
        profile.update(
            {
                "crs": dst_crs,
                "transform": plan.transform,
                "width": plan.width,
                "height": plan.height,
                "dtype": "float32",
                "nodata": nodata,
                "compress": "lzw",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
            }
        )

        with rasterio.open(dst_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=nodata,
                dst_transform=plan.transform,
                dst_crs=dst_crs,
                dst_nodata=nodata,
                resampling=resampling,
            )

    _log_raster("Reprojected DEM", dst_path)


def _clip_to_boundary(
    src_path: Path,
    dst_path: Path,
    dem_crs: str,
    nodata: float,
    boundary: gpd.GeoDataFrame,
    window_size: int,
) -> None:
    boundary_projected = boundary.to_crs(dem_crs)
    geometry = [boundary_projected.geometry.union_all().__geo_interface__]

    with rasterio.open(src_path) as src:
        bounds = transform_bounds(boundary_projected.crs, src.crs, *boundary_projected.total_bounds)
        clip_window = from_bounds(*bounds, transform=src.transform)
        full_window = Window(col_off=0, row_off=0, width=src.width, height=src.height)
        clip_window = clip_window.intersection(full_window).round_offsets().round_lengths()

        if clip_window.width <= 0 or clip_window.height <= 0:
            raise ValueError("Boundary does not overlap reprojected DEM extent.")

        profile = src.profile.copy()
        profile.update(
            {
                "height": int(clip_window.height),
                "width": int(clip_window.width),
                "transform": window_transform(clip_window, src.transform),
                "dtype": "float32",
                "nodata": nodata,
                "compress": "lzw",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
            }
        )

        with rasterio.open(dst_path, "w", **profile) as dst:
            for window in _iter_windows(int(clip_window.width), int(clip_window.height), window_size):
                src_window = Window(
                    col_off=int(clip_window.col_off + window.col_off),
                    row_off=int(clip_window.row_off + window.row_off),
                    width=int(window.width),
                    height=int(window.height),
                )
                block = src.read(1, window=src_window).astype("float32", copy=False)
                block[~np.isfinite(block)] = nodata

                mask_inside = geometry_mask(
                    geometries=geometry,
                    out_shape=(int(window.height), int(window.width)),
                    transform=window_transform(window, dst.transform),
                    invert=True,
                )
                block[~mask_inside] = nodata
                dst.write(block, 1, window=window)

    _log_raster("Clipped DEM", dst_path)


def _compute_hillshade(
    dem_path: Path,
    hillshade_path: Path,
    nodata: float,
    azimuth_deg: float,
    altitude_deg: float,
    vertical_exaggeration: float,
    window_size: int,
) -> None:
    with rasterio.open(dem_path) as src:
        profile = src.profile.copy()
        profile.update(
            {
                "dtype": "uint8",
                "nodata": 0,
                "compress": "lzw",
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
            }
        )

        x_res = abs(src.transform.a)
        y_res = abs(src.transform.e)
        azimuth = np.deg2rad(azimuth_deg)
        altitude = np.deg2rad(altitude_deg)

        with rasterio.open(hillshade_path, "w", **profile) as dst:
            for window in _iter_windows(src.width, src.height, window_size):
                padded_window = _pad_window(window, src.width, src.height, pad=1)
                padded = src.read(1, window=padded_window, boundless=True, fill_value=nodata).astype(
                    "float32", copy=False
                )

                invalid = (padded == nodata) | ~np.isfinite(padded)
                valid = ~invalid
                fill_value = float(np.nanmean(padded[valid])) if np.any(valid) else 0.0
                padded[invalid] = fill_value

                grad_y, grad_x = np.gradient(padded * vertical_exaggeration, y_res, x_res)
                slope = np.pi / 2.0 - np.arctan(np.sqrt(grad_x * grad_x + grad_y * grad_y))
                aspect = np.arctan2(-grad_x, grad_y)
                shaded = (
                    np.sin(altitude) * np.sin(slope)
                    + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
                )
                shaded = np.clip(shaded, 0.0, 1.0)

                row0 = int(window.row_off - padded_window.row_off)
                col0 = int(window.col_off - padded_window.col_off)
                row1 = row0 + int(window.height)
                col1 = col0 + int(window.width)

                core_shaded = shaded[row0:row1, col0:col1]
                core_dem = src.read(1, window=window).astype("float32", copy=False)
                core_invalid = (core_dem == nodata) | ~np.isfinite(core_dem)

                hillshade_block = np.round(core_shaded * 255.0).astype("uint8")
                hillshade_block[core_invalid] = 0
                dst.write(hillshade_block, 1, window=window)

    _log_raster("Hillshade", hillshade_path)


def _write_terrain_tint_png(
    png_path: Path,
    hillshade_path: Path,
    dem_path: Path,
    nodata: float,
    tint_strength: float,
    window_size: int,
) -> None:
    with rasterio.open(hillshade_path) as hs_src, rasterio.open(dem_path) as dem_src:
        profile = hs_src.profile.copy()
        profile.update(
            {
                "driver": "PNG",
                "count": 4,
                "dtype": "uint8",
                "nodata": None,
                "compress": "deflate",
            }
        )
        profile.pop("tiled", None)
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)

        with rasterio.open(png_path, "w", **profile) as dst:
            for window in _iter_windows(hs_src.width, hs_src.height, window_size):
                hillshade = hs_src.read(1, window=window).astype("float32", copy=False)
                dem_block = dem_src.read(1, window=window)
                nodata_mask = (dem_block == nodata) | ~np.isfinite(dem_block)

                hs_norm = hillshade / 255.0
                base_gray = np.clip(150 + hs_norm * 50, 0, 255).astype("uint8")
                alpha = np.clip(
                    hs_norm * float(np.clip(tint_strength, 0.0, 1.0)) * 255.0,
                    0,
                    255,
                ).astype("uint8")

                valid = ~nodata_mask
                r = np.zeros_like(base_gray, dtype="uint8")
                g = np.zeros_like(base_gray, dtype="uint8")
                b = np.zeros_like(base_gray, dtype="uint8")
                a = np.zeros_like(base_gray, dtype="uint8")

                r[valid] = base_gray[valid]
                g[valid] = base_gray[valid]
                b[valid] = base_gray[valid]
                a[valid] = alpha[valid]

                dst.write(r, 1, window=window)
                dst.write(g, 2, window=window)
                dst.write(b, 3, window=window)
                dst.write(a, 4, window=window)

    print(f"[INFO] Terrain tint PNG written: {png_path}")


def _plan_reprojection(src: rasterio.DatasetReader, dst_crs: str, output_resolution: float | None) -> RasterPlan:
    left, bottom, right, top = src.bounds
    transform_kwargs: dict[str, float] = {}
    if output_resolution is not None:
        transform_kwargs["resolution"] = output_resolution

    dst_transform, dst_width, dst_height = calculate_default_transform(
        src.crs,
        dst_crs,
        src.width,
        src.height,
        left,
        bottom,
        right,
        top,
        **transform_kwargs,
    )
    return RasterPlan(transform=dst_transform, width=dst_width, height=dst_height)


def _preflight_raster_size(plan: RasterPlan, max_pixels: int, max_memory_mb: float) -> None:
    pixels = plan.width * plan.height
    if pixels <= 0:
        raise ValueError("Invalid output raster dimensions computed during reprojection.")

    approx_working_set_bytes = pixels * (4 + 4 + 1 + 4)
    approx_mb = approx_working_set_bytes / (1024 * 1024)

    print(
        f"[INFO] Reprojection target width={plan.width}, height={plan.height}, "
        f"pixels={pixels:,}, est_working_set={approx_mb:.1f}MB"
    )

    if pixels > max_pixels or approx_mb > max_memory_mb:
        raise MemoryError(
            "Terrain preprocessing aborted by preflight guardrails. "
            f"target_pixels={pixels:,} (max={max_pixels:,}), "
            f"estimated_working_set_mb={approx_mb:.1f} (max={max_memory_mb:.1f}). "
            "Try increasing terrain.output_resolution (coarser, e.g. 250 or 500), "
            "limit DEM tiles to the area of interest, or raise terrain.max_pixels / "
            "terrain.max_memory_mb if your machine has sufficient RAM."
        )


def _iter_windows(width: int, height: int, window_size: int):
    for row_off in range(0, height, window_size):
        block_h = min(window_size, height - row_off)
        for col_off in range(0, width, window_size):
            block_w = min(window_size, width - col_off)
            yield Window(col_off=col_off, row_off=row_off, width=block_w, height=block_h)


def _pad_window(window: Window, max_width: int, max_height: int, pad: int) -> Window:
    col_off = max(int(window.col_off) - pad, 0)
    row_off = max(int(window.row_off) - pad, 0)
    right = min(int(window.col_off + window.width) + pad, max_width)
    bottom = min(int(window.row_off + window.height) + pad, max_height)
    return Window(col_off=col_off, row_off=row_off, width=right - col_off, height=bottom - row_off)


def _log_raster(label: str, path: Path) -> None:
    with rasterio.open(path) as ds:
        b = ds.bounds
        x_res = abs(ds.transform.a)
        y_res = abs(ds.transform.e)
        print(
            f"[INFO] {label}: path={path.as_posix()}, crs={ds.crs}, "
            f"width={ds.width}, height={ds.height}, res=({x_res:.3f},{y_res:.3f}), "
            f"bounds=({b.left:.3f},{b.bottom:.3f},{b.right:.3f},{b.top:.3f})"
        )


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
