from stealth import *
import json
import os
import time
import BodCycler_Crafting
import BodCycler_AI_Debugger
try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False


from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status, is_prize_enabled,
    swap_talisman
)

NPC_TYPES = [0x0190, 0x0191]       # Male/Female human
CTX_BUY = 1                        # Context Menu entry for 'Buy'
CTX_BOD = 3                        # Context Menu entry for 'Bulk Order Info'
BTN_ACCEPT_BOD = 1                 # 'Accept' button on BOD offer gump
BTN_DROP_BOD_1 = 5                 # First 'Drop' button inside a BOD book
BOD_GUMP_ID_SMALL = 0x9bade6ea    # Small BOD gump ID
BOD_GUMP_ID_LARGE = 0xbe0dad1e    # Large BOD gump ID
CLOTH_1 = 0x1766
CLOTH_2 = 0x1767
BOLT_OF_CLOTH_IDS = [0x0F95, 0x0F97, 0x0F9B, 0x0F9C]
SCISSORS = 0x0F9E
OIL_CLOTH = 0x175D
SANDALS = 0x170D
BOOK_TYPE = 0x2259                 # BOD Book type ID
BOD_TAILOR_COLOR  = 0x0483        # Hue of Tailor Bulk Order Deeds
BOD_SMITH_COLOR   = 0x044E        # Hue of Smith Bulk Order Deeds

# Smith BOD prizes that should be trashed (low-tier / unwanted reward types)
SMITH_JUNK_TYPES = [
    0x0F39,  # Pick-Shovel / Pickaxe
    0x0E86   # Pickaxe
]

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
    armorers, smiths = [], []
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            name  = GetName(npc).lower()
            title = GetAltName(npc).lower()
            if 'armorer' in name or 'armorer' in title:
                armorers.append(npc)
            elif 'blacksmith' in name or 'blacksmith' in title:
                smiths.append(npc)
    if armorers: return armorers[0]
    if smiths:   return smiths[0]
    return 0

def find_all_smiths():
    """Returns all blacksmith/armorer NPCs found within search distance."""
    SetFindDistance(12)
    armorers, smiths = [], []
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            name  = GetName(npc).lower()
            title = GetAltName(npc).lower()
            if 'guildmaster' in name or 'guildmaster' in title:
                continue
            if 'armorer' in name or 'armorer' in title:
                armorers.append(npc)
            elif 'blacksmith' in name or 'blacksmith' in title:
                smiths.append(npc)
    return armorers + smiths

def move_to_npc(npc):
    if npc > 0 and GetDistance(npc) > 1:
        newMoveXY(GetX(npc), GetY(npc), False, 1, True)
        Wait(500)

def sort_new_bods(config):
    """Smart Sorter: Small -> Origine | Valuable Large -> Conserva | Junk/Bone Large -> Scartare | Unknown -> Riprova."""
    origine_serial  = config.get("books", {}).get("Origine", 0)
    consegna_serial = config.get("books", {}).get("Consegna", 0)
    conserva_serial = config.get("books", {}).get("Conserva", 0)
    scartare_serial = config.get("books", {}).get("Scartare", 0)
    riprova_serial  = config.get("books", {}).get("Riprova", 0)

    # Auto-swap Scartare if nearly full (>=480 BODs)
    bbcrate = config.get("containers", {}).get("BodBookCrate", 0)
    cycle_type = config.get("cycle_type", "Tailor")
    if bbcrate and scartare_serial:
        from BodCycler_Crafting import _swap_full_book
        new_scartare = _swap_full_book(bbcrate, scartare_serial, cycle_type, config, "Scartare")
        if new_scartare != scartare_serial:
            scartare_serial = new_scartare
    cycle_type      = config.get("cycle_type", "Tailor")

    bod_color = BOD_SMITH_COLOR if cycle_type == "Smith" else BOD_TAILOR_COLOR
    FindTypeEx(BOD_TYPE, bod_color, Backpack(), False)
    loose_bods = list(GetFoundList())
    
    if not loose_bods: return
        
    AddToSystemJournal(f"Sorting {len(loose_bods)} new BOD(s) from Backpack...")
    
    for bod in loose_bods:
        world_save_guard()
        
        info = BodCycler_Crafting.parse_bod(bod, cycle_type)
        
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
            elif scartare_serial != 0:
                dest_book = scartare_serial
                dest_name = "Scartare"
        elif info.get('material', '').lower() == 'bone':
            # Small bone BODs can't be crafted — route to Scartare
            if scartare_serial != 0:
                dest_book = scartare_serial
                dest_name = "Scartare"
        else:
            if info.get('qty_needed', 1) == 0:
                # Already filled — route to Consegna to be traded
                if consegna_serial != 0:
                    dest_book = consegna_serial
                    dest_name = "Consegna"
            elif origine_serial != 0:
                # Unfilled small non-bone BOD → needs crafting
                dest_book = origine_serial
                dest_name = "Origine"
                
        if dest_book != 0:
            AddToSystemJournal(f"Routing BOD to {dest_name} book...")
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
    if runebook_serial == 0: return False
    start_x = GetX(Self())
    start_y = GetY(Self())
    
    offset = 5 if travel_method == "Recall" else 7
    btn_id = offset + (rune_index - 1) * 6
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
        if abs(GetX(Self()) - start_x) > 5 or abs(GetY(Self()) - start_y) > 5:
            Wait(1000) 
            return True
        Wait(100)
    return False

def process_prizes_at_home(trash_serial, material_crate_serial, dye_tub_serial, reward_crate_serial, rb_serial=0, cycle_type="Tailor"):
    """
    Handles post-cycle cleanup.
    Args:
        trash_serial: ID of the Trash Barrel.
        material_crate_serial: ID for storing processed resources (Cloth/Ore).
        reward_crate_serial: ID for storing high-value rewards (Runics/CBDs/Hammers).
        dye_tub_serial: ID of the Cloth Dye Tub.
        rb_serial: ID of the Runebook to avoid moving it.
        cycle_type: "Tailor" or "Smith" — controls which prizes and materials to process.
    """

    # 1. Clean up trash items (both modes)
    if trash_serial != 0:
        for junk_type in [0x175D, 0x170D]: # OIL_CLOTH (0x175D), SANDALS (0x170D)
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
        for c_type in [0x1766, 0x1767]: # CLOTH_1, CLOTH_2
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

        def _move_prize(item, name):
            AddToSystemJournal(f"Moving {name} to Reward Crate.")
            MoveItem(item, 0, reward_crate_serial, 0, 0, 0)
            Wait(800)
            stats = read_stats()
            stats["prizes_dropped"] = stats.get("prizes_dropped", 0) + 1
            write_stats(stats)
            BodCycler_AI_Debugger.send_prize_notification(name)

        if cycle_type == "Tailor":
            # Barbed Runic Sewing Kit: type 0x0F9D, color 0x0851
            FindType(0x0F9D, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                if GetColor(item) == 0x0851:
                    world_save_guard()
                    _move_prize(item, "Barbed Runic Kit")

            # Clothing Bless Deed: type 0x14F0, color 0x0000, tooltip check
            FindType(0x14F0, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                if GetColor(item) == 0x0000:
                    if "clothing bless deed" in GetTooltip(item).lower():
                        world_save_guard()
                        _move_prize(item, "Clothing Bless Deed")

        elif cycle_type == "Smith":
            # Runic Hammers: type 0x13E3, any non-zero color = a runic tier
            # Color matches ore hues: DC=0x0973, Shadow=0x0966, Copper=0x096D,
            # Bronze=0x0972, Gold=0x08A5, Agapite=0x0979, Verite=0x089F, Valorite=0x08AB
            from bod_data import prize_names as _prize_names
            runic_hues = {
                0x0973: "Dull Copper Runic Hammer",
                0x0966: "Shadow Iron Runic Hammer",
                0x096D: "Copper Runic Hammer",
                0x0972: "Bronze Runic Hammer",
                0x08A5: "Gold Runic Hammer",
                0x0979: "Agapite Runic Hammer",
                0x089F: "Verite Runic Hammer",
                0x08AB: "Valorite Runic Hammer",
            }
            FindType(0x13E3, Backpack())  # Smith's Hammer base type
            for item in GetFoundList():
                if check_abort(): return
                hue = GetColor(item)
                if hue in runic_hues:
                    world_save_guard()
                    _move_prize(item, runic_hues[hue])

            # Power Scrolls: type 0x14F0 — check tooltip for "power scroll"
            FindType(0x14F0, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                tooltip = GetTooltip(item).lower()
                if "power scroll" in tooltip:
                    world_save_guard()
                    _move_prize(item, f"Power Scroll ({GetTooltip(item).split('|')[0].strip()})")

            # Ancient Smith's Hammer: type 0x0FB4
            FindType(0x0FB4, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                world_save_guard()
                _move_prize(item, "Ancient Smith's Hammer")

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

    trash_serial = config.get("containers", {}).get("TrashBarrel", 0)
    crate_serial = config.get("containers", {}).get("MaterialCrate", 0)
    dye_tub_serial = config.get("containers", {}).get("ClothDyeTub", 0)
    reward_crate_serial = config.get("containers", {}).get("RewardCrate", 0)

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
        travel_to(rb_serial, travel_method, rune_idx)
        for npc in find_all_fn():
            if npc not in npc_list:
                npc_list.append(npc)
        if npc_list:
            break  # Found NPCs here — no need to travel further

    if not npc_list:
        AddToSystemJournal(f"execute_trade_loop: No {npc_label} found at any configured location.")
        return

    AddToSystemJournal(f"execute_trade_loop: Found {len(npc_list)} NPC(s) to cycle through.")

    request_new_bod(npc_list[0])
    sort_new_bods(config)
    Wait(1500)

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

        if GetType(consegna_serial) == BOOK_TYPE:
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
                BodCycler_AI_Debugger.send_error_alert("trade_failure", hex(bod_to_give), "All NPCs failed", False)
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
        ws1_index = config.get("travel", {}).get("Runes", {}).get("WorkSpot1", 1)
        travel_to(rb_serial, travel_method, ws1_index)

        if home_x != 0 and home_y != 0:
            newMoveXY(home_x, home_y, True, 0, True)

        process_prizes_at_home(trash_serial, crate_serial, dye_tub_serial, reward_crate_serial, rb_serial, cycle_type)

    AddToSystemJournal("Route Complete. Cycle successful.")

if __name__ == '__main__':
    execute_trade_loop()