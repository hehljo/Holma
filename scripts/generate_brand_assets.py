#!/usr/bin/env python3
"""
Generates derived brand assets (PNGs, favicons, PWA icons) from icon/logo.svg.
Uses Holma blue (#0284c7).
"""
import os
import subprocess
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_SRC = os.path.join(ROOT, 'icon', 'logo.svg')
FE_PUBLIC = os.path.join(ROOT, 'frontend', 'public')


def main():
    with open(SVG_SRC, 'r', encoding='utf-8') as f:
        svg_raw = f.read()

    # Ensure Holma blue fill
    if 'fill="#0284c7"' not in svg_raw:
        svg_blue = svg_raw.replace('<g id="Hintergrund"', '<g id="Hintergrund" fill="#0284c7"')
        with open(SVG_SRC, 'w', encoding='utf-8') as f:
            f.write(svg_blue)
    else:
        svg_blue = svg_raw

    # Copy SVG to public
    fe_svg = os.path.join(FE_PUBLIC, 'logo.svg')
    with open(fe_svg, 'w', encoding='utf-8') as f:
        f.write(svg_blue)

    # Render high-res master via convert
    master_png = '/tmp/holma_brand_master.png'
    subprocess.run(['convert', '-background', 'none', '-density', '288', fe_svg, master_png], check=True)

    master = Image.open(master_png).convert('RGBA')
    mw, mh = master.size

    def make_square_icon(size, target_ratio=0.85):
        target_h = int(size * target_ratio)
        target_w = int(target_h * (mw / mh))
        resized = master.resize((target_w, target_h), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        paste_x = (size - target_w) // 2
        paste_y = (size - target_h) // 2
        canvas.paste(resized, (paste_x, paste_y), resized)
        return canvas

    # Target files
    make_square_icon(1024).save(os.path.join(FE_PUBLIC, 'icon.png'), optimize=True)
    make_square_icon(1024).save(os.path.join(ROOT, 'icon', 'icon.png'), optimize=True)
    make_square_icon(512).save(os.path.join(FE_PUBLIC, 'pwa-512.png'), optimize=True)
    make_square_icon(192).save(os.path.join(FE_PUBLIC, 'pwa-192.png'), optimize=True)
    make_square_icon(180).save(os.path.join(FE_PUBLIC, 'apple-touch-icon.png'), optimize=True)
    make_square_icon(64, target_ratio=0.9).save(os.path.join(FE_PUBLIC, 'favicon.png'), optimize=True)

    # Native aspect ratio logo-mark.png
    logo_mark = master.resize((868, 1083), Image.Resampling.LANCZOS)
    logo_mark.save(os.path.join(FE_PUBLIC, 'logo-mark.png'), optimize=True)

    print('Brand assets successfully generated.')


if __name__ == '__main__':
    main()
