"""配色与尺寸。尺寸都是“逻辑像素”，用之前要乘 DPI 缩放。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg: str
    fg: str
    muted: str            # “= 结果”的灰
    placeholder: str
    icon: str
    error: str
    select_bg: str
    select_fg: str
    chip_bg: str
    chip_hover: str
    chip_fg: str
    section_fg: str
    separator: str
    button_bg: str
    button_hover: str
    hint: str


LIGHT = Palette(
    bg="#F2F1EF",
    fg="#17171A",
    muted="#8A8A8E",
    placeholder="#B4B2AE",
    icon="#86868B",
    error="#C8503F",
    select_bg="#CCE0FA",
    select_fg="#17171A",
    chip_bg="#E7E5E1",
    chip_hover="#D9D7D2",
    chip_fg="#3A3A3C",
    section_fg="#A3A19D",
    separator="#E1DFDB",
    button_bg="#E7E5E1",
    button_hover="#D9D7D2",
    hint="#A8A6A2",
)

DARK = Palette(
    bg="#2A2A2D",
    fg="#F4F4F6",
    muted="#9A9AA0",
    placeholder="#6C6C72",
    icon="#98989E",
    error="#E8836F",
    select_bg="#3D5A80",
    select_fg="#FFFFFF",
    chip_bg="#3A3A3F",
    chip_hover="#48484E",
    chip_fg="#E4E4E8",
    section_fg="#77777D",
    separator="#3A3A3F",
    button_bg="#3A3A3F",
    button_hover="#48484E",
    hint="#6C6C72",
)


@dataclass(frozen=True)
class Metrics:
    """逻辑像素尺寸（按 96 DPI 设计）。"""

    bar_width: int = 720          # 出厂宽度；用户拖边缘改的是 CalcBar.bar_width
    min_bar_width: int = 380      # 再窄就放不下「算式 + = 结果」了
    resize_edge: int = 6          # 左右各留这么宽的一条用来拉伸
    bar_height: int = 66
    icon_x: int = 22
    icon_size: int = 22
    text_x: int = 58
    result_gap: int = 12
    button_size: int = 36
    button_margin: int = 13
    font_input: int = 27
    font_result: int = 17
    font_chip: int = 13
    font_section: int = 11
    font_hint: int = 11
    panel_pad_x: int = 20
    panel_pad_y: int = 14
    chip_h: int = 27
    chip_pad_x: int = 9
    chip_gap: int = 6
    row_gap: int = 6
    section_gap: int = 12
    corner_radius: int = 12


METRICS = Metrics()
