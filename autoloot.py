from py_stealth import *
import os
import json
from Utilities import *
from tkinter import *

#############
# Globals
#############
LOOT_GOLD = False
LOOT_SCROLLS = False
LOOT_MAPS = False
LOOT_GEMS = False
LOOT_REAGENTS = False
LOOT_AMMO = False
LOOT_SOLEN = False
LOOT_JUKA = False
LOOT_KEYS = False
LOOT_RESOURCES = True
CUT_CORPSE = True
LOOT_INSTRUMENTS = False
LOOT_ARMOR = False
LOOT_WEAPONS = False
LOOT_JEWELS = False
LOOT_SHIELDS = False
LOOT_SETS = False
LOOT_ARTIFACTS = False
LOOT_RATING = 0
LOOT_GOLD_INT = None
LOOT_SCROLLS_INT = None
LOOT_MAPS_INT = None
LOOT_GEMS_INT = None
LOOT_REAGENTS_INT = None
LOOT_AMMO_INT = None
LOOT_SOLEN_INT = None
LOOT_JUKA_INT = None
LOOT_KEYS_INT = None
LOOT_RESOURCES_INT = None
CUT_CORPSE_INT = None
LOOT_INSTRUMENTS_INT = None
LOOT_ARMOR_INT = None
LOOT_WEAPONS_INT = None
LOOT_JEWELS_INT = None
LOOT_SHIELDS_INT = None
LOOT_SETS_INT = None
LOOT_ARTIFACTS_INT = None
LOOT_RATING_INT = None
CHECK_GOLD = None
CHECK_SCROLLS = None
CHECK_MAPS = None
CHECK_GEMS = None
CHECK_REGS = None
CHECK_AMMO = None
CHECK_SOLEN = None
CHECK_JUKA = None
CHECK_KEYS = None
CHECK_RES = None
CHECK_CUT = None
CHECK_INST = None
CHECK_ARMOR = None
CHECK_WEPS = None
CHECK_JEWELS = None
CHECK_SETS = None
CHECK_SHIELDS = None
CHECK_ARTI = None
CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_autoloot_config.txt"
ACTIVE = "#55DD55"
INACTIVE = "#AA5555"
LOOT_BAG = Backpack()
BLADE = 0
SCISSORS = [0xf9f, 0xf9e]

#-------
GOLD_TYPE = 0x0EED
#-------
SCROLLS = [
	# First Circle
	0x1F2E,
	0x1F2F,
	0x1F30,
	0x1F31,
	0x1F32,
	0x1F33,
	0x1F2D,
	0x1F34,
	# Second Circle
	0x1F35,
	0x1F36,
	0x1F37,
	0x1F38,
	0x1F39,
	0x1F3A,
	0x1F3B,
	0x1F3C,
	# Third Circle
	0x1F3D,
	0x1F3E,
	0x1F3F,
	0x1F40,
	0x1F41,
	0x1F42,
	0x1F43,
	0x1F44,
	# Fourth Circle
	0x1F45,
	0x1F46,
	0x1F47,
	0x1F48,
	0x1F49,
	0x1F4A,
	0x1F4B,
	0x1F4C,
	# Fifth Circle
	0x1F4D,
	0x1F4E,
	0x1F4F,
	0x1F50,
	0x1F51,
	0x1F52,
	0x1F53,
	0x1F54,
	# Sixth Circle
	0x1F55,
	0x1F56,
	0x1F57,
	0x1F58,
	0x1F59,
	0x1F5A,
	0x1F5B,
	0x1F5C,
	# Seventh Circle
	0x1F5D,
	0x1F5E,
	0x1F5F,
	0x1F60,
	0x1F61,
	0x1F62,
	0x1F63,
	0x1F64,
	# Eigth Circle
	0x1F65,
	0x1F66,
	0x1F67,
	0x1F68,
	0x1F69,
	0x1F6A,
	0x1F6B,
	0x1F6C,
	# Necromancy
	0x2260,
	0x2261,
	0x2262,
	0x2263,
	0x2264,
	0x2265,
	0x2266,
	0x2267,
	0x2268,
	0x2269,
	0x226A,
	0x226B,
	0x226C,
	0x226D,
	0x226E,
	0x226F,
	# Spellweaving
	0x2D51,
	0x2D52,
	0x2D53,
	0x2D54,
	0x2D55,
	0x2D56,
	0x2D57,
	0x2D58,
	0x2D59,
	0x2D5A,
	0x2D5B,
	0x2D5C,
	0x2D5D,
	0x2D5E,
	0x2D5F,
	0x2D60
]
#-------
MAP_TYPE = 0x14ec
#-------
GEMS = [
	0xF15, # Citrine
	0xF18, # Tourmaline
	0xF11, # Sapphire
	0xF10, # Emerald
	0xF16, # Amethyst
	0xF26, # Diamond
	0xF0F, # Star Sap
	0xF25, # Amber
	0xF13, # Ruby
]
#-------
REAGENTS = [
	0xF78, # Bat Wing
	0xF7A, # Black Pearl
	0xF7B, # Bloodmoss
	0xF7D, # Daemon Blood
	0xF84, # Garlic
	0xF85, # Ginseng
	0xF8F, # Grave Dust
	0xF86, # Mandrake
	0xF88, # Nightshade
	0xF8E, # Nox Crystal
	0xF8A, # Pig Iron
	0xF8D, # Spiders Silk
	0xF8C, # Ash
]
#-------
AMMO = [0xF3F, 0x1BFB]
#-------
SOLEN = [
	0x26b7, # Fungus
	0xE2E   # Pet ball
]
#-------
JUKA = [
	0xE75,  # Backpack
	0x13B2, # Juka Bow
	0x13B1, # Juka Bow
	0x1EA7  # Arcane Gem
]
#-------
KEYS = [
	0xef5,  # Disintigrating Thesis Notes
	0x2002, # Travesty Keys
	0x1cdf, # legs
	0x1d9f, # torso
	0x1ae0, # skull
	0x1cee  # spleen
]
#-------
HIDES = [0x1078, 0x1079]
#-------
LEATHER = [0x1081]
#-------
RESOURCES = [
	0x1BF2, # ingot
	0x19B9, # ore
	0xf7e,  # bones
	0xDF8,  # wool
	0x3183, # blight
	0x3191, # fungi
	0x318E, # essence
	0x318D, # eye of trav
	0x3184, # corruption
	0x318A, # DH mane
	0x3190, # parasitic
	0x3188, # muculent
	0x318B, # bark
	0x318C, # grizzle bones
	0x3189, # lard
	0x3185, # scourge
	0x3186, # putrification
	0x3187  # taint
]
RESOURCES += HIDES + LEATHER
#-------
INSTRUMENTS = [
	0x2805, # flute
	0xE9C,  # drums
	0xEB1,  # harp
	0xEB2,  # lap harp
	0xEB3,  # lute
	0xE9D,  # tamborine
	0xE9E   # tamborine
]
#-------
ARTIFACTS = [
	0x153b, # cc
	0x153c, # cc
	0x2617, # grizzled mare
	0x2619, # paroxy swampy
	0x1f09, # djinni ring
	0x154B  # mark of trav
]
ARTIFACT_COLORS = [
	0,     # catch all (grizzle mare)
	1155,  # swampy
	0x485, # cc
	0x011E # Mark of Travesty
]
#-------
SWORD = [
	0x26ca, # YPO
	0xec5, # BNF
	0x13b8, # CPH
	0xec2, # INF
	0xf43, # FSF
	0xf4a, # OSF
	0xf44, # ASF
	0xec3, # HNF
	0x13f7, # FMH
	0xec4, # CNF
	0xf49, # LSF
	0xf4b, # NSF
	0xf4c, # ISF
	0x13fa, # SMH
	0x13fb, # RMH
	0xf46, # CSF
	0xf45, # ZRF
	0x1442, # MPH
	0x1443, # LPH
	0xf48, # MSF
	0xf47, # BSF
	0x26c4, # KPO
	0x26ba, # GUO
	0xf60, # KTF
	0xf61, # JTF
	0x13b9, # BPH
	0x13ba, # EPH
	0xf5f, # ZSF
	0xf5e, # ATF
	0x1441, # JPH
	0x13b6, # SOH
	0x13b5, # POH
	0x13ff, # NMH
	0x13fe, # OMH
	0x26c7, # LPO
	0x26bd, # ZTO
	0x143f, # XTH
	0x143e, # YTH
	0xf4d, # HSF
	0xf4e, # KSF
	0x26c1, # NPO
	0x26cb, # XPO
	0x26bb, # FUO
	0x26c5, # JPO
	0xe86, # QPF
	0xe85, # NPF
	0x1440, # KPH
	0x1203, # FYG
	0x2035, # RHM
	0x2d34, # SFR
    0x2d23 #ButcherWarCleaver
]
#-------
FENCING = [
	0x1404, # SRH
	0xe88, # AQF
	0xe87, # PPF
	0xf51, # TSF
	0xf52, # WSF
	0x26bf, # BUO
	0x26c9, # VPO
	0x26c8, # WPO
	0x1400, # WRH
	0x1401, # VRH
	0x1403, # XRH
	0x1402, # YRH
	0xf63, # LTF
	0xf62, # MTF
	0x26c0, # OPO
	0x1405, # RRH
	0x26be # CUO
]
#-------
MACE = [
	0x13e4, # OLH
	0x13af, # JOH
	0x1406, # URH
	0x13f4, # EMH
	0x143c, # WTH
	0x13f5, # DMH
	0x13f8, # QMH
	0xdf4, # CFF
	0xdf5, # BFF
	0x13f9, # PMH
	0x13f6, # GMH
	0xe89, # ZPF
	0xe8a, # CQF
	0xdf1, # FFF
	0xe81, # RPF
	0x1407, # TRH
	0xf5c, # YSF
	0xf5d, # XSF
	0xfb5, # FBG
	0x143d, # VTH
	0x1438, # AUH
	0x1439, # ZTH
	0x13b0, # UOH
	0x13b3, # VOH
	0x26bc, # AUO
	0x26c6, # MPO
	0x143b, # BUH
	0x143a, # CUH
	0x13f5, # DMH
	0xdf0, # GFF
	0x13b4, # QOH
	0xdf3, # HFF
	0x13e3, # TLH
	0xfb4 # GBG
]
#-------
BOW = [
	0x13b2, # WOH
	0x13b1, # TOH
	0x26c2, # QPO
	0x26cc, # SPO
	0x13b2, # WOH
	0x13b1, # TOH
	0xf4f, # JSF
	0xf50, # USF
	0x13fd, # LMH
	0x13fc, # MMH
	0x26c2, # QPO
	0x26cc, # SPO
	0x26c3, # PPO
	0x26cd, # RPO
	0xf4f, # JSF
	0xf50, # USF
	0x13fd, # LMH
	0x13fc, # MMH
	0x26c3, # PPO
	0x26cd, # RPO
	0xf4f # JSF
]
#-------
SE_SWORD = [
	0xf46, # CSF
	0xf45, # ZRF
	0x1442, # MPH
	0x1443, # LPH
	0xf48, # MSF
	0xf47, # BSF
	0x26c4, # KPO
	0x26ba, # GUO
	0xf60, # KTF
	0xf61, # JTF
	0x13b9, # BPH
	0x13ba, # EPH
	0xf5f, # ZSF
	0xf5e, # ATF
	0x1441, # JPH
	0x13b6, # SOH
	0x13b5, # POH
	0x13ff, # NMH
	0x13fe, # OMH
	0x26c7, # LPO
	0x26bd, # ZTO
	0x143f, # XTH
	0x143e, # YTH
	0xf4d, # HSF
	0xf4e, # KSF
	0x26c1, # NPO
	0x26cb, # XPO
	0x26bb, # FUO
	0x26c5, # JPO
	0xe86, # QPF
	0xe85, # NPF
	0x1440, # KPH
	0x1203, # FYG
	0x2035, # RHM
	0x27a9, # JDP
	0x27a2, # EDP
	0x27a4, # YCP
	0x27a8 # KDP
]
#-------
SE_FENCING = [
	0x27ab, # LDP
	0x27af, # HDP
	0x27a7, # ZCP
	0x27ad # FDP
]
#-------
SE_MACE = [
	0x27a3, # DDP
	0x27a6, # ADP
	0x27ae # IDP
]
#-------
SE_BOW = [
	0x27a5 # XCP
]
#-------
ML_SWORD = [
	0x2d35, # RFR
	0x2d29, # NFR
	0x2d34, # SFR
	0x2d28, # OFR
	0x2d26, # EFR
	0x2d32, # YFR
	0x2d33, # XFR
	0x2d27 # DFR
]
#-------
ML_FENCING = [
	0x2d2c, # KFR
	0x2d20, # GFR
	0x2d2f, # LFR
	0x2d23, # HFR
	0x2d22, # IFR
	0x2d2e, # MFR
	0x2d21, # FFR
	0x2d2d # JFR
]
#-------
ML_MACE = [
	0x2d31, # VFR
	0x2d25, # BFR
	0x2d30, # WFR
	0x2d24 # CFR
]
#-------
ML_BOW = [
	0x2d1f, # VER
	0x2d2b, # PFR
	0x2d1e, # WER
	0x2d2a # QFR
]
#-------
MED_ARMOR = [
	0x13cb, # VKH
	0x1db9, # NJL
	0x1dba, # QJL
	0x13c7, # JKH
	0x13cc, # QKH
	0x13d3, # DLH
	0x13c5, # HKH
	0x13cd, # PKH
	0x13ce, # SKH
	0x13c6, # KKH
	0x13d2, # ELH
	0xf55, # PSF
	0x1c00, # QSK
	0x1c0a, # ATK
	0x1c0b, # ZSK
	0x1c06, # OSK
	0x1c08, # YSK
	0x1c07, # NSK
	0x1db9, # NJL
	0x1dba, # QJL
	0x1549, # NZH
	0x153f, # TDI
	0x1715, # VVI
	0x154c, # KZH
	0x154b, # PZH
	0x1547, # DZH
	0x1544, # CZH
	0x1543, # HZH
	0x1540, # GZH
	0x1713, # BWI
	0x1714, # WVI
	0x1717, # XVI
	0x1716, # YVI
	0x1718, # IWI
	0x1719, # HWI
	0x171a, # KWI
	0x171b, # JWI
	0x171c, # EWI
	0x2305, # JJN
	0x1548, # OZH
	0x1547, # DZH
	0x1545, # BZH
	0x1546, # EZH
	0x141b, # VSH
	0x141c, # QSH
	0x141b, # VSH
	0x1f0b, # NWL
	0x13c7, # JKH
	0x1089, # RJG
	0x1088, # SJG
	0x1085, # FJG
	0x1f08, # MWL
	0x13c5, # HKH
	0x13cd, # PKH
	0x13cc, # QKH
	0x13d3, # DLH
	0x1c0a, # ATK
	0x1c0b, # ZSK
	0x1c06, # OSK
	0x1c07, # NSK
	0x13c6, # KKH
	0x13ce, # SKH
	0x26b0, # WTO
	0x13cb, # VKH
	0x13d2, # ELH
	0x1c00, # QSK
	0x1c08, # YSK
	0x1c01, # PSK
	0x277b, # RWO
	0x278a, # GCP
	0x2786, # UBP
	0x277e, # OWO
	0x2791, # LCP
	0x277a, # SWO
	0x2776, # GWO
	0x278e, # CCP
	0x2793, # NCP
	0x2792, # OCP
	0x2776, # GWO
	0x278e, # CCP
	0x277a, # SWO
	0x277e, # OWO
	0x277b, # RWO
	0x2793, # NCP
	0x2792, # OCP
	0x278a, # GCP
	0x2786, # UBP
	0x2791, # LCP
	0x2788, # ECP
	0x2b6e, # IJQ
	0x2fc7, # BAS
	0x2fc8, # MAS
	0x2fc5, # ZZR
	0x2fc6, # CAS
	0x2fca, # OAS
	0x2fc9 # LAS
]
#-------
NONMED_ARMOR = [
	0x13d6, # ALH
	0x13e2, # ULH
	0x13db, # LLH
	0x13d4, # YKH
	0x13dc, # GLH
	0x13d5, # XKH
	0x13dd, # FLH
	0x13e1, # RLH
	0x13da, # MLH
	0x1c02, # SSK
	0x1c03, # RSK
	0x1451, # ZPH
	0x1456, # YPH
	0x1454, # WPH
	0x144f, # PPH
	0x1453, # BQH
	0x144e, # QPH
	0x1455, # VPH
	0x1457, # XPH
	0x1452, # CQH
	0x1450, # AQH
	0x1409, # DSH
	0x140c, # ASH
	0x1419, # TSH
	0x1408, # ESH
	0x1456, # YPH
	0x140a, # GSH
	0x1412, # OSH
	0x1451, # ZPH
	0x140d, # ZRH
	0x1f0c, # IWL
	0x140e, # CSH
	0x140e, # CSH
	0x140f, # BSH
	0x140b, # FSH
	0x13bb, # DPH
	0x2645, # LKO
	0x1f0b, # NWL
	0x13c0, # MKH
	0x1413, # NSH
	0x13d6, # ALH
	0x1453, # BQH
	0x1417, # JSH
	0x13ef, # XLH
	0x13dc, # GLH
	0x1410, # MSH
	0x13ee, # YLH
	0x144e, # QPH
	0x13d4, # YKH
	0x2657, # DLO
	0x1415, # HSH
	0x13e2, # ULH
	0x13db, # LLH
	0x13bf, # ZOH
	0x13c4, # IKH
	0x13ed, # VLH
	0x1416, # KSH
	0x13ec, # WLH
	0x1454, # WPH
	0x2641, # PKO
	0x144f, # PPH
	0x1c03, # RSK
	0x1c0c, # USK
	0x1c02, # SSK
	0x1c04, # MSK
	0x1c0d, # TSK
	0x1c05, # LSK
	0x1c0c, # USK
	0x1455, # VPH
	0x1414, # ISH
	0x1450, # AQH
	0x13eb, # BMH
	0x1418, # USH
	0x13d5, # XKH
	0x13dd, # FLH
	0x13f2, # KMH
	0x2643, # RKO
	0x13f1, # HMH
	0x1411, # LSH
	0x13f0, # IMH
	0x1452, # CQH
	0x141a, # WSH
	0x13be, # APH
	0x13da, # MLH
	0x13e1, # RLH
	0x13c3, # NKH
	0x1457, # XPH
	0x2647, # NKO
	0x277c, # MWO
	0x277f, # NWO
	0x278b, # FCP
	0x279d, # PCP
	0x2787, # TBP
	0x2785, # RBP
	0x2789, # DCP
	0x2778, # QWO
	0x2775, # DWO
	0x2784, # SBP
	0x2781, # VBP
	0x2777, # FWO
	0x279d, # PCP
	0x277f, # NWO
	0x2780, # WBP
	0x277c, # MWO
	0x277d, # LWO
	0x278b, # FCP
	0x2787, # TBP
	0x278d, # ZBP
	0x2b71, # RJQ
	0x2b72, # UJQ
	0x2b73, # TJQ
	0x2b76, # QJQ
	0x2b69, # JJQ
	0x2b77, # PJQ
	0x2b6c, # GJQ
	0x2b74, # OJQ
	0x2b67, # ZIQ
	0x2b75, # NJQ
	0x2b6a, # MJQ
	0x2b78, # AKQ
	0x2b6b # LJQ
]
#-------
SHIELDS = [
	0x1b79, # LIK
	0x1b78, # MIK
	0x1bc4, # CLK
	0x1b74, # AIK
	0x1b76, # CIK
	0xa25, # LYD
	0x1b72, # GIK
	0x1b7b, # NIK
	0x1b75, # ZHK
	0x1bc3, # HLK
	0x1bc5, # BLK
	0x1b73, # FIK
	0x1b77, # BIK
	0x1b7a, # OIK
	0x4228, # Garg chaos
	0x4229, # Garg chaos
	0x4201, # Garg kite
	0x4206, # Garg kite
	0x422A, # Garg order
	0x422C, # Garg order

]
#-------
JEWELRY = [
	0x1f06, # CWL
	0x1f09, # LWL
	0x108a, # UJG
	0x1086, # IJG
	0x4211, # Garg Brace
	0x4212, # Garg Ring
]
#-------
HATS = [
	0x1544, # CZH
	0x1543, # HZH
	0x1540, # GZH
	0x1713, # BWI
	0x1714, # WVI
	0x1717, # XVI
	0x1716, # YVI
	0x1718, # IWI
	0x1719, # HWI
	0x171a, # KWI
	0x171b, # JWI
	0x171c, # EWI
	0x2305, # JJN
	0x1548, # OZH
	0x1547, # DZH
	0x1545, # BZH
	0x1546, # EZH
	0x141b, # VSH
	0x141c, # QSH
	0x141b, # VSH
	0x1f0b # NWL
]
#-------
WEAPONS = SWORD + FENCING + MACE + BOW + SE_SWORD + SE_FENCING + SE_MACE + SE_BOW + ML_SWORD + ML_FENCING + ML_MACE + ML_BOW
ARMORS = MED_ARMOR + NONMED_ARMOR

#############
# Definitions
#############
def is_weapon(item):
    return GetType(item) in WEAPONS

def is_armor(item):
    return GetType(item) in ARMORS
    
def is_jewelery(item):
    return GetType(item) in JEWELRY

def is_shield(item):
    return GetType(item) in SHIELDS

def is_medable(item):
    return GetType(item) in MED_ARMOR
 
def is_hats(item):
    return GetType(item) in HATS
 
def calculate_value(item):
    value = 0
   
    if LOOT_WEAPONS and is_weapon(item):
        return (
            chance_increase(item,value) + 
            damage_increase(item,value) +  
            speed_increase(item,value) + 
            spell_channeling(item,value) + 
            slayer(item,value) + 
            leech(item,value) + 
            lower_ad(item,value) + 
            hit_spell(item,value) + 
            best_weapon(item,value) + 
            luck(item,value) + 
            elemental_damage(item,value)
        )
    elif LOOT_ARMOR and is_armor(item):
        return (
            medable(item,value) +
            regeneration(item,value) +
            resist(item,value) + 
            lowercost(item,value) + 
            stats_increase(item,value) + 
            luck(item,value) + 
            self_repair(item,value) + 
            reflect_physical(item,value) 
        )
    elif LOOT_JEWELS and is_jewelery(item):
        return (
            skill(item,value) +
            stats(item,value) + 
            chance_increase(item,value) +
            damage_increase(item,value) +
            luck(item,value) +
            night(item,value) +
            fastercast(item,value) +
            resist(item,value) +
            lowercost(item,value) +
            enhancepots(item,value)
        )
    elif LOOT_SHIELDS and is_shield(item):
        return (
            chance_increase(item,value) + 
            self_repair(item,value) + 
            spell_channeling(item,value) + 
            fastercast(item,value) + 
            reflect_physical(item,value) + 
            resist(item,value)
        )
    else:
        return 0

def skill(item, value):
    result = skills(item, value)
    value = value + result / 3

    return value

def fastercast(item, value):
    if 'faster casting' in GetCliloc(item) and 'faster cast recovery' in GetCliloc(item):
        value = value + 4

    fc = property_value('faster casting', item)

    if fc > 0:
        value = value + ( fc * 6 )

    fcr = property_value('faster cast recovery', item)

    if fcr > 0:
        value = value + ( fcr * 4 )

    return value

def stats(item, value):
    int_bonus = property_value('intelligence bonus', item)
    value = value + int_bonus/2 + int_bonus/3
    str_bonus = property_value('strength bonus', item)
    value = value + str_bonus/2 + str_bonus/3
    dex_bonus = property_value('dexterity bonus', item)
    value = value + dex_bonus/2 + dex_bonus/3

    return value

def stats_increase(item, value):
    hpi = property_value('hit point increase', item)
    value = value + hpi/2
    mi = property_value('mana increase', item)
    value = value + mi/2
    si = property_value('stamina increase', item)
    value = value + si/3

    return value 
    
def night(item, value):
    if 'night sight' in GetCliloc(item):
        value = value + 0

    return value
    
def self_repair(item, value):
    sr = property_value('self repair', item)
    value = value + sr/5

    return value
    
def lowercost(item, value):
    lrc = property_value('lower reagent cost', item)

    if lrc >= 12:
        value = value + lrc/2 + lrc/3
        if not is_medable(item):
            value = value - lrc/3

    lmc = property_value('lower mana cost', item)
    value = value + lmc/2 + lmc/3

    return value
    
def enhancepots(item, value):
    ep = property_value('enhance potions', item)
    value = value + ep/3

    return value
    
def regeneration(item, value):
    mr = property_value('mana regeneration', item)
    value = value + mr*4 
    hpr = property_value('hit point regeneration', item)
    value = value + hpr*4 
    sr = property_value('stamina regeneration', item)
    value = value + sr

    return value
    
def slayer(item, value):
    if 'dragon slayer' in GetCliloc(item) or 'daemon slayer' in GetCliloc(item) or 'blood elemental slayer' in GetCliloc(item):
        value = value + 4
    elif 'repond slayer' in GetCliloc(item) or 'undead slayer' in GetCliloc(item) or 'demon slayer' in GetCliloc(item) or 'reptile slayer' in GetCliloc(item) or 'elemental slayer' in GetCliloc(item) or 'arachnid slayer' in GetCliloc(item):
        value = value + 5
    elif 'slayer' in GetCliloc(item):
        value = value + 3
    return value
    
def elemental_damage(item, value):
    elem_dam = 0
    cold = property_value('cold damage', item)
    if cold >= 30:
        elem_dam = 3
    energy = property_value('energy damage', item)
    if energy >= 30:
        elem_dam = 3
    fire = property_value('fire damage', item)
    if fire >= 30:
        elem_dam = 3
    poison = property_value('poison damage', item)
    if poison >= 30:
        elem_dam = 3

    if elem_dam > 0:
        value = value + elem_dam

    return value

def hit_spell(item, value):
    hl = property_value('hit lightning', item)
    if hl >= 30:
        value = value + ( hl/ 6 ) + ( hl / 12 )

    hh = property_value('hit harm', item)
    if hh >= 30:
        value = value + ( hh/ 6 ) + ( hh / 12 )
        
    hf = property_value('hit fireball', item)
    if hf >= 30:
        value = value + ( hf/ 6 ) + ( hf / 12 )

    hd = property_value('hit dispel', item)
    if hd >= 40:
        value = value + 0
        
    ha = property_value('hit area', item)
    if ha >= 30:
        value = value + ( ha/ 12 )
        
    return value
    
def lower_ad(item, value):
    hla = property_value('hit lower attack', item)

    if hla >= 30:
        value = value + hla/5

    hld = property_value('hit lower defense', item)

    if hld >= 30:
        value = value + hld/5
    
    return value

def luck(item, value):
    luck = property_value('luck', item)
    
    if is_hats(item):
        luck = luck - 40

    if luck >= 50:
        value = value + ( luck / 15 )

    return value 
    
def best_weapon(item, value):
    if 'best weapon skill' in GetCliloc(item):
        value = value + 1

    return value 

def chance_increase(item, value):
    hci = property_value('hit chance', item)

    if hci >= 6:
        value = value + hci/2 + hci/3

    dci = property_value('defense chance', item)

    if dci >= 6:
        value = value + dci/2 + dci/3
        
    if hci >= 10 and dci >= 10:
        value = value + 5

    return value

def speed_increase(item, value):
    ssi = property_value('swing speed increase', item)
    if ssi >= 10:
        value = value + ssi / 3 + ssi / 10

    return value
    
def spell_channeling(item, value):
    if 'spell channeling' in GetCliloc(item):
        value = value + 4

        if 'faster casting' in GetCliloc(item) and '-1' in GetCliloc(item):
            value = value - 2
        if 'defense chance increase' in GetCliloc(item):
            value = value + 4
        if 'mage weapon' in GetCliloc(item):
            mw = property_value('mage weapon', item)
            value = value + ( ( 31 - mw ) / 4 )

    return value
    
def medable(item, value):
    if is_medable(item) or ('mage armor' in GetCliloc(item)):
        value = value + 2

    return value
    
def leech(item, value):
    hml = property_value('mana leech', item)

    if hml >= 30:
        value = value + ( hml / 6 ) + ( hml / 10 )
        if 'Slayer' in GetCliloc(item):
            value = value + 10

    hll = property_value('life leech', item)

    if hll >= 30:
        value = value + ( hll / 6 ) + ( hll / 10 )

    hsl = property_value('stamina leech', item)

    if hsl >= 30:
        value = value + ( hsl / 8 ) + ( hsl / 10 )

    return value 
    
def damage_increase(item, value):
    sdi = property_value('spell damage increase', item)

    if sdi > 0:
        value = value + ( sdi / 2 )

    di = property_value('damage increase', item)

    if di > 0 and not 'spell damage increase' in GetCliloc(item) and not is_weapon(item):
        value = value + ( di / 5 ) + ( di / 10 )

    if di > 20 and is_weapon(item):
        value = value + ( di / 15 )

    return value 
    
def reflect_physical(item, value):
    rpd = property_value('reflect physical damage', item)
    value = value + ( rpd / 5 )

    return value 
    
def resist(item, value):
    r = resists(item, value)

    if is_hats(item):
        r = r - 12

    if is_armor(item) and r > 40:
        value = value + ( r / 4 ) + ( r / 10 )

    if not is_armor(item):
        value = value + ( r / 5 )

    return value

def resists(item, value):
    if 'resist' not in GetCliloc(item):
        return 0

    totalresists = get_total_resists(item)

    if 'total resist' in GetCliloc(item).lower():
        tr = property_value('Total Resist', item)
        totalresists = totalresists - tr

    return totalresists
    
def get_total_resists(item):
    physical = property_value('physical resist', item)
    cold = property_value('cold resist', item)
    energy = property_value('energy resist', item)
    fire = property_value('fire resist', item)

    if is_jewelery(item):
        fire = fire * 3

    poison = property_value('poison resist', item)
    
    return physical + cold + energy + fire + poison
    
def get_total_skills(item):
    props = GetCliloc(item).split("|")
    skill_bonus = 0

    for prop in props:
        if '+' in prop:
            skill_bonus = skill_bonus + property_value(prop, item)

            if 'magery' in prop.lower():
                skill_bonus = skill_bonus + 5
            
    return skill_bonus
    
def skills(item, value):
    if '+' not in GetCliloc(item):
        return 0

    totalskills = get_total_skills(item)

    return totalskills

def property_value(prop, item):
    if prop not in GetCliloc(item):
        return 0
        
    parts = GetCliloc(item).split("|")

    for i in parts:
        if prop.lower() in i.lower() or prop.lower() == i.lower():
            value = i.split(' ')

            if 'mage weapon' in i.lower():
                value = value[len(value)-2]
            else:
                value = value[len(value)-1]
            
            value = value.replace('%', '')
            value = value.replace('+', '')
            value = value.replace('-', '')

            try:
                value = float(value)
            except:
                value = 0

            return value

def trunc(num, digits):
    sp = str(num).split('.')  
    decimal = sp[1]

    return (str(sp[0]) + '.' + str(decimal[:digits]))

def loot(corpse):
	if Dead() or not Connected():
		return

	if GetDistance(corpse) <= 8:
		if CUT_CORPSE and BLADE > 0:
			UseObject(BLADE)
			WaitForTarget(15000)
			TargetToObject(corpse)
			Wait(700)

		UseObject(corpse)
		Wait(700)

		if FindType(-1, corpse) > 0:
			for item in GetFoundList(): 
				item_type = GetType(item)
				tooltip = getTooltip(item).lower()

				# EVALUATE ITEM
				value = calculate_value(item)
				
				if value > 30:
					print('---------------------------------------------------------------')
					print("$$$$$$$$$$$$$$$$$$$$$$ BIGGER THAN 30 $$$$$$$$$$$$$$$$$$$$$$$$$")
				elif value > 20:
					print('---------------------------------------------------------------')
					print("********************** BIGGER THAN 20 *************************")
				
				if value > 20:
					print(tooltip, end='')
					props = tooltip.split("|")
					print('--- props: ' + str(len(props)-2) + ' | value: ' + str(trunc(value, 2)))
					print('-------------------------------------------------------------')

				# LOOT ITEM
				if value >= int(LOOT_RATING):
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					ClientPrintEx(item, 1, 1, "> LOOTED <")
					Wait(700)
				# CHECK POR ASSASSIN SET
				elif LOOT_SETS and 'assassin armor' in tooltip:
					print('------------- ASSASSIN SET PIECE -------------')
					print(tooltip, end='')
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					Wait(700)
				# CHECK POR HUNTER SET
				elif LOOT_SETS and 'hunter' in tooltip:
					print('------------- HUNTER SET PIECE -------------')
					print(tooltip, end='')
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					Wait(700)
				# CHECK POR GREYMIST SET
				elif LOOT_SETS and 'greymist' in tooltip:
					print('------------- GREYMIST SET PIECE -------------')
					print(tooltip, end='')
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					Wait(700)
				elif LOOT_SETS and 'death' in tooltip:
					print('------------- DEATH SET PIECE -------------')
					print(tooltip, end='')
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					Wait(700)
				elif LOOT_SETS and 'grizzle' in tooltip:
					print('------------- GRIZZLE SET PIECE -------------')
					print(tooltip, end='')
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					Wait(700)
				elif LOOT_SETS and 'leafweave' in tooltip:
					print('------------- LEAFWEAVE SET PIECE -------------')
					print(tooltip, end='')
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					Wait(700)
				elif LOOT_SETS and 'honor' in tooltip:
					print('------------- HONOR SET PIECE -------------')
					print(tooltip, end='')
					MoveItem(item, 1, LOOT_BAG, 1, 1, 0)
					Wait(700)
				elif LOOT_GOLD and item_type == GOLD_TYPE:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_SCROLLS and item_type in SCROLLS:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_MAPS and item_type == MAP_TYPE:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_GEMS and item_type in GEMS:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_REAGENTS and item_type in REAGENTS:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_AMMO and item_type in AMMO:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_SOLEN and item_type in SOLEN:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_JUKA and item_type in JUKA:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_KEYS and item_type in KEYS:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_RESOURCES and item_type in RESOURCES:
					#if item_type in HIDES:
                    
						#FindTypesArrayEx(SCISSORS, [0xFFFF], [Backpack()], True)
						#scissors = FindItem()

						#if scissors > 0:
						#	UseObject(scissors)
						#	WaitForTarget(15000)
						#	TargetToObject(item)
						#	Wait(100)
						#	FindTypesArrayEx(LEATHER, [0xFFFF], [corpse], True)
						#	item = FindItem()

					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_INSTRUMENTS and item_type in INSTRUMENTS:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)
				elif LOOT_ARTIFACTS and item_type in ARTIFACTS and GetColor(item) in ARTIFACT_COLORS:
					MoveItem(item, 0, LOOT_BAG, 0, 0, 0)
					Wait(700)

	Ignore(corpse)      

def loot_gold_on_ground():
	last_finddistance = GetFindDistance()
	SetFindDistance(2)
    
	if FindType(GOLD_TYPE, Ground()):
		for item in GetFoundList():
			MoveItem(item, 0, Backpack(), 0, 0, 0)
			Wait(800)
                        
	SetFindDistance(last_finddistance)
   
#############
# Classes
#############	
class LootWindow(threading.Thread):
	def __init__(self):
		super(LootWindow, self).__init__(daemon = True)

	def setGlobals(self):
		global LOOT_GOLD, LOOT_SCROLLS, LOOT_MAPS, LOOT_GEMS, LOOT_REAGENTS, LOOT_AMMO, LOOT_SOLEN, LOOT_JUKA, LOOT_KEYS, LOOT_RESOURCES, CUT_CORPSE
		global LOOT_INSTRUMENTS, LOOT_ARMOR, LOOT_WEAPONS, LOOT_JEWELS, LOOT_SHIELDS, LOOT_SETS, LOOT_ARTIFACTS, LOOT_RATING
		
		if LOOT_GOLD_INT.get() > 0:
			LOOT_GOLD = True
		else:
			LOOT_GOLD = False
			
		if LOOT_SCROLLS_INT.get() > 0:
			LOOT_SCROLLS = True
		else:
			LOOT_SCROLLS = False
			
		if LOOT_MAPS_INT.get() > 0:
			LOOT_MAPS = True
		else:
			LOOT_MAPS = False
		
		if LOOT_GEMS_INT.get() > 0:
			LOOT_GEMS = True
		else:
			LOOT_GEMS = False
			
		if LOOT_REAGENTS_INT.get() > 0:
			LOOT_REAGENTS = True
		else:
			LOOT_REAGENTS = False
			
		if LOOT_AMMO_INT.get() > 0:
			LOOT_AMMO = True
		else:
			LOOT_AMMO = False
			
		if LOOT_SOLEN_INT.get() > 0:
			LOOT_SOLEN = True
		else:
			LOOT_SOLEN = False
			
		if LOOT_JUKA_INT.get() > 0:
			LOOT_JUKA = True
		else:
			LOOT_JUKA = False
			
		if LOOT_KEYS_INT.get() > 0:
			LOOT_KEYS = True
		else:
			LOOT_KEYS = False
			
		if LOOT_RESOURCES_INT.get() > 0:
			LOOT_RESOURCES = True
		else:
			LOOT_RESOURCES = False
			
		if CUT_CORPSE_INT.get() > 0:
			CUT_CORPSE = True
		else:
			CUT_CORPSE = False
			
		if LOOT_INSTRUMENTS_INT.get() > 0:
			LOOT_INSTRUMENTS = True
		else:
			LOOT_INSTRUMENTS = False
			
		if LOOT_ARMOR_INT.get() > 0:
			LOOT_ARMOR = True
		else:
			LOOT_ARMOR = False
			
		if LOOT_WEAPONS_INT.get() > 0:
			LOOT_WEAPONS = True
		else:
			LOOT_WEAPONS = False
			
		if LOOT_JEWELS_INT.get() > 0:
			LOOT_JEWELS = True
		else:
			LOOT_JEWELS = False
			
		if LOOT_SHIELDS_INT.get() > 0:
			LOOT_SHIELDS = True
		else:
			LOOT_SHIELDS = False
			
		if LOOT_SETS_INT.get() > 0:
			LOOT_SETS = True
		else:
			LOOT_SETS = False
			
		if LOOT_ARTIFACTS_INT.get() > 0:
			LOOT_ARTIFACTS = True
		else:
			LOOT_ARTIFACTS = False
			
		LOOT_RATING = LOOT_RATING_INT.get()

	def getConfig(self):
		global LOOT_GOLD_INT, LOOT_SCROLLS_INT, LOOT_MAPS_INT, LOOT_GEMS_INT, LOOT_REAGENTS_INT, LOOT_AMMO_INT, LOOT_SOLEN_INT
		global LOOT_JUKA_INT, LOOT_KEYS_INT, LOOT_RESOURCES_INT, CUT_CORPSE_INT, LOOT_INSTRUMENTS_INT, LOOT_ARMOR_INT, LOOT_WEAPONS_INT
		global LOOT_JEWELS_INT, LOOT_SHIELDS_INT, LOOT_SETS_INT, LOOT_ARTIFACTS_INT, LOOT_RATING_INT
	
		if os.path.exists(CONFIG_FILE):
			f = open(CONFIG_FILE, "r")
			config = json.loads(f.read())
			f.close()
		else:
			config = {
				"LOOT_GOLD": 0,
				"LOOT_SCROLLS": 0,
				"LOOT_MAPS": 0,
				"LOOT_GEMS": 0,
				"LOOT_REAGENTS": 0,
				"LOOT_AMMO": 0,
				"LOOT_SOLEN": 0,
				"LOOT_JUKA": 0,
				"LOOT_KEYS": 0,
				"LOOT_RESOURCES": 0,
				"CUT_CORPSE": 0,
				"LOOT_INSTRUMENTS": 0,
				"LOOT_ARMOR": 0,
				"LOOT_WEAPONS": 0,
				"LOOT_JEWELS": 0,
				"LOOT_SHIELDS": 0,
				"LOOT_SETS": 0,
				"LOOT_ARTIFACTS": 0,
				"LOOT_RATING": 25
			}

		LOOT_GOLD_INT.set(config["LOOT_GOLD"])
		LOOT_SCROLLS_INT.set(config["LOOT_SCROLLS"])
		LOOT_MAPS_INT.set(config["LOOT_MAPS"])
		LOOT_GEMS_INT.set(config["LOOT_GEMS"])
		LOOT_REAGENTS_INT.set(config["LOOT_REAGENTS"])
		LOOT_AMMO_INT.set(config["LOOT_AMMO"])
		LOOT_SOLEN_INT.set(config["LOOT_SOLEN"])
		LOOT_JUKA_INT.set(config["LOOT_JUKA"])
		LOOT_KEYS_INT.set(config["LOOT_KEYS"])
		LOOT_RESOURCES_INT.set(config["LOOT_RESOURCES"])
		CUT_CORPSE_INT.set(config["CUT_CORPSE"])
		LOOT_INSTRUMENTS_INT.set(config["LOOT_INSTRUMENTS"])
		LOOT_ARMOR_INT.set(config["LOOT_ARMOR"])
		LOOT_WEAPONS_INT.set(config["LOOT_WEAPONS"])
		LOOT_JEWELS_INT.set(config["LOOT_JEWELS"])
		LOOT_SHIELDS_INT.set(config["LOOT_SHIELDS"])
		LOOT_SETS_INT.set(config["LOOT_SETS"])
		LOOT_ARTIFACTS_INT.set(config["LOOT_ARTIFACTS"])
		LOOT_RATING_INT.set(config["LOOT_RATING"])

		self.setGlobals()

	def saveConfig(self):
		config = {
			"LOOT_GOLD": LOOT_GOLD_INT.get(),
			"LOOT_SCROLLS": LOOT_SCROLLS_INT.get(),
			"LOOT_MAPS": LOOT_MAPS_INT.get(),
			"LOOT_GEMS": LOOT_GEMS_INT.get(),
			"LOOT_REAGENTS": LOOT_REAGENTS_INT.get(),
			"LOOT_AMMO": LOOT_AMMO_INT.get(),
			"LOOT_SOLEN": LOOT_SOLEN_INT.get(),
			"LOOT_JUKA": LOOT_JUKA_INT.get(),
			"LOOT_KEYS": LOOT_KEYS_INT.get(),
			"LOOT_RESOURCES": 0,
			"CUT_CORPSE": 0,
			"LOOT_INSTRUMENTS": LOOT_INSTRUMENTS_INT.get(),
			"LOOT_ARMOR": LOOT_ARMOR_INT.get(),
			"LOOT_WEAPONS": LOOT_WEAPONS_INT.get(),
			"LOOT_JEWELS": LOOT_JEWELS_INT.get(),
			"LOOT_SHIELDS": LOOT_SHIELDS_INT.get(),
			"LOOT_SETS": LOOT_SETS_INT.get(),
			"LOOT_ARTIFACTS": LOOT_ARTIFACTS_INT.get(),
			"LOOT_RATING": LOOT_RATING_INT.get() 
		}

		f = open(CONFIG_FILE, "w")
		f.write(json.dumps(config, indent = 4))
		f.close()

	def setColors(self):
		if LOOT_GOLD_INT.get() > 0:
			CHECK_GOLD.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_GOLD.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_SCROLLS_INT.get() > 0:
			CHECK_SCROLLS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_SCROLLS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_MAPS_INT.get() > 0:
			CHECK_MAPS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_MAPS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_GEMS_INT.get() > 0:
			CHECK_GEMS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_GEMS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_REAGENTS_INT.get() > 0:
			CHECK_REGS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_REGS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_AMMO_INT.get() > 0:
			CHECK_AMMO.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_AMMO.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_SOLEN_INT.get() > 0:
			CHECK_SOLEN.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_SOLEN.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_JUKA_INT.get() > 0:
			CHECK_JUKA.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_JUKA.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_KEYS_INT.get() > 0:
			CHECK_KEYS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_KEYS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_RESOURCES_INT.get() > 0:
			CHECK_RES.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_RES.config(activebackground = ACTIVE, background = INACTIVE)
		
		if CUT_CORPSE_INT.get() > 0:
			LOOT_RESOURCES_INT.set(1)
			CHECK_RES.config(activebackground = INACTIVE, background = ACTIVE)
			CHECK_CUT.config(activebackground = INACTIVE, background = ACTIVE)
			self.setBlade()
		else:
			LOOT_RESOURCES_INT.set(0)
			CHECK_RES.config(activebackground = ACTIVE, background = INACTIVE)
			CHECK_CUT.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_INSTRUMENTS_INT.get() > 0:
			CHECK_INST.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_INST.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_ARMOR_INT.get() > 0:
			CHECK_ARMOR.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_ARMOR.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_WEAPONS_INT.get() > 0:
			CHECK_WEPS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_WEPS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_JEWELS_INT.get() > 0:
			CHECK_JEWELS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_JEWELS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_SHIELDS_INT.get() > 0:
			CHECK_SHIELDS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_SHIELDS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_SETS_INT.get() > 0:
			CHECK_SETS.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_SETS.config(activebackground = ACTIVE, background = INACTIVE)
		
		if LOOT_ARTIFACTS_INT.get() > 0:
			CHECK_ARTI.config(activebackground = INACTIVE, background = ACTIVE)
		else:
			CHECK_ARTI.config(activebackground = ACTIVE, background = INACTIVE)

		self.setGlobals()

	def setLootBag(self):
		global LOOT_BAG

		ClientPrintEx(Self(), 1, 1, "Target the container you'd like to loot to...")
		ClientRequestObjectTarget()
		
		while not ClientTargetResponsePresent():
			Wait(1)
		
		response = ClientTargetResponse()["ID"]
		
		if response > 0 and IsContainer(response):
			LOOT_BAG = response
		else:
			AddToSystemJournalEx("WARNING: That is not a container!", 0xFFA500, 0x0)
			LOOT_BAG = Backpack()

	def setBlade(self):
		global BLADE, LOOT_RESOURCES_INT, CUT_CORPSE_INT

		ClientPrintEx(Self(), 1, 1, "Select a bladed item...")
		ClientRequestObjectTarget()
		
		while not ClientTargetResponsePresent():
			Wait(3000)
		
		response = ClientTargetResponse()["ID"]
		response_type = GetType(response)

		if response > 0 and (response_type in SWORD or response_type in SE_SWORD or response_type in ML_SWORD):
			BLADE = response
			#FindTypesArrayEx(SCISSORS, [0xFFFF], [Backpack()], True)

			#if len(GetFoundList()) <= 0:
			#	AddToSystemJournalEx("WARNING: You don't have any scissors!", 0xFFA500, 0x0)
		else:
			AddToSystemJournalEx("ERROR: That is not a bladed item!", 0x0000FF, 0x0)
			BLADE = 0
			LOOT_RESOURCES_INT.set(0)
			CUT_CORPSE_INT.set(0)

			CHECK_RES.deselect()
			CHECK_CUT.deselect()
			self.setColors()

	def run(self):
		global LOOT_GOLD_INT, LOOT_SCROLLS_INT, LOOT_MAPS_INT, LOOT_GEMS_INT, LOOT_REAGENTS_INT, LOOT_AMMO_INT, LOOT_SOLEN_INT, LOOT_JUKA_INT
		global LOOT_KEYS_INT, LOOT_RESOURCES_INT, CUT_CORPSE_INT, LOOT_INSTRUMENTS_INT, LOOT_ARMOR_INT, LOOT_WEAPONS_INT, LOOT_JEWELS_INT
		global LOOT_SHIELDS_INT, LOOT_SETS_INT, LOOT_ARTIFACTS_INT, LOOT_RATING_INT
		global CHECK_GOLD, CHECK_SCROLLS, CHECK_MAPS, CHECK_GEMS, CHECK_REGS, CHECK_AMMO, CHECK_SOLEN, CHECK_JUKA, CHECK_KEYS, CHECK_RES
		global CHECK_CUT, CHECK_INST, CHECK_ARMOR, CHECK_WEPS, CHECK_JEWELS, CHECK_SETS, CHECK_SHIELDS, CHECK_ARTI
		
		WINDOW = Tk()
		LOOT_GOLD_INT = IntVar()
		LOOT_SCROLLS_INT = IntVar()
		LOOT_MAPS_INT = IntVar()
		LOOT_GEMS_INT = IntVar()
		LOOT_REAGENTS_INT = IntVar()
		LOOT_AMMO_INT = IntVar()
		LOOT_SOLEN_INT = IntVar()
		LOOT_JUKA_INT = IntVar()
		LOOT_KEYS_INT = IntVar()
		LOOT_RESOURCES_INT = IntVar()
		CUT_CORPSE_INT = IntVar()
		LOOT_INSTRUMENTS_INT = IntVar()
		LOOT_ARMOR_INT = IntVar()
		LOOT_WEAPONS_INT = IntVar()
		LOOT_JEWELS_INT = IntVar()
		LOOT_SHIELDS_INT = IntVar()
		LOOT_SETS_INT = IntVar()
		LOOT_ARTIFACTS_INT = IntVar()
		LOOT_RATING_INT = IntVar()
		CHECK_GOLD = Checkbutton()
		CHECK_SCROLLS = Checkbutton()
		CHECK_MAPS = Checkbutton()
		CHECK_GEMS = Checkbutton()
		CHECK_REGS = Checkbutton()
		CHECK_AMMO = Checkbutton()
		CHECK_SOLEN = Checkbutton()
		CHECK_JUKA = Checkbutton()
		CHECK_KEYS = Checkbutton()
		CHECK_RES = Checkbutton()
		CHECK_CUT = Checkbutton()
		CHECK_INST = Checkbutton()
		CHECK_ARMOR = Checkbutton()
		CHECK_WEPS = Checkbutton()
		CHECK_JEWELS = Checkbutton()
		CHECK_SETS = Checkbutton()
		CHECK_SHIELDS = Checkbutton()
		CHECK_ARTI = Checkbutton()

		WINDOW.geometry("420x330-0+0")
		WINDOW.title(CharName() + " - Auto-looter")
		WINDOW.resizable(False, False)
		self.getConfig()

		# Miscellaneous grid
		misc_frame = LabelFrame(master = WINDOW, text = "Misc. Loot:", height = 150, width = 400)
		misc_frame.pack()

		# Column 1
		CHECK_GOLD = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Gold", width = 15, anchor = "w", variable = LOOT_GOLD_INT, command = self.setColors)
		CHECK_GOLD.grid(row = 0, column = 0)

		CHECK_SCROLLS = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Scrolls", width = 15, anchor = "w", variable = LOOT_SCROLLS_INT, command = self.setColors)
		CHECK_SCROLLS.grid(row = 1, column = 0)

		CHECK_MAPS = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Maps", width = 15, anchor = "w", variable = LOOT_MAPS_INT, command = self.setColors)
		CHECK_MAPS.grid(row = 2, column = 0)

		CHECK_GEMS = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Gems", width = 15, anchor = "w", variable = LOOT_GEMS_INT, command = self.setColors)
		CHECK_GEMS.grid(row = 3, column = 0)

		# Column 2
		CHECK_REGS = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Reagents", width = 15, anchor = "w", variable = LOOT_REAGENTS_INT, command = self.setColors)
		CHECK_REGS.grid(row = 0, column = 1)
	
		CHECK_AMMO = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Ammo", width = 15, anchor = "w", variable = LOOT_AMMO_INT, command = self.setColors)
		CHECK_AMMO.grid(row = 1, column = 1)

		CHECK_SOLEN = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Solen", width = 15, anchor = "w", variable = LOOT_SOLEN_INT, command = self.setColors)
		CHECK_SOLEN.grid(row = 2, column = 1)

		CHECK_JUKA = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Juka", width = 15, anchor = "w", variable = LOOT_JUKA_INT, command = self.setColors)
		CHECK_JUKA.grid(row = 3, column = 1)
	
		# Column 3
		CHECK_KEYS = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Keys", width = 15, anchor = "w", variable = LOOT_KEYS_INT, command = self.setColors)
		CHECK_KEYS.grid(row = 0, column = 2)
	
		CHECK_RES = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Resources", width = 15, anchor = "w", variable = LOOT_RESOURCES_INT, command = self.setColors)
		CHECK_RES.grid(row = 1, column = 2)
	
		CHECK_CUT = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Cut corpses", width = 15, anchor = "w", variable = CUT_CORPSE_INT, command = self.setColors)
		CHECK_CUT.grid(row = 2, column = 2)
	
		CHECK_INST = Checkbutton(master = misc_frame, activebackground = ACTIVE, background = INACTIVE, text = "Instruments", width = 15, anchor = "w", variable = LOOT_INSTRUMENTS_INT, command = self.setColors)
		CHECK_INST.grid(row = 3, column = 2)

		# Spacer
		Label(master = WINDOW).pack()

		# equipment grid
		equip_frame = LabelFrame(master = WINDOW, text = "Equipment Loot:", height = 150, width = 400)
		equip_frame.pack()

		# Column 1
		CHECK_ARMOR = Checkbutton(master = equip_frame, activebackground = ACTIVE, background = INACTIVE, text = "Armor", width = 15, anchor = "w", variable = LOOT_ARMOR_INT, command = self.setColors)
		CHECK_ARMOR.grid(row = 0, column = 0)
	
		CHECK_WEPS = Checkbutton(master = equip_frame, activebackground = ACTIVE, background = INACTIVE, text = "Weapons", width = 15, anchor = "w", variable = LOOT_WEAPONS_INT, command = self.setColors)
		CHECK_WEPS.grid(row = 1, column = 0)

		# Column 2
		CHECK_JEWELS = Checkbutton(master = equip_frame, activebackground = ACTIVE, background = INACTIVE, text = "Jewels", width = 15, anchor = "w", variable = LOOT_JEWELS_INT, command = self.setColors)
		CHECK_JEWELS.grid(row = 0, column = 1)
	
		CHECK_SETS = Checkbutton(master = equip_frame, activebackground = ACTIVE, background = INACTIVE, text = "Set pieces", width = 15, anchor = "w", variable = LOOT_SETS_INT, command = self.setColors)
		CHECK_SETS.grid(row = 1, column = 1)

		# Column 3
		CHECK_SHIELDS = Checkbutton(master = equip_frame, activebackground = ACTIVE, background = INACTIVE, text = "Shields", width = 15, anchor = "w", variable = LOOT_SHIELDS_INT, command = self.setColors)
		CHECK_SHIELDS.grid(row = 0, column = 2)
	
		CHECK_ARTI = Checkbutton(master = equip_frame, activebackground = ACTIVE, background = INACTIVE, text = "Artifacts", width = 15, anchor = "w", variable = LOOT_ARTIFACTS_INT, command = self.setColors)
		CHECK_ARTI.grid(row = 1, column = 2)

		# Spacer
		Label(master = WINDOW).pack()

		# Loot rating
		Label(master = WINDOW, text = "Loot rating:").pack(anchor = "w")

		scale_rate = Scale(master = WINDOW, variable = LOOT_RATING_INT, to = 60, orient = HORIZONTAL, length = 400)
		scale_rate.pack(anchor = "w")

		# Buttons
		button_frame = Frame(master = WINDOW)
		button_frame.pack()

		Button(master = button_frame, text = "Set Loot Bag", background = "blue", foreground = "white", command = self.setLootBag).grid(row = 0, column = 0)

		Label(master = button_frame, width = 30).grid(row = 0, column = 1)

		Button(master = button_frame, text = "Save Settings", background = "green", foreground = "white", command = self.saveConfig).grid(row = 0, column = 2)

		self.setColors()
		
		try:
			while True:
				WINDOW.update()
		except KeyboardInterrupt:
			self.terminate()
		finally:
			self.terminate()

	def terminate(self):
		self.saveConfig()
		self.WINDOW.destroy()

#############
# MAIN
#############
# Do nothing, because we are called elsewhere
