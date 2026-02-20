from stealth import *
import json
import os
import time
from datetime import datetime

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

# --- Quick Configuration Variables (Fallbacks) ---
TARGET_TRADES = 2         
BUY_CLOTH_AMOUNT = 80     

# --- Constants ---
NPC_TYPES = [0x0190, 0x0191] # Male/Female human
BOD_TYPE = 0x2258
BOOK_TYPE = 0x2259

# Items
BOLT_OF_CLOTH_IDS = [0x0F95, 0x0F97, 0x0F9B, 0x0F9C] # Fallback IDs for cloth bolts
SCISSORS = 0x0F9E
OIL_CLOTH = 0x175D
SANDALS = 0x170D
CLOTH_1 = 0x1766
CLOTH_2 = 0x1767

# Gumps
BOD_GUMP_ID_SMALL = 0x9bade6ea
BOD_GUMP_ID_LARGE = 0xbe0dad1e
BOOK_GUMP_ID = 0x54F555DF

# UI Buttons 
CTX_BUY = 1           # Context Menu entry for 'Buy'
CTX_BOD = 3           # Context Menu entry for 'Bulk Order Info'
BTN_ACCEPT_BOD = 1    # 'Accept' button on BOD offer gump (Return Value 1)
BTN_DROP_BOD_1 = 5    # The first 'Drop' button inside a BOD book

CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
STATS_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_stats.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None

def check_abort():
    """Checks the stats file to see if the GUI requested a hard stop."""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
                if data.get("status") == "Stopped":
                    return True
        except:
            pass
    return False

def close_all_gumps():
    """Closes all open gumps to ensure a clean UI state."""
    count = GetGumpsCount()
    if count > 0:
        for i in reversed(range(count)):
            CloseSimpleGump(i)
        Wait(500)

def find_tailor():
    """Scans screen for an NPC, prioritizing 'weaver' over 'tailor'."""
    SetFindDistance(10) # Open up the search range to 10 tiles
    
    weavers = []
    tailors = []
    
    for npc_type in NPC_TYPES:
        FindTypeEx(npc_type, 0xFFFF, Ground(), False)
        for npc in GetFoundList():
            name = GetName(npc).lower()
            title = GetAltName(npc).lower()
            if 'weaver' in name or 'weaver' in title:
                weavers.append(npc)
            elif 'tailor' in name or 'tailor' in title:
                tailors.append(npc)
                
    # Prioritize weavers since they sell cloth bolts reliably
    if weavers:
        return weavers[0]
    if tailors:
        return tailors[0]
        
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
            
        # CRITICAL FIX: The shard auto-opens the book gump when dropping items into it.
        # We must close it here, otherwise it blocks the Consegna book extraction!
        close_all_gumps()

def extract_bod_from_book(book_serial):
    """Opens the Consegna book and drops the first BOD into the backpack."""
    # Extra safety: wipe UI state before attempting to open the book
    close_all_gumps()
    
    FindType(BOD_TYPE, Backpack())
    before_bods = GetFoundList()
    
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
    Wait(1500) 
    
    # Close the book gump so it doesn't block the next iteration!
    CloseSimpleGump(found_idx)
    Wait(500)
    
    # Find the newly dropped BOD
    FindType(BOD_TYPE, Backpack())
    after_bods = GetFoundList()
    new_bods = [b for b in after_bods if b not in before_bods]
    if new_bods: 
        return new_bods[0]
        
    AddToSystemJournal("DEBUG: Clicked drop, but no new BOD appeared in backpack.")
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

def find_bod_offer_gump():
    """Dynamically looks for the BOD offer gump by ID or Cliloc."""
    for i in range(GetGumpsCount()):
        g = GetGumpInfo(i)
        
        # Method 1: Check known Gump IDs (Small and Large)
        if g.get('GumpID') in [BOD_GUMP_ID_SMALL, BOD_GUMP_ID_LARGE]:
            return i
            
        # Method 2: Check for specific Cliloc text (Ah! Thanks for the goods!)
        if 'XmfHTMLGumpColor' in g:
            for entry in g['XmfHTMLGumpColor']:
                if entry.get('ClilocID') == 1045135:
                    return i
    return -1

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
        found_idx = find_bod_offer_gump()
        if found_idx != -1: break
        Wait(100) 
        
    if found_idx != -1:
        NumGumpButton(found_idx, BTN_ACCEPT_BOD)
        AddToSystemJournal("BOD Accepted.")
        Wait(1200) 
    else:
        AddToSystemJournal("No BOD offered (Timer active or invalid context menu ID).")

def buy_and_cut_cloth(npc, amount=80):
    """Sets AutoBuy for Bolts of Cloth, buys them with fallbacks, and cuts them."""
    AddToSystemJournal(f"Starting cloth buy sequence for {amount} bolts...")
    world_save_guard()
    move_to_npc(npc)
    
    # Safely clear the buy list
    try: ClearAutoBuy()
    except NameError: pass
    try: ClearBuyList()
    except NameError: pass
    try: ClearBuy()
    except NameError: pass

    bought_any = False
    
    # Loop through the known bolt of cloth IDs to find the one this vendor sells
    for bolt_id in BOLT_OF_CLOTH_IDS:
        if check_abort(): return
        
        if bought_any:
            break
            
        AddToSystemJournal(f"Attempting to buy Bolts using ID: {hex(bolt_id)}...")
        
        # Setup AutoBuy
        try:
            AutoBuy(bolt_id, 0xFFFF, amount) # set buy hook
        except NameError:
            AddToSystemJournal("AutoBuy function missing in PyStealth! Skipping cloth purchase.")
            return
            
        # Trigger Buy Menu via Context Menu exactly as requested
        world_save_guard()
        SetContextMenuHook(npc, CTX_BUY)
        Wait(500)
        world_save_guard()
        RequestContextMenu(npc)
        Wait(1500)
        
        # Clean up AutoBuy / unset buy hook
        try: 
            AutoBuy(bolt_id, 0xFFFF, 0)
            ClearAutoBuy()
        except NameError: 
            pass
            
        # Check if we actually bought them
        FindType(bolt_id, Backpack())
        if FindCount() > 0:
            bought_any = True
            AddToSystemJournal(f"Success! Bought cloth with ID {hex(bolt_id)}.")
            
    if not bought_any:
        AddToSystemJournal("No bolts found in backpack. All fallback IDs failed.")
        return
    
    # Cut Cloth
    FindType(SCISSORS, Backpack())
    if FindCount() == 0:
        AddToSystemJournal("WARNING: No scissors found to cut the cloth!")
        return
        
    scissors = FindItem()
    
    # We must cut any bolt ID that exists in the backpack
    for bolt_id in BOLT_OF_CLOTH_IDS:
        if check_abort(): return
        
        FindType(bolt_id, Backpack())
        bolts = GetFoundList()
        
        if len(bolts) > 0:
            AddToSystemJournal(f"Cutting {len(bolts)} bolt stacks of ID {hex(bolt_id)}...")
            for bolt in bolts:
                if check_abort(): return
                world_save_guard()
                UseObject(scissors)
                WaitForTarget(2000)
                TargetToObject(bolt)
                Wait(700)
                
    AddToSystemJournal("Cloth cutting complete.")

def travel_to(runebook_serial, travel_method, rune_index):
    """Uses Runebook to travel to a specific spot. Returns True if position changed."""
    if runebook_serial == 0: return False
    
    start_x = GetX(Self())
    start_y = GetY(Self())
    
    AddToSystemJournal(f"Traveling to Rune {rune_index} via {travel_method}...")
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
        
    if not gump_pressed:
        AddToSystemJournal("Failed to open runebook.")
        return False
        
    # Wait up to 6 seconds for coordinates to change
    t = time.time()
    while time.time() - t < 6:
        world_save_guard()
        if abs(GetX(Self()) - start_x) > 5 or abs(GetY(Self()) - start_y) > 5:
            Wait(1000) # Give environment an extra second to load 
            return True
        Wait(100)
        
    AddToSystemJournal("Did not detect movement. (Fizzle, blocked, or already there).")
    return False

def process_prizes_at_home(trash_serial, crate_serial, dye_tub_serial):
    """Handles trashing junk and dyeing/storing cloth rewards."""
    AddToSystemJournal("Processing Prizes at Home...")

    # 1. Trash Oil Cloth and Sandals
    if trash_serial != 0:
        for junk_type in [OIL_CLOTH, SANDALS]:
            FindType(junk_type, Backpack())
            for junk in GetFoundList():
                if check_abort(): return
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
                if check_abort(): return
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

    # Dynamically pull trade configurations saved by the GUI
    target_trades = config.get("trade", {}).get("target_trades", TARGET_TRADES)
    buy_cloth_amount = config.get("trade", {}).get("buy_cloth_amount", BUY_CLOTH_AMOUNT)

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

    # Clean UI state before starting
    close_all_gumps()

    # 1. Travel to Trade NPC
    tailor1_idx = config["travel"]["Runes"].get("Tailor1", 3)
    tailor2_idx = config["travel"]["Runes"].get("Tailor2", 7)
    
    travel_to(rb_serial, travel_method, tailor1_idx)
    target_npc = find_tailor()
    
    # Fallback to Tailor2 if the location was blocked, we fizzled, or no NPC was found
    if target_npc == 0:
        AddToSystemJournal("Weaver/Tailor not found at primary spot. Attempting backup spot...")
        travel_to(rb_serial, travel_method, tailor2_idx)
        target_npc = find_tailor()
        
    if target_npc == 0:
        AddToSystemJournal("Error: Could not find Weaver or Tailor at any spots. Aborting.")
        return
    
    AddToSystemJournal(f"Found Target NPC: {hex(target_npc)}. Goal: Deliver {target_trades} BODs.")

    # 2. Immediate Initial Request (Burn off the cooldown timer right away)
    request_new_bod(target_npc)
    move_bods_to_origine(origine_serial)
    Wait(1500)

    trades_completed = 0
    
    # 3. Loop Delivery & Requests
    while trades_completed < target_trades:
        if check_abort():
            AddToSystemJournal("Abort detected. Halting Trade Loop.")
            break
            
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
        success = trade_bod(target_npc, bod_to_give)
        if success:
            trades_completed += 1
            
            # Request new BOD to replace the one we just gave
            request_new_bod(target_npc)
            
            # Move the newly acquired BOD to Origine
            move_bods_to_origine(origine_serial)
            
            # Pause between BOD actions
            Wait(1500)
        else:
            AddToSystemJournal("Failed to trade BOD. Aborting loop.")
            break
            
    AddToSystemJournal(f"Trade Loop Complete. {trades_completed} BODs cycled.")
    
    if not check_abort():
        # 4. Buy & Cut Cloth
        buy_and_cut_cloth(target_npc, buy_cloth_amount)
        
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