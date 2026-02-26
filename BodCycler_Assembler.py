from stealth import *
import json
import os
import time
from bod_data import *

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): pass

from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status
)

def append_to_inventory(bod_obj):
    """
    Appends a new BOD to the inventory JSON, tracking its exact server array position.
    This can be called natively by the Crafting script when it deposits a prized Small BOD.
    """
    if not os.path.exists(INVENTORY_FILE):
        AddToSystemJournal("State Management: Inventory JSON not found. Run a manual Conserva Scan first!")
        return
        
    try:
        with open(INVENTORY_FILE, "r") as f:
            inventory = json.load(f)
    except Exception as e:
        AddToSystemJournal(f"State Management Error reading inventory: {e}")
        return
        
    # Find the current highest position in the book
    max_pos = -1
    for b in inventory:
        if b.get('pos', -1) > max_pos:
            max_pos = b['pos']
            
    # Calculate the exact Drop Button ID and Page based on the new appended position
    bod_obj['pos'] = max_pos + 1
    bod_obj['drop_btn'] = 5 + (bod_obj['pos'] * 2)
    bod_obj['page'] = (bod_obj['pos'] // 10) + 1 
    
    inventory.append(bod_obj)
    
    try:
        with open(INVENTORY_FILE, "w") as f:
            json.dump(inventory, f, indent=4)
            
        item_name = bod_obj.get('item', bod_obj.get('category', 'BOD')).title()
        mat_name = bod_obj.get('material', '')
        AddToSystemJournal(f"State Management: Added {mat_name} {item_name} to Pos #{bod_obj['pos']}")
    except:
        AddToSystemJournal("State Management Error: Failed to write to JSON.")

def find_completable_sets(inventory):
    smalls = [b for b in inventory if b['type'] == 'Small']
    larges = [b for b in inventory if b['type'] == 'Large']
    
    completed_sets = []
    used_smalls = set()
    
    for l_idx, large in enumerate(larges):
        cat = large['category']
        mat = large['material']
        qual = large['quality']
        amt = large['amount']
        
        components = LARGE_COMPONENTS.get(cat, [])
        if not components: continue
        
        matched_smalls = []
        for comp in components:
            found = False
            for s_idx, small in enumerate(smalls):
                if s_idx in used_smalls: continue
                # Allow Thigh Boots in Town Crier set to be either Leather or Cloth
                is_correct_mat = (small['material'] == mat)
                if cat == "Town Crier Set" and comp.lower() == "thigh boots":
                    is_correct_mat = small['material'] in ["Leather", "Cloth"]

                if (small['item'] == comp.lower() and 
                    is_correct_mat and 
                    small['quality'] == qual and 
                    small['amount'] == amt):
                    matched_smalls.append(small)
                    used_smalls.add(s_idx)
                    found = True
                    break
            if not found: break
            
        if len(matched_smalls) == len(components):
            completed_sets.append({
                'large': large,
                'smalls': matched_smalls
            })
            
    return completed_sets

def extract_bods(book_serial, target_bods):
    """Performs a single Reverse Sweep extraction using fast Gump Serial polling."""
    # Ensure strict descending order so UO's server indexing doesn't shift for earlier drops
    target_bods.sort(key=lambda x: x['pos'], reverse=True)
    extracted_map = {}
    
    for bod in target_bods:
        if check_abort(): break
        world_save_guard()
        
        close_all_gumps()
        FindType(BOD_TYPE, Backpack()) 
        before_bods = list(GetFoundList())
        
        UseObject(book_serial)
        
        t = time.time()
        idx = -1
        current_serial = 0
        while time.time() - t < 3:
            Wait(10)
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == BOOK_GUMP_ID:
                    idx = i
                    current_serial = GetGumpInfo(i)['Serial']
                    break
            if idx != -1: break
                
        if idx != -1:
            target_page = bod['page']
            current_page = 1
            lost_gump = False
            
            # Flip to the correct page
            while current_page < target_page:
                if check_abort(): return extracted_map
                NumGumpButton(idx, NEXT_PAGE_BTN)
                idx, current_serial, page_changed = wait_for_gump_serial_change(current_serial, BOOK_GUMP_ID, 8000)
                if not page_changed:
                    break
                    
                current_page += 1
                
            if lost_gump:
                AddToSystemJournal(f"Warning: Lost book gump while turning to page {target_page}.")
                continue
                
            Wait(200) # Tiny tick to let UI register before dropping
            NumGumpButton(idx, bod['drop_btn'])
            
            # Fast polling for the BOD to hit the backpack
            t_drop = time.time()
            extracted = False
            while time.time() - t_drop < 3:
                Wait(10)
                FindType(BOD_TYPE, Backpack())
                after_bods = list(GetFoundList())
                new_bods = [b for b in after_bods if b not in before_bods]
                
                if new_bods:
                    extracted_map[bod['pos']] = new_bods[0]
                    extracted = True
                    break
                    
            if not extracted:
                AddToSystemJournal(f"Warning: Expected drop for Pos #{bod['pos']} but got nothing.")
                
    return extracted_map

def combine_and_store(large_serial, small_serials, config):
    """Combines a single set locally in the backpack and routes to Consegna."""
    if not large_serial: return False

    AddToSystemJournal("Filling Large BOD with exact items...")
    
    for small in small_serials:
        if check_abort(): return False
        combined_successfully = False
        
        for attempt in range(3):
            world_save_guard()
            
            # Verification: If small bod doesn't exist, it was consumed successfully
            FindType(BOD_TYPE, Backpack())
            if small not in list(GetFoundList()):
                combined_successfully = True
                break
                
            if not TargetPresent():
                close_all_gumps()
                UseObject(large_serial)
                
                t_gump = time.time()
                idx = -1
                while time.time() - t_gump < 2:
                    Wait(10)
                    for i in range(GetGumpsCount()):
                        g = GetGumpInfo(i)
                        if g and 'GumpButtons' in g:
                            for btn in g['GumpButtons']:
                                if btn.get('ReturnValue') == COMBINE_BTN:
                                    idx = i
                                    break
                        if idx != -1: break
                    if idx != -1: break
                    
                if idx != -1:
                    NumGumpButton(idx, COMBINE_BTN)
                    WaitForTarget(5000)
                else:
                    break # Large BOD Gump failed to open properly

            if TargetPresent():
                world_save_guard()
                TargetToObject(small)
                Wait(100)
                WaitForTarget(600)
                
        if TargetPresent():
            CancelTarget()
            Wait(600)
            
        FindType(BOD_TYPE, Backpack())
        if small not in list(GetFoundList()):
            combined_successfully = True

        if not combined_successfully:
            AddToSystemJournal(f"CRITICAL: Failed to combine Small BOD {hex(small)}.")
            close_all_gumps()
            return False

    close_all_gumps()
    consegna_serial = config.get("books", {}).get("Consegna", 0)
    if consegna_serial:
        AddToSystemJournal("Dropping completely filled Large BOD into Consegna book...")
        MoveItem(large_serial, 1, consegna_serial, 0, 0, 0)
        Wait(1000)
        return True
    return False

def run_assembler():
    """Reads JSON to find targets, extracts them via Reverse Sweep, and re-indexes the JSON."""
    config = load_config()
    conserva = config.get("books", {}).get("Conserva", 0)
    if not conserva: return 0

    if not os.path.exists(INVENTORY_FILE):
        AddToSystemJournal("Assembler Error: Inventory JSON not found. Please run a manual Scan first.")
        return 0

    # 1. Load the Live Inventory State
    with open(INVENTORY_FILE, "r") as f:
        try:
            inventory = json.load(f)
        except:
            AddToSystemJournal("Assembler Error: Could not parse Inventory JSON.")
            return 0
        
    sets_to_build = find_completable_sets(inventory)
    
    if not sets_to_build:
        AddToSystemJournal("No complete sets found in JSON inventory.")
        return 0
        
    AddToSystemJournal(f"Found {len(sets_to_build)} sets to complete! Initiating Batch Extraction.")
    
    # 2. Build master extraction list
    all_target_bods = []
    for bod_set in sets_to_build:
        all_target_bods.append(bod_set['large'])
        all_target_bods.extend(bod_set['smalls'])
        
    AddToSystemJournal(f"Extracting {len(all_target_bods)} BODs in a single Reverse Sweep...")

    # 3. Extract all targets back-to-front
    extracted_map = extract_bods(conserva, all_target_bods)
    
    sets_completed = 0
    extracted_positions = list(extracted_map.keys())
    
    # 4. Process the extracted BODs locally in the backpack
    for bod_set in sets_to_build:
        if check_abort(): break
        
        # Link original pos mapping to the newly spawned backpack serials
        large_serial = extracted_map.get(bod_set['large']['pos'])
        small_serials = [extracted_map.get(small['pos']) for small in bod_set['smalls']]
        
        if large_serial and all(small_serials):
            if combine_and_store(large_serial, small_serials, config):
                sets_completed += 1
        else:
            AddToSystemJournal("Missing components from extraction. Skipping this set.")

    # 5. Update and Re-Index the JSON Database
    if extracted_positions:
        # Filter out the successfully extracted BODs
        new_inventory = [b for b in inventory if b['pos'] not in extracted_positions]
        
        # Recalculate physical array positions for UO server syncing
        for i, bod in enumerate(new_inventory):
            bod['pos'] = i
            bod['drop_btn'] = 5 + (i * 2)
            bod['page'] = (i // 10) + 1  # 10 BODs per page
            
        try:
            with open(INVENTORY_FILE, "w") as f:
                json.dump(new_inventory, f, indent=4)
            AddToSystemJournal(f"State Management: Removed {len(extracted_positions)} extracted BODs and re-indexed JSON.")
        except Exception as e:
            AddToSystemJournal(f"State Management Error: Could not update JSON. {e}")

    return sets_completed

def check_assembly_readiness(self):
    """
    Reads inventory.json and reports completable sets WITHOUT touching the game client.
    Sets and their components are reported in reverse-position order (mirrors Assembler sweep).
    """
    import json, os
    from bod_data import LARGE_COMPONENTS, prize_names, get_prize_number

    if not os.path.exists(INVENTORY_FILE):
        AddToSystemJournal("Assembly Check: inventory.json not found. Run a Scan first.")
        return

    try:
        with open(INVENTORY_FILE, "r") as f:
            inventory = json.load(f)
    except Exception as e:
        AddToSystemJournal(f"Assembly Check: Failed to read inventory.json — {e}")
        return

    try:
        import BodCycler_Assembler
        importlib.reload(BodCycler_Assembler)
        sets = BodCycler_Assembler.find_completable_sets(inventory)
    except Exception as e:
        AddToSystemJournal(f"Assembly Check: Error running find_completable_sets — {e}")
        return

    AddToSystemJournal("========================================")
    AddToSystemJournal(f"ASSEMBLY CHECK: {len(sets)} completable set(s) found in JSON")
    AddToSystemJournal("========================================")

    if not sets:
        AddToSystemJournal("No complete sets ready. Keep collecting small BODs.")
    else:
        # --- FIX 2: sort sets by large pos descending (mirrors Reverse Sweep order) ---
        sets.sort(key=lambda s: s['large'].get('pos', 0), reverse=True)

        for i, s in enumerate(sets, 1):
            large = s['large']
            smalls = s['smalls']

            # --- FIX 1: compute prize_id live from bod_data if not stored ---
            prize_id = large.get('prize_id')
            if not prize_id:
                cat      = large.get('category', '')
                mat      = large.get('material', '')
                amt      = large.get('amount', 0)
                qual     = large.get('quality', 'Normal')
                prize_id = get_prize_number(cat, mat, amt, qual)
                AddToSystemJournal(f"DEBUG fallback: cat={cat!r} mat={mat!r} amt={amt!r} qual={qual!r} -> {prize_id!r}")

            reward_label = prize_names.get(prize_id, f"Prize #{prize_id}") if prize_id else "No Prize"
            cat  = large.get('category', large.get('item', '?'))
            mat  = large.get('material', '?')
            qual = large.get('quality', '?')
            amt  = large.get('amount', '?')

            # --- FIX 2: sort smalls descending by pos (mirrors Reverse Sweep order) ---
            smalls_sorted = sorted(smalls, key=lambda x: x.get('pos', 0), reverse=True)
            small_positions = ', '.join(str(x.get('pos', '?')) for x in smalls_sorted)

            AddToSystemJournal(
                f"  Set #{i}: {cat} | {mat} {qual} x{amt} "
                f"-> {reward_label} "
                f"[Large @ pos {large.get('pos', '?')} | "
                f"Smalls (high->low): {small_positions}]"
            )

    AddToSystemJournal("========================================")

if __name__ == '__main__':
    run_assembler()