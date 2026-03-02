#!/usr/bin/env python3
"""
Convert any image file to Windows ICO format for desktop shortcut
Usage: python image_to_icon_converter.py <input_image>
"""

import sys
import os
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow library not found. Installing...")
    os.system("pip install pillow")
    from PIL import Image


def convert_image_to_icon(input_path, output_path=None, size=256):
    """
    Convert an image to ICO format
    
    Args:
        input_path: Path to input image (PNG, JPG, etc)
        output_path: Path to save ICO file (defaults to same name with .ico extension)
        size: Icon size in pixels (default 256x256)
    """
    try:
        # Validate input file exists
        input_file = Path(input_path)
        if not input_file.exists():
            print(f"ERROR: File not found: {input_path}")
            return False
        
        # Open image
        print(f"Opening: {input_path}")
        img = Image.open(input_file)
        
        # Convert to RGBA (required for ICO format)
        if img.mode != 'RGBA':
            print(f"Converting from {img.mode} to RGBA...")
            img = img.convert('RGBA')
        
        # Resize to icon size (maintains aspect ratio with padding)
        print(f"Resizing to {size}x{size}...")
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        
        # Create square canvas (for icons)
        new_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        offset = ((size - img.size[0]) // 2, (size - img.size[1]) // 2)
        new_img.paste(img, offset, img)
        
        # Determine output path
        if output_path is None:
            output_path = input_file.stem + '.ico'
        
        # Save as ICO
        output_file = Path(output_path)
        print(f"Saving to: {output_file}")
        new_img.save(output_file, format='ICO')
        
        print(f"\n✓ SUCCESS: Icon created!")
        print(f"   File: {output_file.name}")
        print(f"   Size: {output_file.stat().st_size:,} bytes")
        print(f"   Location: {output_file.parent}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("Image to Icon Converter")
        print("=" * 60)
        print("\nUsage: python image_to_icon_converter.py <image_file>")
        print("\nExamples:")
        print("  python image_to_icon_converter.py my_icon.png")
        print("  python image_to_icon_converter.py C:\\Users\\Pictures\\drone.jpg")
        print("\nSupported formats: PNG, JPG, BMP, GIF, TIFF, etc.")
        print("Output: .ico file in same location as input")
        print("=" * 60)
        
        # Interactive mode
        print("\nEnter image file path (or press Ctrl+C to exit):")
        try:
            input_path = input("> ").strip().strip('"')
            if not input_path:
                print("No file specified.")
                return False
            
            return convert_image_to_icon(input_path)
        except KeyboardInterrupt:
            print("\nCancelled.")
            return False
    else:
        input_path = sys.argv[1]
        return convert_image_to_icon(input_path)


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
