from stealth import *
import json
import os
import sys
import re
import time
from datetime import datetime

# Force Python to look in the current script's directory for custom modules
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import the save guard logic
try:
    from checkWorldSave import world_save_guard
except ImportError:
    # Fallback if file missing so script doesn't crash
    def world_save_guard(): return False

# Import crafting data for dynamic trash cleanup
try:
    from bod_crafting_data import TAILOR_ITEMS
except ImportError:
    TAILOR_ITEMS = {}
    AddToSystemJournal("Warning: Could not import TAILOR_ITEMS for dynamic trash cleanup.")

# --- Constants ---
CRAFT_GUMP_ID = 0x38920abd

# Item Types
INGOT_TYPE = 0x1BF2
CLOTH_TYPE_1 = 0x1766 # Regular / Bought cloth
CLOTH_TYPE_2 = 0x1767 # Prize cloth
LEATHER_TYPE = 0x1081
TINKER_TOOL_TYPE = 0x1EB8
SEWING_KIT_TYPE = 0x0F9D
TONGS_TYPE = 0x0FBC 

# Trash Configuration
TRASH_IDS = [
    #0x0F9E, # Scissors (Common Tailoring/Tinkering miscraft)
    #0x14FC # Lockpicks
]

# Dynamically inject all tailor item IDs into the trash list
for key, data in TAILOR_ITEMS.items():
    # item_id is located at index 2 of the data list based on your crafting script
    if len(data) > 2:
        item_id = data[2]
        if item_id not in TRASH_IDS:
            TRASH_IDS.append(item_id)

# Leather Colors
LEATHER_COLORS = {
    "Normal": 0x0000,
    "Spined": 0x08AC,
    "Horned": 0x0845,
    "Barbed": 0x0851
}

# Crafting Buttons (Tinkering Menu)
BTN_CATEGORY_TOOLS = 8
BTN_MAKE_TINKER_TOOL = 23
BTN_MAKE_SEWING_KIT = 44  
BTN_MAKE_TONGS = 16       

# ✅ AFTER — one import covers everything
from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status
)

def save_supplies_to_json(data):
    """Saves supply data to a separate JSON for the GUI to read."""
    try:
        with open(SUPPLY_FILE, "w") as f:
            json.dump(data, f, indent=4)
        AddToSystemJournal("Supply counts saved to JSON.")
    except Exception as e:
        AddToSystemJournal(f"Error saving supply data: {e}")

def get_item_count(type_id, container_id, color=-1):
    """Returns total quantity (stack size) or count of items."""
    FindTypeEx(type_id, color, container_id, False)
    return FindFullQuantity()

def count_items(type_id, container_id):
    """Returns the number of individual items (good for unstackable tools)."""
    FindType(type_id, container_id)
    return FindCount()

def find_item_in_container(type_id, container_id):
    FindType(type_id, container_id)
    if FindCount() > 0:
        return FindItem()
    return 0

def move_items(type_id, source_id, dest_id, amount):
    """Moves a specific number of items from source to dest."""
    FindType(type_id, source_id)
    found_items = GetFoundList()
    
    count = 0
    for item in found_items:
        if count >= amount: break
        world_save_guard()
        MoveItem(item, 0, dest_id, 0, 0, 0)
        Wait(600)
        count += 1


def text_in_gump(text: str, button_id: int = None, timeout: int = 10, gump_id: int = None) -> bool:
    end_time = time.time() + timeout

    while time.time() < end_time:
        world_save_guard() 
        
        for i in range(GetGumpsCount()):
            g = GetGumpInfo(i)
            if gump_id is not None and g.get('GumpID') != gump_id:
                continue
                
            found = False
            
            if 'XmfHTMLGumpColor' in g:
                for entry in g['XmfHTMLGumpColor']:
                    cliloc = entry.get('ClilocID', 0)
                    content = GetClilocByID(cliloc).upper()
                    clean_content = content.replace("<CENTER>", "").replace("</CENTER>", "").replace("<BASEFONT COLOR=#FFFFFF>", "")
                    if text.upper() in clean_content:
                        found = True
                        break
            
            if not found and 'Text' in g:
                for line in g['Text']:
                     if text.upper() in str(line).upper():
                         found = True
                         break
            
            if found:
                if button_id is not None:
                    NumGumpButton(i, button_id)
                    Wait(500) 
                return True
                
        Wait(50) 
        
    return False

def restock_ingots(backpack_id, crate_id, min_amount=50):
    current = get_item_count(INGOT_TYPE, backpack_id, 0)
    if current < min_amount:
        AddToSystemJournal(f"Restocking Ingots... (Have {current})")
        ingots_crate_item = find_item_in_container(INGOT_TYPE, crate_id)
        if ingots_crate_item:
            world_save_guard()
            MoveItem(ingots_crate_item, 300, backpack_id, 0, 0, 0)
            Wait(1000)
            return True
        else:
            AddToSystemJournal("WARNING: No Iron Ingots in Crate!")
            return False
    return True

def maintain_tool_stock(tool_name, type_id, make_button, bp_target, crate_target, backpack_id, crate_id):
    bp_count = count_items(type_id, backpack_id)
    crate_count = count_items(type_id, crate_id)
    total_have = bp_count + crate_count
    total_need = bp_target + crate_target
    
    if total_have < total_need:
        needed = total_need - total_have
        AddToSystemJournal(f"{tool_name}: Have {total_have} (BP:{bp_count}/C:{crate_count}), Need {total_need}. Crafting {needed}...")

        if not restock_ingots(backpack_id, crate_id):
            return bp_count + crate_count

        tinker_tool = find_item_in_container(TINKER_TOOL_TYPE, backpack_id)
        if tinker_tool == 0:
            t_tool_crate = find_item_in_container(TINKER_TOOL_TYPE, crate_id)
            if t_tool_crate:
                world_save_guard()
                MoveItem(t_tool_crate, 1, backpack_id, 0, 0, 0)
                Wait(1000)
                tinker_tool = t_tool_crate
            else:
                AddToSystemJournal("FATAL: No Tinker Tools anywhere!")
                return bp_count + crate_count

        attempts = 0
        made = 0
        while made < needed and attempts < (needed * 3):
            world_save_guard()
            attempts += 1
            
            UseObject(tinker_tool)
            idx = wait_for_gump(CRAFT_GUMP_ID, 4000)
            
            if idx != -1:
                # 1. Click Category and wait for refresh
                if text_in_gump("Tinkering", BTN_CATEGORY_TOOLS, 5, CRAFT_GUMP_ID):
                    wait_for_gump(CRAFT_GUMP_ID, 2000) 
                    
                    # 2. Click the specific tool to make
                    if text_in_gump("Tinkering", make_button, 5, CRAFT_GUMP_ID):
                        # 3. Dynamic Backpack Polling (No blind waits!)
                        start_qty = count_items(type_id, backpack_id)
                        wait_t = time.time()
                        
                        while time.time() - wait_t < 4.0: # 4 second timeout for craft to finish
                            Wait(200)
                            if count_items(type_id, backpack_id) > start_qty:
                                made += 1
                                break
                    else:
                        AddToSystemJournal("Failed to find specific item button.")
                else:
                    AddToSystemJournal("Failed to click Tools category.")
            else:
                 AddToSystemJournal("Failed to open Tinkering Gump.")
                
    bp_count = count_items(type_id, backpack_id)
    crate_count = count_items(type_id, crate_id)
    
    if bp_count < bp_target:
        needed_in_bp = bp_target - bp_count
        if crate_count > 0:
            move_amt = min(needed_in_bp, crate_count)
            move_items(type_id, crate_id, backpack_id, move_amt)
            
    elif bp_count > bp_target:
        excess_in_bp = bp_count - bp_target
        move_items(type_id, backpack_id, crate_id, excess_in_bp)

    final_bp = count_items(type_id, backpack_id)
    final_crate = count_items(type_id, crate_id)
    AddToSystemJournal(f"Stock Check {tool_name}: BP {final_bp}/{bp_target}, Crate {final_crate}/{crate_target}")
    
    return final_bp + final_crate

def cleanup_trash():
    """Scans the backpack for known miscrafts and moves them to the trash barrel."""
    config = load_config()
    if not config: return
    
    trash_id = config.get("containers", {}).get("TrashBarrel", 0)
    
    if trash_id != 0:
        found_junk = False
        for junk_id in TRASH_IDS:
            FindType(junk_id, Backpack())
            for junk in GetFoundList():
                if check_abort(): return
                world_save_guard()
                if not found_junk:
                    AddToSystemJournal("Cleaning up leftover miscrafts and prizes...")
                    found_junk = True
                MoveItem(junk, 0, trash_id, 0, 0, 0)
                Wait(800) # Wait for the item to drop into the barrel

def dye_and_store_colored_cloth(backpack_id, crate_id):
    """Scans backpack for cloth, dyes colored ones, and moves ALL of it to the crate."""
    config = load_config()
    if not config: return
    
    dye_tub_id = config.get("containers", {}).get("ClothDyeTub", 0)
    
    if crate_id != 0:
        for c_type in [CLOTH_TYPE_1, CLOTH_TYPE_2]:
            FindType(c_type, backpack_id)
            for cloth in GetFoundList():
                if check_abort(): return
                world_save_guard()
                
                if dye_tub_id != 0 and GetColor(cloth) != 0x0000:
                    AddToSystemJournal(f"Dyeing colored cloth ({hex(cloth)})...")
                    UseObject(dye_tub_id)
                    WaitForTarget(2000)
                    if TargetPresent():
                        TargetToObject(cloth)
                        Wait(600)
                        
                MoveItem(cloth, 0, crate_id, 0, 0, 0)
                Wait(800)

def check_supplies():
    config = load_config()
    if not config:
        AddToSystemJournal("Error: Config file not found.")
        return

    backpack_id = Backpack()
    crate_id = config["containers"]["MaterialCrate"]
    origine_book_id = config["books"]["Origine"]
    
    craft_type = config.get("cycle_type", "Tailor") 

    if crate_id == 0:
        AddToSystemJournal("Error: Material Crate not set in Config.")
        return

    AddToSystemJournal(f"--- STARTING SUPPLY CHECK ({craft_type}) ---")
    
    world_save_guard()
    UseObject(crate_id)
    Wait(1000)

    # Dye any colored cloth back to normal and stash it
    dye_and_store_colored_cloth(backpack_id, crate_id)

    # Count Base Materials
    ingots_total = get_item_count(INGOT_TYPE, crate_id, 0) + get_item_count(INGOT_TYPE, backpack_id, 0)
    
    # Count Both Types of Cloth
    cloth_total = (
        get_item_count(CLOTH_TYPE_1, crate_id) + get_item_count(CLOTH_TYPE_1, backpack_id) +
        get_item_count(CLOTH_TYPE_2, crate_id) + get_item_count(CLOTH_TYPE_2, backpack_id)
    )
    
    # Count Leather by Color
    l_normal = get_item_count(LEATHER_TYPE, crate_id, LEATHER_COLORS["Normal"]) + get_item_count(LEATHER_TYPE, backpack_id, LEATHER_COLORS["Normal"])
    l_spined = get_item_count(LEATHER_TYPE, crate_id, LEATHER_COLORS["Spined"]) + get_item_count(LEATHER_TYPE, backpack_id, LEATHER_COLORS["Spined"])
    l_horned = get_item_count(LEATHER_TYPE, crate_id, LEATHER_COLORS["Horned"]) + get_item_count(LEATHER_TYPE, backpack_id, LEATHER_COLORS["Horned"])
    l_barbed = get_item_count(LEATHER_TYPE, crate_id, LEATHER_COLORS["Barbed"]) + get_item_count(LEATHER_TYPE, backpack_id, LEATHER_COLORS["Barbed"])
    
    tt_count = maintain_tool_stock("Tinker Tools", TINKER_TOOL_TYPE, BTN_MAKE_TINKER_TOOL, 1, 7, backpack_id, crate_id)
    sk_count, tg_count = 0, 0
    
    if craft_type == "Tailor":
        sk_count = maintain_tool_stock("Sewing Kit", SEWING_KIT_TYPE, BTN_MAKE_SEWING_KIT, 5, 5, backpack_id, crate_id)
        tg_count = count_items(TONGS_TYPE, crate_id) 
    elif craft_type == "Smith":
        tg_count = maintain_tool_stock("Tongs", TONGS_TYPE, BTN_MAKE_TONGS, 5, 5, backpack_id, crate_id)
        sk_count = count_items(SEWING_KIT_TYPE, crate_id)

    # Clean up any mess made during the tool creation process
    cleanup_trash()

    bod_count = 0
    if origine_book_id != 0:
        tooltip = GetTooltip(origine_book_id)
        match = re.search(r'(\d+)\s+deeds', tooltip.lower())
        if match:
            bod_count = int(match.group(1))

    # Save Data for GUI
    supply_data = {
        "timestamp": str(datetime.now()),
        "resources": {
            "Ingots": ingots_total,
            "Cloth": cloth_total,
            "Leather": l_normal,
            "Spined": l_spined,
            "Horned": l_horned,
            "Barbed": l_barbed
        },
        "tools": {
            "TinkerTools": tt_count,
            "SewingKits": sk_count,
            "Tongs": tg_count
        },
        "bods": {
            "OrigineCount": bod_count
        }
    }
    save_supplies_to_json(supply_data)
    AddToSystemJournal("--- SUPPLY CHECK COMPLETE ---")

if __name__ == '__main__':
    check_supplies()