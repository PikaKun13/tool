"""生成 exe 用的多尺寸图标 assets/calcbar.ico。"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "calcbar.ico"

N = 1024                      # 先画大的，再缩到各个尺寸
BODY = "#26262A"
SCREEN = "#F4F3F0"
KEY = "#8E8E96"
ACCENT = "#FF9F0A"


def draw() -> Image.Image:
    image = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle([0, 0, N - 1, N - 1], radius=N * 0.22, fill=BODY)

    margin = N * 0.16
    screen_h = N * 0.20
    pen.rounded_rectangle([margin, margin, N - margin, margin + screen_h],
                          radius=N * 0.04, fill=SCREEN)

    top = margin + screen_h + N * 0.09
    grid_w = N - margin * 2
    grid_h = N - margin - top
    cols = rows = 3
    key_w = grid_w / (cols + (cols - 1) * 0.42)
    key_h = grid_h / (rows + (rows - 1) * 0.42)
    for row in range(rows):
        for col in range(cols):
            x = margin + col * key_w * 1.42
            y = top + row * key_h * 1.42
            color = ACCENT if (row, col) == (2, 2) else KEY
            pen.rounded_rectangle([x, y, x + key_w, y + key_h],
                                  radius=key_w * 0.32, fill=color)
    return image


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    draw().save(OUT, format="ICO", sizes=sizes)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
