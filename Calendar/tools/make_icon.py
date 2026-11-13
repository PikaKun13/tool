"""exe 用のマルチサイズアイコン src/Assets/KKCalendar.ico を生成する（トレイアイコンはプログラムが実行時に自分で描く）。

    .venv\\Scripts\\python tools\\make_icon.py [プレビュー.png]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "Assets" / "KKCalendar.ico"

N = 1024                      # まず大きく描いてから各サイズに縮小する
PAGE = "#FBFAF8"
EDGE = "#D9D6D0"
HEADER = "#D93A3F"
DOT = "#B9B5AE"
RED = "#D93A3F"
RING = "#5B5852"


def draw() -> Image.Image:
    image = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    margin = N * 0.06
    top = N * 0.12
    radius = N * 0.16
    box = [margin, top, N - margin, N - margin]
    pen.rounded_rectangle(box, radius=radius, fill=PAGE, outline=EDGE, width=int(N * 0.012))

    # 赤いヘッダー：上側は角丸、下端はまっすぐ
    header_h = N * 0.24
    pen.rounded_rectangle([margin, top, N - margin, top + header_h + radius],
                          radius=radius, fill=HEADER)
    pen.rectangle([margin, top + header_h, N - margin, top + header_h + radius], fill=PAGE)

    # 2 つのリング
    for cx in (N * 0.32, N * 0.68):
        w, h = N * 0.075, N * 0.2
        pen.rounded_rectangle([cx - w / 2, top - h * 0.45, cx + w / 2, top + h * 0.55],
                              radius=w / 2, fill=RING)

    # 日付のマス：3 行 4 列の丸。そのうち 1 つが赤い祝日
    cols, rows = 4, 3
    left, right = margin + N * 0.13, N - margin - N * 0.13
    upper, lower = top + header_h + N * 0.13, N - margin - N * 0.12
    r = N * 0.052
    for row in range(rows):
        for col in range(cols):
            cx = left + (right - left) * col / (cols - 1)
            cy = upper + (lower - upper) * row / (rows - 1)
            if (row, col) == (1, 2):
                big = r * 1.75
                pen.ellipse([cx - big, cy - big, cx + big, cy + big], fill=RED)
            else:
                pen.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DOT)
    return image


def main() -> None:
    image = draw()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
    image.save(OUT, format="ICO", sizes=sizes)
    print("wrote", OUT)
    if len(sys.argv) > 1:
        preview = Image.new("RGBA", (16 + 24 + 32 + 48 + 256 + 60, 260), "#FFFFFF")
        x = 4
        for s in (16, 24, 32, 48, 256):
            preview.paste(image.resize((s, s), Image.LANCZOS), (x, 2), image.resize((s, s), Image.LANCZOS))
            x += s + 12
        preview.save(sys.argv[1])


if __name__ == "__main__":
    main()
