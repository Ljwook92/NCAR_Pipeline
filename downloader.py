#!/usr/bin/env python3
import argparse
import os
import socket
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import build_opener

import numpy as np
import rioxarray  # noqa: F401
import xarray as xr
from scipy.interpolate import griddata

BASE_URL = "https://osdf-director.osg-htc.org/ncar/gdex"
BASE_DIR = Path(__file__).resolve().parent / "Data"
RAW_DIR = BASE_DIR / "raw"
WGS84_DIR = BASE_DIR / "wgs84"


def build_filelist(date_str, dataset="d340000", domain="d01", hours=None):
    if hours is None:
        hours = [f"{h:02d}" for h in range(24)]

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    yyyymm = dt.strftime("%Y%m")

    return [
        f"{BASE_URL}/{dataset}/{yyyymm}/wrfout_hourly_{domain}_{date_str}_{hour}:00:00.nc"
        for hour in hours
    ]


def build_date_range(start_date_str, end_date_str=None):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else start_date

    if end_date < start_date:
        raise ValueError("end date must be the same as or later than start date")

    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def append_log(log_path, status, filename, message=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp}\t{status}\t{filename}"
    if message:
        line += f"\t{message}"
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")


def dims_and_shape(data_array):
    return f"dims={tuple(data_array.dims)}, shape={tuple(data_array.shape)}"


def open_dataset_safely(nc_path):
    open_kwargs = {"decode_times": False, "mask_and_scale": False}
    errors = []

    for engine in ["netcdf4", "h5netcdf", None]:
        try:
            if engine is None:
                return xr.open_dataset(nc_path, **open_kwargs)
            return xr.open_dataset(nc_path, engine=engine, **open_kwargs)
        except Exception as exc:
            errors.append(f"{engine or 'default'}: {exc}")

    raise ValueError("Failed to open dataset with available engines: " + " | ".join(errors))


def format_size(num_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f}{unit}"
        size /= 1024


def render_progress(prefix, downloaded, total_size, width=20):
    if total_size:
        ratio = min(downloaded / total_size, 1.0)
        filled = int(width * ratio)
        bar = "=" * filled + " " * (width - filled)
        percent = int(ratio * 100)
        return (
            f"\r{prefix} [{bar}] {percent:3d}% "
            f"({format_size(downloaded)}/{format_size(total_size)})"
        )

    return f"\r{prefix} downloaded {format_size(downloaded)}"


def download_with_progress(opener, url, filename, prefix, chunk_size=1024 * 1024):
    with opener.open(url, timeout=180) as response, open(filename, "wb") as out:
        total_size = response.headers.get("Content-Length")
        total_size = int(total_size) if total_size else None
        downloaded = 0

        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            print(render_progress(prefix, downloaded, total_size), end="", flush=True)

    if total_size:
        print(render_progress(prefix, total_size, total_size), end="", flush=True)
    print(" done")


def remove_partial_file(filename):
    if os.path.exists(filename):
        os.remove(filename)


def output_name_for_nc(nc_path):
    name = Path(nc_path).name
    stem = name.removesuffix(".nc")
    parts = stem.split("_")
    if len(parts) < 5:
        raise ValueError(f"Unexpected WRF filename: {name}")

    date_str = parts[-2].replace("-", "")
    hour_str = parts[-1].split(":")[0]
    return f"{date_str}_{hour_str}.tif"


def prepare_2d_array(data_array, preferred_dims):
    arr = data_array

    for dim in list(arr.dims):
        if dim not in preferred_dims:
            arr = arr.isel({dim: 0})

    arr = arr.squeeze(drop=True)

    if arr.ndim != 2:
        raise ValueError(
            f"Could not reduce variable to 2D. {dims_and_shape(data_array)} -> "
            f"dims={tuple(arr.dims)}, shape={tuple(arr.shape)}"
        )

    if tuple(arr.dims) != tuple(preferred_dims):
        try:
            arr = arr.transpose(*preferred_dims)
        except ValueError:
            pass

    return arr.values


def convert_nc_to_wgs84(nc_path, out_dir, x_size=494, y_size=211):
    nc_path = Path(nc_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_tif = out_dir / output_name_for_nc(nc_path)

    with open_dataset_safely(nc_path) as ds:
        if "PM2_5_DRY_SFC" not in ds or "XLAT" not in ds or "XLONG" not in ds:
            raise ValueError(
                f"Required variables missing. Available variables: {list(ds.data_vars)}"
            )

        pm25_da = ds["PM2_5_DRY_SFC"]
        lat_da = ds["XLAT"]
        lon_da = ds["XLONG"]

        pm25 = prepare_2d_array(pm25_da, preferred_dims=("south_north", "west_east"))
        lat = prepare_2d_array(lat_da, preferred_dims=("south_north", "west_east"))
        lon = prepare_2d_array(lon_da, preferred_dims=("south_north", "west_east"))

    if pm25.shape != lat.shape or pm25.shape != lon.shape:
        raise ValueError(
            "Shape mismatch after dimension handling: "
            f"pm25={pm25.shape}, lat={lat.shape}, lon={lon.shape}"
        )

    points = np.column_stack((lon.ravel(), lat.ravel()))
    values = pm25.ravel()

    lon_new = np.linspace(float(lon.min()), float(lon.max()), x_size)
    lat_new = np.linspace(float(lat.min()), float(lat.max()), y_size)
    lon_grid, lat_grid = np.meshgrid(lon_new, lat_new)

    pm25_interp = griddata(points, values, (lon_grid, lat_grid), method="linear")

    da = xr.DataArray(
        pm25_interp,
        coords={"y": lat_new, "x": lon_new},
        dims=("y", "x"),
        name="PM2_5_DRY_SFC",
    )
    da.rio.write_crs("EPSG:4326", inplace=True)
    da.rio.to_raster(out_tif)

    return out_tif


def inspect_nc_structure(nc_path):
    with open_dataset_safely(nc_path) as ds:
        parts = []
        for var_name in ["PM2_5_DRY_SFC", "XLAT", "XLONG"]:
            if var_name in ds:
                parts.append(f"{var_name}:{dims_and_shape(ds[var_name])}")
            else:
                parts.append(f"{var_name}:missing")
        return "; ".join(parts)


def ensure_directories():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    WGS84_DIR.mkdir(parents=True, exist_ok=True)


def download_and_convert(opener, url, raw_path, prefix, log_path):
    retry_attempted = False

    while True:
        try:
            download_with_progress(opener, url, raw_path, prefix)
            append_log(log_path, "DOWNLOAD_DONE", raw_path.name, "downloaded successfully")
            break
        except HTTPError as exc:
            remove_partial_file(raw_path)
            if exc.code == 404:
                print(f"\r{prefix} missing (404), skipped")
                append_log(log_path, "DOWNLOAD_MISSING", raw_path.name, "404 not found")
                return
            if exc.code == 500 and not retry_attempted:
                retry_attempted = True
                print(f"\r{prefix} HTTP 500, retrying once...")
                append_log(log_path, "DOWNLOAD_RETRY", raw_path.name, "HTTP 500, retrying once")
                time.sleep(2)
                continue

            append_log(log_path, "DOWNLOAD_ERROR", raw_path.name, f"HTTP {exc.code}: {exc.reason}")
            print(f"\r{prefix} HTTP {exc.code}, skipped")
            return
        except (TimeoutError, socket.timeout) as exc:
            remove_partial_file(raw_path)
            if not retry_attempted:
                retry_attempted = True
                print(f"\r{prefix} download timed out, retrying once...")
                append_log(log_path, "DOWNLOAD_RETRY", raw_path.name, f"timeout, retrying once: {exc}")
                time.sleep(2)
                continue

            append_log(log_path, "DOWNLOAD_ERROR", raw_path.name, f"timeout: {exc}")
            print(f"\r{prefix} download timed out, skipped")
            return

    try:
        structure_info = inspect_nc_structure(raw_path)
        append_log(log_path, "NC_STRUCTURE", raw_path.name, structure_info)
        wgs84_tif = convert_nc_to_wgs84(raw_path, WGS84_DIR)
        print(f"{prefix} wgs84 -> {wgs84_tif.name}")
        append_log(log_path, "WGS84_DONE", wgs84_tif.name, f"source={raw_path.name}")
    except Exception as exc:
        append_log(log_path, "WGS84_ERROR", raw_path.name, str(exc))
        print(f"{prefix} wgs84 conversion failed, skipped")
    finally:
        if raw_path.exists():
            raw_path.unlink()
            append_log(log_path, "RAW_DELETED", raw_path.name, "deleted after processing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="End date in YYYY-MM-DD format")
    parser.add_argument("--hours", nargs="+", default=None)
    parser.add_argument("--dataset", default="d340000")
    parser.add_argument("--domain", default="d01")
    parser.add_argument("--log", default=None, help="Log file path. Default: download_<date>.log")
    args = parser.parse_args()

    ensure_directories()
    date_list = build_date_range(args.date, args.end_date)
    filelist = []
    for date_str in date_list:
        filelist.extend(build_filelist(date_str, args.dataset, args.domain, args.hours))

    total_files = len(filelist)
    if args.end_date:
        default_log_name = f"download_{args.date}_to_{args.end_date}.log"
    else:
        default_log_name = f"download_{args.date}.log"
    log_path = Path(args.log) if args.log else BASE_DIR / default_log_name
    opener = build_opener()

    append_log(
        log_path,
        "START",
        args.date if not args.end_date else f"{args.date}_to_{args.end_date}",
        f"total_files={total_files}, raw_cache={RAW_DIR}, wgs84_dir={WGS84_DIR}",
    )

    for index, url in enumerate(filelist, start=1):
        filename = os.path.basename(url)
        prefix = f"({index}/{total_files}) {filename}"
        raw_path = RAW_DIR / filename

        if raw_path.exists() and raw_path.stat().st_size > 0:
            print(f"{prefix} already exists in raw, skipped")
            append_log(log_path, "DOWNLOAD_SKIPPED", raw_path.name, "already exists in raw")
            continue

        try:
            download_and_convert(opener, url, raw_path, prefix, log_path)
        except URLError as exc:
            remove_partial_file(raw_path)
            append_log(log_path, "DOWNLOAD_ERROR", raw_path.name, f"URL error: {exc.reason}")
            raise

    append_log(log_path, "END", args.date if not args.end_date else f"{args.date}_to_{args.end_date}", "completed")
    print(f"log saved to {log_path.resolve()}")


if __name__ == "__main__":
    main()
