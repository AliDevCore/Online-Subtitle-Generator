"""
Script to generate modern app icon (.ico and .png) for OnlineSub.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path


def create_icon():
    root = Path(__file__).resolve().parent.parent
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    size = (256, 256)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer rounded rectangle (gradient-like deep blue)
    bg_color = (15, 23, 42, 255)       # Slate 900
    border_color = (56, 189, 248, 255) # Sky 400
    accent_color = (2, 132, 199, 255)  # Sky 600

    draw.rounded_rectangle([8, 8, 248, 248], radius=48, fill=bg_color, outline=border_color, width=6)

    # Draw subtitle box illustration
    draw.rounded_rectangle([36, 60, 220, 160], radius=20, fill=(30, 41, 59, 255), outline=accent_color, width=4)

    # Subtitle lines inside box
    draw.rounded_rectangle([56, 85, 170, 97], radius=6, fill=(56, 189, 248, 255))
    draw.rounded_rectangle([56, 115, 200, 127], radius=6, fill=(148, 163, 184, 255))

    # Sound wave / globe badge in bottom right
    draw.ellipse([140, 140, 230, 230], fill=(2, 132, 199, 255), outline=(240, 249, 255, 255), width=4)

    # Wave arcs inside badge
    draw.arc([160, 160, 210, 210], start=210, end=330, fill=(255, 255, 255, 255), width=5)
    draw.arc([170, 170, 200, 200], start=210, end=330, fill=(255, 255, 255, 255), width=5)

    png_path = assets_dir / "app_icon.png"
    ico_path = assets_dir / "app_icon.ico"

    img.save(png_path, "PNG")

    # Generate multi-size ICO
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)

    print(f"Icons generated:\n{png_path}\n{ico_path}")


if __name__ == "__main__":
    create_icon()
