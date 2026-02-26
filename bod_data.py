# bod_data.py

# --- Reward Names ---
prize_names = {
    # Smithy
    1: "Durable Pick / Shovel",
    2: "Durable Pick / Shovel (90); +1 MGloves (10)",
    3: "GargoyleP (45); Prospector (45); +3 MGloves (10)",
    4: "GargoyleP (40); Prospector (40); POF (20)",
    5: "POF (90); +5 Mining Gloves (10)",
    6: "D.C Runic",
    7: "D.C Runic (60); Shadow Runic (40)",
    8: "Shadow Runic",
    9: "105 SOP (60); Shadow Runic (30); Ore Anvil (10)",
    10: "Copper Runic",
    11: "110 SOP (60); Copper Runic (30); Ore Anvil (10)",
    12: "Bronze Runic",
    13: "+10 Ancient Smith's Hammer",
    14: "115 Power Scroll",
    15: "+15 Ancient Smith's Hammer",
    16: "120 Power Scroll",
    17: "Golden Runic",
    18: "+30 Ancient Smith's Hammer",
    19: "Agapite Runic",
    20: "+60 Ancient Smith's Hammer",
    21: "Verite Runic",
    22: "Valorite Runic",
    
    # Tailor (Target Rewards)
    23: "Clothing Bless Deed",
    24: "Barbed Runic Kit"
}

# --- Prize Logic ---
prize_pattern = {
    # TAILORING (Specific Targets)
    "Male Leather Set": {
        "Normal": {
            "Leather": {20: 23}  # <--- NEW: Large Normal Leather 20 = CBD
        },
        "Exceptional": {
            "Spined": {20: 24}, # Barbed Kit
            "Horned": {10: 24, 15: 24, 20: 24},
            "Barbed": {10: 24, 15: 24, 20: 24}
        }
    },
    "Female Leather Set": {
        "Normal": {
            "Leather": {20: 23}  # <--- NEW: Large Normal Leather 20 = CBD
        },
        "Exceptional": {
            "Spined": {20: 24}, # Barbed Kit
            "Horned": {10: 24, 15: 24, 20: 24},
            "Barbed": {10: 24, 15: 24, 20: 24}
        }
    },
    "Studded Set": {
        "Exceptional": {
            "Leather": {20: 23}, # CBD
            "Spined":  {10: 23}, # CBD
            "Horned":  {20: 24},
            "Barbed":  {20: 24}
        }
    },
    "Town Crier Set": {
        "Exceptional": {
            "Cloth": {20: 23},    # CBD
            "Leather": {20: 23}
        }
    },
    
    # BLACKSMITHY (Originals Preserved)
    "Ringmail": {
        "Normal": {"Dull Copper": {10:4,15:4,20:5}, "Shadow Iron": {10:5,15:5,20:6}, "Copper": {10:6,15:6,20:7}, "Bronze": {10:7,15:7,20:8}, "Gold": {10:8,15:9,20:10}, "Agapite": {10:10,15:10,20:11}, "Verite": {10:12,15:12,20:13}, "Valorite": {10:13,15:13,20:14}},
        "Exceptional": {"Dull Copper": {10:8,15:9,20:10}, "Shadow Iron": {10:10,15:11,20:12}, "Copper": {10:12,15:12,20:13}, "Bronze": {10:13,15:13,20:14}, "Gold": {10:14,15:14,20:15}, "Agapite": {10:15,15:15,20:16}, "Verite": {10:16,15:16,20:17}, "Valorite": {10:17,15:17,20:18}}
    },
    "Chainmail": {
        "Normal": {"Dull Copper": {10:6,15:6,20:7}, "Shadow Iron": {10:7,15:7,20:8}, "Copper": {10:8,15:9,20:10}, "Bronze": {10:10,15:11,20:12}, "Gold": {10:12,15:12,20:13}, "Agapite": {10:13,15:13,20:14}, "Verite": {10:14,15:14,20:15}, "Valorite": {10:15,15:15,20:16}},
        "Exceptional": {"Dull Copper": {10:12,15:12,20:13}, "Shadow Iron": {10:13,15:13,20:14}, "Copper": {10:14,15:14,20:15}, "Bronze": {10:15,15:15,20:16}, "Gold": {10:16,15:16,20:17}, "Agapite": {10:17,15:17,20:18}, "Verite": {10:18,15:18,20:19}, "Valorite": {10:19,15:19,20:20}}
    },
    "Platemail": {
        "Normal": {"Dull Copper": {10:8,15:9,20:10}, "Shadow Iron": {10:10,15:11,20:12}, "Copper": {10:12,15:12,20:13}, "Bronze": {10:13,15:13,20:14}, "Gold": {10:14,15:14,20:15}, "Agapite": {10:15,15:15,20:16}, "Verite": {10:16,15:16,20:17}, "Valorite": {10:17,15:17,20:18}},
        "Exceptional": {"Dull Copper": {10:14,15:14,20:15}, "Shadow Iron": {10:15,15:15,20:16}, "Copper": {10:16,15:16,20:17}, "Bronze": {10:17,15:17,20:18}, "Gold": {10:18,15:18,20:19}, "Agapite": {10:19,15:19,20:20}, "Verite": {10:20,15:20,20:21}, "Valorite": {10:21,15:21,20:22}}
    },
    "Small Bods": { "Normal": {}, "Exceptional": {} }
}

# --- Component Lists ---
LARGE_COMPONENTS = {
    # Target Sets
    # NOTE: "leather armor" removed from Male set components as it is the name of the Large BOD only
    "Male Leather Set": ["leather gorget", "leather cap", "leather sleeves", "leather gloves", "leather leggings", "leather tunic"],
    "Female Leather Set": ["leather skirt", "leather bustier", "leather shorts", "female leather armor", "studded armor", "studded bustier"],
    "Studded Set": ["studded gorget", "studded gloves", "studded sleeves", "studded leggings", "studded tunic"],
    "Town Crier Set": ["feathered hat", "surcoat", "fancy shirt", "short pants", "thigh boots"],
    
    # Generic / Ignored Sets
    "Footwear Set": ["sandals", "shoes", "boots", "thigh boots"],
    "Ringmail": ["ringmail gloves", "ringmail tunic", "ringmail sleeves", "ringmail leggings"],
    "Chainmail": ["chainmail coif", "chainmail tunic", "chainmail leggings"],
    "Platemail": ["platemail gloves", "platemail arms", "platemail tunic", "platemail legs", "plate helm", "platemail gorget"]
}

def normalize_material(material):
    material = material.lower().strip()
    if "dull copper" in material: return "Dull Copper"
    elif "shadow iron" in material: return "Shadow Iron"
    elif "copper" in material: return "Copper"
    elif "bronze" in material: return "Bronze"
    elif "gold" in material: return "Gold"
    elif "agapite" in material: return "Agapite"
    elif "verite" in material: return "Verite"
    elif "valorite" in material: return "Valorite"
    elif "cloth" in material: return "Cloth"
    elif "leather" in material: return "Leather"
    elif "spined" in material: return "Spined"
    elif "horned" in material: return "Horned"
    elif "barbed" in material: return "Barbed"
    elif "bone" in material: return "Leather"
    else: return "Iron"

def categorize_items(item):
    name = item.lower().strip()
    
    # Special Case: "leather armor" is the name of the Large BOD for Male set
    if name == "leather armor":
        return "Male Leather Set"

    # Check Sets
    for set_name, components in LARGE_COMPONENTS.items():
        if name in [c.lower() for c in components]:
            return set_name
            
    # Fallback
    if "ringmail" in name: return "Ringmail"
    if "chainmail" in name: return "Chainmail"
    if "platemail" in name or "plate helm" in name: return "Platemail"
    return "Small Bods"

def get_prize_number(category, material, quantity, quality):
    try:
        return prize_pattern[category][quality][material][quantity]
    except KeyError:
        return None

def compute_large_fill_capacity(bods):
    smalls = [b for b in bods if b['type'].lower() == 'small']
    larges = [b for b in bods if b['type'].lower() == 'large']
    from collections import defaultdict
    small_inventory = defaultdict(int)
    for s in smalls:
        key = (s['item'], s['material'], s['quality'], s['amount'])
        small_inventory[key] += 1

    report = []
    for l in larges:
        l_item = l['item'].lower()
        comp_key = None
        
        # Special case for Male Large Name
        if l_item == "leather armor":
            comp_key = "Male Leather Set"
        else:
            for set_name, components in LARGE_COMPONENTS.items():
                 if l_item in [c.lower() for c in components]:
                     comp_key = set_name
                     break
        
        if not comp_key: continue
            
        components = LARGE_COMPONENTS[comp_key]
        missing = []
        for c in components:
            key = (c.lower(), l['material'], l['quality'], l['amount'])
            if small_inventory[key] > 0: pass 
            else: missing.append(c)
        
        report.append({
            "large_name": l['item'],
            "material": l['material'],
            "quality": l['quality'],
            "prize_id": l.get('prize_id'),
            "can_fill": (len(missing) == 0),
            "missing": missing
        })
    return report