# SMART TAILORING DICTIONARY: Name -> (CategoryName, ItemName, GraphicID, ResourceCost)
# Updated with the latest shard-specific Hex IDs provided by the user
TAILOR_ITEMS = {
    "bandana": ("Hats", "bandana", 0x1540, 2),
    "skullcap": ("Hats", "skullcap", 0x1544, 2),
    "floppy hat": ("Hats", "floppy hat", 0x1713, 11),
    "cap": ("Hats", "cap", 0x1715, 11),
    "wide-brim hat": ("Hats", "wide-brim hat", 0x1714, 14),
    "straw hat": ("Hats", "straw hat", 0x1717, 10),
    "tall straw hat": ("Hats", "tall straw hat", 0x1716, 10),
    "wizard's hat": ("Hats", "wizard's hat", 0x1718, 15),
    "bonnet": ("Hats", "bonnet", 0x1719, 11),
    "feathered hat": ("Hats", "feathered hat", 0x171A, 14),
    "tricorne hat": ("Hats", "tricorne hat", 0x171B, 12),
    "jester hat": ("Hats", "jester hat", 0x171C, 15),

    "doublet": ("Shirts", "doublet", 0x1F7B, 8),
    "shirt": ("Shirts", "shirt", 0x1559, 8),
    "fancy shirt": ("Shirts", "fancy shirt", 0x1EBF, 8),
    "tunic": ("Shirts", "tunic", 0x1FA1, 12),
    "surcoat": ("Shirts", "surcoat", 0x1FFD, 14),
    "plain dress": ("Shirts", "plain dress", 0x1F01, 10),
    "fancy dress": ("Shirts", "fancy dress", 0x1F4C, 12),
    "cloak": ("Shirts", "cloak", 0x1557, 14),
    "robe": ("Shirts", "robe", 0x1F4D, 16),
    "jester suit": ("Shirts", "jester suit", 0x1F9F, 24),

    "short pants": ("Pants", "short pants", 0x1572, 6),
    "long pants": ("Pants", "long pants", 0x1583, 8),
    "kilt": ("Pants", "kilt", 0x1579, 8),
    "skirt": ("Pants", "skirt", 0x155A, 10),

    "body sash": ("Miscellaneous", "body sash", 0x1541, 4),
    "half apron": ("Miscellaneous", "half apron", 0x1585, 6),
    "full apron": ("Miscellaneous", "full apron", 0x157F, 10),

    "sandals": ("Footwear", "sandals", 0x174F, 4),
    "shoes": ("Footwear", "shoes", 0x1751, 6),
    "boots": ("Footwear", "boots", 0x170B, 8), 
    "thigh boots": ("Footwear", "thigh boots", 0x175B, 10),
    "tight boots": ("Footwear", "thigh boots", 0x175B, 10),

    "leather gorget": ("Leather Armor", "leather gorget", 0x1389, 4),
    "leather cap": ("Leather Armor", "leather cap", 0x1E03, 2),
    "leather gloves": ("Leather Armor", "leather gloves", 0x138A, 3),
    "leather sleeves": ("Leather Armor", "leather sleeves", 0x1387, 4),
    "leather leggings": ("Leather Armor", "leather leggings", 0x1395, 10),
    "leather tunic": ("Leather Armor", "leather tunic", 0x1390, 12),
    "leather skirt": ("Female Armor", "leather skirt", 0x1C54, 10),
    "leather bustier": ("Female Armor", "leather bustier", 0x1C56, 8),
    "leather shorts": ("Female Armor", "leather shorts", 0x1C4C, 8),
    "female leather armor": ("Female Armor", "female leather armor", 0x1C4A, 12),

    "studded gorget": ("Studded Armor", "studded gorget", 0x139A, 6),
    "studded gloves": ("Studded Armor", "studded gloves", 0x1397, 8),
    "studded sleeves": ("Studded Armor", "studded sleeves", 0x1398, 10),
    "studded leggings": ("Studded Armor", "studded leggings", 0x13A6, 12),
    "studded tunic": ("Studded Armor", "studded tunic", 0x13A5, 14),
    "studded bustier": ("Female Armor", "studded bustier", 0x1C50, 10),
    "studded armor": ("Female Armor", "studded armor", 0x1C4E, 14),

    "bone helmet": ("Bone Armor", "bone helmet", 0x141B, 4),
    "bone gloves": ("Bone Armor", "bone gloves", 0x1417, 3),
    "bone arms": ("Bone Armor", "bone arms", 0x141D, 4),
    "bone leggings": ("Bone Armor", "bone leggings", 0x141E, 10),
    "bone armor": ("Bone Armor", "bone armor", 0x1411, 12)
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