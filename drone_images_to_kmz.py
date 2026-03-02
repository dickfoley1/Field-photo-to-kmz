import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import exifread
from PIL import Image, ImageDraw, ImageFilter, ImageTk
from PIL.ExifTags import GPSTAGS, TAGS
import simplekml
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

EXIFTOOL_EXE = "exiftool"
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".jpe", ".heic", ".heif"}
PRESET_ICONS = {
    "Camera": "http://maps.google.com/mapfiles/kml/shapes/camera.png",
    "Red Circle": "http://maps.google.com/mapfiles/kml/paddle/red-circle.png",
    "Blue Circle": "http://maps.google.com/mapfiles/kml/paddle/blu-circle.png",
    "Target": "http://maps.google.com/mapfiles/kml/shapes/target.png",
    "Placemark": "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png",
}
LABEL_MODES = {
    "filename": "File name",
    "timestamp": "Timestamp",
    "filename_altitude": "File + altitude",
}
GOOGLE_EARTH_ALTITUDE_MODES = {
    "absolute": "Absolute",
    "clampToGround": "Clamp to ground",
    "relativeToGround": "Relative to ground",
    "clampToSeaFloor": "Clamp to sea floor",
    "relativetoseafloor": "Relative to sea floor",
}
ALTITUDE_MODE_NOTES = {
    "absolute": "Uses the altitude value as meters above sea level.",
    "clampToGround": "Ignores altitude and sticks the point to the terrain surface.",
    "relativeToGround": "Treats altitude as meters above the terrain at that location.",
    "clampToSeaFloor": "Ignores altitude and sticks the point to the sea floor.",
    "relativetoseafloor": "Treats altitude as meters above the sea floor, or above ground when on land.",
}
ALTITUDE_SOURCES = {
    "metadata": "Use metadata altitude",
    "override": "Use fixed altitude value",
}
ALTITUDE_MODE_LABEL_TO_KEY = {
    label: key for key, label in GOOGLE_EARTH_ALTITUDE_MODES.items()
}
SITE_LOGO_PATH = Path(__file__).with_name("above_beyond806_logo.png")
APP_ICON_PATH = Path(__file__).with_name("806app.ico")
BRAND = {
    "bg": "#dff2ff",
    "surface": "#f4fbff",
    "surface_alt": "#ffffff",
    "header": "#08111d",
    "footer": "#08111d",
    "text": "#0f2436",
    "muted": "#55788f",
    "accent": "#ff2f43",
    "accent_hover": "#ff5565",
    "line": "#ffffff",
    "light": "#ffffff",
    "chip": "#102235",
    "chip_line": "#8ad7ff",
    "input_bg": "#ffffff",
    "input_line": "#a8d8f2",
    "glow": "#dff5ff",
    "glass_edge": "#ffffff",
    "glass_highlight": "#ffffff",
    "glass_shadow": "#75afd2",
    "glass_shadow_deep": "#4f85aa",
    "panel_line": "#caeaff",
}


@dataclass
class KMZRenderOptions:
    icon_preset: str = "Camera"
    icon_file: Optional[str] = None
    icon_scale: float = 0.8
    show_labels: bool = False
    label_mode: str = "filename"
    altitude_source: str = "metadata"
    google_earth_altitude_mode: str = "absolute"
    altitude_override: Optional[float] = None


def _default_output_folder():
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        return downloads
    documents = Path.home() / "Documents"
    if documents.exists():
        return documents
    return Path.cwd()


def _bundled_exiftool_path():
    candidates = [
        Path(__file__).with_name("exiftool.exe"),
        Path(__file__).with_name("exiftool") / "exiftool.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


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

    numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if not numbers:
        return None

    try:
        if len(numbers) >= 3:
            deg = float(numbers[0])
            mins = float(numbers[1])
            secs = float(numbers[2])
            dd = abs(deg) + mins / 60.0 + secs / 3600.0
            if deg < 0:
                dd = -dd
        elif len(numbers) == 2:
            deg = float(numbers[0])
            mins = float(numbers[1])
            dd = abs(deg) + mins / 60.0
            if deg < 0:
                dd = -dd
        else:
            dd = float(numbers[0])

        text_u = text.upper()
        if "S" in text_u or "W" in text_u:
            dd = -abs(dd)
        return dd
    except Exception:
        return None


def get_decimal_from_dms(dms, ref):
    try:
        degrees = _ratio_to_float(dms[0])
        minutes = _ratio_to_float(dms[1])
        seconds = _ratio_to_float(dms[2])
        if degrees is None or minutes is None or seconds is None:
            return None

        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if _normalize_ref(ref) in {"S", "W"}:
            decimal = -abs(decimal)
        return decimal
    except Exception:
        return None


def _extract_float_pair(value):
    if value is None:
        return None, None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        lat = _parse_text_coordinate(value[0])
        lon = _parse_text_coordinate(value[1])
        return lat, lon

    text = str(value)
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if len(nums) >= 2:
        try:
            return float(nums[0]), float(nums[1])
        except Exception:
            return None, None
    return None, None


def _extract_gps_with_exiftool(image_path):
    exiftool_exe = globals().get("EXIFTOOL_EXE", "exiftool")
    res = subprocess.run(
        [
            exiftool_exe,
            "-j",
            "-n",
            "-GPSLatitude",
            "-GPSLongitude",
            "-GPSAltitude",
            "-GPSPosition",
            "-GPSCoordinates",
            "-DateTimeOriginal",
            "-SubSecDateTimeOriginal",
            "-CreateDate",
            "-MediaCreateDate",
            "-TrackCreateDate",
            image_path,
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

    altitude = _parse_text_coordinate(meta.get("GPSAltitude"))
    if altitude is None:
        altitude = 0.0

    timestamp = ""
    for key in (
        "SubSecDateTimeOriginal",
        "DateTimeOriginal",
        "CreateDate",
        "MediaCreateDate",
        "TrackCreateDate",
    ):
        val = meta.get(key)
        if val:
            timestamp = str(val)
            break

    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": altitude,
        "timestamp": timestamp,
    }


def extract_gps_exif(image_path):
    try:
        gps = _extract_gps_with_exiftool(image_path)
        if gps:
            return gps
    except FileNotFoundError:
        pass
    except Exception:
        pass

    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        if not exif_data:
            raise ValueError("no exif from PIL")

        exif_dict = {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            exif_dict[tag_name] = value

        gps_info = exif_dict.get("GPSInfo")
        if not gps_info:
            return None

        gps_dict = {}
        for tag_id, value in gps_info.items():
            tag_name = GPSTAGS.get(tag_id, tag_id)
            gps_dict[tag_name] = value

        lat_ref = gps_dict.get("GPSLatitudeRef", "N")
        lat_dms = gps_dict.get("GPSLatitude")
        lon_ref = gps_dict.get("GPSLongitudeRef", "E")
        lon_dms = gps_dict.get("GPSLongitude")

        if not lat_dms or not lon_dms:
            return None

        lat = get_decimal_from_dms(lat_dms, lat_ref)
        lon = get_decimal_from_dms(lon_dms, lon_ref)
        if lat is None or lon is None:
            return None

        alt = 0.0
        alt_data = gps_dict.get("GPSAltitude")
        alt_ref = gps_dict.get("GPSAltitudeRef", 0)
        if alt_data:
            parsed_alt = _ratio_to_float(alt_data)
            if parsed_alt is not None:
                alt = parsed_alt
                if str(alt_ref).strip() in {"1", "b'\\x01'"}:
                    alt = -abs(alt)

        ts = exif_dict.get("DateTimeOriginal") or exif_dict.get("DateTime") or ""
        return {
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "timestamp": str(ts),
        }
    except Exception:
        pass

    try:
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_tag = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")
        if not lat_tag or not lon_tag or not lat_ref or not lon_ref:
            return None

        lat = get_decimal_from_dms(
            lat_tag.values,
            lat_ref.values if hasattr(lat_ref, "values") else lat_ref,
        )
        lon = get_decimal_from_dms(
            lon_tag.values,
            lon_ref.values if hasattr(lon_ref, "values") else lon_ref,
        )
        if lat is None or lon is None:
            return None

        alt = 0.0
        alt_tag = tags.get("GPS GPSAltitude")
        if alt_tag and hasattr(alt_tag, "values") and alt_tag.values:
            parsed_alt = _ratio_to_float(alt_tag.values[0])
            if parsed_alt is not None:
                alt = parsed_alt
        alt_ref = tags.get("GPS GPSAltitudeRef")
        if alt_ref and str(alt_ref).strip() in {"1", "[1]"}:
            alt = -abs(alt)

        ts_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        ts = str(ts_tag) if ts_tag else ""
        return {"latitude": lat, "longitude": lon, "altitude": alt, "timestamp": ts}
    except Exception:
        pass

    try:
        with open(image_path, "rb") as f:
            data = f.read()

        start = data.find(b"<x:xmpmeta")
        end = data.find(b"</x:xmpmeta>")
        if start == -1 or end == -1:
            return None

        xmp = data[start : end + 12].decode("utf-8", errors="ignore")

        def _search_value(tag):
            match = re.search(rf"<{tag}>([^<]+)</{tag}>", xmp)
            if match:
                return match.group(1).strip()
            return None

        lat_raw = (
            _search_value("exif:GPSLatitude")
            or _search_value("GPSTag:GPSLatitude")
            or _search_value("xmp:GPSLatitude")
        )
        lon_raw = (
            _search_value("exif:GPSLongitude")
            or _search_value("GPSTag:GPSLongitude")
            or _search_value("xmp:GPSLongitude")
        )
        lat = _parse_text_coordinate(lat_raw)
        lon = _parse_text_coordinate(lon_raw)
        if lat is None or lon is None:
            return None

        ts = _search_value("exif:DateTimeOriginal") or ""
        return {"latitude": lat, "longitude": lon, "altitude": 0.0, "timestamp": ts}
    except Exception:
        return None


def resolve_images(input_path=None, recursive=False, selected_files=None):
    if selected_files:
        images = []
        for item in selected_files:
            path = Path(item)
            if path.exists() and path.suffix.lower() in SUPPORTED_IMAGE_EXTS:
                images.append(path)
        return sorted(images)

    if input_path is None:
        return []

    root = Path(input_path)
    if recursive:
        return sorted(p for p in root.rglob("*") if p.suffix.lower() in SUPPORTED_IMAGE_EXTS)
    return sorted(p for p in root.iterdir() if p.suffix.lower() in SUPPORTED_IMAGE_EXTS)


def _resolve_icon_href(kml, options):
    if options.icon_file:
        icon_path = Path(options.icon_file)
        if not icon_path.exists():
            raise FileNotFoundError(f"Icon file not found: {icon_path}")
        return kml.addfile(str(icon_path))
    return PRESET_ICONS.get(options.icon_preset, PRESET_ICONS["Camera"])


def _build_label_text(img, gps, altitude, options):
    if options.label_mode == "timestamp":
        return gps.get("timestamp") or img.stem
    if options.label_mode == "filename_altitude":
        return f"{img.stem} ({altitude:.1f} m)"
    return img.stem


def _is_clamp_mode(mode):
    return mode in {"clampToGround", "clampToSeaFloor"}


def _is_gx_altitude_mode(mode):
    return mode in {"clampToSeaFloor", "relativetoseafloor"}


def _earth_mode_display(mode):
    return GOOGLE_EARTH_ALTITUDE_MODES.get(mode, mode)


def _earth_mode_key(display_value):
    return ALTITUDE_MODE_LABEL_TO_KEY.get(display_value, display_value)


def _rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def create_kmz_from_images(
    input_path,
    output_path,
    max_images=1000,
    recursive=False,
    selected_files=None,
    render_options=None,
):
    options = render_options or KMZRenderOptions()
    images = resolve_images(input_path, recursive=recursive, selected_files=selected_files)
    if not images:
        print("No supported image files found (JPG/JPEG/JPE/HEIC/HEIF).")
        return {"added": 0, "skipped": 0, "total": 0}

    if len(images) > max_images:
        images = images[:max_images]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kml = simplekml.Kml()
    kml.document.name = output_path.stem
    icon_href = _resolve_icon_href(kml, options)

    count_ok = 0
    count_fail = 0

    for idx, img in enumerate(images, 1):
        print(f"[{idx}/{len(images)}] {img.name}")
        gps = extract_gps_exif(str(img))
        if not gps:
            print("  -> no GPS, skipped")
            count_fail += 1
            continue

        altitude = gps["altitude"]
        if (
            options.altitude_source == "override"
            and options.altitude_override is not None
            and not _is_clamp_mode(options.google_earth_altitude_mode)
        ):
            altitude = options.altitude_override
        if _is_clamp_mode(options.google_earth_altitude_mode):
            altitude = 0.0

        label_text = _build_label_text(img, gps, altitude, options)
        placemark_name = label_text if options.show_labels else img.stem

        pnt = kml.newpoint(
            name=placemark_name,
            coords=[(gps["longitude"], gps["latitude"], altitude)],
        )

        image_in_kmz = kml.addfile(str(img))
        desc = f"""
        <![CDATA[
        <div style=\"font-family:Segoe UI,Arial,sans-serif;padding:8px;\">
          <h3 style=\"margin:0 0 8px 0;\">{img.name}</h3>
          <p><b>Timestamp:</b> {gps['timestamp'] or 'Unavailable'}</p>
          <p><b>Earth mode:</b> {GOOGLE_EARTH_ALTITUDE_MODES[options.google_earth_altitude_mode]}</p>
          <p><b>Lat:</b> {gps['latitude']:.6f}</p>
          <p><b>Lon:</b> {gps['longitude']:.6f}</p>
          <p><b>Alt:</b> {altitude:.2f} m</p>
          <p><img src=\"{image_in_kmz}\" style=\"max-width:800px;border-radius:8px;\" /></p>
        </div>
        ]]>
        """
        pnt.description = desc
        if _is_gx_altitude_mode(options.google_earth_altitude_mode):
            pnt.gxaltitudemode = options.google_earth_altitude_mode
        else:
            pnt.altitudemode = options.google_earth_altitude_mode
        pnt.style.iconstyle.icon.href = icon_href
        pnt.style.iconstyle.scale = options.icon_scale
        pnt.style.labelstyle.scale = 0.85 if options.show_labels else 0

        count_ok += 1

    if count_ok > 0:
        kml.savekmz(str(output_path))
        print(f"KMZ saved: {output_path}")
    else:
        print("No images with GPS were added.")

    print(f"Done: {count_ok} added, {count_fail} skipped.")
    return {"added": count_ok, "skipped": count_fail, "total": len(images)}


class KMZApp:
    def __init__(self, exiftool_path=None):
        self.root = tk.Tk()
        self.root.title("Above & Beyond 806 | Field Photo to KMZ Studio")
        self.root.geometry("980x760")
        self.root.minsize(900, 700)
        self.root.configure(bg=BRAND["bg"])
        try:
            self.root.iconbitmap(str(APP_ICON_PATH))
        except Exception:
            pass

        self.selected_files = []
        self.logo_image = None
        self.app_background_image = None

        if exiftool_path:
            globals()["EXIFTOOL_EXE"] = exiftool_path

        self.folder_var = tk.StringVar()
        self.output_name_var = tk.StringVar(value="field_photos")
        self.output_folder_var = tk.StringVar(value=str(_default_output_folder()))
        self.icon_preset_var = tk.StringVar(value="Camera")
        self.icon_file_var = tk.StringVar()
        self.icon_scale_var = tk.DoubleVar(value=0.8)
        self.show_labels_var = tk.BooleanVar(value=False)
        self.label_mode_var = tk.StringVar(value="filename")
        self.altitude_source_var = tk.StringVar(value="metadata")
        self.google_earth_altitude_mode_var = tk.StringVar(
            value=_earth_mode_display("absolute")
        )
        self.altitude_override_var = tk.StringVar(value="25")
        self.recursive_var = tk.BooleanVar(value=False)
        self.max_images_var = tk.IntVar(value=1000)
        self.status_var = tk.StringVar(value="Select a folder or specific images to begin.")
        self.count_var = tk.StringVar(value="0 supported images ready")
        self.altitude_mode_note_var = tk.StringVar()

        self._configure_styles()
        self._load_background_images()
        self._build_ui()
        self._wire_events()
        self._toggle_custom_icon_state()
        self._toggle_altitude_state()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family="Segoe UI", size=10)
        text_font = tkfont.nametofont("TkTextFont")
        text_font.configure(family="Segoe UI", size=10)
        menu_font = tkfont.nametofont("TkMenuFont")
        menu_font.configure(family="Segoe UI", size=10)

        style.configure("App.TFrame", background=BRAND["bg"])
        style.configure("Card.TFrame", background=BRAND["surface"], relief="flat")
        style.configure("Header.TFrame", background=BRAND["header"])
        style.configure(
            "HeaderTitle.TLabel",
            background=BRAND["header"],
            foreground=BRAND["light"],
            font=("Segoe UI", 26, "bold"),
        )
        style.configure(
            "HeaderSub.TLabel",
            background=BRAND["header"],
            foreground=BRAND["muted"],
            font=("Segoe UI", 11),
        )
        style.configure(
            "CardTitle.TLabel",
            background=BRAND["surface"],
            foreground=BRAND["text"],
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Body.TLabel",
            background=BRAND["surface"],
            foreground=BRAND["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Accent.TButton",
            background=BRAND["accent"],
            foreground=BRAND["light"],
            borderwidth=0,
            padding=(16, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", BRAND["accent_hover"])])
        style.configure(
            "Soft.TButton",
            background=BRAND["surface_alt"],
            foreground=BRAND["text"],
            borderwidth=0,
            padding=(10, 8),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Soft.TButton",
            background=[("active", BRAND["glow"])],
            foreground=[("active", BRAND["text"])],
        )
        style.configure(
            "Field.TEntry",
            fieldbackground=BRAND["input_bg"],
            foreground=BRAND["text"],
            bordercolor=BRAND["input_line"],
            lightcolor=BRAND["input_line"],
            darkcolor=BRAND["input_line"],
            insertcolor=BRAND["text"],
            padding=8,
        )
        style.configure(
            "Field.TCombobox",
            fieldbackground=BRAND["input_bg"],
            foreground=BRAND["text"],
            bordercolor=BRAND["input_line"],
            lightcolor=BRAND["input_line"],
            darkcolor=BRAND["input_line"],
            arrowsize=16,
            padding=6,
        )
        style.configure(
            "TCheckbutton",
            background=BRAND["surface"],
            foreground=BRAND["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "TRadiobutton",
            background=BRAND["surface"],
            foreground=BRAND["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Status.TLabel",
            background=BRAND["footer"],
            foreground=BRAND["muted"],
            font=("Segoe UI", 10, "bold"),
        )

    def _load_background_images(self):
        self.app_background_image = self._build_sky_background((980, 1600))

    def _build_sky_background(self, size):
        width, height = size
        image = Image.new("RGB", size)
        draw = ImageDraw.Draw(image)

        top = (70, 156, 245)
        mid = (137, 198, 255)
        bottom = (212, 239, 255)
        for y in range(height):
            blend = y / max(height - 1, 1)
            if blend < 0.55:
                inner = blend / 0.55
                color = tuple(int(top[i] * (1 - inner) + mid[i] * inner) for i in range(3))
            else:
                inner = (blend - 0.55) / 0.45
                color = tuple(
                    int(mid[i] * (1 - inner) + bottom[i] * inner) for i in range(3)
                )
            draw.line((0, y, width, y), fill=color)

        # Faint diagonal HUD lines to keep the sky background from feeling flat.
        line_overlay = Image.new("RGBA", size, (255, 255, 255, 0))
        line_draw = ImageDraw.Draw(line_overlay)
        for offset in range(-220, width + 240, 120):
            line_draw.line(
                [(offset, height), (offset + 220, 0)],
                fill=(255, 255, 255, 22),
                width=2,
            )
        for y in range(160, height, 140):
            line_draw.arc(
                (-140, y - 80, width + 160, y + 120),
                start=188,
                end=356,
                fill=(110, 210, 255, 28),
                width=2,
            )

        cloud_specs = [
            (130, 108, 230, 72),
            (340, 178, 300, 82),
            (660, 126, 280, 78),
            (820, 236, 250, 74),
            (505, 316, 330, 92),
            (195, 430, 280, 78),
            (720, 430, 220, 64),
        ]
        overlay = Image.new("RGBA", size, (255, 255, 255, 0))
        cloud_draw = ImageDraw.Draw(overlay)
        for cx, cy, w, h in cloud_specs:
            puffs = [
                (cx - w * 0.34, cy + h * 0.02, w * 0.34, h * 0.76),
                (cx - w * 0.12, cy - h * 0.1, w * 0.4, h * 0.96),
                (cx + w * 0.18, cy + h * 0.01, w * 0.34, h * 0.78),
                (cx + w * 0.02, cy + h * 0.16, w * 0.58, h * 0.58),
            ]
            for px, py, pw, ph in puffs:
                x0 = int(px - pw / 2)
                y0 = int(py - ph / 2)
                x1 = int(px + pw / 2)
                y1 = int(py + ph / 2)
                cloud_draw.ellipse((x0, y0, x1, y1), fill=(255, 255, 255, 205))

        wisp_specs = [
            (250, 265, 210, 30),
            (590, 235, 185, 26),
            (860, 145, 165, 24),
            (410, 470, 260, 32),
        ]
        for cx, cy, w, h in wisp_specs:
            x0 = int(cx - w / 2)
            y0 = int(cy - h / 2)
            x1 = int(cx + w / 2)
            y1 = int(cy + h / 2)
            cloud_draw.ellipse((x0, y0, x1, y1), fill=(255, 255, 255, 110))

        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=18))
        combined = Image.alpha_composite(image.convert("RGBA"), line_overlay)
        combined = Image.alpha_composite(combined, overlay)
        return ImageTk.PhotoImage(combined.convert("RGB"))

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = tk.Frame(self.root, bg=BRAND["header"], bd=0, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        if SITE_LOGO_PATH.exists():
            try:
                self.logo_image = tk.PhotoImage(file=str(SITE_LOGO_PATH))
                tk.Label(
                    header,
                    image=self.logo_image,
                    bg=BRAND["header"],
                    bd=0,
                    highlightthickness=0,
                ).grid(row=0, column=0, rowspan=3, sticky="w", padx=(24, 18), pady=(22, 18))
            except Exception:
                self.logo_image = None
        ttk.Label(header, text="Field Photo to KMZ Studio", style="HeaderTitle.TLabel").grid(
            row=0, column=1, sticky="w", padx=(0, 24), pady=(18, 0)
        )
        ttk.Label(
            header,
            text="Mission-control styling for geotagged exports, Google Earth altitude modes, and branded placemarks.",
            style="HeaderSub.TLabel",
        ).grid(row=1, column=1, sticky="w", padx=(0, 24), pady=(6, 0))
        badge_row = tk.Frame(header, bg=BRAND["header"], bd=0, highlightthickness=0)
        badge_row.grid(row=2, column=1, sticky="w", padx=(0, 24), pady=(14, 18))
        self._make_header_badge(badge_row, "PHONE PHOTO READY").pack(side="left", padx=(0, 10))
        self._make_header_badge(badge_row, "GOOGLE EARTH MODES").pack(side="left", padx=(0, 10))
        self._make_header_badge(badge_row, "ABOVE & BEYOND 806").pack(side="left")

        body = tk.Frame(self.root, bg=BRAND["bg"], bd=0, highlightthickness=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.body_canvas = tk.Canvas(
            body,
            bg=BRAND["bg"],
            bd=0,
            highlightthickness=0,
            yscrollincrement=20,
        )
        self.body_canvas.grid(row=0, column=0, sticky="nsew")
        body_scroll = ttk.Scrollbar(body, orient="vertical", command=self.body_canvas.yview)
        body_scroll.grid(row=0, column=1, sticky="ns")
        self.body_canvas.configure(yscrollcommand=body_scroll.set)

        self.body_bg_id = None
        if self.app_background_image:
            self.body_bg_id = self.body_canvas.create_image(
                0,
                0,
                image=self.app_background_image,
                anchor="nw",
            )

        left = tk.Frame(self.body_canvas, bg=BRAND["bg"], bd=0, highlightthickness=0)
        left.columnconfigure(0, weight=1)
        right = tk.Frame(self.body_canvas, bg=BRAND["bg"], bd=0, highlightthickness=0)
        right.columnconfigure(0, weight=1)

        self.left_column_window = self.body_canvas.create_window(20, 20, anchor="nw", window=left)
        self.right_column_window = self.body_canvas.create_window(20, 20, anchor="nw", window=right)

        self._build_input_card(left)
        self._build_output_card(left)
        self._build_process_card(left)
        self._build_style_card(right)
        self._build_altitude_card(right)
        self._build_summary_card(right)

        self.body_canvas.bind("<Configure>", self._layout_body_canvas)
        left.bind("<Configure>", self._layout_body_canvas)
        right.bind("<Configure>", self._layout_body_canvas)
        self.body_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.after_idle(self._layout_body_canvas)

        footer = tk.Frame(self.root, bg=BRAND["footer"], bd=0, highlightthickness=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="w", padx=(20, 0), pady=14
        )
        ttk.Button(footer, text="Build KMZ", style="Accent.TButton", command=self.run).grid(
            row=0, column=1, sticky="e", padx=(0, 20), pady=10
        )

    def _make_header_badge(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            bg=BRAND["chip"],
            fg=BRAND["light"],
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=5,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=BRAND["chip_line"],
            highlightcolor=BRAND["chip_line"],
        )

    def _card(self, parent, title, row):
        host = tk.Frame(parent, bg=BRAND["bg"], bd=0, highlightthickness=0)
        host.grid(row=row, column=0, sticky="ew", pady=(0, 18))
        host.columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            host,
            bg=BRAND["bg"],
            highlightthickness=0,
            bd=0,
            height=220,
        )
        canvas.grid(row=0, column=0, sticky="ew")

        panel = tk.Frame(canvas, bg=BRAND["surface"], bd=0, highlightthickness=0)
        panel.columnconfigure(0, weight=1)
        panel_window = canvas.create_window(26, 26, anchor="nw", window=panel)

        top = tk.Frame(panel, bg=BRAND["surface"], bd=0, highlightthickness=0)
        top.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        top.columnconfigure(1, weight=1)
        tk.Frame(top, bg=BRAND["accent"], width=58, height=4).grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        tk.Frame(top, bg=BRAND["glow"], height=1).grid(row=0, column=1, sticky="ew")
        tk.Label(
            panel,
            text=title.upper(),
            bg=BRAND["surface"],
            fg=BRAND["text"],
            font=("Segoe UI", 10, "bold"),
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 14))
        content = tk.Frame(panel, bg=BRAND["surface"], bd=0, highlightthickness=0)
        content.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        content.columnconfigure(1, weight=1)

        def redraw(_event=None):
            host.update_idletasks()
            width = max(host.winfo_width(), 320)
            panel_width = max(width - 52, 268)
            content_height = panel.winfo_reqheight()
            total_height = content_height + 34
            canvas.configure(height=total_height + 18)
            canvas.coords(panel_window, 20, 14)
            canvas.itemconfigure(panel_window, width=panel_width)
            canvas.delete("card_bg")
            _rounded_rect(
                canvas,
                22,
                20,
                width - 8,
                total_height + 14,
                30,
                fill=BRAND["glass_shadow_deep"],
                outline="",
                tags="card_bg",
            )
            _rounded_rect(
                canvas,
                16,
                14,
                width - 14,
                total_height + 8,
                30,
                fill=BRAND["glass_shadow"],
                outline="",
                tags="card_bg",
            )
            _rounded_rect(
                canvas,
                10,
                8,
                width - 18,
                total_height + 2,
                28,
                fill=BRAND["surface"],
                outline=BRAND["panel_line"],
                width=1,
                tags="card_bg",
            )
            canvas.create_line(
                34,
                28,
                width - 42,
                28,
                fill=BRAND["glass_highlight"],
                width=2,
                tags="card_bg",
            )
            canvas.create_line(
                36,
                34,
                width - 84,
                34,
                fill=BRAND["glow"],
                width=1,
                tags="card_bg",
            )
            canvas.lower("card_bg")

        host.bind("<Configure>", redraw)
        panel.bind("<Configure>", redraw)
        self.root.after_idle(redraw)
        return content

    def _layout_body_canvas(self, _event=None):
        if not hasattr(self, "body_canvas"):
            return

        self.body_canvas.update_idletasks()
        width = max(self.body_canvas.winfo_width(), 780)
        margin = 20
        gutter = 18
        usable = max(width - (margin * 2) - gutter, 520)
        left_width = max(int(usable * 0.58), 320)
        right_width = max(usable - left_width, 260)
        right_x = margin + left_width + gutter

        self.body_canvas.coords(self.left_column_window, margin, 20)
        self.body_canvas.coords(self.right_column_window, right_x, 20)
        self.body_canvas.itemconfigure(self.left_column_window, width=left_width)
        self.body_canvas.itemconfigure(self.right_column_window, width=right_width)

        if self.body_bg_id is not None:
            bg_x = max((width - self.app_background_image.width()) // 2, 0)
            self.body_canvas.coords(self.body_bg_id, bg_x, 0)
            self.body_canvas.tag_lower(self.body_bg_id)

        left_height = self.body_canvas.nametowidget(
            self.body_canvas.itemcget(self.left_column_window, "window")
        ).winfo_reqheight()
        right_height = self.body_canvas.nametowidget(
            self.body_canvas.itemcget(self.right_column_window, "window")
        ).winfo_reqheight()
        content_height = max(left_height, right_height) + 40
        self.body_canvas.configure(scrollregion=(0, 0, width, content_height))

    def _on_mousewheel(self, event):
        if not hasattr(self, "body_canvas"):
            return
        if not self.body_canvas.winfo_exists():
            return
        self.body_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_input_card(self, parent):
        card = self._card(parent, "1. Choose Images", 0)
        ttk.Label(card, text="Folder", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.folder_entry = ttk.Entry(card, textvariable=self.folder_var, style="Field.TEntry")
        self.folder_entry.grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=4)
        ttk.Button(card, text="Browse Folder", style="Soft.TButton", command=self.browse_folder).grid(row=1, column=2, sticky="ew", pady=4)

        ttk.Label(card, text="Specific Files", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        self.files_label = ttk.Label(card, text="No files selected", style="Body.TLabel")
        self.files_label.grid(row=2, column=1, sticky="w", padx=(8, 8), pady=4)
        ttk.Button(card, text="Select Images", style="Soft.TButton", command=self.browse_files).grid(row=2, column=2, sticky="ew", pady=4)

        ttk.Checkbutton(card, text="Scan subfolders recursively", variable=self.recursive_var).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 4))
        ttk.Label(card, textvariable=self.count_var, style="Body.TLabel").grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _build_output_card(self, parent):
        card = self._card(parent, "2. Output", 1)
        ttk.Label(card, text="KMZ name", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(card, textvariable=self.output_name_var, style="Field.TEntry").grid(row=1, column=1, columnspan=2, sticky="ew", pady=4, padx=(8, 0))

        ttk.Label(card, text="Save to", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(card, textvariable=self.output_folder_var, style="Field.TEntry").grid(row=2, column=1, sticky="ew", pady=4, padx=(8, 8))
        ttk.Button(card, text="Browse", style="Soft.TButton", command=self.browse_output_folder).grid(row=2, column=2, sticky="ew", pady=4)

    def _build_process_card(self, parent):
        card = self._card(parent, "3. Processing", 2)
        ttk.Label(card, text="Max images", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Spinbox(card, from_=1, to=50000, textvariable=self.max_images_var, width=12).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=4)
        ttk.Label(card, text="Set a cap for very large folders to keep exports responsive.", style="Body.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _build_style_card(self, parent):
        card = self._card(parent, "4. Map Style", 0)
        ttk.Label(card, text="Icon preset", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        self.icon_combo = ttk.Combobox(card, textvariable=self.icon_preset_var, values=list(PRESET_ICONS.keys()) + ["Custom file"], state="readonly", style="Field.TCombobox")
        self.icon_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

        ttk.Label(card, text="Custom icon", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        self.icon_file_entry = ttk.Entry(card, textvariable=self.icon_file_var, style="Field.TEntry")
        self.icon_file_entry.grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=4)
        self.icon_file_button = ttk.Button(card, text="Browse", style="Soft.TButton", command=self.browse_icon)
        self.icon_file_button.grid(row=2, column=2, sticky="ew", pady=4)

        ttk.Label(card, text="Icon scale", style="Body.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Spinbox(card, from_=0.2, to=4.0, increment=0.1, textvariable=self.icon_scale_var, width=12).grid(row=3, column=1, sticky="w", padx=(8, 0), pady=4)

        ttk.Checkbutton(card, text="Show labels on the map", variable=self.show_labels_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 4))
        ttk.Label(card, text="Label text", style="Body.TLabel").grid(row=5, column=0, sticky="w", pady=4)
        self.label_combo = ttk.Combobox(card, textvariable=self.label_mode_var, values=list(LABEL_MODES.keys()), state="readonly", style="Field.TCombobox")
        self.label_combo.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

    def _build_altitude_card(self, parent):
        card = self._card(parent, "5. Altitude", 1)
        ttk.Label(card, text="Google Earth mode", style="Body.TLabel").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.earth_mode_combo = ttk.Combobox(
            card,
            textvariable=self.google_earth_altitude_mode_var,
            values=list(GOOGLE_EARTH_ALTITUDE_MODES.values()),
            state="readonly",
            style="Field.TCombobox",
        )
        self.earth_mode_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)
        ttk.Label(
            card,
            textvariable=self.altitude_mode_note_var,
            style="Body.TLabel",
            wraplength=320,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 8))
        ttk.Radiobutton(
            card,
            text=ALTITUDE_SOURCES["metadata"],
            value="metadata",
            variable=self.altitude_source_var,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Radiobutton(
            card,
            text=ALTITUDE_SOURCES["override"],
            value="override",
            variable=self.altitude_source_var,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(card, text="Fixed altitude (meters)", style="Body.TLabel").grid(row=5, column=0, sticky="w", pady=4)
        self.altitude_entry = ttk.Entry(card, textvariable=self.altitude_override_var, style="Field.TEntry")
        self.altitude_entry.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=4)

    def _build_summary_card(self, parent):
        card = self._card(parent, "6. Export Summary", 2)
        card.columnconfigure(0, weight=1)
        summary = (
            "Inputs can come from a whole folder or a hand-picked list of images.\n\n"
            "Styling controls affect the placemark icon, its scale, and whether labels appear on the map.\n\n"
            "Google Earth mode controls whether the altitude is absolute, relative to terrain, or clamped to the ground/sea floor."
        )
        ttk.Label(card, text=summary, style="Body.TLabel", justify="left", wraplength=280).grid(row=1, column=0, sticky="w")

    def _wire_events(self):
        self.icon_preset_var.trace_add("write", lambda *_: self._toggle_custom_icon_state())
        self.altitude_source_var.trace_add("write", lambda *_: self._toggle_altitude_state())
        self.google_earth_altitude_mode_var.trace_add("write", lambda *_: self._toggle_altitude_state())
        self.recursive_var.trace_add("write", lambda *_: self.refresh_count())
        self.folder_var.trace_add("write", lambda *_: self.refresh_count())

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder with geotagged images")
        if not folder:
            return
        self.folder_var.set(folder)
        self.selected_files = []
        self.files_label.config(text="No files selected")
        self.status_var.set("Folder selected. Review styling options, then export.")
        self.refresh_count()

    def browse_files(self):
        files = filedialog.askopenfilenames(title="Select geotagged images", filetypes=[("Image files", "*.jpg *.jpeg *.jpe *.heic *.heif")])
        if not files:
            return
        self.selected_files = list(files)
        self.folder_var.set("")
        self.files_label.config(text=f"{len(files)} files selected")
        self.status_var.set("Specific files selected. Review styling options, then export.")
        self.refresh_count()

    def browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.output_folder_var.set(folder)

    def browse_icon(self):
        file_path = filedialog.askopenfilename(
            title="Select custom icon",
            filetypes=[("Icon/image files", "*.png *.jpg *.jpeg *.gif *.bmp *.ico"), ("All files", "*.*")],
        )
        if file_path:
            self.icon_file_var.set(file_path)
            self.icon_preset_var.set("Custom file")

    def _toggle_custom_icon_state(self):
        use_custom = self.icon_preset_var.get() == "Custom file"
        state = "normal" if use_custom else "disabled"
        self.icon_file_entry.configure(state=state)
        self.icon_file_button.configure(state=state)

    def _toggle_altitude_state(self):
        mode_key = _earth_mode_key(self.google_earth_altitude_mode_var.get())
        self.altitude_mode_note_var.set(ALTITUDE_MODE_NOTES.get(mode_key, ""))
        state = "normal"
        if self.altitude_source_var.get() != "override":
            state = "disabled"
        if _is_clamp_mode(mode_key):
            state = "disabled"
        self.altitude_entry.configure(state=state)

    def refresh_count(self):
        try:
            images = resolve_images(
                self.folder_var.get().strip() or None,
                recursive=self.recursive_var.get(),
                selected_files=self.selected_files,
            )
            self.count_var.set(f"{len(images)} supported images ready")
        except Exception:
            self.count_var.set("Unable to count images")

    def _build_output_path(self):
        output_name = self.output_name_var.get().strip()
        if not output_name:
            raise ValueError("Enter a KMZ file name.")
        if output_name.lower().endswith(".kmz"):
            output_name = output_name[:-4]

        output_folder_text = self.output_folder_var.get().strip()
        if not output_folder_text:
            raise ValueError("Choose an output folder.")
        output_folder = Path(output_folder_text)
        return output_folder / f"{output_name}.kmz"

    def _build_options(self):
        icon_preset = self.icon_preset_var.get()
        icon_file = self.icon_file_var.get().strip() or None
        if icon_preset == "Custom file" and not icon_file:
            raise ValueError("Choose a custom icon file or select a preset icon.")
        if icon_preset != "Custom file":
            icon_file = None

        icon_scale = float(self.icon_scale_var.get())
        if icon_scale <= 0:
            raise ValueError("Icon scale must be greater than 0.")

        altitude_source = self.altitude_source_var.get()
        google_earth_altitude_mode = _earth_mode_key(
            self.google_earth_altitude_mode_var.get()
        )
        altitude_override = None
        if altitude_source == "override" and not _is_clamp_mode(google_earth_altitude_mode):
            altitude_override = float(self.altitude_override_var.get())

        return KMZRenderOptions(
            icon_preset=icon_preset if icon_preset != "Custom file" else "Camera",
            icon_file=icon_file,
            icon_scale=icon_scale,
            show_labels=self.show_labels_var.get(),
            label_mode=self.label_mode_var.get(),
            altitude_source=altitude_source,
            google_earth_altitude_mode=google_earth_altitude_mode,
            altitude_override=altitude_override,
        )

    def run(self):
        input_folder = self.folder_var.get().strip() or None
        if not input_folder and not self.selected_files:
            messagebox.showerror("Missing Input", "Choose a folder or select specific images before exporting.")
            return

        try:
            output_path = self._build_output_path()
            options = self._build_options()
        except Exception as exc:
            messagebox.showerror("Invalid Settings", str(exc))
            return

        self.status_var.set("Building KMZ. This can take a while for large image sets.")
        self.root.update_idletasks()

        try:
            result = create_kmz_from_images(
                input_folder,
                output_path,
                max_images=int(self.max_images_var.get()),
                recursive=self.recursive_var.get(),
                selected_files=self.selected_files,
                render_options=options,
            )
        except Exception as exc:
            self.status_var.set("Export failed.")
            messagebox.showerror("Export Failed", str(exc))
            return

        added = result["added"]
        skipped = result["skipped"]
        if added <= 0:
            self.status_var.set("No geotagged images were exported.")
            messagebox.showwarning("No GPS Data", "No images with GPS metadata were added to the KMZ.\nCheck the console or metadata on the source files.")
            return

        self.status_var.set(f"KMZ created: {output_path}")
        if messagebox.askyesno("Export Complete", f"KMZ created successfully.\n\nAdded: {added}\nSkipped: {skipped}\nOutput: {output_path}\n\nOpen the output folder now?"):
            os.startfile(str(output_path.parent))

    def mainloop(self):
        self.root.mainloop()


def gui_mode(exiftool_path=None):
    app = KMZApp(exiftool_path=exiftool_path)
    app.mainloop()


def build_render_options_from_args(args):
    if (
        args.altitude_source == "override"
        and args.altitude_override is None
        and not _is_clamp_mode(args.google_earth_altitude_mode)
    ):
        raise ValueError(
            "--altitude-override is required when --altitude-source override is used."
        )

    return KMZRenderOptions(
        icon_preset=args.icon_preset,
        icon_file=args.icon_file,
        icon_scale=args.icon_scale,
        show_labels=args.show_labels,
        label_mode=args.label_mode,
        altitude_source=args.altitude_source,
        google_earth_altitude_mode=args.google_earth_altitude_mode,
        altitude_override=args.altitude_override,
    )


def main():
    ap = argparse.ArgumentParser(description="Geotagged images to KMZ")
    ap.add_argument("input", nargs="?", default=None, help="Input folder with images")
    ap.add_argument("--output", "-o", default=None, help="Output KMZ filename")
    ap.add_argument("--max-images", "-m", type=int, default=1000, help="Max images")
    ap.add_argument("--recursive", "-r", action="store_true", help="Scan subfolders")
    ap.add_argument("--exiftool", help="Path to exiftool executable (optional)")
    ap.add_argument("--gui", action="store_true", help="Launch GUI mode")
    ap.add_argument("--icon-preset", choices=sorted(PRESET_ICONS.keys()), default="Camera", help="Placemark icon preset")
    ap.add_argument("--icon-file", help="Path to a custom icon image file")
    ap.add_argument("--icon-scale", type=float, default=0.8, help="Placemark icon scale")
    ap.add_argument("--show-labels", action="store_true", help="Show map labels")
    ap.add_argument("--label-mode", choices=sorted(LABEL_MODES.keys()), default="filename", help="Text used for labels")
    ap.add_argument(
        "--google-earth-altitude-mode",
        choices=sorted(GOOGLE_EARTH_ALTITUDE_MODES.keys()),
        default="absolute",
        help="Google Earth altitude mode for the placemark",
    )
    ap.add_argument(
        "--altitude-source",
        choices=sorted(ALTITUDE_SOURCES.keys()),
        default="metadata",
        help="Use image altitude metadata or a fixed value",
    )
    ap.add_argument(
        "--altitude-override",
        type=float,
        help="Fixed altitude in meters when altitude source is override",
    )
    args = ap.parse_args()

    handlers = [logging.FileHandler("script_run.log", encoding="utf-8")]
    if not args.gui and sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=handlers,
    )
    logging.info("Starting drone_images_to_kmz")

    exiftool_path = args.exiftool or _bundled_exiftool_path()
    if exiftool_path:
        globals()["EXIFTOOL_EXE"] = exiftool_path

    if args.gui:
        gui_mode(exiftool_path)
        return

    if not args.input:
        ap.print_help()
        sys.exit(1)

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input path does not exist: {in_path}")
        sys.exit(1)

    try:
        render_options = build_render_options_from_args(args)
    except Exception as exc:
        print(f"Invalid options: {exc}")
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = Path(f"{in_path.name}.kmz")

    create_kmz_from_images(
        str(in_path),
        str(out_path),
        max_images=args.max_images,
        recursive=args.recursive,
        render_options=render_options,
    )


if __name__ == "__main__":
    main()
