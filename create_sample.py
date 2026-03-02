from PIL import Image
import piexif
import os

os.makedirs('sample_images', exist_ok=True)
img = Image.new('RGB', (800,600), color=(200,50,50))

# Sample GPS coordinates
lat = 37.4221
lon = -122.0841
alt = 50

def to_deg_rational(deg_float):
    deg = int(abs(deg_float))
    minutes_float = (abs(deg_float) - deg) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60, 5)
    return ((deg,1),(minutes,1),(int(seconds*100000),100000))

gps_ifd = {
    piexif.GPSIFD.GPSLatitudeRef: 'N' if lat >= 0 else 'S',
    piexif.GPSIFD.GPSLatitude: to_deg_rational(lat),
    piexif.GPSIFD.GPSLongitudeRef: 'E' if lon >= 0 else 'W',
    piexif.GPSIFD.GPSLongitude: to_deg_rational(lon),
    piexif.GPSIFD.GPSAltitudeRef: 0,
    piexif.GPSIFD.GPSAltitude: (int(alt), 1),
}
exif_ifd = {
    piexif.ExifIFD.DateTimeOriginal: '2026:02:08 12:00:00'
}
exif_dict = {
    '0th': {},
    'Exif': exif_ifd,
    'GPS': gps_ifd,
}
exif_bytes = piexif.dump(exif_dict)

path = os.path.join('sample_images', 'img1.jpg')
img.save(path, 'jpeg', exif=exif_bytes)
print('Created', path)
