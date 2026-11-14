"""Картинка стока: фон Normal/Mirage (активный A / завершённый B) + до 7 физических фруктов.

Фрукты берутся из trade_assets/fruit (ИмяB.webp, 1024×1024), масштаб 20%.
Слева самые дорогие, справа дешёвые. Если фруктов больше 7, самый дешёвый не попадает на фото.
Meme и Permanent в стоке не используются.
"""
from __future__ import annotations

from PIL import Image

from trade_image import CANVAS, CENTER, _find, _placeholder, fit_box, item_image_path

STOCK_SLOTS = [(-500, 240), (-300, 240), (-100, 240), (100, 240), (300, 240), (500, 240), (700, 240)]
MIRAGE_SLOTS = [(x, -230) for x, _ in STOCK_SLOTS]  # Mirage: фрукты выше, Y −230
STOCK_ITEM_PX = round(1024 * 0.20)  # масштаб 20%
STOCK_MAX = len(STOCK_SLOTS)
STOCK_EXCLUDE = {"meme"}
BG_NAMES = {"normal": "Normal", "mirage": "Mirage"}


def stock_background(kind: str, active: bool) -> Image.Image | None:
    path = _find("backgrounds", [f"{BG_NAMES[kind]}{'A' if active else 'B'}"])
    if not path:
        return None
    img = Image.open(path).convert("RGBA")
    return img if img.size == CANVAS else img.resize(CANVAS, Image.LANCZOS)


def compose_stock_image(kind: str, items: list[tuple[str, int]], active: bool) -> bytes:
    """items: [(название фрукта, цена)]."""
    import io
    canvas = stock_background(kind, active) or Image.new("RGBA", CANVAS, (40, 40, 48, 255))
    visible = [(n, p or 0) for n, p in items if n.lower() not in STOCK_EXCLUDE]
    visible.sort(key=lambda x: x[1], reverse=True)  # дорогие слева
    slots = MIRAGE_SLOTS if kind == "mirage" else STOCK_SLOTS
    for (name, _price), (sx, sy) in zip(visible[:STOCK_MAX], slots):
        path = item_image_path("fn", name)
        img = Image.open(path).convert("RGBA") if path else _placeholder(name)
        img = fit_box(img, (STOCK_ITEM_PX, STOCK_ITEM_PX))
        x = CENTER[0] + sx - img.width // 2
        y = CENTER[1] + sy - img.height // 2
        canvas.alpha_composite(img, dest=(x, y))
    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
