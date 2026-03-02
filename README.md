# Field Photo to KMZ Studio

Convert geotagged phone photos and drone images into KMZ files for Google Earth.

## What It Does

- Reads GPS metadata from JPG, JPEG, JPE, HEIC, and HEIF images
- Supports Samsung, iPhone, DJI, Autel, and other geotagged image sources
- Builds a KMZ with placemarks, embedded images, labels, icons, and altitude modes
- Includes a desktop-style GUI for non-command-line use
- Supports Google Earth altitude modes:
  - `Absolute`
  - `Clamp to ground`
  - `Relative to ground`
  - `Clamp to sea floor`
  - `Relative to sea floor`

## Requirements

- Windows
- Python 3.10 or newer recommended
- ExifTool included in this repository as `exiftool_bundle.zip`
- ExifTool is still optional at runtime, but strongly recommended for HEIC/phone metadata reliability

Python packages are listed in `requirements.txt`.

## Quick Start

1. Download or clone this repository.
2. Run `setup_windows.bat`
3. Run `launcher.bat`
4. Optional: run `create_desktop_shortcut.bat`

Bundled ExifTool is included as:

- `.\exiftool_bundle.zip`

`setup_windows.bat` extracts it automatically to:

- `.\exiftool\exiftool.exe`

The app then detects it automatically.

## Install Manually

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run The GUI

```powershell
py -3 drone_images_to_kmz.py --gui
```

If you want to point to a different ExifTool build:

```powershell
py -3 drone_images_to_kmz.py --gui --exiftool ".\exiftool\exiftool.exe"
```

## Run From Command Line

```powershell
py -3 drone_images_to_kmz.py ".\sample_images" -o output.kmz
```

```powershell
py -3 drone_images_to_kmz.py ".\sample_images" -r -o output.kmz --show-labels --icon-preset "Red Circle" --icon-scale 1.2 --google-earth-altitude-mode relativeToGround --altitude-source override --altitude-override 120
```

## Main Files

- `drone_images_to_kmz.py`: primary app and GUI
- `make_kmz.py`: alternate command-line builder
- `launcher.bat`: launches the app
- `launcher_gui.ps1`: PowerShell launcher
- `launch_app.vbs`: hidden-window launcher used by the desktop shortcut
- `create_desktop_shortcut.bat`: creates a desktop shortcut
- `setup_windows.bat`: creates a virtual environment, installs dependencies, and extracts ExifTool if bundled
- `exiftool_bundle.zip`: bundled Windows ExifTool package

## GitHub Download Notes

This repository is set up so another user can:

1. download the repo ZIP from GitHub
2. extract it anywhere
3. run `setup_windows.bat`
4. run `launcher.bat`

No hardcoded local drive paths are required.

## Output

The generated KMZ contains:

- `doc.kml`
- embedded source images
- placemarks with coordinates, timestamp, altitude, and image preview

## License

This project is currently packaged with the `MIT` license in `LICENSE`.

Bundled ExifTool remains under its own license and documentation after extraction in:

- `exiftool\README.txt`
- `exiftool\exiftool_files\LICENSE`
