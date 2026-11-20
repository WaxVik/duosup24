"""Сборка картинки трейда: фон сезона + до 4 предметов слева («Отдаю») и до 4 справа («Хочу взамен»).

Координаты — px от центра фона в масштабе 100% (фон 1672×941).
Предмет вписывается в SLOT_SIZE и центрируется в точке ячейки.
"""
from __future__ import annotations

import datetime
import difflib
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
ITEM_PX = round(1024 * 0.30)  # фото предметов 1024×1024, масштаб 30%
SLOT_SIZE = (ITEM_PX, ITEM_PX)

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
    # Скины фруктов: если в боте имя отличается от файла, впишите сюда «имя в боте»: [«имя файла без .png»]
    # Пример: "Eagle Paro": ["EagleParro"],
}


def _names(name: str) -> list[str]:
    return [name] + FILE_ALIASES.get(name, [])


def _key(text: str) -> str:
    """Сравнение имён без регистра, пробелов и знаков: «T-Rex» == «TRex», «Dark Blade» == «darkblade»."""
    return re.sub(r"[^0-9a-zа-яё]", "", text.lower())


# Папки на GitHub/Linux чувствительны к регистру и могут называться иначе: Backgrounds, skin, Other.
FOLDER_ALIASES = {"backgrounds": ["background"], "skins": ["skin"], "other": ["others"]}


def _folder_dir(folder: str) -> Path | None:
    """Находит папку внутри trade_assets без учёта регистра и с запасными именами."""
    if not ASSET_DIR.is_dir():
        return None
    wanted = {_key(folder)} | {_key(a) for a in FOLDER_ALIASES.get(folder, [])}
    for child in ASSET_DIR.iterdir():
        if child.is_dir() and _key(child.name) in wanted:
            return child
    return None


def _tokens(text: str) -> frozenset[str]:
    """Слова имени без учёта порядка: «Kitsune Empyrean Galaxy» == «GalaxyKitsuneEmpyrean» == «KitsuneEmpyreanGalaxy»."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return frozenset(re.findall(r"[0-9a-zа-яё]+", spaced.lower()))


FUZZY_CUTOFF = 0.88  # похожесть имён при опечатке (Parro/Paro, Dracon/Draconn и т.п.)


def _find(folder: str, stems: list[str], fuzzy: bool = False) -> Path | None:
    """Ищет файл по имени (без расширения) в папке; stems — варианты по приоритету.

    Порядок: точное совпадение -> те же слова в другом порядке/написании -> (если fuzzy) похожее имя.
    """
    d = _folder_dir(folder)
    if d is None:
        return None
    files = [p for p in d.iterdir() if p.suffix.lower() in IMG_EXTS]
    for stem in stems:  # 1. точное (без регистра/пробелов/знаков)
        want = _key(stem)
        for p in files:
            if _key(p.stem) == want:
                return p
    for stem in stems:  # 2. те же слова, другой порядок или слитное/раздельное написание
        want = _tokens(stem)
        if want:
            for p in files:
                if _tokens(p.stem) == want:
                    return p
    if fuzzy:  # 3. опечатка в названии (в боте или в файле)
        by_key = {_key(p.stem): p for p in files}
        for stem in stems:
            close = difflib.get_close_matches(_key(stem), list(by_key), n=1, cutoff=FUZZY_CUTOFF)
            if close:
                LOG.info("трейд: «%s» найден по похожему имени файла «%s»", stem, by_key[close[0]].name)
                return by_key[close[0]]
    return None


def item_image_path(cat: str, name: str, variant: str | None = None) -> Path | None:
    """Файл предмета. Фрукт: fruit/<Название><East|West><A|B>. Остальные: <папка>/<Название>."""
    if cat in FRUIT_SUFFIX:
        suf = FRUIT_SUFFIX[cat]
        stems = []
        for n in _names(name):
            stems += ([f"{n}{variant}{suf}"] if variant else []) + [f"{n}{suf}"]
        hit = _find("fruit", stems)
        if hit:
            return hit
        # скин, добавленный в /redacttrade в раздел Fruit: файла «НазваниеB» нет, ищем по имени в skins/ и др.
        for other in ALL_FOLDERS:
            hit = _find(other, _names(name), fuzzy=True)
            if hit:
                return hit
        LOG.warning("трейд: нет картинки для «%s» (категория %s), ищу в %s", name, cat, ASSET_DIR)
        return None
    folder = ITEM_FOLDER.get(cat)
    if folder:
        hit = _find(folder, _names(name), fuzzy=True)
        if hit:
            return hit
    for other in ALL_FOLDERS:  # скин или предмет лежит в другой папке
        hit = _find(other, _names(name), fuzzy=True)
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


def fit_box(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    """Масштабирует с сохранением пропорций так, чтобы поместиться в box (и увеличивает при необходимости)."""
    scale = min(box[0] / img.width, box[1] / img.height)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def merge_duplicates(items: list[dict]) -> list[dict]:
    """Одинаковые предметы (категория+название+вариант) сворачиваются в один слот с количеством \"q\"."""
    merged: dict[tuple, dict] = {}
    for it in items:
        k = (it.get("c"), it.get("n"), it.get("v"))
        if k in merged:
            merged[k]["q"] += max(1, int(it.get("q", 1)))
        else:
            merged[k] = {**it, "q": max(1, int(it.get("q", 1)))}
    return list(merged.values())


def _paste(canvas: Image.Image, img: Image.Image, slot_xy: tuple[int, int]) -> tuple[int, int, int, int]:
    img = fit_box(img.convert("RGBA"), SLOT_SIZE)
    x = CENTER[0] + slot_xy[0] - img.width // 2
    y = CENTER[1] + slot_xy[1] - img.height // 2
    canvas.alpha_composite(img, dest=(x, y))
    return x, y, x + img.width, y + img.height


def _badge(canvas: Image.Image, box: tuple[int, int, int, int], qty: int) -> None:
    """Плашка «x3» в правом нижнем углу предмета."""
    d = ImageDraw.Draw(canvas)
    font = _font(44)
    text = f"x{qty}"
    w = d.textlength(text, font=font)
    pad = 14
    x2, y2 = box[2] + 6, box[3] + 6
    x1, y1 = x2 - w - pad * 2, y2 - 44 - pad
    d.rounded_rectangle((x1, y1, x2, y2), radius=18, fill=(20, 20, 28, 235), outline=(255, 255, 255, 255), width=3)
    d.text(((x1 + x2) / 2, (y1 + y2) / 2), text, font=font, fill=(255, 255, 255, 255), anchor="mm")


def compose_trade_image(give: list[dict], want: list[dict], when: datetime.datetime | None = None,
                        season: str | None = None) -> bytes:
    """give / want: [{"c": "fn|fp|sk|ot|gp", "id": ..., "n": "Название", "v": "East|West" (необяз.), "q": количество (необяз.)}, ...].
    Одинаковые предметы объединяются в один слот с плашкой «xN»."""
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

    for slots, items in ((GIVE_SLOTS, merge_duplicates(give)), (WANT_SLOTS, merge_duplicates(want))):
        for slot, item in zip(slots, items[:4]):
            path = item_image_path(item["c"], item["n"], item.get("v"))
            img = Image.open(path) if path else _placeholder(item["n"])
            box = _paste(canvas, img, slot)
            if item.get("q", 1) > 1:
                _badge(canvas, box, item["q"])

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
