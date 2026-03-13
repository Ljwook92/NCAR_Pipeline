# NCAR_Pipeline

## Paths

Run everything from the repository root:

```bash
cd /path/to/NCAR_Pipeline
```

The downloader uses this fixed project layout:

```text
NCAR_Pipeline/
├── downloader.py
├── requirements.txt
├── README.md
└── Data/
    ├── raw/      # temporary downloaded .nc files
    └── wgs84/    # converted GeoTIFF outputs
```

Notes:

- Downloaded `.nc` files are stored in `Data/raw/` temporarily.
- Converted `WGS84` GeoTIFF files are stored in `Data/wgs84/`.
- Raw `.nc` files are deleted automatically after successful or failed conversion.
- Log files are written to `Data/`.

## HPC Conda Setup

Configure user-level conda storage first:

```bash
conda config --add envs_dirs /cluster/pixstor/hdtg3-lab/jlc3q/conda/envs
conda config --add pkgs_dirs /cluster/pixstor/hdtg3-lab/jlc3q/conda/pkgs
```

Create the environment:

```bash
conda create -n pm25_env -c conda-forge \
python=3.10 \
gdal=3.6.4 \
libgdal \
libnetcdf \
hdf5 \
netcdf-fortran \
xarray \
rioxarray \
rasterio \
geopandas \
rasterstats \
shapely \
pyproj \
netcdf4 \
h5netcdf \
scipy \
numpy \
-y
```

Activate the environment:

```bash
conda activate pm25_env
```

Check GDAL NetCDF support:

```bash
gdalinfo --formats | grep -i netcdf
```

Optional cleanup:

```bash
conda clean -a -y
```

Check active environment:

```bash
echo $CONDA_PREFIX
```

Deactivate:

```bash
conda deactivate
```

## Alternative Install

If you already have a working Python environment, you can install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

For HPC use, the conda setup above is the recommended path.

## What `downloader.py` Does

`downloader.py` does only two things:

1. Download hourly NCAR/GDEX WRF `.nc` files
2. Convert `PM2_5_DRY_SFC` into `WGS84` GeoTIFF files

It does not run zonal statistics.

## Outputs

For a file like:

```text
wrfout_hourly_d01_2019-05-02_01:00:00.nc
```

the output will be:

```text
Data/wgs84/20190502_01.tif
```

## Usage

Download a full day, 24 hourly files:

```bash
python3 downloader.py 2019-05-02
```

Download only one hour:

```bash
python3 downloader.py 2019-05-02 --hours 01
```

Download multiple specific hours:

```bash
python3 downloader.py 2019-05-02 --hours 01 02 03
```

Download a date range:

```bash
python3 downloader.py 2019-05-01 --end-date 2019-05-03
```

Download a date range with specific hours:

```bash
python3 downloader.py 2019-05-01 --end-date 2019-05-03 --hours 01
```

## Logs

Default log locations:

```text
Data/download_YYYY-MM-DD.log
Data/download_YYYY-MM-DD_to_YYYY-MM-DD.log
```

Log entries include:

- `START`
- `DOWNLOAD_DONE`
- `DOWNLOAD_RETRY`
- `DOWNLOAD_MISSING`
- `DOWNLOAD_ERROR`
- `NC_STRUCTURE`
- `WGS84_DONE`
- `WGS84_ERROR`
- `RAW_DELETED`
- `END`

## Example Session

```bash
cd /path/to/NCAR_Pipeline
conda activate pm25_env
python3 downloader.py 2020-06-24 --end-date 2020-06-25 --hours 01 02
```
