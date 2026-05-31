from stealth import *
import json
import os
import time
from datetime import datetime
import BodCycler_Crafting

from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status, is_prize_enabled,
    swap_talisman, world_save_guard,
    NPC_TYPES, CTX_BUY, CTX_BOD,
    BTN_ACCEPT_BOD, BTN_DROP_BOD_1,
    BOD_GUMP_ID_SMALL, BOD_GUMP_ID_LARGE,
    BOD_TAILOR_COLOR, BOD_SMITH_COLOR,
    CLOTH_1, CLOTH_2, BOLT_OF_CLOTH_IDS,
    SCISSORS, OIL_CLOTH, SANDALS,
    SMITH_JUNK_TYPES, log_event, send_prize_notification
)

# Persists across execute_trade_loop() calls — True only on the very first run
# so the bot requests a BOD on arrival. Subsequent cycles already have one pre-fetched.
_first_bod_taken = False

def find_tailor():
    SetFindDistance(10) 
    weavers, tailors = [], []
    
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            name = GetName(npc).lower()
            title = GetAltName(npc).lower()
            if 'weaver' in name or 'weaver' in title:
                weavers.append(npc)
            elif 'tailor' in name or 'tailor' in title:
                tailors.append(npc)
                
    if weavers: return weavers[0]
    if tailors: return tailors[0]
    return 0

def find_all_tailors():
    """Returns all tailor/weaver NPCs found within search distance."""
    SetFindDistance(12)
    weavers, tailors = [], []
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            name = GetName(npc).lower()
            title = GetAltName(npc).lower()
            if 'guildmaster' in name or 'guildmaster' in title:
                continue
            if 'weaver' in name or 'weaver' in title:
                weavers.append(npc)
            elif 'tailor' in name or 'tailor' in title:
                tailors.append(npc)
    return weavers + tailors

def find_smith():
    SetFindDistance(10)
    smiths, weaponsmiths = [], []
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            combined = (GetName(npc) + ' ' + GetAltName(npc)).lower()
            if 'blacksmith' in combined:
                smiths.append(npc)
            elif 'weaponsmith' in combined:
                weaponsmiths.append(npc)
    if smiths: return smiths[0]
    if weaponsmiths: return weaponsmiths[0]
    return 0

def find_all_smiths():
    """Returns all blacksmith/weaponsmith NPCs found within search distance."""
    SetFindDistance(12)
    smiths, weaponsmiths = [], []
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            combined = (GetName(npc) + ' ' + GetAltName(npc)).lower()
            if 'guildmaster' in combined:
                continue
            if 'blacksmith' in combined:
                smiths.append(npc)
            elif 'weaponsmith' in combined:
                weaponsmiths.append(npc)
    return smiths + weaponsmiths

def move_to_npc(npc):
    if npc > 0 and GetDistance(npc) > 1:
        newMoveXY(GetX(npc), GetY(npc), False, 1, True)
        Wait(500)

def _log_route(info, dest):
    """One compact routing line per BOD: type material amount quality -> destination.
    'dest' is the display label (Origine is shown as 'Fuel' — BODs queued for crafting)."""
    btype = "Large" if (info and info.get("is_large")) else "Small"
    mat = (info.get("material") if info else "") or "?"
    qty = (info.get("qty_total") if info else "") or "?"
    qual = "Exc" if (info and info.get("is_except")) else "Norm"
    log_event("ROUTE", f"{btype} {mat} {qty} {qual} -> {dest}")


def sort_new_bods(config):
    """Smart Sorter: Small -> Origine | Valuable Large -> Conserva | Junk/Bone Large -> Scartare | Unknown -> Riprova."""
    origine_serial  = config.get("books", {}).get("Origine", 0)
    consegna_serial = config.get("books", {}).get("Consegna", 0)
    conserva_serial = config.get("books", {}).get("Conserva", 0)
    scartare_serial = config.get("books", {}).get("Scartare", 0)
    riprova_serial  = config.get("books", {}).get("Riprova", 0)

    cycle_type = config.get("cycle_type", "Tailor")
    bod_color = BOD_SMITH_COLOR if cycle_type == "Smith" else BOD_TAILOR_COLOR
    FindTypeEx(BOD_TYPE, bod_color, Backpack(), False)
    loose_bods = list(GetFoundList())
    
    if not loose_bods: return
        
    #AddToSystemJournal(f"Sorting {len(loose_bods)} new BOD(s) from Backpack...")
    
    trash_dc = config.get("trade", {}).get("trash_dc_bods", False)
    trash_scartare = config.get("trade", {}).get("trash_scartare_bods", False)

    for bod in loose_bods:
        world_save_guard()

        info = BodCycler_Crafting.parse_bod(bod, cycle_type)

        if trash_dc and info and info.get('material', '').lower() == 'dull copper':
            AddToSystemJournal(f"[DC Killswitch] Dropping Dull Copper BOD {hex(bod)} on floor.")
            _log_route(info, "Trash")
            DropHere(bod)
            Wait(600)
            continue

        dest_book = 0
        dest_name = ""
        parsed_bod = None

        if not info or info.get('item_name', '').lower() == "unknown":
            AddToSystemJournal(f"WARNING: Unrecognised BOD {hex(bod)} — routing to Riprova for manual review.")
            if riprova_serial != 0:
                dest_book = riprova_serial
                dest_name = "Riprova"
        elif info.get('is_large'):
            # STRICT SCARTARE LOGIC (Identical to Crafting script using prize_id)
            # AddToSystemJournal(info) # Debug
            is_scartare = False
            if info.get('material', '').lower() == "bone":
                is_scartare = True
            elif not is_prize_enabled(info.get('prize_id'), config):
                is_scartare = True
                
            if not is_scartare and conserva_serial != 0:
                dest_book = conserva_serial
                dest_name = "Conserva"
                stats = read_stats()
                stats["prized_large"] = stats.get("prized_large", 0) + 1
                write_stats(stats)

                # Format exactly what the Assembler expects
                parsed_bod = {
                    "type": "Large",
                    "item": info['item_name'].lower(),
                    "quality": "Exceptional" if info.get('is_except') else "Normal",
                    "material": info.get('material', 'Iron'),
                    "amount": info.get('qty_needed', 20),
                    "category": info['item_name'], # For Large BODs, item_name equates to the Category Set
                    "prize_id": info.get('prize_id')
                }
            else:
                # Classified as Scartare. Name it regardless of book config so the
                # killswitch can trash it even when no Scartare book is set.
                dest_name = "Scartare"
                if scartare_serial != 0:
                    dest_book = scartare_serial
        elif info.get('material', '').lower() == 'bone':
            # Small bone BODs can't be crafted — classified as Scartare.
            dest_name = "Scartare"
            if scartare_serial != 0:
                dest_book = scartare_serial
        else:
            if info.get('qty_needed', 1) == 0:
                # Already filled small — prize-enabled goes to Conserva, otherwise Consegna
                if is_prize_enabled(info.get('prize_id'), config) and conserva_serial != 0:
                    dest_book = conserva_serial
                    dest_name = "Conserva"
                    parsed_bod = {
                        "type": "Small",
                        "item": info['item_name'].lower(),
                        "quality": "Exceptional" if info.get('is_except') else "Normal",
                        "material": info.get('material', 'Iron'),
                        "amount": info.get('qty_total', 20),
                        "category": info.get('cat', 'Small Bods'),
                    }
                elif consegna_serial != 0:
                    dest_book = consegna_serial
                    dest_name = "Consegna"
            elif origine_serial != 0:
                # Unfilled small non-bone BOD → needs crafting
                dest_book = origine_serial
                dest_name = "Origine"
                
        if trash_scartare and dest_name == "Scartare":
            AddToSystemJournal(f"[Scartare Killswitch] Dropping Scartare BOD {hex(bod)} on floor.")
            _log_route(info, "Trash")
            DropHere(bod)
            Wait(600)
            close_all_gumps()
            continue

        if dest_book != 0:
            AddToSystemJournal(f"Routing BOD to {dest_name} book...")
            _log_route(info, "Fuel" if dest_name == "Origine" else dest_name)
            MoveItem(bod, 0, dest_book, 0, 0, 0)
            Wait(1000)
            
            # --- PERFECT STATE MANAGEMENT ---
            if dest_name == "Conserva" and parsed_bod:
                try:
                    import BodCycler_Assembler
                    BodCycler_Assembler.append_to_inventory(parsed_bod, conserva_serial)
                except Exception as e:
                    AddToSystemJournal(f"Failed to push BOD to Assembler JSON: {e}")
                
        close_all_gumps()

def extract_bod_from_book(book_serial):
    close_all_gumps()
    FindType(BOD_TYPE, Backpack())
    before_bods = GetFoundList()
    
    UseObject(book_serial)
    
    t = time.time()
    found_idx = -1
    while time.time() - t < 3:
        world_save_guard()
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == BOOK_GUMP_ID:
                found_idx = i
                break
        if found_idx != -1: break
        Wait(100) 
        
    if found_idx == -1: return 0
        
    NumGumpButton(found_idx, BTN_DROP_BOD_1)
    Wait(1500) 
    CloseSimpleGump(found_idx)
    Wait(500)
    
    FindType(BOD_TYPE, Backpack())
    after_bods = GetFoundList()
    new_bods = [b for b in after_bods if b not in before_bods]
    if new_bods: return new_bods[0]
    return 0

def trade_bod(npc, bod_serial):
    if bod_serial == 0: return False
    world_save_guard()
    move_to_npc(npc)
    MoveItem(bod_serial, 1, npc, 0, 0, 0)
    Wait(3500)
    FindType(BOD_TYPE, Backpack())
    if bod_serial in GetFoundList():
        AddToSystemJournal(f"trade_bod: BOD {hex(bod_serial)} still in backpack — MoveItem failed.")
        return False
    return True

def find_bod_offer_gump():
    for i in range(GetGumpsCount()):
        g = GetGumpInfo(i)
        if g.get('GumpID') in [BOD_GUMP_ID_SMALL, BOD_GUMP_ID_LARGE]:
            return i
        if 'XmfHTMLGumpColor' in g:
            for entry in g['XmfHTMLGumpColor']:
                if entry.get('ClilocID') == 1045135:
                    return i
    return -1

def request_new_bod(npc):
    world_save_guard()
    move_to_npc(npc)
    SetContextMenuHook(npc, CTX_BOD)
    Wait(250)
    RequestContextMenu(npc)

    t = time.time()
    found_idx = -1
    while time.time() - t < 3:
        world_save_guard()
        found_idx = find_bod_offer_gump()
        if found_idx != -1: break
        Wait(100)

    if found_idx != -1:
        NumGumpButton(found_idx, BTN_ACCEPT_BOD)
        Wait(1200)
        return True

    AddToSystemJournal("request_new_bod: No BOD offer gump — NPC may be on cooldown.")
    return False

def buy_and_cut_cloth(npc, amount=80):
    world_save_guard()
    move_to_npc(npc)
    
    try: ClearAutoBuy()
    except Exception: pass
    try: ClearBuyList()
    except Exception: pass
    try: ClearBuy()
    except Exception: pass

    bought_any = False
    for bolt_id in BOLT_OF_CLOTH_IDS:
        if check_abort(): return
        if bought_any: break
            
        try: AutoBuy(bolt_id, 0xFFFF, amount)
        except Exception: return
            
        world_save_guard()
        SetContextMenuHook(npc, CTX_BUY)
        Wait(250)
        world_save_guard()
        RequestContextMenu(npc)
        Wait(999)
        
        try: 
            AutoBuy(bolt_id, 0xFFFF, 0)
            ClearAutoBuy()
        except Exception: pass
            
        FindType(bolt_id, Backpack())
        if FindCount() > 0: bought_any = True
            
    if not bought_any: return
    
    FindType(SCISSORS, Backpack())
    if FindCount() == 0: return
    scissors = FindItem()
    
    for bolt_id in BOLT_OF_CLOTH_IDS:
        if check_abort(): return
        FindType(bolt_id, Backpack())
        bolts = GetFoundList()
        
        for bolt in bolts:
            if check_abort(): return
            world_save_guard()
            UseObject(scissors)
            WaitForTarget(2000)
            TargetToObject(bolt)
            Wait(700)

def travel_to(runebook_serial, travel_method, rune_index):
    """Recalls to a single rune. Returns True on success, 'blocked' if location blocked,
    'disturbed' if concentration interrupted, False if gump never appeared."""
    if runebook_serial == 0: return False
    start_x = GetX(Self())
    start_y = GetY(Self())

    offset = 5 if travel_method == "Recall" else 7
    btn_id = offset + (rune_index - 1) * 6

    cast_start = datetime.now()
    UseObject(runebook_serial)

    t = time.time()
    gump_pressed = False
    while time.time() - t < 3:
        world_save_guard()
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == 0x554B87F3:
                NumGumpButton(i, btn_id)
                gump_pressed = True
                break
        if gump_pressed: break
        Wait(100)

    if not gump_pressed: return False

    t = time.time()
    while time.time() - t < 6:
        world_save_guard()
        now = datetime.now()
        if InJournalBetweenTimes("That location is blocked", cast_start, now) != -1:
            Wait(900)
            return 'blocked'
        if InJournalBetweenTimes("Your concentration is disturbed", cast_start, now) != -1:
            return 'disturbed'
        if abs(GetX(Self()) - start_x) > 5 or abs(GetY(Self()) - start_y) > 5:
            Wait(1000)
            return True
        Wait(100)
    # Gump was pressed but no 5-tile movement detected — recall likely landed
    # very close to start position (same area). Treat as success.
    return True if gump_pressed else False


def travel_to_with_fallback(runebook_serial, travel_method, rune_indices):
    """Tries rune_indices in order. Blocked → next rune. Disturbed → retry same rune."""
    idx_iter = iter(rune_indices)
    current  = next(idx_iter, None)
    while current is not None:
        while True:  # retry loop for disturbed
            result = travel_to(runebook_serial, travel_method, current)
            if result is True:
                return True
            elif result == 'disturbed':
                AddToSystemJournal(f"travel_to_with_fallback: concentration disturbed on rune {current} — retrying.")
                Wait(1500)
                continue  # retry same rune
            elif result == 'blocked':
                AddToSystemJournal(f"travel_to_with_fallback: rune {current} blocked — trying next.")
                break  # advance to next rune
            else:
                AddToSystemJournal(f"travel_to_with_fallback: rune {current} failed — trying next.")
                break
        current = next(idx_iter, None)
    AddToSystemJournal("travel_to_with_fallback: all runes exhausted.")
    return False

CONSUMABLE_CRATE_CAP = 125

def process_prizes_at_home(trash_serial, material_crate_serial, dye_tub_serial, reward_crate_serial, rb_serial=0, cycle_type="Tailor",
                           prospector_crate=0, powder_crate=0, config=None):
    """
    Handles post-cycle cleanup.
    Args:
        trash_serial: ID of the Trash Barrel.
        material_crate_serial: ID for storing processed resources (Cloth/Ore).
        reward_crate_serial: ID for storing high-value rewards (Runics/CBDs/Hammers).
        dye_tub_serial: ID of the Cloth Dye Tub.
        rb_serial: ID of the Runebook to avoid moving it.
        cycle_type: "Tailor" or "Smith" — controls which prizes and materials to process.
        config: loaded config dict; loaded fresh if not provided.
    """
    if config is None:
        config = load_config() or {}

    # 1. Clean up trash items (both modes)
    if trash_serial != 0:
        for junk_type in [OIL_CLOTH, SANDALS]:
            FindType(junk_type, Backpack())
            for junk in GetFoundList():
                if check_abort(): return
                world_save_guard()
                MoveItem(junk, 0, trash_serial, 0, 0, 0)
                Wait(800)

        if cycle_type == "Smith":
            for junk_type in SMITH_JUNK_TYPES:
                FindType(junk_type, Backpack())
                for junk in GetFoundList():
                    if check_abort(): return
                    world_save_guard()
                    MoveItem(junk, 0, trash_serial, 0, 0, 0)
                    Wait(800)

    # 2. Dye colored cloth and move to MATERIAL crate (Tailor only)
    if cycle_type == "Tailor" and material_crate_serial != 0:
        for c_type in [CLOTH_1, CLOTH_2]:
            FindType(c_type, Backpack())
            for cloth in GetFoundList():
                if check_abort(): return
                world_save_guard()
                if dye_tub_serial != 0 and GetColor(cloth) != 0x0000:
                    UseObject(dye_tub_serial)
                    WaitForTarget(2000)
                    if TargetPresent():
                        TargetToObject(cloth)
                        Wait(600)
                MoveItem(cloth, 0, material_crate_serial, 0, 0, 0)
                Wait(800)

    # 3. Move high-value prizes to REWARD crate
    if reward_crate_serial != 0:

        def _move_prize(item, name, prize_id=None):
            AddToSystemJournal(f"Moving {name} to Reward Crate.")
            MoveItem(item, 0, reward_crate_serial, 0, 0, 0)
            Wait(800)
            stats = read_stats()
            stats["prizes_dropped"] = stats.get("prizes_dropped", 0) + 1
            write_stats(stats)
            log_event("PRIZE", f"Prize obtained and routed: {name}")
            if prize_id is not None:
                try:
                    send_prize_notification(name, prize_id, config)
                except Exception:
                    pass

        if cycle_type == "Tailor":
            # Barbed Runic Sewing Kit: type 0x0F9D, color 0x0851
            FindType(0x0F9D, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                if GetColor(item) == 0x0851:
                    world_save_guard()
                    _move_prize(item, "Barbed Runic Kit", prize_id=24)

            # Clothing Bless Deed: type 0x14F0, color 0x0000, tooltip check
            FindType(0x14F0, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                if GetColor(item) == 0x0000:
                    if "clothing bless deed" in GetTooltip(item).lower():
                        world_save_guard()
                        _move_prize(item, "Clothing Bless Deed", prize_id=23)

        elif cycle_type == "Smith":
            # Runic Hammers: type 0x13E3, any non-zero color = a runic tier.
            # prize_id from bod_data: DC=6, Shadow=8, Copper=10, Bronze=12,
            # Gold=17, Agapite=19, Verite=21, Valorite=22
            runic_hues = {
                0x0973: (6,  "Dull Copper Runic Hammer"),
                0x0966: (8,  "Shadow Iron Runic Hammer"),
                0x096D: (10, "Copper Runic Hammer"),
                0x0972: (12, "Bronze Runic Hammer"),
                0x08A5: (17, "Gold Runic Hammer"),
                0x0979: (19, "Agapite Runic Hammer"),
                0x089F: (21, "Verite Runic Hammer"),
                0x08AB: (22, "Valorite Runic Hammer"),
            }
            def _route_prize(item, prize_id, label):
                """Send to reward crate if prize is enabled, trash if disabled (and trash exists)."""
                if is_prize_enabled(prize_id, config):
                    _move_prize(item, label, prize_id=prize_id)
                elif trash_serial:
                    AddToSystemJournal(f"Trashing {label} (prize disabled).")
                    MoveItem(item, 1, trash_serial, 0, 0, 0)
                    Wait(600)
                else:
                    _move_prize(item, label, prize_id=prize_id)  # no trash configured — keep in reward crate

            FindType(0x13E3, Backpack())  # Smith's Hammer base type
            for item in GetFoundList():
                if check_abort(): return
                hue = GetColor(item)
                if hue not in runic_hues:
                    continue
                prize_id, label = runic_hues[hue]
                world_save_guard()
                _route_prize(item, prize_id, label)

            # Power Scrolls: type 0x14F0 — check tooltip for "power scroll"
            ps_prize_ids = {"105": 9, "110": 11, "115": 14, "120": 16}
            FindType(0x14F0, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                tooltip = GetTooltip(item).lower()
                if "power scroll" not in tooltip:
                    continue
                label = f"Power Scroll ({GetTooltip(item).split('|')[0].strip()})"
                prize_id = next((pid for val, pid in ps_prize_ids.items() if val in tooltip), None)
                world_save_guard()
                if prize_id:
                    _route_prize(item, prize_id, label)
                else:
                    _move_prize(item, label)  # unknown PS value — keep

            # Ancient Smith's Hammers
            ash_prize_ids = {"+10": 13, "+15": 15, "+30": 18, "+60": 20}
            FindType(0x13E4, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                tooltip = GetTooltip(item).lower()
                prize_id = next((pid for val, pid in ash_prize_ids.items() if val in tooltip), None)
                world_save_guard()
                if prize_id:
                    _route_prize(item, prize_id, "Ancient Smith's Hammer")
                else:
                    _move_prize(item, "Ancient Smith's Hammer")  # unknown bonus — keep

    # 4. Consumables with capped crates (both cycle types)
    def _store_consumable(item_type, crate_serial, label):
        """Move item to crate if under cap, otherwise trash it."""
        FindType(item_type, Backpack())
        backpack_items = GetFoundList()
        if not backpack_items:
            return
        if crate_serial:
            UseObject(crate_serial)
            Wait(800)
            FindType(item_type, crate_serial)
            crate_count = FindCount()
        else:
            crate_count = 0
        for item in backpack_items:
            if check_abort(): return
            world_save_guard()
            if crate_serial:
                if crate_count < CONSUMABLE_CRATE_CAP:
                    AddToSystemJournal(f"Storing {label} ({crate_count + 1}/{CONSUMABLE_CRATE_CAP}).")
                    MoveItem(item, 1, crate_serial, 0, 0, 0)
                    Wait(600)
                    crate_count += 1
                else:
                    AddToSystemJournal(f"{label} crate full ({CONSUMABLE_CRATE_CAP}) — trashing.")
                    if trash_serial:
                        MoveItem(item, 1, trash_serial, 0, 0, 0)
                        Wait(600)
            elif trash_serial:
                MoveItem(item, 1, trash_serial, 0, 0, 0)
                Wait(600)

    _store_consumable(0x0FB4, prospector_crate, "Prospector's Tool")
    _store_consumable(0x1006, powder_crate,     "Powder of Fortifying")

    # 5. Final cloth sweep — catches any colored cloth missed by step 2
    if cycle_type == "Tailor" and material_crate_serial != 0:
        for c_type in [CLOTH_1, CLOTH_2]:
            FindType(c_type, Backpack())
            for cloth in GetFoundList():
                if check_abort(): return
                world_save_guard()
                if dye_tub_serial != 0 and GetColor(cloth) != 0x0000:
                    UseObject(dye_tub_serial)
                    WaitForTarget(2000)
                    if TargetPresent():
                        TargetToObject(cloth)
                        Wait(600)
                MoveItem(cloth, 0, material_crate_serial, 0, 0, 0)
                Wait(800)

def execute_trade_loop():
    config = load_config()
    if not config: return

    target_trades = config.get("trade", {}).get("target_trades")
    if target_trades is None:
        AddToSystemJournal("Error: 'target_trades' missing from config.")
        return
    buy_cloth_amount  = config.get("trade", {}).get("buy_cloth_amount", 80)
    buy_cloth_enabled = config.get("trade", {}).get("buy_cloth_enabled", True)
    cycle_type        = config.get("cycle_type", "Tailor")
    swap_talisman(cycle_type, config)

    consegna_serial = config.get("books", {}).get("Consegna", 0)
    rb_serial = config.get("travel", {}).get("RuneBook", 0)
    travel_method = config.get("travel", {}).get("Method", "Recall")
    home_x = config.get("home", {}).get("X", 0)
    home_y = config.get("home", {}).get("Y", 0)

    trash_serial        = config.get("containers", {}).get("TrashBarrel", 0)
    crate_serial        = config.get("containers", {}).get("MaterialCrate", 0)
    dye_tub_serial      = config.get("containers", {}).get("ClothDyeTub", 0)
    reward_crate_serial = config.get("containers", {}).get("RewardCrate", 0)
    prospector_crate    = config.get("containers", {}).get("ProspectorCrate", 0)
    powder_crate        = config.get("containers", {}).get("PowderCrate", 0)

    if consegna_serial == 0: return

    close_all_gumps()

    # Select rune keys and NPC finder based on cycle type.
    # Smith1/Smith2 are in config already. Set a rune index to 0 to skip that location.
    if cycle_type == "Smith":
        rune_keys   = ["Smith1", "Smith2"]
        find_all_fn = find_all_smiths
        npc_label   = "blacksmiths"
    else:
        rune_keys   = ["Tailor1", "Tailor2", "Tailor3"]
        find_all_fn = find_all_tailors
        npc_label   = "tailors"

    # Collect all available NPCs. Travel to each configured rune location
    # in order and stop as soon as at least one NPC is found. If NPCs are at
    # different locations (e.g. Tailor1 + Tailor3), set Tailor2 = 0 to skip it.
    npc_list = []
    for rune_key in rune_keys:
        rune_idx = config.get("travel", {}).get("Runes", {}).get(rune_key, 0)
        if rune_idx == 0:
            continue
        # Build primary + backup: e.g. Smith1 primary, Smith2 backup
        backup_key = rune_key[:-1] + str(int(rune_key[-1]) + 1)
        backup_idx = config.get("travel", {}).get("Runes", {}).get(backup_key, 0)
        indices = [rune_idx] + ([backup_idx] if backup_idx else [])
        travel_to_with_fallback(rb_serial, travel_method, indices)
        for npc in find_all_fn():
            if npc not in npc_list:
                npc_list.append(npc)
        if npc_list:
            break  # Found NPCs here — no need to travel further

    if not npc_list:
        # Nudge 4 tiles in each cardinal and re-search before giving up
        cx, cy = GetX(Self()), GetY(Self())
        for label, dx, dy in [("North", 0, -4), ("East", 4, 0), ("West", -4, 0), ("South", 0, 4)]:
            AddToSystemJournal(f"execute_trade_loop: No {npc_label} found — trying {label}.")
            newMoveXY(cx + dx, cy + dy, False, 1, True)
            Wait(800)
            for npc in find_all_fn():
                if npc not in npc_list:
                    npc_list.append(npc)
            newMoveXY(cx, cy, False, 1, True)  # return to landing tile
            Wait(600)
            if npc_list:
                break

    if not npc_list:
        AddToSystemJournal(f"execute_trade_loop: No {npc_label} found after nudge search — returning to master cycle.")
        return

    AddToSystemJournal(f"execute_trade_loop: Found {len(npc_list)} NPC(s) to cycle through.")

    global _first_bod_taken
    trades_completed = 0
    npc_index = 0
    consecutive_failures = 0
    AddToSystemJournal(f"execute_trade_loop: Starting — target {target_trades} trades.")

    while trades_completed < target_trades:
        if check_abort():
            AddToSystemJournal("execute_trade_loop: Stop signal received.")
            break
        world_save_guard()

        npc_pos = npc_index % len(npc_list)
        current_npc = npc_list[npc_pos]

        if not _first_bod_taken:
            request_new_bod(current_npc)
            sort_new_bods(config)
            Wait(1500)
            _first_bod_taken = True

        if GetType(consegna_serial) == BOD_BOOK_TYPE:
            bod_to_give = extract_bod_from_book(consegna_serial)
        else:
            FindType(BOD_TYPE, consegna_serial)
            bod_to_give = FindItem() if FindCount() > 0 else 0

        if bod_to_give == 0:
            AddToSystemJournal("execute_trade_loop: Consegna book is empty — stopping.")
            break

        if not trade_bod(current_npc, bod_to_give):
            consecutive_failures += 1
            AddToSystemJournal(f"execute_trade_loop: Trade failed with NPC #{npc_pos + 1} — rotating. ({consecutive_failures}/{len(npc_list)} failures)")
            sort_new_bods(config)  # routes the failed BOD back to Consegna
            npc_index += 1
            if consecutive_failures >= len(npc_list):
                AddToSystemJournal("execute_trade_loop: All NPCs on cooldown or unreachable — stopping.")
                log_event("TRADE_FAILURE", f"All NPCs failed for BOD {hex(bod_to_give)} — trade loop halted.")
                break
            Wait(500)
            continue

        consecutive_failures = 0
        trades_completed += 1
        AddToSystemJournal(f"execute_trade_loop: Trade {trades_completed}/{target_trades} complete (NPC #{npc_pos + 1}).")

        got_bod = request_new_bod(current_npc)
        if not got_bod:
            AddToSystemJournal("execute_trade_loop: No new BOD offer — NPC may be on cooldown.")
        sort_new_bods(config)
        npc_index += 1  # rotate to next NPC for next trade
        Wait(1500)

    if trades_completed > 0:
        stats = read_stats()
        stats["bods_traded"] = stats.get("bods_traded", 0) + trades_completed
        write_stats(stats)

    if not check_abort():
        if cycle_type == "Tailor" and buy_cloth_enabled:
            buy_and_cut_cloth(npc_list[0], buy_cloth_amount)
        elif cycle_type == "Tailor":
            AddToSystemJournal("Buy Cloth: OFF — skipping.")
        # Smith: ore is pre-stocked in MaterialCrate — no NPC buying needed.
        ws1_index = config.get("travel", {}).get("Runes", {}).get("WorkSpot1", 0)
        ws2_index = config.get("travel", {}).get("Runes", {}).get("WorkSpot2", 0)
        ws_indices = [i for i in [ws1_index, ws2_index] if i]
        if ws_indices:
            travel_to_with_fallback(rb_serial, travel_method, ws_indices)

        if home_x != 0 and home_y != 0:
            newMoveXY(home_x, home_y, True, 0, True)

        process_prizes_at_home(trash_serial, crate_serial, dye_tub_serial, reward_crate_serial, rb_serial, cycle_type,
                               prospector_crate=prospector_crate, powder_crate=powder_crate, config=config)

    AddToSystemJournal("Route Complete. Cycle successful.")

if __name__ == '__main__':
    execute_trade_loop()