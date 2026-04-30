from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_ROOT = PROJECT_ROOT / "assets"
BANNERS_ROOT = ASSETS_ROOT / "banners"
AVATAR_ROOT = ASSETS_ROOT / "avatar"


Color = tuple[int, int, int, int]

OFF_WHITE: Color = (246, 247, 243, 255)
INK: Color = (34, 51, 54, 255)
SAGE: Color = (124, 201, 183, 255)
SKY: Color = (143, 184, 232, 255)
PALE_SAGE: Color = (231, 241, 236, 255)
PALE_SKY: Color = (237, 244, 247, 255)
WHITE: Color = (255, 255, 255, 255)
LINE: Color = (221, 233, 224, 255)


@dataclass(slots=True)
class Canvas:
    width: int
    height: int
    pixels: list[list[Color]]

    @classmethod
    def create(cls, width: int, height: int, fill: Color) -> Canvas:
        return cls(
            width=width,
            height=height,
            pixels=[[fill for _ in range(width)] for _ in range(height)],
        )

    def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        x_end = min(self.width, x + w)
        y_end = min(self.height, y + h)
        for py in range(max(0, y), y_end):
            row = self.pixels[py]
            for px in range(max(0, x), x_end):
                row[px] = color

    def fill_circle(self, cx: int, cy: int, radius: int, color: Color) -> None:
        min_x = max(0, cx - radius)
        max_x = min(self.width - 1, cx + radius)
        min_y = max(0, cy - radius)
        max_y = min(self.height - 1, cy + radius)
        squared = radius * radius
        for py in range(min_y, max_y + 1):
            dy = py - cy
            row = self.pixels[py]
            for px in range(min_x, max_x + 1):
                dx = px - cx
                if dx * dx + dy * dy <= squared:
                    row[px] = color

    def fill_rounded_rect(self, x: int, y: int, w: int, h: int, radius: int, color: Color) -> None:
        self.fill_rect(x + radius, y, w - 2 * radius, h, color)
        self.fill_rect(x, y + radius, radius, h - 2 * radius, color)
        self.fill_rect(x + w - radius, y + radius, radius, h - 2 * radius, color)
        self.fill_circle(x + radius, y + radius, radius, color)
        self.fill_circle(x + w - radius - 1, y + radius, radius, color)
        self.fill_circle(x + radius, y + h - radius - 1, radius, color)
        self.fill_circle(x + w - radius - 1, y + h - radius - 1, radius, color)

    def stroke_rect(self, x: int, y: int, w: int, h: int, thickness: int, color: Color) -> None:
        self.fill_rect(x, y, w, thickness, color)
        self.fill_rect(x, y + h - thickness, w, thickness, color)
        self.fill_rect(x, y, thickness, h, color)
        self.fill_rect(x + w - thickness, y, thickness, h, color)

    def line(self, x1: int, y1: int, x2: int, y2: int, thickness: int, color: Color) -> None:
        dx = x2 - x1
        dy = y2 - y1
        steps = max(abs(dx), abs(dy), 1)
        radius = max(1, thickness // 2)
        for step in range(steps + 1):
            px = round(x1 + dx * step / steps)
            py = round(y1 + dy * step / steps)
            self.fill_circle(px, py, radius, color)

    def save_png(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = bytearray()
        for row in self.pixels:
            raw.append(0)
            for r, g, b, a in row:
                raw.extend((r, g, b, a))
        compressed = zlib.compress(bytes(raw), level=9)
        ihdr = struct.pack("!IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0)
        png = bytearray(b"\x89PNG\r\n\x1a\n")
        png.extend(_chunk(b"IHDR", ihdr))
        png.extend(_chunk(b"IDAT", compressed))
        png.extend(_chunk(b"IEND", b""))
        path.write_bytes(png)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack("!I", len(data))
        + tag
        + data
        + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _draw_banner_frame(canvas: Canvas) -> None:
    canvas.fill_circle(800, 448, 212, WHITE)
    canvas.fill_circle(906, 620, 246, PALE_SAGE)
    canvas.fill_circle(1040, 172, 110, PALE_SKY)
    canvas.fill_circle(564, 272, 76, WHITE)
    canvas.fill_circle(504, 652, 46, PALE_SKY)
    canvas.fill_circle(1148, 492, 36, WHITE)
    canvas.line(620, 306, 664, 262, 8, SKY)
    canvas.line(978, 258, 1020, 290, 8, SAGE)
    canvas.line(1078, 324, 1126, 276, 8, SKY)
    canvas.line(582, 566, 630, 614, 8, SAGE)


def _draw_shield(canvas: Canvas, cx: int, cy: int) -> None:
    canvas.fill_rounded_rect(cx - 78, cy - 88, 156, 196, 42, WHITE)
    canvas.stroke_rect(cx - 78, cy - 88, 156, 196, 12, INK)
    canvas.fill_circle(cx, cy + 10, 18, INK)
    canvas.fill_rect(cx - 14, cy + 28, 28, 54, INK)


def _draw_lock(canvas: Canvas, cx: int, cy: int, accent: Color = SAGE) -> None:
    canvas.line(cx - 36, cy - 18, cx - 36, cy - 42, 10, INK)
    canvas.line(cx + 36, cy - 18, cx + 36, cy - 42, 10, INK)
    canvas.line(cx - 36, cy - 42, cx + 36, cy - 42, 10, INK)
    canvas.fill_rounded_rect(cx - 56, cy - 6, 112, 92, 24, accent)
    canvas.stroke_rect(cx - 56, cy - 6, 112, 92, 8, INK)


def _draw_user(canvas: Canvas, cx: int, cy: int) -> None:
    canvas.fill_circle(cx, cy - 36, 44, WHITE)
    canvas.stroke_rect(cx - 44, cy - 80, 88, 88, 6, INK)
    canvas.fill_circle(cx, cy - 34, 26, PALE_SAGE)
    canvas.line(cx - 46, cy + 70, cx + 46, cy + 70, 16, INK)
    canvas.line(cx - 56, cy + 70, cx - 26, cy + 18, 16, INK)
    canvas.line(cx + 56, cy + 70, cx + 26, cy + 18, 16, INK)
    canvas.fill_circle(cx + 74, cy - 54, 18, SAGE)


def _draw_help(canvas: Canvas, cx: int, cy: int) -> None:
    canvas.fill_circle(cx, cy, 78, WHITE)
    canvas.stroke_rect(cx - 78, cy - 78, 156, 156, 8, INK)
    canvas.line(cx, cy - 34, cx, cy - 12, 12, INK)
    canvas.line(cx, cy + 36, cx, cy + 38, 16, INK)
    canvas.line(cx, cy - 10, cx + 22, cy + 10, 12, INK)
    canvas.fill_rounded_rect(cx + 94, cy + 4, 94, 62, 20, SAGE)
    canvas.stroke_rect(cx + 94, cy + 4, 94, 62, 6, INK)


def _draw_link(canvas: Canvas, cx: int, cy: int) -> None:
    canvas.line(cx - 76, cy - 20, cx - 12, cy - 20, 18, INK)
    canvas.line(cx + 12, cy + 20, cx + 76, cy + 20, 18, INK)
    canvas.fill_rounded_rect(cx - 18, cy - 58, 138, 76, 30, SAGE)
    canvas.stroke_rect(cx - 18, cy - 58, 138, 76, 8, INK)
    canvas.fill_rounded_rect(cx - 120, cy - 18, 138, 76, 30, PALE_SKY)
    canvas.stroke_rect(cx - 120, cy - 18, 138, 76, 8, INK)
    canvas.line(cx - 8, cy + 100, cx + 72, cy + 100, 18, INK)
    canvas.line(cx + 62, cy + 60, cx + 112, cy + 100, 14, INK)
    canvas.line(cx + 62, cy + 140, cx + 112, cy + 100, 14, INK)


def _draw_pricing_cards(canvas: Canvas, cx: int, cy: int) -> None:
    cards = (
        (cx - 120, cy + 10, 82, 126, WHITE, LINE),
        (cx - 8, cy - 26, 98, 162, WHITE, SAGE),
        (cx + 128, cy + 18, 82, 118, WHITE, LINE),
    )
    for x, y, w, h, fill, border in cards:
        canvas.fill_rounded_rect(x, y, w, h, 18, fill)
        canvas.stroke_rect(x, y, w, h, 4, border)
        canvas.line(x + 20, y + 34, x + w - 20, y + 34, 8, INK)
        canvas.line(x + 20, y + 64, x + w - 20, y + 64, 8, border)
        canvas.line(
            x + 20,
            y + h - 30,
            x + w - 20,
            y + h - 30,
            10,
            INK if border == SAGE else border,
        )


def _draw_dashboard(canvas: Canvas, cx: int, cy: int) -> None:
    canvas.fill_rounded_rect(cx - 116, cy - 84, 232, 168, 28, WHITE)
    canvas.stroke_rect(cx - 116, cy - 84, 232, 168, 8, INK)
    canvas.line(cx - 78, cy + 28, cx - 22, cy - 8, 10, SAGE)
    canvas.line(cx - 22, cy - 8, cx + 26, cy + 18, 10, SAGE)
    canvas.line(cx + 26, cy + 18, cx + 82, cy - 34, 10, SAGE)
    canvas.fill_circle(cx + 138, cy - 62, 24, SAGE)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = round(cx + 138 + math.cos(rad) * 26)
        y1 = round(cy - 62 + math.sin(rad) * 26)
        x2 = round(cx + 138 + math.cos(rad) * 40)
        y2 = round(cy - 62 + math.sin(rad) * 40)
        canvas.line(x1, y1, x2, y2, 6, INK)


def _draw_buy(canvas: Canvas, cx: int, cy: int) -> None:
    points = [
        (cx, cy - 88),
        (cx + 64, cy - 18),
        (cx, cy + 78),
        (cx - 64, cy - 18),
    ]
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        canvas.line(x1, y1, x2, y2, 16, SAGE)
    canvas.fill_rounded_rect(cx + 56, cy + 6, 136, 88, 22, WHITE)
    canvas.stroke_rect(cx + 56, cy + 6, 136, 88, 8, INK)
    canvas.line(cx + 78, cy + 40, cx + 170, cy + 40, 10, SKY)
    canvas.fill_circle(cx + 142, cy - 20, 18, SAGE)


def _draw_main_banner() -> Canvas:
    canvas = Canvas.create(1600, 900, OFF_WHITE)
    _draw_banner_frame(canvas)
    _draw_shield(canvas, 800, 430)
    canvas.line(922, 342, 958, 368, 8, SAGE)
    canvas.line(672, 536, 634, 572, 8, SKY)
    return canvas


def _draw_buy_banner() -> Canvas:
    canvas = Canvas.create(1600, 900, OFF_WHITE)
    _draw_banner_frame(canvas)
    _draw_buy(canvas, 736, 434)
    return canvas


def _draw_tariffs_banner() -> Canvas:
    canvas = Canvas.create(1600, 900, OFF_WHITE)
    _draw_banner_frame(canvas)
    _draw_pricing_cards(canvas, 754, 406)
    return canvas


def _draw_profile_banner() -> Canvas:
    canvas = Canvas.create(1600, 900, OFF_WHITE)
    _draw_banner_frame(canvas)
    _draw_user(canvas, 800, 440)
    return canvas


def _draw_join_banner() -> Canvas:
    canvas = Canvas.create(1600, 900, OFF_WHITE)
    _draw_banner_frame(canvas)
    _draw_link(canvas, 792, 432)
    return canvas


def _draw_help_banner() -> Canvas:
    canvas = Canvas.create(1600, 900, OFF_WHITE)
    _draw_banner_frame(canvas)
    _draw_help(canvas, 744, 430)
    return canvas


def _draw_admin_banner() -> Canvas:
    canvas = Canvas.create(1600, 900, OFF_WHITE)
    _draw_banner_frame(canvas)
    _draw_dashboard(canvas, 776, 434)
    return canvas


def _draw_avatar() -> Canvas:
    canvas = Canvas.create(1024, 1024, OFF_WHITE)
    canvas.fill_circle(512, 512, 344, PALE_SAGE)
    canvas.fill_circle(728, 306, 52, PALE_SKY)
    canvas.fill_circle(298, 736, 34, SAGE)
    _draw_shield(canvas, 476, 500)
    _draw_lock(canvas, 586, 534, accent=SAGE)
    return canvas


def generate_assets() -> list[Path]:
    outputs = {
        BANNERS_ROOT / "main.png": _draw_main_banner(),
        BANNERS_ROOT / "buy.png": _draw_buy_banner(),
        BANNERS_ROOT / "tariffs.png": _draw_tariffs_banner(),
        BANNERS_ROOT / "profile.png": _draw_profile_banner(),
        BANNERS_ROOT / "join.png": _draw_join_banner(),
        BANNERS_ROOT / "help.png": _draw_help_banner(),
        BANNERS_ROOT / "admin.png": _draw_admin_banner(),
        AVATAR_ROOT / "bot_avatar.png": _draw_avatar(),
    }
    written: list[Path] = []
    for path, canvas in outputs.items():
        canvas.save_png(path)
        written.append(path)
    return written


def main() -> None:
    for path in generate_assets():
        print(path)


if __name__ == "__main__":
    main()
