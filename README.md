# NCAR_Pipeline

NSF NCAR dataset reference: [NSF NCAR](https://gdex.ucar.edu/datasets/d340000/#)

This repository currently downloads and converts only `PM2_5_DRY_SFC` into `WGS84` GeoTIFF files.

## Paths

Run everything from the repository root:

```bash
mkdir -p /cluster/pixstor/hdtg3-lab/$USER
cd /cluster/pixstor/hdtg3-lab/$USER
git clone <repo-url>
cd NCAR_Pipeline
```

Example HPC path after cloning:

```bash
cd /cluster/pixstor/hdtg3-lab/$USER/NCAR_Pipeline
```

The downloader uses this fixed project layout:

```text
NCAR_Pipeline/
├── downloader.py
├── environment.yml
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

Run these commands in your terminal from the repository root:

```bash
cd NCAR_Pipeline
```

Configure user-level conda storage first:

```bash
mkdir -p /cluster/pixstor/hdtg3-lab/$USER/conda/envs
mkdir -p /cluster/pixstor/hdtg3-lab/$USER/conda/pkgs
conda config --add envs_dirs /cluster/pixstor/hdtg3-lab/$USER/conda/envs
conda config --add pkgs_dirs /cluster/pixstor/hdtg3-lab/$USER/conda/pkgs
```

Create the environment:

```bash
conda env create -f environment.yml
```

Note:
- Environment creation can take more than 1 hour on HPC, depending on solver speed and package download conditions.
- After the environment is ready, `tmux` is recommended for long-running downloads so your session keeps running after disconnects.
- With `tmux`, the download can continue even if you close your terminal or lose your SSH connection.

Basic `tmux` workflow:

```bash
tmux new -s pm25_setup
```

Detach from the session without stopping the job:

```bash
Ctrl + B
D
```

List existing sessions:

```bash
tmux ls
```

Reconnect to the session:

```bash
tmux attach -t pm25_download
```

Activate the environment:

```bash
conda activate pm25_env
```

Recommended workflow for downloads:

```bash
tmux new -s pm25_download
conda activate pm25_env
python3 downloader.py 2020-06-24 --end-date 2020-06-25 --hours 01 02
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

Aggregate selected hourly GeoTIFF files into one daily file:

```bash
python3 downloader.py 2019-05-02 --hours 01 02 03 --agg mean
```

Available aggregation methods:

- `mean`
- `max`
- `min`
- `sum`

Aggregate output example:

```text
Data/wgs84/20190502_agg_mean.tif
```
