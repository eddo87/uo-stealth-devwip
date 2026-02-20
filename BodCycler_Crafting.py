from stealth import *
import json
import os
import sys
import time
import re
from datetime import datetime

# Force Python to look in the current script's directory for custom modules
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import external modules
from bod_data import categorize_items, get_prize_number
from bod_crafting_data import TAILOR_ITEMS, MATERIAL_MAP
import Utilities

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

# --- Config ---
BODS_TO_PROCESS = 5

# --- Constants ---
BOD_TYPE = 0x2258
BOOK_GUMP_ID = 0x54F555DF
CRAFT_GUMP_ID = 0x38920abd

CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None

def close_all_gumps():
    """Closes all open gumps to ensure a clean UI state."""
    count = GetGumpsCount()
    if count > 0:
        for i in reversed(range(count)):
            CloseSimpleGump(i)
        Wait(500)

def consolidate_cloth(crate_serial):
    """Scans the backpack for loose cloth and moves it to the resource crate."""
    if crate_serial == 0: return
    
    found_any = False
    for c_type in [0x1766, 0x1767]:
        FindType(c_type, Backpack())
        items = GetFoundList()
        if items and not found_any:
            AddToSystemJournal("Consolidating leftover cloth into crate...")
            found_any = True
            
        for item in items:
            world_save_guard()
            MoveItem(item, 0, crate_serial, 0, 0, 0)
            Wait(800)

def wait_for_gump(gump_id, timeout_ms=3000):
    t = datetime.now()
    while (datetime.now() - t).total_seconds() * 1000 < timeout_ms:
        world_save_guard()
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == gump_id: return i
        Wait(50)
    return -1

def find_button_for_text(gump_data, text_to_find):
    target_y = -1
    target_x = -1
    target_page = -1
    
    # Use regex word boundaries so 'cap' doesn't accidentally match 'skullcap'
    pattern = r'\b' + re.escape(text_to_find.upper()) + r'\b'
    
    if 'XmfHTMLGumpColor' in gump_data:
        for entry in gump_data['XmfHTMLGumpColor']:
            cliloc = entry.get('ClilocID', 0)
            content = GetClilocByID(cliloc).upper()
            clean_content = content.replace("<CENTER>", "").replace("</CENTER>", "")
            if re.search(pattern, clean_content):
                target_y = entry.get('Y')
                target_x = entry.get('X')
                target_page = entry.get('Page', 0)
                break
                
    if target_y == -1 and 'GumpText' in gump_data and 'Text' in gump_data:
         for entry in gump_data['GumpText']:
             tid = entry.get('TextID')
             if tid < len(gump_data['Text']):
                 content = str(gump_data['Text'][tid]).upper()
                 if re.search(pattern, content):
                     target_y = entry.get('Y')
                     target_x = entry.get('X')
                     target_page = entry.get('Page', 0)
                     break

    if target_y == -1: return None

    best_btn_id = None
    min_dist = 1000
    if 'GumpButtons' in gump_data:
        for btn in gump_data['GumpButtons']:
            btn_page = btn.get('Page', 0)
            if btn_page != target_page and btn_page != 0: continue
            by = btn.get('Y')
            bx = btn.get('X')
            bid = btn.get('ReturnValue') 
            if bx < target_x and abs(by - target_y) < 20:
                dist = target_x - bx
                if dist < min_dist:
                    min_dist = dist
                    best_btn_id = bid
    return best_btn_id

def extract_bod_from_origine(origine_serial):
    if GetType(origine_serial) != 0x2259:
        FindType(BOD_TYPE, origine_serial)
        if FindCount() > 0:
            bod = FindItem()
            world_save_guard()
            MoveItem(bod, 1, Backpack(), 0, 0, 0)
            Wait(1200)
            return bod
        return 0

    FindType(BOD_TYPE, Backpack())
    before = GetFoundList()
    UseObject(origine_serial)
    idx = wait_for_gump(BOOK_GUMP_ID, 5000)
    if idx == -1: return 0
    
    NumGumpButton(idx, 5) # Drop first BOD
    Wait(2000)
    CloseSimpleGump(idx)
    Wait(500)
    
    FindType(BOD_TYPE, Backpack())
    after = GetFoundList()
    new_bods = [b for b in after if b not in before]
    if new_bods: return new_bods[0]
    return 0

def parse_bod(bod_serial):
    tooltip = GetTooltip(bod_serial).lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]
    
    is_large = "large" in tooltip
    is_except = "exceptional" in tooltip
    
    qty_total = 0
    qty_finished = 0
    item_name = "unknown"
    
    # 1. Find the Item Name using dict
    sorted_keys = sorted(TAILOR_ITEMS.keys(), key=len, reverse=True)
    for line in lines:
        for key in sorted_keys:
            if key in line:
                item_name = key
                break
        if item_name != "unknown": break

    # 2. Extract Numbers
    for line in lines:
        if "amount to make" in line:
            match = re.search(r'\d+', line)
            if match: qty_total = int(match.group())
        elif item_name != "unknown" and item_name in line and ":" in line:
            match = re.search(r':\s*(\d+)', line)
            if match: qty_finished = int(match.group(1))

    qty_needed = qty_total - qty_finished

    # 3. Material Determination
    mat = "unknown"
    sorted_mats = sorted(MATERIAL_MAP.keys(), key=len, reverse=True)
    for m in sorted_mats:
        if m in tooltip:
            mat = m
            break
            
    if mat == "unknown" or mat == "iron":
        if item_name in TAILOR_ITEMS:
            if "leather" in item_name or "studded" in item_name: mat = "leather"
            elif "bone" in item_name: mat = "bone"
            else: mat = "cloth"
        else: mat = "iron"
            
    cat = categorize_items(item_name) if item_name != "unknown" else "Small Bods"
    mat_proper = mat.title()
    if mat_proper == "Dull copper": mat_proper = "Dull Copper"
    elif mat_proper == "Shadow iron": mat_proper = "Shadow Iron"
    
    prize_id = get_prize_number(cat, mat_proper, qty_total, "Exceptional" if is_except else "Normal")
    
    return {
        "serial": bod_serial, "is_large": is_large, "is_except": is_except,
        "qty_total": qty_total, "qty_finished": qty_finished, "qty_needed": qty_needed,
        "item_name": item_name, "material": mat, "cat": cat, "prize_id": prize_id
    }

def count_valid_backpack_items(item_id, is_except):
    """Counts valid items currently in backpack."""
    FindType(item_id, Backpack())
    found = GetFoundList()
    count = 0
    for item in found:
        if not is_except:
            count += 1
        else:
            tt = GetTooltip(item)
            # Failsafe for newly crafted items where the server hasn't sent properties yet
            if not tt:
                ClickOnObject(item)
                Wait(200)
                tt = GetTooltip(item)
                
            if tt and "exceptional" in tt.lower():
                count += 1
    return count

def get_craft_info(item_name):
    item_lower = item_name.lower()
    if item_lower in TAILOR_ITEMS:
        return TAILOR_ITEMS[item_lower][0], TAILOR_ITEMS[item_lower][1], TAILOR_ITEMS[item_lower][2], 0x0F9D, TAILOR_ITEMS[item_lower][3]
    return None, None, None, None, None

def check_and_pull_materials(material, qty_to_craft, item_cost, crate_serial):
    if material not in MATERIAL_MAP: return False
    mat_info = MATERIAL_MAP[material]
    mat_types = mat_info["types"]
    
    # Safe Hex color parsing for Stealth API
    mat_color = mat_info["color"]
    if mat_color == -1: mat_color = 0xFFFF
    
    required_units = int((qty_to_craft * item_cost) * 1.2)
    bp_qty = 0
    for t in mat_types:
        FindTypeEx(t, mat_color, Backpack(), False)
        bp_qty += FindFullQuantity()
        
    if bp_qty >= required_units: return True
    
    AddToSystemJournal(f"Low on {material} (Need {required_units}, Have {bp_qty}). Pulling from crate...")
    
    # CRITICAL FIX: Explicitly open crate to cache its contents
    if crate_serial != 0:
        UseObject(crate_serial)
        Wait(1000)
    
    for t in mat_types:
        FindTypeEx(t, mat_color, crate_serial, False)
        found_stacks = GetFoundList()
        
        # Keep pulling stacks until we have what we need
        for stack in found_stacks:
            world_save_guard()
            
            # Re-check current backpack quantity dynamically
            FindTypeEx(t, mat_color, Backpack(), False)
            current_bp_qty = FindFullQuantity()
            
            if current_bp_qty >= required_units: 
                return True
                
            amount_needed_now = required_units - current_bp_qty
            pull_amt = max(400, amount_needed_now) # Pull minimum 400 to limit crate queries
            
            MoveItem(stack, pull_amt, Backpack(), 0, 0, 0)
            Wait(1200)
            
        # Check one final time after iterating through all stacks
        FindTypeEx(t, mat_color, Backpack(), False)
        if FindFullQuantity() >= required_units: 
            return True
            
    AddToSystemJournal(f"CRITICAL: Out of {material} in Crate!")
    return False

def recycle_invalid_items(item_id, is_except, tool_type):
    FindType(item_id, Backpack())
    items = GetFoundList()
    for it in items:
        tt = GetTooltip(it).lower()
        if is_except and "exceptional" not in tt:
            world_save_guard()
            if tool_type == 0x0F9D: # Scissors
                FindType(0x0F9E, Backpack()) 
                if FindCount() > 0:
                    UseObject(FindItem()); WaitForTarget(1500); TargetToObject(it); Wait(800)
            elif tool_type == 0x0FBC: # Tongs (Smelt)
                FindType(tool_type, Backpack())
                if FindCount() > 0:
                    UseObject(FindItem())
                    idx = wait_for_gump(CRAFT_GUMP_ID)
                    if idx != -1: NumGumpButton(idx, 14); WaitForTarget(1500); TargetToObject(it); Wait(800)

def craft_items_until_done(tool_type, cat_text, item_text, item_id, qty_needed, is_except, mat_btn):
    """Crafts until the backpack has enough items to fulfill qty_needed."""
    made_valid = count_valid_backpack_items(item_id, is_except)
    attempts = 0
    
    while made_valid < qty_needed and attempts < (qty_needed * 3):
        world_save_guard()
        attempts += 1
        
        FindType(tool_type, Backpack())
        if FindCount() == 0: 
            AddToSystemJournal("Out of tools!")
            return False
        tool = FindItem()
        
        # Check if the crafting gump is already open, if not, wait up to 10s for it to open
        idx = wait_for_gump(CRAFT_GUMP_ID, 500)
        if idx == -1:
            UseObject(tool)
            idx = wait_for_gump(CRAFT_GUMP_ID, 10000) # Increased to 10s per RE analysis
        
        if idx == -1: 
            AddToSystemJournal("Crafting gump failed to open.")
            continue
        
        gump_data = GetGumpInfo(idx)
        
        # --- Dynamic Pacing Logic based on Razor Enhanced ---
        if attempts > 1:
            NumGumpButton(idx, 21) # Make Last
            Wait(600) # Quick pause for action to process
            
            # Dynamically wait for gump to reappear (up to 5s) instead of hard sleeping
            if wait_for_gump(CRAFT_GUMP_ID, 5000) == -1:
                AddToSystemJournal("Gump did not refresh. Tool broke or server lagged.")
                
        else:
            # First attempt: Navigate menus manually
            if mat_btn is not None and mat_btn != 6:
                NumGumpButton(idx, 7); Wait(1000)
                idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
                if idx != -1: 
                    NumGumpButton(idx, mat_btn)
                    Wait(1000)
                    idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
                    gump_data = GetGumpInfo(idx)
            
            cat_btn = find_button_for_text(gump_data, cat_text)
            if cat_btn is None: return False
            
            NumGumpButton(idx, cat_btn)
            Wait(1000)
            idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
            
            item_craft_btn = find_button_for_text(GetGumpInfo(idx), item_text)
            if item_craft_btn is None: return False
            
            NumGumpButton(idx, item_craft_btn)
            Wait(600)
            
            # Dynamic wait for craft completion
            if wait_for_gump(CRAFT_GUMP_ID, 5000) == -1:
                 AddToSystemJournal("Gump did not refresh. Tool broke or server lagged.")

        recycle_invalid_items(item_id, is_except, tool_type)
        made_valid = count_valid_backpack_items(item_id, is_except)
        AddToSystemJournal(f"Crafting check: {made_valid}/{qty_needed} in bag.")
        
    return made_valid >= qty_needed

def is_bod_full(bod_serial, item_name):
    tooltip = GetTooltip(bod_serial).lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]
    amt_to_make, amt_finished = 0, 0
    for line in lines:
        if "amount to make" in line:
            match = re.search(r'\d+', line); amt_to_make = int(match.group()) if match else 0
        elif item_name.lower() in line and ":" in line:
            match = re.search(r':\s*(\d+)', line); amt_finished = int(match.group(1)) if match else 0
            
    return amt_to_make > 0 and amt_to_make == amt_finished

def fill_bod_completely(bod_serial, item_id, qty_to_fill, item_name, is_except):
    """Fills only the amount required to finish the BOD, filtering valid items first."""
    AddToSystemJournal(f"Filling BOD...")
    
    # 1. Filter out only the Valid Items to prevent feeding normal items to an exceptional BOD
    FindType(item_id, Backpack())
    all_items = GetFoundList()
    valid_items = []
    
    for item in all_items:
        if not is_except:
            valid_items.append(item)
        else:
            tt = GetTooltip(item)
            if not tt:
                ClickOnObject(item)
                Wait(200)
                tt = GetTooltip(item)
            if tt and "exceptional" in tt.lower():
                valid_items.append(item)
                
    if not valid_items:
        AddToSystemJournal("No valid crafted items found to fill the BOD!")
        return False

    # 2. Iterate through valid items, shoving them into the BOD until full
    for item in valid_items:
        # If target drops (start of loop, server lag, or BOD became full)
        if not TargetPresent():
            # Check if it actually finished before bothering to reopen gump
            if is_bod_full(bod_serial, item_name):
                AddToSystemJournal("BOD filled completely!")
                break
                
            UseObject(bod_serial)
            Wait(1500)
            idx = -1
            for i in range(GetGumpsCount()):
                g = GetGumpInfo(i)
                if 'GumpButtons' in g:
                    for btn in g['GumpButtons']:
                        if btn.get('ReturnValue') == 2: 
                            idx = i
                            break
                if idx != -1: break
                
            if idx != -1: 
                NumGumpButton(idx, 2)
                WaitForTarget(5000)
            else:
                AddToSystemJournal("CRITICAL: Could not find Combine button on BOD gump.")
                break

        if TargetPresent():
            world_save_guard()
            TargetToObject(item)
            Wait(500) # Small pause for packet
            WaitForTarget(2000) # Wait for the *recurring* cursor
            
    # Clean up leftover target
    if TargetPresent(): 
        CancelTarget()
        Wait(600)
        
    return is_bod_full(bod_serial, item_name)

def run_crafting_cycle():
    config = load_config()
    if not config: return
    
    origine = config['books']['Origine']; consegna = config['books']['Consegna']
    conserva = config['books']['Conserva']; scartare = config['books']['Scartare']
    riprova = config['books']['Riprova']; crate = config['containers']['MaterialCrate']
    
    AddToSystemJournal("=== Starting Crafting Cycle ===")
    
    # Initialize crate contents for PyStealth caching at the start of the macro
    if crate != 0:
        UseObject(crate)
        Wait(1000)
        
    for i in range(BODS_TO_PROCESS):
        close_all_gumps(); consolidate_cloth(crate)
        bod = extract_bod_from_origine(origine)
        if bod == 0: AddToSystemJournal("Origine book is empty."); break
            
        info = parse_bod(bod)
        if info['qty_needed'] <= 0:
            AddToSystemJournal(f"BOD {info['item_name']} already full.")
            MoveItem(bod, 0, consegna, 0,0,0); continue

        p_status = f"PRIZE {info['prize_id']}" if info['prize_id'] else "TRASH"
        AddToSystemJournal(f"BOD: {info['item_name']} (Needed: {info['qty_needed']}/{info['qty_total']}) [{p_status}]")
        
        if info['material'] == "bone" or info['is_large']:
            # Safe check for NoneType prize_id
            dest = conserva if (info['prize_id'] and info['prize_id'] > 0) else scartare
            MoveItem(bod, 0, dest, 0,0,0); Wait(1000); continue
            
        cat_text, item_text, item_id, tool_type, item_cost = get_craft_info(info['item_name'])
        if cat_text is None: MoveItem(bod, 0, scartare, 0,0,0); continue
            
        # Count existing valid items in backpack first
        in_bag = count_valid_backpack_items(item_id, info['is_except'])
        to_make = info['qty_needed'] - in_bag
        
        if to_make > 0:
            if not check_and_pull_materials(info['material'], to_make, item_cost, crate):
                MoveItem(bod, 0, riprova, 0,0,0); continue
                
            mat_btn = MATERIAL_MAP[info['material']]['btn']
            success = craft_items_until_done(tool_type, cat_text, item_text, item_id, info['qty_needed'], info['is_except'], mat_btn)
            
            # FORCE CLOSE crafting gump to guarantee it won't block the BOD opening
            close_all_gumps()
            
            if not success: MoveItem(bod, 0, riprova, 0,0,0); continue
            
        is_full = fill_bod_completely(bod, item_id, info['qty_needed'], info['item_name'], info['is_except'])
        
        # FIXED: Use logical and to guard against NoneType prize_id comparison
        dest = (conserva if info['prize_id'] and info['prize_id'] > 0 else consegna) if is_full else riprova
        MoveItem(bod, 0, dest, 0,0,0); Wait(1000)

    AddToSystemJournal("=== Crafting Cycle Complete ===")

if __name__ == '__main__':
    run_crafting_cycle()