"""Данные мини-игр DuoSup. Редактируйте списки прямо здесь: названия, достижения, титулы, крафты стилей.
ВАЖНО: ключи (первое значение) не меняйте после запуска — по ним хранится инвентарь игроков."""

CREATOR_SWORD = "triple_dark_blade"  # выдаётся только создателю, получить его нельзя

# ---------- МЕЧИ (41). Ключ, название ----------
SWORDS = [
    ("katana", "Katana"), ("cutlass", "Cutlass"), ("dual_katana", "Dual Katana"), ("iron_mace", "Iron Mace"),
    ("triple_katana", "Triple Katana"), ("pipe", "Pipe"), ("dual_headed_blade", "Dual-Headed Blade"),
    ("soul_cane", "Soul Cane"), ("bisento", "Bisento"), ("pole_1", "Pole (1st Form)"), ("pole_2", "Pole (2nd Form)"),
    ("saber", "Saber"), ("shisui", "Shisui"), ("saddi", "Saddi"), ("wando", "Wando"), ("dark_blade", "Dark Blade"),
    ("buddy_sword", "Buddy Sword"), ("spikey_trident", "Spikey Trident"), ("midnight_blade", "Midnight Blade"),
    ("rengoku", "Rengoku"), ("yama", "Yama"), ("tushita", "Tushita"), ("canvander", "Canvander"),
    ("dragon_trident", "Dragon Trident"), ("hallow_scythe", "Hallow Scythe"), ("cursed_dual_katana", "Cursed Dual Katana"),
    ("true_triple_katana", "True Triple Katana"), ("dark_dagger", "Dark Dagger"), ("koko", "Koko"),
    ("shark_anchor", "Shark Anchor"), ("shark_saw", "Shark Saw"), ("fox_lamp", "Fox Lamp"), ("jitte", "Jitte"),
    ("gravity_cane", "Gravity Cane"), ("dog_blade", "Dog Blade"), ("rabid_dog_blade", "Rabid Dog Blade"),
    ("wardens_sword", "Warden's Sword"), ("flail", "Flail"), ("trident", "Trident"), ("long_sword", "Long Sword"),
    ("triple_dark_blade", "Triple Dark Blade"),
]

# ---------- ОРУЖИЯ (16) ----------
WEAPONS = [
    ("slingshot", "Slingshot"), ("flintlock", "Flintlock"), ("musket", "Musket"), ("refined_slingshot", "Refined Slingshot"),
    ("refined_flintlock", "Refined Flintlock"), ("cannon", "Cannon"), ("magma_blaster", "Magma Blaster"),
    ("dragonstorm", "Dragonstorm"), ("acidum_rifle", "Acidum Rifle"), ("bazooka", "Bazooka"), ("kabucha", "Kabucha"),
    ("bizarre_rifle", "Bizarre Rifle"), ("serpent_bow", "Serpent Bow"), ("venom_bow", "Venom Bow"),
    ("soul_guitar", "Soul Guitar"), ("skull_guitar", "Skull Guitar"),
]

# ---------- СТИЛИ БОЯ ----------
# tier: 1 = V1, 2 = V2, 3 = финальные; max мастери 600
STYLES = [
    ("dragon_breath", "Dragon Breath", 1), ("electric", "Electric", 1), ("dark_step", "Dark Step", 1),
    ("water_kung_fu", "Water Kung Fu", 1), ("superhuman", "Superhuman", 2),
    ("dragon_talon", "Dragon Talon", 2), ("electric_claw", "Electric Claw", 2), ("death_step", "Death Step", 2),
    ("water_karate", "Water Karate", 2), ("godhuman", "Godhuman", 3), ("sanguine_art", "Sanguine Art", 3),
]
MASTERY_NEED = 400
MASTERY_MAX = 600

# Крафт стиля: items = нужные предметы (kind, key | "a|b" = любой из), styles = {стиль: мастери}, title = нужный титул
CRAFTS = {
    "dragon_breath": {"items": [("fruit", "dragon_west|dragon_east"), ("sword", "dragon_trident")]},
    "electric":      {"items": [("fruit", "lightning"), ("sword", "saber")]},
    "dark_step":     {"items": [("fruit", "dark"), ("sword", "dark_dagger")]},
    "water_kung_fu": {"items": [("fruit", "ice"), ("sword", "shark_saw")]},
    "superhuman":    {"styles": {"dragon_breath": 400, "electric": 400, "dark_step": 400, "water_kung_fu": 400}},
    "dragon_talon":  {"styles": {"dragon_breath": 400}},
    "electric_claw": {"styles": {"electric": 400}},
    "death_step":    {"styles": {"dark_step": 400}},
    "water_karate":  {"styles": {"water_kung_fu": 400}},
    "godhuman":      {"styles": {"dragon_talon": 400, "electric_claw": 400, "death_step": 400, "water_karate": 400}},
    "sanguine_art":  {"title": "serpent_slayer"},
}

# ---------- ГАЧА: редкость фруктов ----------
FRUIT_RARITY = {
    "common": ["rocket", "spin", "blade", "spring", "bomb", "smoke", "spike"],
    "uncommon": ["flame", "ice", "sand", "dark", "eagle", "diamond"],
    "rare": ["light", "rubber", "ghost", "magma", "magnet"],
    "legendary": ["quake", "buddha", "love", "creation", "spider", "sound", "phoenix", "portal", "lightning", "pain", "blizzard"],
    "mythical": ["gravity", "mammoth", "trex", "dough", "shadow", "venom", "gas", "spirit", "tiger", "yeti", "kitsune",
                 "control", "dragon_west", "dragon_east"],
}
RARITY_WEIGHT = {"common": 40, "uncommon": 28, "rare": 17, "legendary": 10, "mythical": 5}
RARITY_RU = {"common": "Обычный", "uncommon": "Необычный", "rare": "Редкий", "legendary": "Легендарный", "mythical": "Мифический"}
PITY_LIMIT = 20          # гарантия легендарного+ каждые 20 круток
GACHA_COOLDOWN = 2 * 3600  # крутка раз в 2 часа

# ---------- ДОСТИЖЕНИЯ ----------
# счётчики: pulls, days (дней с круткой), fruits, styles, mastery (сумма мастери), pvp_wins, pvp_streak, rep (баунти/хонор), titles
COUNTER_RU = {"pulls": "круток гачи", "days": "дней с круткой", "fruits": "разных фруктов", "styles": "стилей боя",
              "mastery": "суммарного мастери", "pvp_wins": "побед в PvP", "pvp_streak": "побед подряд",
              "rep": "баунти/хонора", "titles": "титулов"}

_SWORD_LADDER = (
    [("pulls", g) for g in (1, 5, 10, 25, 50, 100, 200)]
    + [("fruits", g) for g in (3, 6, 10, 15, 20, 25, 30, 35)]
    + [("pvp_wins", g) for g in (1, 3, 5, 10, 20, 35, 50, 75, 100, 150)]
    + [("pvp_streak", g) for g in (3, 5, 10)]
    + [("rep", g) for g in (5000, 25000, 100000, 500000, 1000000, 2500000)]
    + [("mastery", g) for g in (400, 1000, 2000)]
    + [("styles", g) for g in (2, 4, 6)]
)
_WEAPON_LADDER = (
    [("pulls", g) for g in (15, 30, 75)] + [("fruits", g) for g in (12, 18, 28)]
    + [("pvp_wins", g) for g in (2, 7, 15, 30, 60)] + [("rep", g) for g in (2000, 10000)]
    + [("titles", g) for g in (3, 6)] + [("days", 7)]
)
# титулы: (ключ, название, счётчик, цель, описание)
TITLES = [
    ("newbie", "Новичок", "pulls", 1, "Сделайте первую крутку"),
    ("lucky", "Везунчик", "pulls", 50, "50 круток гачи"),
    ("gambler", "Азартный", "pulls", 200, "200 круток гачи"),
    ("regular", "Постоянный", "days", 7, "Крутите гачу 7 разных дней"),
    ("fruit_hunter", "Охотник за фруктами", "fruits", 10, "10 разных фруктов"),
    ("collector", "Коллекционер", "fruits", 25, "25 разных фруктов"),
    ("completionist", "Полный набор", "fruits", 43, "Соберите все фрукты"),
    ("duelist", "Дуэлянт", "pvp_wins", 10, "10 побед в PvP"),
    ("champion", "Чемпион", "pvp_wins", 50, "50 побед в PvP"),
    ("legend", "Легенда", "pvp_wins", 150, "150 побед в PvP"),
    ("unbeaten", "Неудержимый", "pvp_streak", 10, "10 побед подряд"),
    ("warlord", "Полководец", "rep", 500000, "500 000 баунти/хонора"),
    ("style_master", "Мастер стилей", "mastery", 2000, "2000 суммарного мастери"),
    ("god_fist", "Кулак бога", "styles", 8, "Получите 8 стилей боя"),
]
# титулы без счётчика (выдаются событиями): Serpent Slayer — за убийство Левиафана с командой
SPECIAL_TITLES = [("serpent_slayer", "Serpent Slayer", "Убейте Левиафана с командой (заявка на Левиафана)")]


def _build():
    ach = []
    swords = [s for s in SWORDS if s[0] != CREATOR_SWORD]
    assert len(SWORDS) == 41 and len(swords) == len(_SWORD_LADDER), (len(SWORDS), len(_SWORD_LADDER))
    assert len(WEAPONS) == len(_WEAPON_LADDER), (len(WEAPONS), len(_WEAPON_LADDER))
    for (k, n), (c, g) in zip(swords, _SWORD_LADDER):
        ach.append({"key": f"sw_{k}", "name": f"Меч: {n}", "counter": c, "goal": g, "reward": ("sword", k)})
    for (k, n), (c, g) in zip(WEAPONS, _WEAPON_LADDER):
        ach.append({"key": f"wp_{k}", "name": f"Оружие: {n}", "counter": c, "goal": g, "reward": ("weapon", k)})
    for k, n, c, g, d in TITLES:
        ach.append({"key": f"tt_{k}", "name": f"Титул: {n}", "counter": c, "goal": g, "reward": ("title", k), "desc": d})
    return ach


ACHIEVEMENTS = _build()
TITLE_NAMES = {k: n for k, n, *_ in TITLES} | {k: n for k, n, _ in SPECIAL_TITLES}
