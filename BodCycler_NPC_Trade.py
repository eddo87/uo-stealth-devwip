from stealth import *
import json
import os
import time
from datetime import datetime
from bod_data import *

import BodCycler_Crafting
try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False


from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status
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

CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None

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

def move_to_npc(npc):
    if npc > 0 and GetDistance(npc) > 1:
        newMoveXY(GetX(npc), GetY(npc), False, 1, True)
        Wait(500)

def sort_new_bods(config):
    """Smart Sorter: Small -> Origine | Valuable Large -> Conserva | Junk Large -> Scartare."""
    origine_serial = config.get("books", {}).get("Origine", 0)
    conserva_serial = config.get("books", {}).get("Conserva", 0)
    scartare_serial = config.get("books", {}).get("Scartare", 0)
    
    FindType(BOD_TYPE, Backpack())
    loose_bods = list(GetFoundList())
    
    if not loose_bods: return
        
    AddToSystemJournal(f"Sorting {len(loose_bods)} new BOD(s) from Backpack...")
    
    for bod in loose_bods:
        world_save_guard()
        
        # We rely on the central parse_bod logic from bod_data to perfectly identify the BOD properties!
        info = BodCycler_Crafting.parse_bod(bod)
        
        dest_book = 0
        dest_name = ""
        parsed_bod = None
        
        if not info or info.get('item_name') == "Unknown":
            AddToSystemJournal(f"WARNING: Failed to parse BOD {hex(bod)}. Routing to Scartare for safety.")
            if scartare_serial != 0:
                dest_book = scartare_serial
                dest_name = "Scartare"
        elif info.get('is_large'):
            # STRICT SCARTARE LOGIC (Identical to Crafting script using prize_id)
            # AddToSystemJournal(info) # Debug
            is_scartare = False
            if info.get('material', '').lower() == "bone":
                is_scartare = True
            elif info.get('prize_id') not in [23, 24]:
                is_scartare = True
                
            if not is_scartare and conserva_serial != 0:
                dest_book = conserva_serial
                dest_name = "Conserva"
                
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
            # Small BODs go to Origine to be crafted
            if origine_serial != 0:
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
                    BodCycler_Assembler.append_to_inventory(parsed_bod)
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
    Wait(2000) 
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

def buy_and_cut_cloth(npc, amount=80):
    world_save_guard()
    move_to_npc(npc)
    
    try: ClearAutoBuy()
    except: pass
    try: ClearBuyList()
    except: pass
    try: ClearBuy()
    except: pass

    bought_any = False
    for bolt_id in BOLT_OF_CLOTH_IDS:
        if check_abort(): return
        if bought_any: break
            
        try: AutoBuy(bolt_id, 0xFFFF, amount)
        except: return
            
        world_save_guard()
        SetContextMenuHook(npc, CTX_BUY)
        Wait(500)
        world_save_guard()
        RequestContextMenu(npc)
        Wait(1500)
        
        try: 
            AutoBuy(bolt_id, 0xFFFF, 0)
            ClearAutoBuy()
        except: pass
            
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

def process_prizes_at_home(trash_serial, material_crate_serial, dye_tub_serial, reward_crate_serial, rb_serial=0):
    """
    Handles post-cycle cleanup. 
    Args:
        trash_serial: ID of the Trash Barrel.
        material_crate_serial: ID for storing processed resources (Cloth).
        reward_crate_serial: ID for storing high-value rewards (Runics/CBDs).
        dye_tub_serial: ID of the Cloth Dye Tub.
        rb_serial: ID of the Runebook to avoid moving it.
    """

    # 1. Clean up trash items
    if trash_serial != 0:
        for junk_type in [0x175D, 0x170D]: # OIL_CLOTH (0x175D), SANDALS (0x170D)
            FindType(junk_type, Backpack())
            for junk in GetFoundList():
                if check_abort(): return
                world_save_guard()
                MoveItem(junk, 0, trash_serial, 0, 0, 0)
                Wait(800)

    # 2. Dye colored cloth and move to MATERIAL crate
    if material_crate_serial != 0:
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
                # Note: Cloth moves to material_crate_serial
                MoveItem(cloth, 0, material_crate_serial, 0, 0, 0)
                Wait(800)
                
    # 3. Move specific high-value rewards to REWARD crate
    if reward_crate_serial != 0:
        for prize_type in [0x14F0, 0x0F9D]:
            FindType(prize_type, Backpack())
            for item in GetFoundList():
                if check_abort(): return
                
                i_color = GetColor(item)
                should_move = False
                
                # Check Sewing Kits (0x0F9D) specifically for Barbed Runic color (0x0851)
                if prize_type == 0x0F9D and i_color == 0x0851:
                    should_move = True
                    
                # Check Deeds (0x14F0) for Clothing Bless Deed (Color 0x0000 + tooltip)
                elif prize_type == 0x14F0 and i_color == 0x0000:
                    tooltip = GetTooltip(item).lower()
                    if "clothing bless deed" in tooltip:
                        should_move = True
                
                # If it passed the checks, move it to the reward crate
                if should_move:
                    world_save_guard()
                    print(item)
                    print(reward_crate_serial)
                    AddToSystemJournal(f"Moving reward item {hex(prize_type)} to Reward Crate.")
                    MoveItem(item, 0, reward_crate_serial, 0, 0, 0)
                    Wait(800)

def execute_trade_loop():
    config = load_config()
    if not config: return

    target_trades = config.get("trade", {}).get("target_trades")
    if target_trades is None:
        AddToSystemJournal("Error: 'target_trades' missing from config.")
        return
    buy_cloth_amount = config.get("trade", {}).get("buy_cloth_amount")
    if buy_cloth_amount is None:
        AddToSystemJournal("Error: 'buy_cloth_amount' missing from config.")
        return

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

    tailor1_idx = config.get("travel", {}).get("Runes", {}).get("Tailor1", 3)
    tailor2_idx = config.get("travel", {}).get("Runes", {}).get("Tailor2", 7)
    
    travel_to(rb_serial, travel_method, tailor1_idx)
    target_npc = find_tailor()
    
    if target_npc == 0:
        travel_to(rb_serial, travel_method, tailor2_idx)
        target_npc = find_tailor()
        
    if target_npc == 0: return
    
    request_new_bod(target_npc)
    sort_new_bods(config)
    Wait(1500)

    trades_completed = 0
    
    while trades_completed < target_trades:
        if check_abort(): break
        world_save_guard()
        
        if GetType(consegna_serial) == BOOK_TYPE:
            bod_to_give = extract_bod_from_book(consegna_serial)
        else:
            FindType(BOD_TYPE, consegna_serial)
            bod_to_give = FindItem() if FindCount() > 0 else 0
            
        if bod_to_give == 0: break
            
        success = trade_bod(target_npc, bod_to_give)
        if success:
            trades_completed += 1
            request_new_bod(target_npc)
            sort_new_bods(config)
            Wait(1500)
        else:
            break
            
    if not check_abort():
        buy_and_cut_cloth(target_npc, buy_cloth_amount)
        ws1_index = config.get("travel", {}).get("Runes", {}).get("WorkSpot1", 1)
        travel_to(rb_serial, travel_method, ws1_index)
        
        if home_x != 0 and home_y != 0:
            newMoveXY(home_x, home_y, True, 0, True)
            
        process_prizes_at_home(trash_serial, crate_serial, dye_tub_serial, reward_crate_serial, rb_serial)
        
    AddToSystemJournal("Route Complete. Cycle successful.")

if __name__ == '__main__':
    execute_trade_loop()