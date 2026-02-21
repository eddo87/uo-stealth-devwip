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
import BodCycler_Item_Verification as Verifier

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): 
        return False

# --- Config ---
# Fallback count if Config file is unreadable
BODS_TO_PROCESS = 5

# --- Constants ---
BOD_TYPE = 0x2258
BOOK_GUMP_ID = 0x54F555DF
CRAFT_GUMP_ID = 0x38920abd

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


def update_stats(crafted=0, prized_small=0, prized_large=0):
    """Updates the persistent stats JSON file for the GUI to read."""
    stats = {"crafted": 0, "prized_small": 0, "prized_large": 0}
    
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                stats.update(json.load(f))
        except Exception:
            pass
            
    stats["crafted"] += crafted
    stats["prized_small"] += prized_small
    stats["prized_large"] += prized_large
    
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=4)
    except Exception as e:
        AddToSystemJournal(f"Failed to save stats: {e}")


def close_all_gumps():
    """Closes all open gumps to ensure a clean UI state."""
    count = GetGumpsCount()
    if count > 0:
        for i in reversed(range(count)):
            CloseSimpleGump(i)
        Wait(500)


def consolidate_materials(crate_serial):
    """Scans the backpack for loose cloth, leather, bone, and iron and moves it to the resource crate."""
    if crate_serial == 0: 
        return
    
    found_any = False
    # Materials to clean up
    for c_type in [0x1766, 0x1767, 0x1081, 0x0F7E, 0x1BF2]:
        FindType(c_type, Backpack())
        items = GetFoundList()
        if items and not found_any:
            AddToSystemJournal("Consolidating leftover materials into crate...")
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
            if GetGumpID(i) == gump_id: 
                return i
        Wait(50)
    return -1


def find_button_for_text(gump_data, text_to_find):
    """
    Finds a button near a specific text. 
    Pass 1: Checks for an Exact Match.
    Pass 2: Checks for regex word-boundary fallback.
    """
    search_text = text_to_find.upper()
    
    def _get_btn(target_x, target_y, target_page):
        best_btn = None
        min_dist = 1000
        if 'GumpButtons' in gump_data:
            for btn in gump_data['GumpButtons']:
                btn_page = btn.get('Page', 0)
                if btn_page != target_page and btn_page != 0: 
                    continue
                by = btn.get('Y')
                bx = btn.get('X')
                bid = btn.get('ReturnValue') 
                if bx < target_x and abs(by - target_y) < 20:
                    dist = target_x - bx
                    if dist < min_dist:
                        min_dist = dist
                        best_btn = bid
        return best_btn

    # Pass 1: EXACT MATCH (Prevents "Elven Boots" from matching "Boots")
    if 'XmfHTMLGumpColor' in gump_data:
        for entry in gump_data['XmfHTMLGumpColor']:
            cliloc = entry.get('ClilocID', 0)
            content = GetClilocByID(cliloc).upper()
            clean_content = content.replace("<CENTER>", "").replace("</CENTER>", "").strip()
            if clean_content == search_text:
                return _get_btn(entry.get('X'), entry.get('Y'), entry.get('Page', 0))
                
    if 'GumpText' in gump_data and 'Text' in gump_data:
         for entry in gump_data['GumpText']:
             tid = entry.get('TextID')
             if tid < len(gump_data['Text']):
                 content = str(gump_data['Text'][tid]).upper().strip()
                 if content == search_text:
                     return _get_btn(entry.get('X'), entry.get('Y'), entry.get('Page', 0))

    # Pass 2: REGEX WORD BOUNDARY (Fallback for slight deviations)
    pattern = r'\b' + re.escape(search_text) + r'\b'
    
    if 'XmfHTMLGumpColor' in gump_data:
        for entry in gump_data['XmfHTMLGumpColor']:
            cliloc = entry.get('ClilocID', 0)
            content = GetClilocByID(cliloc).upper()
            clean_content = content.replace("<CENTER>", "").replace("</CENTER>", "")
            if re.search(pattern, clean_content):
                return _get_btn(entry.get('X'), entry.get('Y'), entry.get('Page', 0))
                
    if 'GumpText' in gump_data and 'Text' in gump_data:
         for entry in gump_data['GumpText']:
             tid = entry.get('TextID')
             if tid < len(gump_data['Text']):
                 content = str(gump_data['Text'][tid]).upper()
                 if re.search(pattern, content):
                     return _get_btn(entry.get('X'), entry.get('Y'), entry.get('Page', 0))

    return None


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

    close_all_gumps()
    
    FindType(BOD_TYPE, Backpack())
    before = GetFoundList()
    UseObject(origine_serial)
    idx = wait_for_gump(BOOK_GUMP_ID, 5000)
    
    if idx == -1: 
        AddToSystemJournal("Debug: Failed to open Origine book gump.")
        return 0
    
    NumGumpButton(idx, 5) # Drop first BOD
    Wait(2000)
    CloseSimpleGump(idx)
    Wait(500)
    
    FindType(BOD_TYPE, Backpack())
    after = GetFoundList()
    new_bods = [b for b in after if b not in before]
    
    if new_bods: 
        return new_bods[0]
        
    AddToSystemJournal("Debug: Clicked drop, but no new BOD appeared in backpack.")
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
        if item_name != "unknown": 
            break

    # 2. Extract Numbers
    for line in lines:
        if "amount to make" in line:
            match = re.search(r'\d+', line)
            if match: 
                qty_total = int(match.group())
        elif item_name != "unknown" and item_name in line and ":" in line:
            match = re.search(r':\s*(\d+)', line)
            if match: 
                qty_finished = int(match.group(1))

    qty_needed = qty_total - qty_finished

    # 3. Material Determination (Fixed order to prioritize explicit colored materials)
    mat = "unknown"
    
    # Step 3a: ALWAYS check the tooltip first for explicit colored material requirements.
    # Exclude base materials so "leather" (7 chars) doesn't overwrite "horned" (6 chars)
    colored_mats = [m for m in MATERIAL_MAP.keys() if m not in ["iron", "leather", "cloth", "bone"]]
    sorted_colored = sorted(colored_mats, key=len, reverse=True)
    
    for m in sorted_colored:
        if m in tooltip:
            mat = m
            break
            
    # Step 3b: If no specific color is requested, fall back to our dictionary's base material
    if mat == "unknown":
        # Use explicit base material from dictionary if provided (Index 4)
        if item_name in TAILOR_ITEMS and len(TAILOR_ITEMS[item_name]) >= 5:
            mat = TAILOR_ITEMS[item_name][4]
            
        # Step 3c: Fallback to smart parsing if the dictionary isn't updated yet
        else:
            if item_name in TAILOR_ITEMS:
                item_cat = TAILOR_ITEMS[item_name][0]
                if "leather" in item_name or "studded" in item_name or item_cat == "Footwear": 
                    mat = "leather"
                elif "bone" in item_name: 
                    mat = "bone"
                else: 
                    mat = "cloth"
            else: 
                mat = "iron"
            
    cat = categorize_items(item_name) if item_name != "unknown" else "Small Bods"
    mat_proper = mat.title()
    
    if mat_proper == "Dull copper": 
        mat_proper = "Dull Copper"
    elif mat_proper == "Shadow iron": 
        mat_proper = "Shadow Iron"
    
    prize_id = get_prize_number(cat, mat_proper, qty_total, "Exceptional" if is_except else "Normal")
    
    return {
        "serial": bod_serial, 
        "is_large": is_large, 
        "is_except": is_except,
        "qty_total": qty_total, 
        "qty_finished": qty_finished, 
        "qty_needed": qty_needed,
        "item_name": item_name, 
        "material": mat, 
        "cat": cat, 
        "prize_id": prize_id
    }


def is_item_exceptional(item_serial):
    """Safely checks if an item is exceptional, waiting for server tooltips to load."""
    tt = GetTooltip(item_serial)
    if tt and "exceptional" in tt.lower():
        return True
        
    ClickOnObject(item_serial)
    Wait(400) 
    tt = GetTooltip(item_serial)
    
    return tt and "exceptional" in tt.lower()


def count_valid_backpack_items(item_id, is_except):
    """Counts valid items currently in backpack."""
    FindType(item_id, Backpack())
    found = GetFoundList()
    count = 0
    for item in found:
        if not is_except:
            count += 1
        elif is_item_exceptional(item):
            count += 1
    return count


def get_craft_info(item_name):
    """Retrieves Crafting parameters, supporting both String names and exact Button IDs."""
    item_lower = item_name.lower()
    if item_lower in TAILOR_ITEMS:
        data = TAILOR_ITEMS[item_lower]
        return (
            data[0], # Category (Text OR Button ID)
            data[1], # Item (Text OR Button ID)
            data[2], # Graphic ID
            0x0F9D,  # Tool Type
            data[3]  # Resource Cost
        )
    return None, None, None, None, None


def check_and_pull_materials(material, qty_to_craft, item_cost, crate_serial):
    if material not in MATERIAL_MAP: 
        return False
        
    mat_info = MATERIAL_MAP[material]
    mat_types = mat_info["types"]
    mat_color = mat_info["color"]
    
    if mat_color == -1: 
        mat_color = 0xFFFF
    
    required_units = int((qty_to_craft * item_cost) * 1.2)
    bp_qty = 0
    for t in mat_types:
        FindTypeEx(t, mat_color, Backpack(), False)
        bp_qty += FindFullQuantity()
        
    if bp_qty >= required_units: 
        return True
    
    AddToSystemJournal(f"Low on {material} (Need {required_units}, Have {bp_qty}). Pulling from crate...")
    if crate_serial != 0:
        UseObject(crate_serial)
        Wait(1000)
    
    for t in mat_types:
        if check_abort(): 
            return False
            
        FindTypeEx(t, mat_color, crate_serial, False)
        found_stacks = GetFoundList()
        
        for stack in found_stacks:
            if check_abort(): 
                return False
                
            world_save_guard()
            FindTypeEx(t, mat_color, Backpack(), False)
            current_bp_qty = FindFullQuantity()
            
            if current_bp_qty >= required_units: 
                return True
                
            amount_needed_now = required_units - current_bp_qty
            pull_amt = max(400, amount_needed_now)
            MoveItem(stack, pull_amt, Backpack(), 0, 0, 0)
            Wait(1200)
            
    FindTypeEx(t, mat_color, Backpack(), False)
    if FindFullQuantity() >= required_units: 
        return True
            
    AddToSystemJournal(f"CRITICAL: Out of {material} in Crate!")
    return False


def recycle_invalid_items(item_id, is_except, tool_type):
    if not is_except: 
        return 
        
    FindType(item_id, Backpack())
    items = GetFoundList()
    
    for it in items:
        if check_abort(): 
            break
            
        if not is_item_exceptional(it):
            world_save_guard()
            
            if tool_type == 0x0F9D: # Scissors
                FindType(0x0F9E, Backpack()) 
                if FindCount() > 0:
                    UseObject(FindItem())
                    WaitForTarget(1500)
                    TargetToObject(it)
                    Wait(800)
                    
            elif tool_type == 0x0FBC: # Tongs (Smelt)
                FindType(tool_type, Backpack())
                if FindCount() > 0:
                    UseObject(FindItem())
                    idx = wait_for_gump(CRAFT_GUMP_ID)
                    if idx != -1: 
                        NumGumpButton(idx, 14)
                        WaitForTarget(1500)
                        TargetToObject(it)
                        Wait(800)


def craft_items_until_done(bod_serial, tool_type, cat_identifier, item_identifier, item_name, item_id, qty_needed, is_except, mat_btn):
    """Crafts items utilizing either exact Button IDs or intelligent text fallback."""
    current_target_id = item_id 
    made_valid = count_valid_backpack_items(current_target_id, is_except)
    attempts = 0
    make_last_ready = False
    
    while made_valid < qty_needed and attempts < (qty_needed * 3):
        if check_abort(): 
            AddToSystemJournal("Abort detected. Stopping tool crafting.")
            return False
            
        world_save_guard()
        attempts += 1
        
        FindType(tool_type, Backpack())
        if FindCount() == 0: 
            AddToSystemJournal("Out of tools!")
            return False
            
        tool = FindItem()
        
        idx = wait_for_gump(CRAFT_GUMP_ID, 500)
        if idx == -1:
            UseObject(tool)
            idx = wait_for_gump(CRAFT_GUMP_ID, 10000)
            
        if idx == -1: 
            AddToSystemJournal("Crafting gump failed to open.")
            continue
        
        gump_data = GetGumpInfo(idx)
        
        FindType(0xFFFF, Backpack())
        before_serials = set(GetFoundList())
        
        if make_last_ready:
            NumGumpButton(idx, 21) # Make Last
            Wait(600) 
            if wait_for_gump(CRAFT_GUMP_ID, 5000) == -1:
                AddToSystemJournal("Gump did not refresh.")
        else:
            if mat_btn is not None:
                NumGumpButton(idx, 7)
                Wait(800)
                idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
                if idx != -1: 
                    NumGumpButton(idx, mat_btn)
                    Wait(800) 
                    idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
                    gump_data = GetGumpInfo(idx)
            
            # Category Selection (Button ID vs Text Scan)
            if isinstance(cat_identifier, int):
                cat_btn = cat_identifier
            else:
                cat_btn = find_button_for_text(gump_data, cat_identifier)
                
            if cat_btn is None: 
                AddToSystemJournal("Could not find/process Category Button.")
                return False
                
            NumGumpButton(idx, cat_btn)
            Wait(800)
            idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
            
            # Item Selection (Button ID vs Text Scan)
            if isinstance(item_identifier, int):
                item_craft_btn = item_identifier
            else:
                # We changed pages, so we must pull fresh Gump Info before searching text!
                gump_data = GetGumpInfo(idx) 
                item_craft_btn = find_button_for_text(gump_data, item_identifier)
                
            if item_craft_btn is None: 
                AddToSystemJournal("Could not find/process Item Button.")
                return False
                
            NumGumpButton(idx, item_craft_btn)
            Wait(600)
            if wait_for_gump(CRAFT_GUMP_ID, 5000) == -1:
                 AddToSystemJournal("Gump did not refresh.")

        Wait(400)
        
        FindType(0xFFFF, Backpack())
        after_serials = set(GetFoundList())
        new_items = after_serials - before_serials
        
        if new_items:
            new_serial = list(new_items)[0]
            actual_graphic = GetType(new_serial) 
            
            if actual_graphic != current_target_id:
                AddToSystemJournal(f"ID Mismatch Detected. Verifying...")
                if Verifier.test_item_acceptance(bod_serial, new_serial, item_name):
                    current_target_id = actual_graphic
                    make_last_ready = True 
                else:
                    AddToSystemJournal("Item REJECTED by BOD. Tripping Circuit Breaker.")
                    try:
                        import BodCycler_AI_Debugger
                        # Uses original item_name so the Debugger logic doesn't break on Integers
                        BodCycler_AI_Debugger.report_mismatch(item_name, current_target_id, actual_graphic, str(cat_identifier))
                    except: 
                        pass
                    return False 
            else:
                make_last_ready = True
        
        recycle_invalid_items(current_target_id, is_except, tool_type)
        made_valid = count_valid_backpack_items(current_target_id, is_except)
        AddToSystemJournal(f"Crafting check: {made_valid}/{qty_needed} in bag.")
        
    return made_valid >= qty_needed


def is_bod_full(bod_serial, item_name):
    tooltip = GetTooltip(bod_serial).lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]
    amt_to_make = 0
    amt_finished = 0
    
    for line in lines:
        if "amount to make" in line:
            match = re.search(r'\d+', line)
            if match:
                amt_to_make = int(match.group())
        elif item_name.lower() in line and ":" in line:
            match = re.search(r':\s*(\d+)', line)
            if match:
                amt_finished = int(match.group(1))
                
    return amt_to_make > 0 and amt_to_make == amt_finished


def fill_bod_completely(bod_serial, item_id, qty_to_fill, item_name, is_except):
    """Fills only the amount required to finish the BOD, filtering valid items first."""
    AddToSystemJournal(f"Filling BOD...")
    
    FindType(item_id, Backpack())
    all_items = GetFoundList()
    valid_items = []
    
    for item in all_items:
        if not is_except:
            valid_items.append(item)
        elif is_item_exceptional(item):
            valid_items.append(item)
                
    if not valid_items:
        AddToSystemJournal("No valid crafted items found.")
        return False

    for item in valid_items:
        if check_abort(): 
            break
            
        if not TargetPresent():
            if is_bod_full(bod_serial, item_name):
                break
                
            close_all_gumps()
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
                if idx != -1: 
                    break
                    
            if idx != -1: 
                NumGumpButton(idx, 2)
                WaitForTarget(5000)
            else:
                break

        if TargetPresent():
            world_save_guard()
            TargetToObject(item)
            Wait(100) 
            WaitForTarget(600) 
            
    if TargetPresent(): 
        CancelTarget()
        Wait(600)
        
    close_all_gumps()
    return is_bod_full(bod_serial, item_name)


def run_crafting_cycle():
    config = load_config()
    if not config: 
        return
        
    origine = config['books']['Origine']
    consegna = config['books']['Consegna']
    conserva = config['books']['Conserva']
    scartare = config['books']['Scartare']
    riprova = config['books']['Riprova']
    crate = config['containers']['MaterialCrate']
    
    try: 
        target_trades = int(config.get("trade", {}).get("target_trades", BODS_TO_PROCESS))
    except ValueError: 
        target_trades = BODS_TO_PROCESS
        
    session_crafted = 0
    session_small = 0
    session_large = 0
    
    AddToSystemJournal(f"=== Starting Crafting Cycle ({target_trades} BODs) ===")
    
    if crate != 0:
        UseObject(crate)
        Wait(1000)
        
    for i in range(target_trades):
        if check_abort(): 
            break
            
        close_all_gumps()
        consolidate_materials(crate) 
        
        FindType(BOD_TYPE, Backpack())
        if FindCount() > 0:
            bod = FindItem()
            AddToSystemJournal(f"Found existing BOD in backpack: {hex(bod)}")
        else:
            bod = extract_bod_from_origine(origine)
            if bod == 0: 
                break
            
        info = parse_bod(bod)
        
        if info['qty_needed'] <= 0:
            dest = conserva if (info['prize_id'] and info['prize_id'] > 0) else consegna
            if dest == conserva:
                if info['is_large']: 
                    session_large += 1
                else: 
                    session_small += 1
            MoveItem(bod, 0, dest, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            continue

        if info['material'] == "bone" or info['is_large']:
            dest = conserva if (info['prize_id'] and info['prize_id'] > 0) else scartare
            if dest == conserva:
                if info['is_large']: 
                    session_large += 1
                else: 
                    session_small += 1
            MoveItem(bod, 0, dest, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            continue
            
        cat_identifier, item_identifier, item_id, tool_type, item_cost = get_craft_info(info['item_name'])
        
        if cat_identifier is None: 
            MoveItem(bod, 0, scartare, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            continue
            
        in_bag = count_valid_backpack_items(item_id, info['is_except'])
        to_make = info['qty_needed'] - in_bag
        
        if to_make > 0:
            if not check_and_pull_materials(info['material'], to_make, item_cost, crate):
                MoveItem(bod, 0, riprova, 0, 0, 0)
                Wait(1000)
                close_all_gumps()
                continue
                
            mat_btn = MATERIAL_MAP[info['material']]['btn']
            success = craft_items_until_done(bod, tool_type, cat_identifier, item_identifier, info['item_name'], item_id, info['qty_needed'], info['is_except'], mat_btn)
            close_all_gumps()
            
            if not success: 
                MoveItem(bod, 0, riprova, 0, 0, 0)
                Wait(1000)
                close_all_gumps()
                continue
            
        is_full = fill_bod_completely(bod, item_id, info['qty_needed'], info['item_name'], info['is_except'])
                     
        close_all_gumps()
        
        if is_full:
            session_crafted += 1
            dest = conserva if (info['prize_id'] and info['prize_id'] > 0) else consegna
            if dest == conserva:
                if info['is_large']: 
                    session_large += 1
                else: 
                    session_small += 1
        else:
            dest = riprova
            
        MoveItem(bod, 0, dest, 0, 0, 0)
        Wait(1000)
        close_all_gumps()

    update_stats(session_crafted, session_small, session_large)
    AddToSystemJournal("=== Crafting Cycle Complete ===")


if __name__ == '__main__':
    run_crafting_cycle()