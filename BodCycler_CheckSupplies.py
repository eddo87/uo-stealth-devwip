from stealth import *
import json
import os
import re
import time
from datetime import datetime

# Import the save guard logic
try:
    from checkWorldSave import world_save_guard
except ImportError:
    # Fallback if file missing so script doesn't crash
    def world_save_guard(): return False

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

# Config Paths
CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
SUPPLY_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_supplies.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None

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
            
            if text_in_gump("Tinkering", BTN_CATEGORY_TOOLS, 10, CRAFT_GUMP_ID):
                if text_in_gump("Tinkering", make_button, 10, CRAFT_GUMP_ID):
                    Wait(1500) 
                    made += 1
                else:
                    AddToSystemJournal("Failed to find item button or Tools menu did not load.")
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
        sk_count = maintain_tool_stock("Sewing Kit", SEWING_KIT_TYPE, BTN_MAKE_SEWING_KIT, 5, 10, backpack_id, crate_id)
        tg_count = count_items(TONGS_TYPE, crate_id) 
    elif craft_type == "Smith":
        tg_count = maintain_tool_stock("Tongs", TONGS_TYPE, BTN_MAKE_TONGS, 5, 10, backpack_id, crate_id)
        sk_count = count_items(SEWING_KIT_TYPE, crate_id)

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