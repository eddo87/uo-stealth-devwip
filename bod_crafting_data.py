# SMART TAILORING DICTIONARY: Name: (CategoryCraftButton, ItemCraftButton, GraphicID, ResourceCost, Material)
TAILOR_ITEMS = {
    "bandana": (8, 9, 0x1540, 2, "cloth"),
    "skullcap": (8, 2, 0x1544, 2, "cloth"),
    "floppy hat": (8, 16, 0x1713, 11, "cloth"),
    "cap": (8, 23, 0x1715, 11, "cloth"),
    "wide-brim hat": (8, 30, 0x1714, 14, "cloth"),
    "straw hat": (8, 37, 0x1717, 10, "cloth"),
    "tall straw hat": (8, 44, 0x1716, 10, "cloth"),
    "wizard's hat": (8, 51, 0x1718, 15, "cloth"),
    "bonnet": (8, 58, 0x1719, 11, "cloth"),
    "feathered hat": (8, 65, 0x171A, 14, "cloth"),
    "tricorne hat": (8, 72, 0x171B, 12, "cloth"),
    "jester hat": (8, 79, 0x171C, 15, "cloth"),
    "doublet": (15, 2, 0x1F7B, 8, "cloth"),
    "shirt": (15, 9, 0x1517, 8, "cloth"),
    "fancy shirt": (15, 16, 0x1EFD, 8, "cloth"),
    "tunic": (15, 23, 0x1FA1, 12, "cloth"),
    "surcoat": (15, 30, 0x1FFD, 14, "cloth"),
    "plain dress": (15, 37, 0x1F01, 10, "cloth"),
    "fancy dress": (15, 44, 0x1F00, 12, "cloth"),
    "cloak": (15, 51, 0x1515, 14, "cloth"),
    "robe": (15, 58, 0x1F03, 16, "cloth"),
    "jester suit": (15, 65, 0x1F9F, 24, "cloth"),
    "short pants": (15, 177, 0x152E, 6, "cloth"),
    "long pants": (15, 184, 0x1539, 8, "cloth"),
    "kilt": (15, 191, 0x1537, 8, "cloth"),
    "skirt": (15, 198, 0x1516, 10, "cloth"),
    "body sash": (22, 2, 0x1541, 4, "cloth"),
    "half apron": (22, 9, 0x153B, 6, "cloth"),
    "full apron": (22, 16, 0x153D, 10, "cloth"),
    "sandals": (29, 30, 0x170D, 4, "leather"),
    "shoes": (29, 37, 0x170F, 6, "leather"),
    "boots": (29, 44, 0x170B, 8, "leather"),
    "thigh boots": (29, 51, 0x1711, 10, "leather"),
    "leather gorget": (36, 23, 0x13C7, 4, "leather"),
    "leather cap": (36, 30, 0x1DB9, 2, "leather"),
    "leather gloves": (36, 37, 0x13C6, 3, "leather"),
    "leather sleeves": (36, 44, 0x13C5, 4, "leather"),
    "leather leggings": (36, 51, 0x13CB, 10, "leather"),
    "leather tunic": (36, 58, 0x13CC, 12, "leather"),
    "leather skirt": (57, 9, 0x1C08, 10, "leather"),
    "leather bustier": (57, 16, 0x1C0A, 8, "leather"),
    "leather shorts": (57, 2, 0x1C00, 8, "leather"),
    "female leather armor": (57, 30, 0x1C06, 12, "leather"),
    "studded gorget": (50, 2, 0x13D6, 6, "leather"),
    "studded gloves": (50, 9, 0x13D5, 8, "leather"),
    "studded sleeves": (50, 16, 0x13D4, 10, "leather"),
    "studded leggings": (50, 23, 0x13DA, 12, "leather"),
    "studded tunic": (50, 30, 0x13DB, 14, "leather"),
    "studded bustier": (57, 23, 0x1C0C, 10, "leather"),
    "studded armor": (57, 37, 0x1C02, 14, "leather"),
    "bone helmet": (64, 2, 0x141B, 4, "bone"),
    "bone gloves": (64, 9, 0x1417, 3, "bone"),
    "bone arms": (64, 16, 0x141D, 4, "bone"),
    "bone leggings": (64, 23, 0x141E, 10, "bone"),
    "bone armor": (64, 64, 0x1411, 12, "bone"),
}

# BLACKSMITHING DICTIONARY: Name: (CategoryCraftButton, ItemCraftButton, GraphicID, ResourceCost, "iron")
#
# CategoryCraftButton / ItemCraftButton are PLACEHOLDERS (0, 0) until confirmed in-game
# via BodCycler_GumpDebug.py. Everything else (graphic IDs, costs) is from standard UO data.
#
# Resource costs are in ingots. Material type is always "iron" — the specific ore variant
# (dull copper, shadow iron, etc.) is read from the BOD tooltip at runtime via parse_bod().
#
# PRIORITY GROUPS (fill button IDs in this order):
#   P1 — Prize sets  : Ringmail, Chainmail, Platemail (needed for Large BOD assembly)
#   P2 — Prize smalls: bascinet, norse helm, female plate, buckler, bronze shield
#                      (yield runic hammers when filled exceptional+colored)
#   P3 — Junk smalls : mace, maul, dagger, kite shields, metal shield
#                      (no prize value — route to Scartare; button IDs optional)
SMITH_ITEMS = {
    # ── P1: Ringmail set (Metal Armor cat=1, page 1, items 1–4) ──────────────
    "ringmail gloves":      (1, 2,  0x13EB, 10,  "iron"),
    "ringmail leggings":    (1, 9,  0x13F0, 14, "iron"),
    "ringmail sleeves":     (1, 16, 0x13EF, 14, "iron"),
    "ringmail tunic":       (1, 23, 0x13EC, 14, "iron"),
    # ── P1: Chainmail set (Metal Armor cat=1, page 1, items 5–7) ─────────────
    "chainmail coif":       (1, 30, 0x13BB, 10,  "iron"),
    "chainmail leggings":   (1, 37, 0x13BE, 16, "iron"),
    "chainmail tunic":      (1, 44, 0x13BF, 20, "iron"),
    # ── P1: Platemail set (Metal Armor cat=1, pages 1–2, items 8–14) ─────────
    "platemail arms":       (1, 51, 0x1410, 18, "iron"),
    "platemail gloves":     (1, 58, 0x1414, 12, "iron"),
    "platemail gorget":     (1, 65, 0x1413, 10, "iron"),  # item 10, page 1
    "platemail legs":       (1, 72, 0x1411, 18, "iron"),  # item 11, page 2
    "platemail tunic":      (1, 79, 0x1415, 26, "iron"),  # item 12, page 2
    # ── P2: Prize-eligible standalone smalls ─────────────────────────────────
    # Exceptional + colored ore → yields runic hammer prizes
    "female plate":         (1, 86, 0x1C04, 20, "iron"),  # item 13 (Metal Armor, page 2, last)
    "bascinet":             (8, 2,  0x140C, 15, "iron"),
    "close helmet":         (8, 9,  0x1408, 15, "iron"),
    "norse helm":           (8, 23, 0x140E, 10, "iron"),
    "plate helm":           (8, 30, 0x1412, 15, "iron"),
    "buckler":              (15, 2,  0x1B73, 10, "iron"),
    "bronze shield":        (15, 9,  0x1B72, 10, "iron"),
    # ── P3: Junk smalls (recognized for routing; button IDs optional) ─────────
    # Items below never yield prizes — they go to Scartare when not exceptional iron.
    # Fill button IDs only if you want the bot to actively craft them.
    "heater shield":        (15, 16, 0x1B76, 12, "iron"),
    "metal shield":         (15, 23, 0x1B7B, 14, "iron"),
    "metal kite shield":    (15, 30, 0x1B74, 20, "iron"),
    "tear kite shield":     (15, 37, 0x1B78, 20, "iron"),
    # ── Axes (cat=22) ─────────────────────────────────────────────────────────
    "battle axe":           (22, 9,  0x0F47, 13, "iron"),
    # ── Bladed weapons (cat=29) ───────────────────────────────────────────────
    "bone harvester":       (29, 2,  0x26BB, 10, "iron"),
    "broadsword":           (29, 9,  0x0F5E, 10, "iron"),
    "crescent blade":       (29, 16, 0x26C1, 12, "iron"),
    "cutlass":              (29, 23, 0x1441, 8,  "iron"),
    "dagger":               (29, 30, 0x0F51, 3,  "iron"),
    "katana":               (29, 37, 0x13FF, 8,  "iron"),
    "kryss":                (29, 44, 0x1401, 4,  "iron"),
    "longsword":            (29, 51, 0x0F61, 12, "iron"),
    "scimitar":             (29, 58, 0x13B6, 8,  "iron"),
    "viking sword":         (29, 65, 0x13B9, 15, "iron"),
    # ── Bashing (cat=50) ──────────────────────────────────────────────────────
    "mace":                 (50, 9,  0x0F5C, 6,  "iron"),
    "maul":                 (50, 16, 0x143B, 14, "iron"),
    "war hammer":           (50, 37, 0x1439, 17, "iron"),
    # ── Polearms (cat=57) ─────────────────────────────────────────────────────
    "spear":                (57, 51, 0x0F62, 6,  "iron"),
}

MATERIAL_MAP = {
    "iron": {"types": [0x1BF2], "color": 0x0000, "btn": 6},
    "dull copper": {"types": [0x1BF2], "color": 0x0973, "btn": 13},
    "shadow iron": {"types": [0x1BF2], "color": 0x0966, "btn": 20},
    "copper": {"types": [0x1BF2], "color": 0x096D, "btn": 27},
    "bronze": {"types": [0x1BF2], "color": 0x0972, "btn": 34},
    "gold": {"types": [0x1BF2], "color": 0x08A5, "btn": 41},
    "agapite": {"types": [0x1BF2], "color": 0x0979, "btn": 48},
    "verite": {"types": [0x1BF2], "color": 0x089F, "btn": 55},
    "valorite": {"types": [0x1BF2], "color": 0x08AB, "btn": 62},
    
    "cloth": {"types": [0x1766, 0x1767], "color": -1, "btn": 6},
    "leather": {"types": [0x1081], "color": 0x0000, "btn": 6},
    "spined": {"types": [0x1081], "color": 0x08AC, "btn": 13},
    "horned": {"types": [0x1081], "color": 0x0845, "btn": 20},
    "barbed": {"types": [0x1081], "color": 0x0851, "btn": 27},
    "bone": {"types": [0x0F7E], "color": -1, "btn": None}
}