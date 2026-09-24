"""Generate high-resolution ParqBench icon assets (PNG and multi-size ICO)."""
import os
from PIL import Image, ImageDraw, ImageFont

def generate_icons():
    os.makedirs("assets", exist_ok=True)
    size = 256
    # 256x256 master RGBA canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background rounded rectangle with sleek emerald gradient / dark slate card
    # Base dark rounded card
    r = 48
    # Outer glow / shadow base
    draw.rounded_rectangle([8, 8, 248, 248], radius=r, fill=(15, 23, 42, 255), outline=(16, 185, 129, 220), width=4)

    # Gradient-like inner table header bar
    draw.rounded_rectangle([18, 18, 238, 76], radius=24, fill=(16, 124, 65, 255))
    draw.rectangle([18, 50, 238, 76], fill=(16, 124, 65, 255)) # straighten bottom of header

    # Header columns representation
    draw.rectangle([32, 38, 80, 56], fill=(255, 255, 255, 230))
    draw.rectangle([94, 38, 150, 56], fill=(255, 255, 255, 180))
    draw.rectangle([164, 38, 222, 56], fill=(255, 255, 255, 180))

    # Grid rows
    row_y = [88, 124, 160, 196]
    for y in row_y:
        draw.line([(24, y), (232, y)], fill=(30, 41, 59, 255), width=2)
    
    # Column grid lines
    draw.line([(88, 76), (88, 234)], fill=(30, 41, 59, 255), width=2)
    draw.line([(158, 76), (158, 234)], fill=(30, 41, 59, 255), width=2)

    # Cell content pills (simulating structured Parquet columnar data)
    # Row 1
    draw.rounded_rectangle([32, 96, 76, 114], radius=4, fill=(52, 211, 153, 200)) # emerald active cell
    draw.rounded_rectangle([98, 98, 146, 112], radius=4, fill=(100, 116, 139, 140))
    draw.rounded_rectangle([168, 98, 215, 112], radius=4, fill=(100, 116, 139, 140))

    # Row 2
    draw.rounded_rectangle([32, 134, 72, 148], radius=4, fill=(100, 116, 139, 140))
    draw.rounded_rectangle([98, 132, 150, 150], radius=4, fill=(56, 189, 248, 180)) # cyan highlight
    draw.rounded_rectangle([168, 134, 205, 148], radius=4, fill=(100, 116, 139, 140))

    # Row 3
    draw.rounded_rectangle([32, 170, 68, 184], radius=4, fill=(100, 116, 139, 140))
    draw.rounded_rectangle([98, 170, 138, 184], radius=4, fill=(100, 116, 139, 140))
    draw.rounded_rectangle([168, 168, 218, 186], radius=4, fill=(245, 158, 11, 180)) # amber highlight

    # Bold "PQ" or Parquet badge in bottom corner
    draw.rounded_rectangle([140, 172, 238, 238], radius=16, fill=(16, 185, 129, 255), outline=(255, 255, 255, 200), width=2)
    # Text in badge
    # Draw simple clean geometric 'PQ'
    # P
    draw.line([(162, 188), (162, 222)], fill=(255, 255, 255, 255), width=4)
    draw.arc([(158, 188), (185, 208)], start=270, end=90, fill=(255, 255, 255, 255), width=4)
    draw.line([(162, 188), (172, 188)], fill=(255, 255, 255, 255), width=4)
    draw.line([(162, 208), (172, 208)], fill=(255, 255, 255, 255), width=4)

    # Q
    draw.ellipse([(190, 192), (218, 220)], outline=(255, 255, 255, 255), width=4)
    draw.line([(208, 212), (222, 226)], fill=(255, 255, 255, 255), width=4)

    png_path = os.path.abspath("assets/icon.png")
    ico_path = os.path.abspath("assets/icon.ico")

    img.save(png_path, format="PNG")
    print(f"Saved {png_path}")

    # Generate multi-size icon: 16, 24, 32, 48, 64, 128, 256
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)
    print(f"Saved {ico_path}")

if __name__ == "__main__":
    generate_icons()
