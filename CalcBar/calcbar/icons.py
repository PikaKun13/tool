"""图标绘制。

用 Pillow 4 倍超采样画完再缩小，得到抗锯齿的放大镜和计算器图标，
输出成 base64 PNG，交给 ``tk.PhotoImage(data=...)``（不需要 ImageTk）。
没装 Pillow 也能跑：``available()`` 返回 False，界面会退回用 Canvas 画。
"""

from __future__ import annotations

import base64
from io import BytesIO

try:
    from PIL import Image, ImageDraw
    _PIL = True
except ImportError:                               # pragma: no cover
    _PIL = False

SS = 4          # 超采样倍数


def available() -> bool:
    return _PIL


def _encode(image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _canvas(size: int, bg: str):
    return Image.new("RGB", (size * SS, size * SS), bg)


def _finish(image, size: int) -> str:
    return _encode(image.resize((size, size), Image.LANCZOS))


def rounded_chip(width: int, height: int, bg: str, fill: str) -> str:
    """面板小按钮的圆角底：tk 的 Label 画不出圆角，就贴一张图。"""
    image = Image.new("RGB", (width * SS, height * SS), bg)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, width * SS - 1, height * SS - 1],
                           radius=height * SS * 0.30, fill=fill)
    return _encode(image.resize((width, height), Image.LANCZOS))


def magnifier(size: int, bg: str, color: str) -> str:
    """左侧的放大镜：一个圆环加一根斜柄。"""
    image = _canvas(size, bg)
    draw = ImageDraw.Draw(image)
    n = size * SS
    stroke = max(2, round(n * 0.085))
    radius = n * 0.30
    cx = cy = n * 0.40
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                 outline=color, width=stroke)
    start = cx + radius * 0.72
    draw.line([start, start, n * 0.90, n * 0.90],
              fill=color, width=stroke)
    # 手柄末端补一个圆点，模拟圆头线帽
    cap = stroke / 2
    draw.ellipse([n * 0.90 - cap, n * 0.90 - cap, n * 0.90 + cap, n * 0.90 + cap],
                 fill=color)
    return _finish(image, size)


def calculator(size: int, bg: str, plate: str, glyph: str, screen: str) -> str:
    """右侧按钮：圆角底板 + 一个计算器小图标。"""
    image = _canvas(size, bg)
    draw = ImageDraw.Draw(image)
    n = size * SS
    draw.rounded_rectangle([0, 0, n - 1, n - 1], radius=n * 0.26, fill=plate)

    inset = n * 0.22
    body = [inset, inset * 0.86, n - inset, n - inset * 0.86]
    draw.rounded_rectangle(body, radius=n * 0.07, fill=glyph)

    width = body[2] - body[0]
    height = body[3] - body[1]
    margin = width * 0.14

    # 顶部显示屏
    screen_h = height * 0.22
    draw.rounded_rectangle(
        [body[0] + margin, body[1] + margin,
         body[2] - margin, body[1] + margin + screen_h],
        radius=n * 0.02, fill=screen)

    # 3 列 x 3 行按键
    top = body[1] + margin + screen_h + height * 0.12
    grid_w = width - margin * 2
    grid_h = body[3] - margin - top
    cols, rows = 3, 3
    key_w = grid_w / (cols + (cols - 1) * 0.45)
    key_h = grid_h / (rows + (rows - 1) * 0.45)
    for row in range(rows):
        for col in range(cols):
            x = body[0] + margin + col * key_w * 1.45
            y = top + row * key_h * 1.45
            draw.rounded_rectangle([x, y, x + key_w, y + key_h],
                                   radius=key_w * 0.3, fill=screen)
    return _finish(image, size)
