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
import checkWorldSave
import BodCycler_AI_Debugger
import BodCycler_Assembler

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

def update_stats(crafted=0, prized_small=0, prized_large=0, recovery_success=0, mats_used=None):
    """Updates the persistent stats JSON safely and tracks material consumption & time."""
    stats = {"crafted": 0, "prized_small": 0, "prized_large": 0, "recovery_success": 0, "mats_used": {}}
    
    if os.path.exists(STATS_FILE):
        for _ in range(5):
            try:
                with open(STATS_FILE, "r") as f:
                    content = f.read()
                    if content.strip():
                        stats.update(json.loads(content))
                break 
            except Exception:
                time.sleep(0.2) 
                
    if "session_start" not in stats:
        stats["session_start"] = time.time()
                
    stats["crafted"] = stats.get("crafted", 0) + crafted
    stats["prized_small"] = stats.get("prized_small", 0) + prized_small
    stats["prized_large"] = stats.get("prized_large", 0) + prized_large
    stats["recovery_success"] = stats.get("recovery_success", 0) + recovery_success
    
    if "mats_used" not in stats:
        stats["mats_used"] = {}
        
    if mats_used:
        for k, v in mats_used.items():
            stats["mats_used"][k] = stats["mats_used"].get(k, 0) + v
    
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
    for c_type in [0x1766, 0x1767, 0x1081, 0x0F7E, 0x1BF2]:
        FindType(c_type, Backpack())
        items = GetFoundList()
        if items and not found_any:
            AddToSystemJournal("Consolidating leftover materials into crate...")
            found_any = True
            
        for item in items:
            checkWorldSave.world_save_guard()
            MoveItem(item, 0, crate_serial, 0, 0, 0)
            Wait(800)

def wait_for_gump(gump_id, timeout_ms=3000):
    t = datetime.now()
    while (datetime.now() - t).total_seconds() * 1000 < timeout_ms:
        checkWorldSave.world_save_guard()
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == gump_id: 
                return i
        Wait(50)
    return -1

def extract_bod_from_origine(origine_serial):
    if GetType(origine_serial) != 0x2259:
        FindType(BOD_TYPE, origine_serial)
        if FindCount() > 0:
            bod = FindItem()
            checkWorldSave.world_save_guard()
            MoveItem(bod, 1, Backpack(), 0, 0, 0)
            Wait(1200)
            return bod
        return 0

    close_all_gumps()
    FindType(BOD_TYPE, Backpack())
    before = GetFoundList()
    UseObject(origine_serial)
    idx = wait_for_gump(BOOK_GUMP_ID, 4000)
    
    if idx == -1: 
        return 0
    
    NumGumpButton(idx, 5) # Drop first BOD
    Wait(1500)
    CloseSimpleGump(idx)
    Wait(500)
    
    FindType(BOD_TYPE, Backpack())
    after = GetFoundList()
    new_bods = [b for b in after if b not in before]
    
    if new_bods: 
        return new_bods[0]
        
    return 0

def parse_bod(bod_serial):
    tooltip = GetTooltip(bod_serial).lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]
    
    is_large = "large" in tooltip
    is_except = "exceptional" in tooltip
    
    qty_total = 0
    qty_finished = 0
    item_name = "unknown"
    
    sorted_keys = sorted(TAILOR_ITEMS.keys(), key=len, reverse=True)
    for line in lines:
        for key in sorted_keys:
            if key in line:
                item_name = key
                break
        if item_name != "unknown": 
            break

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
    mat = "unknown"
    
    colored_mats = [m for m in MATERIAL_MAP.keys() if m not in ["iron", "leather", "cloth", "bone"]]
    sorted_colored = sorted(colored_mats, key=len, reverse=True)
    
    for m in sorted_colored:
        if m in tooltip:
            mat = m
            break
            
    if mat == "unknown":
        if item_name in TAILOR_ITEMS and len(TAILOR_ITEMS[item_name]) >= 5:
            mat = TAILOR_ITEMS[item_name][4]
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
    tt = GetTooltip(item_serial)
    if tt and "exceptional" in tt.lower():
        return True
        
    ClickOnObject(item_serial)
    Wait(300) 
    tt = GetTooltip(item_serial)
    
    return tt and "exceptional" in tt.lower()

def count_valid_backpack_items(item_id, is_except):
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
    item_lower = item_name.lower()
    if item_lower in TAILOR_ITEMS:
        data = TAILOR_ITEMS[item_lower]
        # Return exact integers based on bod_crafting_data.py
        return data[0], data[1], data[2], 0x0F9D, data[3]
    return None, None, None, None, None

def check_and_pull_materials(material, qty_to_craft, item_cost, crate_serial):
    if material not in MATERIAL_MAP: 
        return False
        
    mat_info = MATERIAL_MAP[material]
    mat_types = mat_info["types"]
    mat_color = mat_info["color"]
    
    if mat_color == -1: 
        mat_color = 0xFFFF
    
    required_units = int((qty_to_craft * item_cost) + 40)
    
    def get_total_bp_qty():
        total = 0
        for t in mat_types:
            FindTypeEx(t, mat_color, Backpack(), False)
            total += FindFullQuantity()
        return total

    current_total = get_total_bp_qty()
    if current_total >= required_units: 
        return True
    
    AddToSystemJournal(f"Need {required_units}. Pulling from crate...")
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
                
            checkWorldSave.world_save_guard()
            current_total = get_total_bp_qty()
            
            if current_total >= required_units: 
                return True
                
            amount_needed_now = required_units - current_total
            pull_amt = amount_needed_now
            
            stack_qty = GetQuantity(stack)
            if stack_qty <= 0:
                continue
                
            actual_pull = min(pull_amt, stack_qty)
            MoveItem(stack, actual_pull, Backpack(), 0, 0, 0)
            
            # Dynamic wait for the exact requested amount to hit the bag before proceeding
            t_wait = time.time()
            while time.time() - t_wait < 3.0:
                Wait(200)
                if get_total_bp_qty() > current_total:
                    break
                    
            if get_total_bp_qty() >= required_units: 
                return True
            
    if get_total_bp_qty() >= required_units: 
        return True
            
    AddToSystemJournal(f"CRITICAL: Out of {material} in Crate!")
    return False

            

def craft_items_until_done(bod_serial, tool_type, cat_btn, item_btn, item_id, qty_needed, is_except, mat_btn):
    """Restored the bulletproof Integer-based crafting logic from the backup version."""
    made_valid = count_valid_backpack_items(item_id, is_except)
    attempts = 0
    AddToSystemJournal(f"Crafting this BOD...")
    
    while made_valid < qty_needed and attempts < (qty_needed * 3):
        if check_abort(): return False
        checkWorldSave.world_save_guard()
        attempts += 1
        
        FindType(tool_type, Backpack())
        if FindCount() == 0: 
            AddToSystemJournal("Out of tools!")
            return False
            
        tool = FindItem()
        
        idx = wait_for_gump(CRAFT_GUMP_ID, 500)
        if idx == -1:
            UseObject(tool)
            idx = wait_for_gump(CRAFT_GUMP_ID, 8000)
            
        if idx == -1: 
            AddToSystemJournal("Crafting gump failed to open.")
            continue
        
        # Pacing Logic
        if attempts > 1:
            NumGumpButton(idx, 21) # Make Last
            Wait(600) 
            wait_for_gump(CRAFT_GUMP_ID, 4000)
        else:
            # change materials everytime
            if mat_btn is not None:
                NumGumpButton(idx, 7)
                Wait(800)
                idx = wait_for_gump(CRAFT_GUMP_ID, 4000)
                if idx != -1: 
                    NumGumpButton(idx, mat_btn)
                    Wait(800) 
                    idx = wait_for_gump(CRAFT_GUMP_ID, 4000)
            
            # Use exact integer buttons provided from dictionary
            if idx != -1 and cat_btn is not None:
                NumGumpButton(idx, cat_btn)
                Wait(800)
                idx = wait_for_gump(CRAFT_GUMP_ID, 4000)
                
            if idx != -1 and item_btn is not None:
                NumGumpButton(idx, item_btn)
                Wait(600)
                wait_for_gump(CRAFT_GUMP_ID, 4000)

        Wait(250)
        made_valid = count_valid_backpack_items(item_id, is_except)
        # AddToSystemJournal(f"Crafting check: {made_valid}/{qty_needed} in bag.") # Keep commented for debugging
        
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
            checkWorldSave.world_save_guard()
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
    session_recovery = 0
    session_mats_used = {}
    
    AddToSystemJournal(f"=== Starting Crafting Cycle ({target_trades} BODs) ===")
    
    if crate != 0:
        UseObject(crate)
        Wait(1000)
        
    origine_empty = False
        
    for i in range(target_trades):
        if check_abort(): 
            break
            
        if checkWorldSave.check_server_restart():
            break 
            
        close_all_gumps()
        consolidate_materials(crate) 
        
        is_recovery = False
        
        FindType(BOD_TYPE, Backpack())
        if FindCount() > 0:
            bod = FindItem()
            AddToSystemJournal(f"Found existing BOD in backpack: {hex(bod)}")
        else:
            if not origine_empty:
                bod = extract_bod_from_origine(origine)
                if bod == 0:
                    origine_empty = True
            else:
                bod = 0

            if bod == 0:

                AddToSystemJournal("Origine empty. No viable BODs left to process.")

                break
            
 
            
        info = parse_bod(bod)

        # STRICT SCARTARE LOGIC
        is_scartare = False
        if info['material'].lower() == "bone":
            is_scartare = True
        elif info['is_large']:
            if info.get('prize_id') not in [23, 24]:
                is_scartare = True

        if is_scartare:
            AddToSystemJournal(f"Trashing unwanted BOD: {info['item_name']} ({info['material']})")
            MoveItem(bod, 0, scartare, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            continue
        
        if info['qty_needed'] <= 0:
            dest = conserva if (info.get('prize_id') and info['prize_id'] > 0) else consegna
            if dest == conserva:
                if info['is_large']: 
                    session_large += 1
                else: 
                    session_small += 1
            MoveItem(bod, 0, dest, 0, 0, 0)
            Wait(1000)
            # --- ASSEMBLER INJECTION FOR PRE-FILLED BODS ---
            if dest == conserva:
                import BodCycler_Assembler
                new_bod_data = {
                    "type": "Large" if info.get('is_large') else "Small",
                    "item": info['item_name'].lower(),
                    "quality": "Exceptional" if info['is_except'] else "Normal",
                    "material": info.get('material', 'Iron'),
                    "amount": info.get('amount', info.get('qty_total', 20)),
                    "category": "Small Bods"
                }
                BodCycler_Assembler.append_to_inventory(new_bod_data)
            close_all_gumps()
            continue
            
        cat_btn, item_btn, item_id, tool_type, item_cost = get_craft_info(info['item_name'])
        
        if cat_btn is None: 
            MoveItem(bod, 0, scartare, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            continue
            
        in_bag = count_valid_backpack_items(item_id, info['is_except'])
        to_make = info['qty_needed'] - in_bag
        
        if to_make > 0:
            if not check_and_pull_materials(info['material'], to_make, item_cost, crate):
                AddToSystemJournal(f"Material Shortage: {info['item_name']} ({info['material']})")
                MoveItem(bod, 0, riprova, 0, 0, 0)
                Wait(1000)
                close_all_gumps()
                continue
                
            mat_btn = MATERIAL_MAP[info['material']]['btn']
            success = craft_items_until_done(
                bod, tool_type, cat_btn, item_btn, 
                item_id, info['qty_needed'], 
                info['is_except'], mat_btn
            )
            close_all_gumps()
            
            if not success: 
                AddToSystemJournal(f"Crafting Error: {info['item_name']} ({info['material']})")
                MoveItem(bod, 0, riprova, 0, 0, 0)
                Wait(1000)
                close_all_gumps()
                continue
            else:
                mat_key = info['material'].lower()
                session_mats_used[mat_key] = session_mats_used.get(mat_key, 0) + (to_make * item_cost)
            
        is_full = fill_bod_completely(bod, item_id, info['qty_needed'], info['item_name'], info['is_except'])
                     
        close_all_gumps()
        
        if is_full:
            session_crafted += 1
            if is_recovery:
                session_recovery += 1
                
            dest = conserva if (info.get('prize_id') and info['prize_id'] > 0) else consegna
            if dest == conserva:
                if info['is_large']: 
                    session_large += 1
                else: 
                    session_small += 1
        else:
            dest = riprova
            
        MoveItem(bod, 0, dest, 0, 0, 0)
        Wait(1000)
                # --- ASSEMBLER INJECTION FOR NEWLY CRAFTED BODS ---
        if dest == conserva:
            import BodCycler_Assembler
            new_bod_data = {
                "type": "Large" if info.get('is_large') else "Small",
                "item": info['item_name'].lower(),
                "quality": "Exceptional" if info['is_except'] else "Normal",
                "material": info.get('material', 'Iron'),
                "amount": info.get('amount', info.get('qty_total', info.get('qty_needed', 20))),
                "category": "Small Bods"
            }
            BodCycler_Assembler.append_to_inventory(new_bod_data)
        close_all_gumps()

    update_stats(session_crafted, session_small, session_large, session_recovery, session_mats_used)
    AddToSystemJournal("=== Crafting Cycle Complete ===")

if __name__ == '__main__':
    run_crafting_cycle()