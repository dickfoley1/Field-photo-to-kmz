#!/usr/bin/env python3
"""make_kmz.py

Scan a folder of geotagged images, extract GPS metadata, generate a KML and
package into a KMZ that includes the original images (lossless).

Usage:
  python make_kmz.py /path/to/images -o output.kmz

Requires: exifread (ExifTool recommended for HEIC/phone metadata)
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

import exifread

EXIFTOOL_EXE = "exiftool"
SUPPORTED_IMAGE_EXTS = (".jpg", ".jpeg", ".jpe", ".heic", ".heif")


def _ratio_to_float(value):
    try:
        if hasattr(value, "num") and hasattr(value, "den"):
            return float(value.num) / float(value.den)
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return float(value.numerator) / float(value.denominator)
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return float(value[0]) / float(value[1])
        return float(value)
    except Exception:
        return None


def _normalize_ref(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    return str(value).strip().upper()


def _parse_text_coordinate(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    direct = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text)
    if direct:
        return float(text)

    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if not nums:
        return None

    try:
        if len(nums) >= 3:
            deg = float(nums[0])
            mins = float(nums[1])
            secs = float(nums[2])
            dd = abs(deg) + mins / 60.0 + secs / 3600.0
            if deg < 0:
                dd = -dd
        elif len(nums) == 2:
            deg = float(nums[0])
            mins = float(nums[1])
            dd = abs(deg) + mins / 60.0
            if deg < 0:
                dd = -dd
        else:
            dd = float(nums[0])

        text_u = text.upper()
        if "S" in text_u or "W" in text_u:
            dd = -abs(dd)
        return dd
    except Exception:
        return None


def _dms_to_dd(dms, ref):
    degrees = _ratio_to_float(dms[0])
    minutes = _ratio_to_float(dms[1])
    seconds = _ratio_to_float(dms[2])
    if degrees is None or minutes is None or seconds is None:
        return None

    dd = degrees + minutes / 60.0 + seconds / 3600.0
    if _normalize_ref(ref) in {"S", "W"}:
        dd = -abs(dd)
    return dd


def _extract_float_pair(value):
    if value is None:
        return None, None
    text = str(value)
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if len(nums) < 2:
        return None, None
    try:
        return float(nums[0]), float(nums[1])
    except Exception:
        return None, None


def _get_gps_from_exiftool(path):
    res = subprocess.run(
        [
            EXIFTOOL_EXE,
            "-j",
            "-n",
            "-GPSLatitude",
            "-GPSLongitude",
            "-GPSPosition",
            "-GPSCoordinates",
            path,
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        return None

    try:
        payload = json.loads(res.stdout)
        if not payload:
            return None
        meta = payload[0]
    except Exception:
        return None

    lat = _parse_text_coordinate(meta.get("GPSLatitude"))
    lon = _parse_text_coordinate(meta.get("GPSLongitude"))
    if lat is None or lon is None:
        lat2, lon2 = _extract_float_pair(meta.get("GPSPosition"))
        lat = lat if lat is not None else lat2
        lon = lon if lon is not None else lon2

    if lat is None or lon is None:
        lat2, lon2 = _extract_float_pair(meta.get("GPSCoordinates"))
        lat = lat if lat is not None else lat2
        lon = lon if lon is not None else lon2

    if lat is None or lon is None:
        return None

    return lat, lon


def get_gps_from_exif(path):
    # First pass: ExifTool handles HEIC and many phone-specific metadata paths.
    try:
        gps = _get_gps_from_exiftool(path)
        if gps:
            return gps
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Fallback: EXIF GPS via exifread (best for JPEGs).
    with open(path, "rb") as f:
        tags = exifread.process_file(f, details=False, stop_tag=None)

    lat_tag = tags.get("GPS GPSLatitude")
    lat_ref = tags.get("GPS GPSLatitudeRef")
    lon_tag = tags.get("GPS GPSLongitude")
    lon_ref = tags.get("GPS GPSLongitudeRef")

    if not lat_tag or not lat_ref or not lon_tag or not lon_ref:
        return None

    try:
        lat = _dms_to_dd(lat_tag.values, lat_ref.values)
        lon = _dms_to_dd(lon_tag.values, lon_ref.values)
        if lat is None or lon is None:
            return None
        return lat, lon
    except Exception:
        return None


def build_kml(placemarks):
    header = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
"""
    footer = """
  </Document>
</kml>
"""
    body = []
    for pm in placemarks:
        name = pm["name"]
        lat = pm["lat"]
        lon = pm["lon"]
        img = pm["img"]
        desc = f"<![CDATA[<img src=\"files/{img}\" width=\"800\"/>]]>"
        placemark = f"""
    <Placemark>
      <name>{name}</name>
      <description>{desc}</description>
      <Point>
        <coordinates>{lon},{lat},0</coordinates>
      </Point>
    </Placemark>
"""
        body.append(placemark)

    return header + "".join(body) + footer


def create_kmz(input_dir, output_kmz):
    files = []
    for ext in SUPPORTED_IMAGE_EXTS:
        files.extend(glob.glob(os.path.join(input_dir, f"*{ext}")))
        files.extend(glob.glob(os.path.join(input_dir, f"*{ext.upper()}")))
    files = sorted(files)

    placemarks = []
    for fpath in files:
        gps = get_gps_from_exif(fpath)
        if gps:
            lat, lon = gps
            placemarks.append(
                {
                    "name": os.path.basename(fpath),
                    "lat": lat,
                    "lon": lon,
                    "img": os.path.basename(fpath),
                    "src": fpath,
                }
            )

    if not placemarks:
        print("No GPS data found in any images in", input_dir)
        return False

    kml_text = build_kml(placemarks)

    tmp = tempfile.mkdtemp(prefix="kmztmp_")
    try:
        files_dir = os.path.join(tmp, "files")
        os.makedirs(files_dir, exist_ok=True)

        # copy images
        for pm in placemarks:
            shutil.copy2(pm["src"], os.path.join(files_dir, pm["img"]))

        kml_path = os.path.join(tmp, "doc.kml")
        with open(kml_path, "w", encoding="utf-8") as kf:
            kf.write(kml_text)

        # create zip (kmz)
        with zipfile.ZipFile(output_kmz, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(kml_path, arcname="doc.kml")
            for root, _, fnames in os.walk(files_dir):
                for fname in fnames:
                    full = os.path.join(root, fname)
                    arc = os.path.relpath(full, tmp)
                    zf.write(full, arcname=arc)

        print("Created", output_kmz)
        return True
    finally:
        shutil.rmtree(tmp)


def main():
    p = argparse.ArgumentParser(description="Create KMZ from geotagged images")
    p.add_argument("input", help="Input folder containing images")
    p.add_argument("-o", "--output", default="output.kmz", help="Output KMZ filename")
    p.add_argument("--exiftool", default=None, help="Path to exiftool executable")
    args = p.parse_args()

    if args.exiftool:
        globals()["EXIFTOOL_EXE"] = args.exiftool

    input_dir = args.input
    output = args.output

    if not os.path.isdir(input_dir):
        print("Input folder not found:", input_dir)
        return

    ok = create_kmz(input_dir, output)
    if not ok:
        print("KMZ not created (no GPS data).")


if __name__ == "__main__":
    main()
