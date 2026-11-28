"""Данные мини-игр DuoSup (гача, PvP, комбо, крафты, достижения, титулы, магазин за Gram).
Редактируйте списки прямо здесь: названия, шансы, крафты, дропы с заявок, достижения, цены.
ВАЖНО: ключи (первое значение) не меняйте после запуска — по ним хранится инвентарь игроков."""

CREATOR_SWORD = "triple_dark_blade"  # выдаётся только создателю, получить его нельзя

# ---------- ФРУКТЫ (43). Ключ, английское название, русское название, редкость ----------
# Ключи совпадают с ключами эмодзи стока/трейдов (DEFAULT_FRUIT_EMOJI в app.py).
FRUITS = [
    ("rocket", "Rocket", "Ракета", "common"), ("spin", "Spin", "Вращение", "common"),
    ("blade", "Blade", "Лезвие", "common"), ("spring", "Spring", "Пружина", "common"),
    ("bomb", "Bomb", "Бомба", "common"), ("smoke", "Smoke", "Дым", "common"), ("spike", "Spike", "Шип", "common"),
    ("flame", "Flame", "Пламя", "uncommon"), ("ice", "Ice", "Лёд", "uncommon"), ("sand", "Sand", "Песок", "uncommon"),
    ("dark", "Dark", "Тьма", "uncommon"), ("eagle", "Eagle", "Орёл", "uncommon"), ("diamond", "Diamond", "Алмаз", "uncommon"),
    ("light", "Light", "Свет", "rare"), ("rubber", "Rubber", "Резина", "rare"), ("ghost", "Ghost", "Призрак", "rare"),
    ("magma", "Magma", "Лава", "rare"),
    ("quake", "Quake", "Дрожь", "legendary"), ("buddha", "Buddha", "Будда", "legendary"), ("love", "Love", "Любовь", "legendary"),
    ("creation", "Creation", "Создание", "legendary"), ("spider", "Spider", "Паук", "legendary"),
    ("sound", "Sound", "Звук", "legendary"), ("phoenix", "Phoenix", "Феникс", "legendary"),
    ("portal", "Portal", "Портал", "legendary"), ("lightning", "Lightning", "Молния", "legendary"),
    ("pain", "Pain", "Боль", "legendary"), ("blizzard", "Blizzard", "Метель", "legendary"),
    ("gravity", "Gravity", "Гравитация", "mythical"), ("mammoth", "Mammoth", "Мамонт", "mythical"),
    ("trex", "T-Rex", "Тираннозавр", "mythical"), ("dough", "Dough", "Тесто", "mythical"),
    ("shadow", "Shadow", "Тень", "mythical"), ("venom", "Venom", "Яд", "mythical"), ("gas", "Gas", "Газ", "mythical"),
    ("spirit", "Spirit", "Дух", "mythical"), ("tiger", "Tiger", "Тигр", "mythical"), ("yeti", "Yeti", "Йети", "mythical"),
    ("magnet", "Magnet", "Магнит", "mythical"), ("kitsune", "Kitsune", "Кицунэ", "mythical"),
    ("control", "Control", "Контроль", "mythical"),
    ("dragon_west", "Dragon West", "Дракон Западный", "mythical"), ("dragon_east", "Dragon East", "Дракон Восточный", "mythical"),
]
FRUIT_NAMES = {k: n for k, n, _r, _rar in FRUITS}
FRUIT_RU = {k: r for k, _n, r, _rar in FRUITS}
FRUIT_RARITY_OF = {k: rar for k, _n, _r, rar in FRUITS}
RARITY_RU = {"common": "Обычный", "uncommon": "Необычный", "rare": "Редкий", "legendary": "Легендарный", "mythical": "Мифический"}

# ---------- ГАЧА: шанс выпадения, % ----------
# Spider в списке шансов не было — поставлен 1.27% (как у Creation). Поменяйте, если нужно.
GACHA_CHANCE = {
    "rocket": 13.89, "spin": 11.58, "blade": 9.26, "spring": 8.10, "bomb": 6.95, "smoke": 5.79, "spike": 4.63,
    "eagle": 3.47, "flame": 3.47, "ice": 3.47, "sand": 2.89, "dark": 2.89, "diamond": 2.32, "light": 2.32,
    "rubber": 2.08, "ghost": 1.74, "magma": 1.74, "quake": 1.50, "buddha": 0.93, "love": 1.39, "creation": 1.27,
    "spider": 1.27, "sound": 1.16, "phoenix": 1.04, "portal": 0.81, "lightning": 0.81, "pain": 0.69, "blizzard": 0.69,
    "gravity": 0.58, "mammoth": 0.46, "trex": 0.41, "dough": 0.35, "shadow": 0.29, "venom": 0.23, "gas": 0.21,
    "spirit": 0.17, "tiger": 0.14, "yeti": 0.12, "magnet": 0.09, "control": 0.05, "kitsune": 0.01,
    "dragon_west": 0.001, "dragon_east": 0.001,
}
GACHA_COOLDOWN = 2 * 3600  # крутка раз в 2 часа

# ---------- МАГАЗИН ЗА GRAM (Permanent-фрукты). Цена в Gram ----------
TON_WALLET = "UQD_0O9OGyLdFLj7fVRekIE4nMioKT5zOW7cfQOycR5lZrGj"
SHOP = {  # ключ -> цена. set_common / set_uncommon — наборы всех фруктов этой редкости
    "set_common": 0.1, "set_uncommon": 0.1,
    "flame": 0.1, "ice": 0.1, "sand": 0.1, "dark": 0.1, "eagle": 0.1, "diamond": 0.1,
    "rubber": 0.1, "ghost": 0.1, "magma": 0.1, "quake": 0.1, "love": 0.1, "creation": 0.12, "sound": 0.15,
    "phoenix": 0.17, "pain": 0.18, "blizzard": 0.2, "gravity": 0.2, "lightning": 0.25, "portal": 0.3, "buddha": 0.3,
    "mammoth": 0.4, "shadow": 0.4, "control": 0.5, "venom": 0.5, "spirit": 0.6, "dough": 0.7, "trex": 0.7,
    "gas": 0.8, "yeti": 1.0, "tiger": 1.2, "kitsune": 1.5, "dragon_west": 1.5, "dragon_east": 1.5,
}
SHOP_SETS = {"set_common": ("COMMON SET", "common"), "set_uncommon": ("UNCOMMON SET", "uncommon")}

# ---------- МЕЧИ (39 + меч создателя). Ключ, название, сила (1–6) ----------
SWORDS = [
    ("boarding_saber", "Boarding Saber", 1), ("katana", "Katana", 1), ("dual_katana", "Dual Katana", 2),
    ("iron_mace", "Iron Mace", 2), ("shark_saw", "Shark Saw", 2), ("triple_katana", "Triple Katana", 3),
    ("twin_hooks", "Twin Hooks", 3), ("pipe", "Pipe", 1), ("dual_headed_blade", "Dual-Headed Blade", 2),
    ("soul_cane", "Soul Cane", 2), ("trident", "Trident", 2), ("wardens_sword", "Warden's Sword", 2),
    ("long_sword", "Longsword", 3), ("gravity_cane", "Gravity Cane", 3), ("flail", "Flail", 2),
    ("dragon_trident", "Dragon Trident", 3), ("bisento", "Bisento", 3), ("pole_1", "Pole (1st Form)", 3),
    ("saber", "Saber", 3), ("koko", "Koko", 4), ("midnight_blade", "Midnight Blade", 4), ("rengoku", "Rengoku", 4),
    ("saishi", "Saishi", 4), ("oroshi", "Oroshi", 4), ("shizu", "Shizu", 4), ("pole_2", "Pole (2nd Form)", 4),
    ("canvander", "Canvander", 4), ("buddy_sword", "Buddy Sword", 4), ("spikey_trident", "Spikey Trident", 4),
    ("shark_anchor", "Shark Anchor", 5), ("fox_lamp", "Fox Lamp", 5), ("dragonheart", "Dragonheart", 5),
    ("yama", "Yama", 5), ("tushita", "Tushita", 5), ("dark_dagger", "Dark Dagger", 5),
    ("true_triple_katana", "True Triple Katana", 6), ("hallow_scythe", "Hallow Scythe", 5),
    ("cursed_dual_katana", "Cursed Dual Katana", 6), ("dark_blade", "Dark Blade", 5),
    ("triple_dark_blade", "Triple Dark Blade", 7),
]

# ---------- ОРУЖИЯ (14). Ключ, название, сила (1–6) ----------
WEAPONS = [
    ("slingshot", "Slingshot", 1), ("musket", "Musket", 1), ("flintlock", "Flintlock", 2),
    ("refined_slingshot", "Refined Slingshot", 2), ("dual_flintlock", "Dual Flintlock", 3), ("cannon", "Cannon", 3),
    ("magma_blaster", "Magma Blaster", 4), ("acidum_rifle", "Acidum Rifle", 4), ("bizarre_revolver", "Bizarre Revolver", 4),
    ("bazooka", "Bazooka", 4), ("kabucha", "Kabucha", 5), ("serpent_bow", "Serpent Bow", 5),
    ("dragonstorm", "Dragonstorm", 6), ("skull_guitar", "Skull Guitar", 6),
]

# ---------- СТИЛИ БОЯ (13). Ключ, название, сила ----------
STYLES = [
    ("combat", "Combat", 1), ("dark_step", "Dark Step", 2), ("electric", "Electric", 2),
    ("water_kung_fu", "Water Kung Fu", 2), ("dragon_breath", "Dragon Breath", 2), ("death_step", "Death Step", 3),
    ("superhuman", "Superhuman", 4), ("electric_claw", "Electric Claw", 3), ("sharkman_karate", "Sharkman Karate", 3),
    ("dragon_talon", "Dragon Talon", 3), ("godhuman", "Godhuman", 6), ("sanguine_art", "Sanguine Art", 6),
    ("advanced_combat", "Advanced Combat", 5),
]
BASE_STYLE = "combat"  # даётся всем сразу
MASTERY_MAX = 600
PVP_MASTERY = (10, 30)  # мастери за PvP на каждый предмет комбо

# ---------- ПРЕДМЕТЫ ----------
ITEMS = {"leviathan_heart": "Сердце Левиафана"}

# ---------- КРАФТЫ. Ключ = (вид, ключ результата) ----------
# items: нужные предметы [(вид, ключ | "a|b" — любой из)], mastery: [(вид, ключ, мастери)],
# title: нужный титул, heart: сколько сердец Левиафана тратится, helped: ивенты, на которые надо помочь,
# once: скрафтить можно 1 раз навсегда
ADV_HELPS = ["terror", "volcano", "leviathan", "mirage", "seabeast", "kitsune", "ship", "rip", "doughking",
             "reaper", "tyrant", "blackbeard", "law", "trial", "raid"]
CRAFTS = {
    # стили боя V1: прокачка Combat
    ("style", "dark_step"): {"mastery": [("style", "combat", 100)]},
    ("style", "electric"): {"mastery": [("style", "combat", 200)]},
    ("style", "water_kung_fu"): {"mastery": [("style", "combat", 300)]},
    ("style", "dragon_breath"): {"mastery": [("style", "combat", 400)]},
    # V2: V1 на 400 мастери
    ("style", "death_step"): {"mastery": [("style", "dark_step", 400)]},
    ("style", "electric_claw"): {"mastery": [("style", "electric", 400)]},
    ("style", "sharkman_karate"): {"mastery": [("style", "water_kung_fu", 400)]},
    ("style", "dragon_talon"): {"mastery": [("style", "dragon_breath", 400)]},
    ("style", "superhuman"): {"mastery": [("style", "dark_step", 400), ("style", "electric", 400),
                                          ("style", "water_kung_fu", 400), ("style", "dragon_breath", 400)]},
    ("style", "godhuman"): {"mastery": [("style", "death_step", 400), ("style", "superhuman", 400),
                                        ("style", "electric_claw", 400), ("style", "sharkman_karate", 400),
                                        ("style", "dragon_talon", 400)]},
    ("style", "sanguine_art"): {"heart": 1, "once": True},
    ("style", "advanced_combat"): {"helped": ADV_HELPS},
    # мечи
    ("sword", "dual_katana"): {"mastery": [("sword", "katana", 300)]},
    ("sword", "triple_katana"): {"mastery": [("sword", "dual_katana", 400)]},
    ("sword", "pole_2"): {"mastery": [("sword", "pole_1", 400)]},
    ("sword", "true_triple_katana"): {"mastery": [("sword", "saishi", 300), ("sword", "shizu", 300), ("sword", "oroshi", 300)]},
    ("sword", "cursed_dual_katana"): {"mastery": [("sword", "yama", 400), ("sword", "tushita", 400)]},
    # оружия
    ("weapon", "refined_slingshot"): {"mastery": [("weapon", "slingshot", 400)]},
    ("weapon", "dual_flintlock"): {"mastery": [("weapon", "flintlock", 400)]},
    ("weapon", "dragonstorm"): {"mastery": [("sword", "dragonheart", 300), ("sword", "dragon_trident", 300)]},
    ("weapon", "skull_guitar"): {"title": "sea_hunter", "mastery": [("sword", "soul_cane", 400)]},
}

# ---------- ДРОП С ЗАЯВОК. Ключ ивента -> [(вид, ключ, шанс от %, до %)] ----------
# Помощник получает шанс, когда заявка завершается (не раньше чем через APP_MIN_AGE после создания).
# Шанс каждый раз случайный в пределах «от–до». Не выпало — бот ничего не пишет.
# raid — любой рейд, trial — любой триал.
DROPS = {
    "terror": [("sword", "shark_anchor", 5, 10)],
    "seabeast": [("sword", "shark_saw", 8, 15)],
    "volcano": [("sword", "dragon_trident", 6, 12), ("sword", "dragonheart", 2, 6), ("weapon", "magma_blaster", 5, 12)],
    "kitsune": [("sword", "fox_lamp", 5, 12)],
    "mirage": [("sword", "shizu", 3, 8)],
    "ship": [("sword", "midnight_blade", 5, 12), ("sword", "saishi", 3, 8)],
    "leviathan": [("weapon", "serpent_bow", 5, 12)],
    "rip": [("sword", "dark_dagger", 5, 10), ("sword", "tushita", 3, 8)],
    "doughking": [("sword", "spikey_trident", 5, 15), ("sword", "buddy_sword", 5, 12)],
    "reaper": [("sword", "hallow_scythe", 5, 15)],
    "tyrant": [("sword", "gravity_cane", 5, 12)],
    "blackbeard": [("sword", "twin_hooks", 8, 15), ("sword", "oroshi", 3, 8)],
    "law": [("sword", "koko", 5, 12)],
    "raid": [("weapon", "kabucha", 5, 12)],
    "trial": [("weapon", "acidum_rifle", 5, 12)],
}
APP_MIN_AGE = 10 * 60  # заявка, завершённая быстрее 10 минут, наград не даёт (защита от накрутки)
# Сердце Левиафана: в заявке (автор + помощники) должно быть не меньше 5 человек.
# Каждый бросает шанс 5–25%; если выпало хоть у одного — сердце получает вся группа.
HEART_MIN_GROUP = 5
HEART_CHANCE = (5, 25)

# ---------- СЧЁТЧИКИ ----------
COUNTER_RU = {
    "pulls": "круток гачи", "days": "дней с круткой", "fruits": "разных фруктов", "styles": "стилей боя",
    "mastery": "суммарного мастери", "pvp_games": "PvP-боёв", "pvp_wins": "побед в PvP",
    "pvp_best_streak": "побед подряд", "rep": "баунти/хонора", "titles": "титулов", "helps": "помощи по заявкам",
    "sea_helps": "помощи с морскими ивентами", "event_helps": "помощи с ивентами", "hearts_got": "сердец Левиафана",
}

# ---------- ДОСТИЖЕНИЯ: (счётчик, цель) -> награда ----------
ACH_ITEMS = [
    ("sword", "boarding_saber", "helps", 1), ("sword", "katana", "pvp_games", 1),
    ("sword", "iron_mace", "pvp_wins", 3), ("sword", "pipe", "pulls", 10),
    ("sword", "dual_headed_blade", "pvp_wins", 10), ("sword", "soul_cane", "helps", 15),
    ("sword", "trident", "sea_helps", 5), ("sword", "wardens_sword", "pvp_games", 25),
    ("sword", "long_sword", "days", 7), ("sword", "flail", "fruits", 10),
    ("sword", "bisento", "rep", 5_000_000), ("sword", "pole_1", "pvp_wins", 25),
    ("sword", "saber", "event_helps", 5), ("sword", "rengoku", "pvp_best_streak", 5),
    ("sword", "canvander", "rep", 10_000_000), ("sword", "yama", "mastery", 3000),
    ("sword", "dark_blade", "pvp_wins", 100),
    ("weapon", "slingshot", "pvp_games", 3), ("weapon", "musket", "pulls", 25),
    ("weapon", "flintlock", "pvp_wins", 5), ("weapon", "cannon", "sea_helps", 15),
    ("weapon", "bizarre_revolver", "helps", 50), ("weapon", "bazooka", "pvp_wins", 50),
]

# ---------- ТИТУЛЫ: (ключ, название, счётчик, цель, описание) ----------
TITLES = [
    ("newbie", "Новичок", "pulls", 1, "Сделайте первую крутку"),
    ("regular", "Постоянный", "days", 7, "Крутите гачу 7 разных дней"),
    ("lucky", "Везунчик", "pulls", 50, "50 круток гачи"),
    ("fruit_hunter", "Охотник за фруктами", "fruits", 15, "15 разных фруктов"),
    ("collector", "Коллекционер", "fruits", 30, "30 разных фруктов"),
    ("completionist", "Полный набор", "fruits", 43, "Соберите все 43 фрукта"),
    ("helper", "Помощник", "helps", 10, "Помогите с 10 заявками"),
    ("sea_hunter", "Sea Hunter", "sea_helps", 30, "Помогите с 30 любыми морскими ивентами"),
    ("boss_hunter", "Охотник на боссов", "event_helps", 30, "Помогите с 30 ивентами"),
    ("serpent_slayer", "Serpent Slayer", "hearts_got", 1, "Добудьте сердце Левиафана"),
    ("duelist", "Дуэлянт", "pvp_wins", 10, "10 побед в PvP"),
    ("champion", "Чемпион", "pvp_wins", 50, "50 побед в PvP"),
    ("legend", "Легенда", "pvp_wins", 150, "150 побед в PvP"),
    ("unbeaten", "Неудержимый", "pvp_best_streak", 10, "10 побед подряд"),
    ("warlord", "Полководец", "rep", 20_000_000, "20 000 000 баунти/хонора"),
    ("style_master", "Мастер стилей", "mastery", 5000, "5000 суммарного мастери"),
    ("god_fist", "Кулак бога", "styles", 13, "Соберите все 13 стилей боя"),
]
TITLE_NAMES = {k: n for k, n, *_ in TITLES}

# ---------- PvP ----------
PVP_HP = 15000
PVP_ENERGY = 15000
REP_START = 2_500_000
REP_MAX = 30_000_000
PVP_POINTS_MAX = 3          # очков кулдауна на пару игроков
PVP_POINT_DECAY = 24 * 3600  # одно очко спадает за 24 часа
PVP_CMD_COOLDOWN = 10 * 60   # !пвп — раз в 10 минут
PVP_WAIT = 10 * 60           # комната ждёт соперника 10 минут
PVP_TURN = 120               # на ход — 2 минуты, иначе поражение
STAT_LEVEL = 2800            # максимальный уровень и максимум одной характеристики
STAT_CHOICES = {"fruit": "Фрукт", "sword": "Меч", "weapon": "Оружие"}
# действие: (энергия, базовый урон за 1 «силу» предмета, урон при силе 0)
PVP_ACTIONS = {"style": (1200, 200, 1500), "fruit": (2600, 230, 1500), "sword": (1800, 210, 1450), "weapon": (1500, 200, 1400)}
PVP_REST = 4500  # «Отдышаться» — восстановить энергию
FRUIT_POWER = {"common": 1, "uncommon": 2, "rare": 3, "legendary": 4, "mythical": 6}


def _build():
    """Плоский список достижений (мечи/оружия/титулы) — для проверки и показа."""
    names = {"sword": {k: n for k, n, _ in SWORDS}, "weapon": {k: n for k, n, _ in WEAPONS}}
    ach = []
    for kind, key, c, g in ACH_ITEMS:
        pre = "sw" if kind == "sword" else "wp"
        ach.append({"key": f"{pre}_{key}", "name": f"{'Меч' if kind == 'sword' else 'Оружие'}: {names[kind][key]}",
                    "counter": c, "goal": g, "reward": (kind, key)})
    for k, n, c, g, d in TITLES:
        ach.append({"key": f"tt_{k}", "name": f"Титул: {n}", "counter": c, "goal": g, "reward": ("title", k), "desc": d})
    return ach


ACHIEVEMENTS = _build()


def _check():
    assert len(FRUITS) == 43, len(FRUITS)
    assert set(GACHA_CHANCE) == {k for k, *_ in FRUITS}
    assert len(SWORDS) == 40 and len(WEAPONS) == 14 and len(STYLES) == 13
    keys = {("sword", k) for k, *_ in SWORDS} | {("weapon", k) for k, *_ in WEAPONS} | {("style", k) for k, *_ in STYLES}
    got = set(CRAFTS) | {(k, x) for k, x, *_ in ACH_ITEMS} | {(k, x) for v in DROPS.values() for k, x, *_ in v}
    got |= {("sword", CREATOR_SWORD), ("style", BASE_STYLE)}
    missing = keys - got
    assert not missing, f"нет способа получения: {missing}"
    for k in SHOP:
        assert k in SHOP_SETS or k in FRUIT_NAMES, k


_check()
