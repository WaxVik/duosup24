"""Сборка картинки трейда: фон сезона + до 4 предметов слева («Отдаю») и до 4 справа («Хочу взамен»).

Координаты — px от центра фона в масштабе 100% (фон 1672×941).
Предмет вписывается в SLOT_SIZE и центрируется в точке ячейки.
"""
from __future__ import annotations

import datetime
import io
import logging
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSET_DIR = Path(os.getenv("TRADE_ASSETS_DIR", Path(__file__).resolve().parent / "trade_assets"))
TRADE_TZ = os.getenv("TRADE_TZ", "Europe/Moscow")

CANVAS = (1672, 941)
CENTER = (CANVAS[0] // 2, CANVAS[1] // 2)
SLOT_SIZE = (260, 260)  # ВРЕМЕННО: размер ячейки уточнить

GIVE_SLOTS = [(-560, -155), (-240, -155), (-560, 160), (-240, 160)]
WANT_SLOTS = [(240, -155), (560, -155), (240, 160), (560, 160)]

SEASON_BY_MONTH = {12: "Зима", 1: "Зима", 2: "Зима", 3: "Весна", 4: "Весна", 5: "Весна",
                   6: "Лето", 7: "Лето", 8: "Лето", 9: "Осень", 10: "Осень", 11: "Осень"}
IMG_EXTS = (".webp", ".png", ".jpg", ".jpeg")
FRUIT_SUFFIX = {"fn": "B", "fp": "A"}  # ...B = обычный, ...A = Permanent
ITEM_FOLDER = {"sk": "skins", "ot": "other", "gp": "gamepass"}
ALL_FOLDERS = ("skins", "other", "gamepass", "fruit")  # запасной поиск: если файл положили не в свою папку
LOG = logging.getLogger("trade_image")

# Название в боте -> другое имя файла (как лежит в архиве). Файлы не переименовываем.
FILE_ALIASES = {
    "Leopard": ["Tiger"],          # TigerA / TigerB
    "Yeti": ["YetiFruit"],         # YetiFruitA / YetiFruitB
    "Fruit Notifier": ["Fruit Notifer"],  # опечатка в файле Fruit-Notifer.png
}


def _names(name: str) -> list[str]:
    return [name] + FILE_ALIASES.get(name, [])


def _key(text: str) -> str:
    """Сравнение имён без регистра, пробелов и знаков: «T-Rex» == «TRex», «Dark Blade» == «darkblade»."""
    return re.sub(r"[^0-9a-zа-яё]", "", text.lower())


def _find(folder: str, stems: list[str]) -> Path | None:
    """Ищет файл по имени (без расширения) в папке; stems — варианты по приоритету."""
    d = ASSET_DIR / folder
    if not d.is_dir():
        return None
    files = [p for p in d.iterdir() if p.suffix.lower() in IMG_EXTS]
    for stem in stems:
        want = _key(stem)
        for p in files:
            if _key(p.stem) == want:
                return p
    return None


def item_image_path(cat: str, name: str, variant: str | None = None) -> Path | None:
    """Файл предмета. Фрукт: fruit/<Название><East|West><A|B>. Остальные: <папка>/<Название>."""
    if cat in FRUIT_SUFFIX:
        suf = FRUIT_SUFFIX[cat]
        stems = []
        for n in _names(name):
            stems += ([f"{n}{variant}{suf}"] if variant else []) + [f"{n}{suf}"]
        return _find("fruit", stems)
    folder = ITEM_FOLDER.get(cat)
    if folder:
        hit = _find(folder, _names(name))
        if hit:
            return hit
    for other in ALL_FOLDERS:  # скин или предмет лежит в другой папке
        hit = _find(other, _names(name))
        if hit:
            return hit
    LOG.warning("трейд: нет картинки для «%s» (категория %s), ищу в %s", name, cat, ASSET_DIR)
    return None


def season_now(when: datetime.datetime | None = None) -> str:
    if when is None:
        from zoneinfo import ZoneInfo
        when = datetime.datetime.now(ZoneInfo(TRADE_TZ))
    return SEASON_BY_MONTH[when.month]


FONT_CANDIDATES = [
    ASSET_DIR / "font.ttf",  # положите сюда любой шрифт с кириллицей
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Шрифт с кириллицей. Без TTF Pillow рисует только латиницу, поэтому кладите font.ttf в trade_assets."""
    for path in FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _placeholder(name: str) -> Image.Image:
    img = Image.new("RGBA", SLOT_SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, SLOT_SIZE[0] - 1, SLOT_SIZE[1] - 1), radius=28,
                        fill=(70, 70, 80, 230), outline=(160, 160, 170, 255), width=4)
    font = _font(30)
    d.text((SLOT_SIZE[0] / 2, SLOT_SIZE[1] / 2), name, font=font, fill=(235, 235, 240, 255),
           anchor="mm", align="center")
    return img


def _paste(canvas: Image.Image, img: Image.Image, slot_xy: tuple[int, int]) -> None:
    img = img.convert("RGBA")
    img.thumbnail(SLOT_SIZE, Image.LANCZOS)
    x = CENTER[0] + slot_xy[0] - img.width // 2
    y = CENTER[1] + slot_xy[1] - img.height // 2
    canvas.alpha_composite(img, dest=(x, y))


def compose_trade_image(give: list[dict], want: list[dict], when: datetime.datetime | None = None,
                        season: str | None = None) -> bytes:
    """give / want: [{"c": "fn|fp|sk|ot|gp", "id": ..., "n": "Название", "v": "East|West" (необяз.)}, ...]."""
    season = season or season_now(when)  # season: ручной выбор через /seasont, иначе по месяцу
    bg_path = _find("backgrounds", [season])
    if not bg_path:
        LOG.warning("трейд: нет фона «%s» в %s", season, ASSET_DIR / "backgrounds")
    if bg_path:
        canvas = Image.open(bg_path).convert("RGBA")
        if canvas.size != CANVAS:
            canvas = canvas.resize(CANVAS, Image.LANCZOS)
    else:
        canvas = Image.new("RGBA", CANVAS, (40, 40, 48, 255))

    for slots, items in ((GIVE_SLOTS, give), (WANT_SLOTS, want)):
        for slot, item in zip(slots, items[:4]):
            path = item_image_path(item["c"], item["n"], item.get("v"))
            img = Image.open(path) if path else _placeholder(item["n"])
            _paste(canvas, img, slot)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
