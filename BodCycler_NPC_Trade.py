from stealth import *
import json
import os
import time
from datetime import datetime

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

# --- Quick Configuration Variables ---
TARGET_TRADES = 2         # How many BODs to deliver per cycle (Set to 2 for testing)
BUY_CLOTH_AMOUNT = 80     # How many Bolts of Cloth to buy per cycle

# --- Constants ---
NPC_TYPES = [0x0190, 0x0191] # Male/Female human
BOD_TYPE = 0x2258
BOOK_TYPE = 0x2259

# Items
BOLT_OF_CLOTH = 0x0F95
SCISSORS = 0x0F9E
OIL_CLOTH = 0x175D
SANDALS = 0x170D
CLOTH_1 = 0x1766
CLOTH_2 = 0x1767

# Gumps
BOD_GUMP_ID_SMALL = 0x9bade6ea
BOOK_GUMP_ID = 0x54F555DF

# UI Buttons (You may need to tweak these using BodCycler_DebugCraft if they differ on your shard)
CTX_BUY = 1           # Context Menu entry for 'Buy'
CTX_BOD = 3           # Context Menu entry for 'Bulk Order Info'
BTN_ACCEPT_BOD = 1    # 'Accept' button on BOD offer gump
BTN_DROP_BOD_1 = 5    # The first 'Drop' button inside a BOD book

CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None

def find_tailor():
    """Scans screen for an NPC with 'tailor' or 'weaver' in their name/title."""
    SetFindDistance(10) # Open up the search range to 10 tiles
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            name = GetName(npc).lower()
            title = GetAltName(npc).lower()
            if 'tailor' in name or 'weaver' in name or 'tailor' in title or 'weaver' in title:
                return npc
    return 0

def move_to_npc(npc):
    """Ensures character is next to the NPC before interacting."""
    if npc > 0 and GetDistance(npc) > 1:
        newMoveXY(GetX(npc), GetY(npc), False, 1, True)
        Wait(500)

def move_bods_to_origine(origine_book_serial):
    """Moves any loose BODs in the backpack (newly received) into the Origine book."""
    if origine_book_serial == 0:
        AddToSystemJournal("Origine book not set, skipping BOD filing.")
        return
        
    FindType(BOD_TYPE, Backpack())
    loose_bods = GetFoundList()
    
    if len(loose_bods) > 0:
        AddToSystemJournal(f"Filing {len(loose_bods)} new BOD(s) into Origine book...")
        for bod in loose_bods:
            world_save_guard()
            MoveItem(bod, 0, origine_book_serial, 0, 0, 0)
            Wait(1000)

def extract_bod_from_book(book_serial):
    """Opens the Consegna book and drops the first BOD into the backpack."""
    UseObject(book_serial)
    
    # Wait for book gump
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
        
    if found_idx == -1:
        AddToSystemJournal("Failed to open Consegna book.")
        return 0
        
    # Press the drop button for the first BOD
    NumGumpButton(found_idx, BTN_DROP_BOD_1)
    Wait(1200) 
    
    # Find the newly dropped BOD
    FindType(BOD_TYPE, Backpack())
    if FindCount() > 0:
        return FindItem()
    return 0

def trade_bod(npc, bod_serial):
    """Drags and drops the filled BOD onto the NPC."""
    if bod_serial == 0: return False
    
    world_save_guard()
    move_to_npc(npc)
    
    AddToSystemJournal("Dropping filled BOD on NPC...")
    MoveItem(bod_serial, 1, npc, 0, 0, 0)
    Wait(2000) 
    return True

def request_new_bod(npc):
    """Requests a new BOD from the NPC and accepts it."""
    world_save_guard()
    move_to_npc(npc)
    
    AddToSystemJournal("Requesting new BOD...")
    SetContextMenuHook(npc, CTX_BOD)
    RequestContextMenu(npc)
    
    # Wait for the BOD offer gump
    t = time.time()
    found_idx = -1
    while time.time() - t < 3:
        world_save_guard()
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == BOD_GUMP_ID_SMALL:
                found_idx = i
                break
        if found_idx != -1: break
        Wait(100) 
        
    if found_idx != -1:
        NumGumpButton(found_idx, BTN_ACCEPT_BOD)
        AddToSystemJournal("BOD Accepted.")
        Wait(1200) 
    else:
        AddToSystemJournal("No BOD offered (Timer active or invalid context menu ID).")

def buy_and_cut_cloth(npc, amount=80):
    """Sets AutoBuy for Bolts of Cloth, buys them, and cuts them."""
    AddToSystemJournal(f"Buying {amount} Bolts of Cloth...")
    world_save_guard()
    move_to_npc(npc)
    
    # Safely clear the buy list
    try: ClearAutoBuy()
    except NameError: pass
    try: ClearBuyList()
    except NameError: pass
    try: ClearBuy()
    except NameError: pass

    # Setup AutoBuy
    try:
        AutoBuy(BOLT_OF_CLOTH, 0x0000, amount)
    except NameError:
        AddToSystemJournal("AutoBuy function missing in PyStealth! Skipping cloth purchase.")
        
    # Trigger Buy Menu
    SetContextMenuHook(npc, CTX_BUY)
    RequestContextMenu(npc)
    Wait(2000)
    
    # Clean up AutoBuy
    try: ClearAutoBuy()
    except NameError: pass
    
    # Cut Cloth
    FindType(SCISSORS, Backpack())
    if FindCount() == 0:
        AddToSystemJournal("WARNING: No scissors found to cut the cloth!")
        return
        
    scissors = FindItem()
    FindType(BOLT_OF_CLOTH, Backpack())
    bolts = GetFoundList()
    
    if len(bolts) > 0:
        AddToSystemJournal(f"Cutting {len(bolts)} bolt stacks...")
        for bolt in bolts:
            world_save_guard()
            UseObject(scissors)
            WaitForTarget(2000)
            TargetToObject(bolt)
            Wait(700)
        AddToSystemJournal("Cloth cutting complete.")
    else:
        AddToSystemJournal("No bolts found in backpack. Buy failed or none available.")

def travel_to(runebook_serial, travel_method, rune_index):
    """Uses Runebook to travel to a specific spot."""
    if runebook_serial == 0: return
    
    AddToSystemJournal(f"Traveling to Rune {rune_index} via {travel_method}...")
    offset = 5 if travel_method == "Recall" else 7
    btn_id = offset + (rune_index - 1) * 6
    
    UseObject(runebook_serial)
    
    t = time.time()
    while time.time() - t < 3:
        world_save_guard()
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == 0x554B87F3:
                NumGumpButton(i, btn_id)
                Wait(3000) # Wait for travel cast
                return
        Wait(100) 

def process_prizes_at_home(trash_serial, crate_serial, dye_tub_serial):
    """Handles trashing junk and dyeing/storing cloth rewards."""
    AddToSystemJournal("Processing Prizes at Home...")

    # 1. Trash Oil Cloth and Sandals
    if trash_serial != 0:
        for junk_type in [OIL_CLOTH, SANDALS]:
            FindType(junk_type, Backpack())
            for junk in GetFoundList():
                world_save_guard()
                AddToSystemJournal(f"Trashing junk item: {hex(junk)}")
                MoveItem(junk, 0, trash_serial, 0, 0, 0)
                Wait(800)
    else:
        AddToSystemJournal("Trash Barrel not set in Config. Skipping trashing.")

    # 2. Dye and Store Cloth
    if crate_serial != 0:
        for c_type in [CLOTH_1, CLOTH_2]:
            FindType(c_type, Backpack())
            for cloth in GetFoundList():
                world_save_guard()
                
                # Dye the cloth first
                if dye_tub_serial != 0:
                    UseObject(dye_tub_serial)
                    WaitForTarget(2000)
                    TargetToObject(cloth)
                    Wait(600)
                    
                # Move to Resource Crate
                MoveItem(cloth, 0, crate_serial, 0, 0, 0)
                Wait(800)
    else:
        AddToSystemJournal("Material Crate not set in Config. Skipping cloth storage.")

def execute_trade_loop():
    config = load_config()
    if not config:
        AddToSystemJournal("Error: Config not found.")
        return

    consegna_serial = config["books"]["Consegna"]
    origine_serial = config["books"]["Origine"]
    rb_serial = config["travel"]["RuneBook"]
    travel_method = config["travel"]["Method"]
    home_x = config["home"]["X"]
    home_y = config["home"]["Y"]
    
    trash_serial = config["containers"]["TrashBarrel"]
    crate_serial = config["containers"]["MaterialCrate"]
    dye_tub_serial = config["containers"]["ClothDyeTub"]

    if consegna_serial == 0:
        AddToSystemJournal("Error: Consegna Book/Bag not set in Config.")
        return

    # 1. Find NPC
    tailor = find_tailor()
    if tailor == 0:
        AddToSystemJournal("Error: Could not find Tailor or Weaver nearby.")
        return
    
    AddToSystemJournal(f"Found Tailor: {hex(tailor)}. Starting Trade Loop.")

    # 2. Immediate Initial Request (Burn off the cooldown timer right away)
    request_new_bod(tailor)
    move_bods_to_origine(origine_serial)
    Wait(1500)

    trades_completed = 0
    
    # 3. Loop Delivery & Requests
    while trades_completed < TARGET_TRADES:
        world_save_guard()
        
        # Check if Consegna is a Book or a Bag
        if GetType(consegna_serial) == BOOK_TYPE:
            bod_to_give = extract_bod_from_book(consegna_serial)
        else:
            FindType(BOD_TYPE, consegna_serial)
            bod_to_give = FindItem() if FindCount() > 0 else 0
            
        if bod_to_give == 0:
            AddToSystemJournal(f"Consegna is empty! Stopped after {trades_completed} trades.")
            break
            
        # Give BOD -> Get Reward
        success = trade_bod(tailor, bod_to_give)
        if success:
            trades_completed += 1
            
            # Request new BOD to replace the one we just gave
            request_new_bod(tailor)
            
            # Move the newly acquired BOD to Origine
            move_bods_to_origine(origine_serial)
            
            # Pause between BOD actions
            Wait(1500)
        else:
            AddToSystemJournal("Failed to trade BOD. Aborting loop.")
            break
            
    AddToSystemJournal(f"Trade Loop Complete. {trades_completed} BODs cycled.")
    
    # 4. Buy & Cut Cloth
    buy_and_cut_cloth(tailor, BUY_CLOTH_AMOUNT)
    
    # 5. Recall to WorkSpot1
    ws1_index = config["travel"]["Runes"]["WorkSpot1"]
    travel_to(rb_serial, travel_method, ws1_index)
    
    # 6. Walk to exact Home Spot
    if home_x != 0 and home_y != 0:
        AddToSystemJournal(f"Walking to Home Spot ({home_x}, {home_y})...")
        newMoveXY(home_x, home_y, True, 0, True)
        
    # 7. Scan and Process Prizes
    process_prizes_at_home(trash_serial, crate_serial, dye_tub_serial)
        
    AddToSystemJournal("Route Complete. Cycle successful.")

if __name__ == '__main__':
    execute_trade_loop()