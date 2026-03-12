from stealth import *
import json
import os
import time
from bod_data import LARGE_COMPONENTS

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status,
    _INV_LOCK
)

COMBINE_BTN = 2

def append_to_inventory(bod_obj):
    """
    Appends a new BOD to the inventory JSON, tracking its exact server array position.
    This can be called natively by the Crafting script when it deposits a prized Small BOD.
    """
    with _INV_LOCK:
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

        tmp = INVENTORY_FILE + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(inventory, f, indent=4)
            os.replace(tmp, INVENTORY_FILE)
            item_name = bod_obj.get('item', bod_obj.get('category', 'BOD')).title()
            mat_name = bod_obj.get('material', '')
            AddToSystemJournal(f"State Management: Added {mat_name} {item_name} to Pos #{bod_obj['pos']}")
        except Exception as e:
            AddToSystemJournal(f"State Management Error: Failed to write to JSON — {e}")

def reindex_inventory():
    """Re-calculates pos, drop_btn, and page for every entry in the inventory JSON.

    Entries are sorted by their current pos value to preserve relative order,
    then renumbered 0..N-1.  Useful after a manual scanner re-scan or any
    out-of-band edit that left the file with gaps or stale page numbers.

    Formulas (same as append_to_inventory and extract_bods):
        drop_btn = 5 + (pos * 2)
        page     = (pos // 10) + 1
    """
    with _INV_LOCK:
        if not os.path.exists(INVENTORY_FILE):
            AddToSystemJournal("Reindex Error: Inventory JSON not found.")
            return False

        try:
            with open(INVENTORY_FILE, "r") as f:
                inventory = json.load(f)
        except Exception as e:
            AddToSystemJournal(f"Reindex Error reading inventory: {e}")
            return False

        inventory.sort(key=lambda b: b.get('pos', 0))

        for new_pos, bod in enumerate(inventory):
            bod['pos']      = new_pos
            bod['drop_btn'] = 5 + (new_pos * 2)
            bod['page']     = (new_pos // 10) + 1

        tmp = INVENTORY_FILE + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(inventory, f, indent=4)
            os.replace(tmp, INVENTORY_FILE)
            AddToSystemJournal(f"Reindex complete: {len(inventory)} BODs renumbered (pos 0–{len(inventory)-1}).")
            return True
        except Exception as e:
            AddToSystemJournal(f"Reindex Error writing inventory: {e}")
            return False


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

def extract_bods(book_serial, target_bods, inventory=None):
    """Performs a single Reverse Sweep extraction using fast Gump Serial polling.

    If inventory is provided, re-indexes it in-place after each successful drop:
    the extracted item is removed and every subsequent item's pos/drop_btn/page
    decrements by 1 to mirror UO's server-side compaction.  The JSON is saved
    atomically after each step so append_to_inventory() always has accurate positions,
    and a crash mid-sweep still leaves the file in a consistent state.
    """
    # Ensure strict descending order so UO's server indexing doesn't shift for earlier drops
    target_bods.sort(key=lambda x: x['pos'], reverse=True)
    extracted_map = {}
    
    for bod in target_bods:
        if check_abort(): break
        world_save_guard()
        
        close_all_gumps()
        # Cancel any lingering target cursor left by crafting tools (scissors/tongs).
        # If TargetPresent() is True, UseObject() is consumed as a target click
        # instead of opening the book, causing the gump to never appear (idx = -1).
        if TargetPresent():
            CancelTarget()
            Wait(300)
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
                    lost_gump = True
                    break

                current_page += 1

            if lost_gump:
                AddToSystemJournal(f"Warning: Lost book gump while turning to page {target_page}.")
                continue

            Wait(200) # Tiny tick to let UI register before dropping

            # Verify the book gump is still open at idx before pressing.
            # It can close during Wait() if a world save or server event fires.
            if GetGumpID(idx) != BOOK_GUMP_ID:
                AddToSystemJournal(f"Warning: Book gump closed before drop for Pos #{bod['pos']}. Skipping.")
                continue

            extracted = False
            for attempt in range(2):  # press + one retry
                NumGumpButton(idx, bod['drop_btn'])

                t_drop = time.time()
                while time.time() - t_drop < 3:
                    Wait(10)
                    FindType(BOD_TYPE, Backpack())
                    after_bods = list(GetFoundList())
                    new_bods = [b for b in after_bods if b not in before_bods]

                    if new_bods:
                        extracted_map[bod['pos']] = new_bods[0]
                        extracted = True
                        break

                if extracted:
                    break

                if attempt == 0:
                    # First attempt failed — re-open the book to the correct page and retry once
                    AddToSystemJournal(f"Retry: Pos #{bod['pos']} drop failed, re-opening book...")
                    close_all_gumps()
                    Wait(300)
                    UseObject(book_serial)
                    t_reopen = time.time()
                    idx = -1
                    while time.time() - t_reopen < 3:
                        Wait(10)
                        for i in range(GetGumpsCount()):
                            if GetGumpID(i) == BOOK_GUMP_ID:
                                idx = i
                                current_serial = GetGumpInfo(i)['Serial']
                                break
                        if idx != -1:
                            break
                    if idx == -1:
                        break  # book didn't reopen — give up
                    # Navigate back to target_page
                    current_page = 1
                    lost_gump = False
                    while current_page < target_page:
                        NumGumpButton(idx, NEXT_PAGE_BTN)
                        idx, current_serial, page_changed = wait_for_gump_serial_change(current_serial, BOOK_GUMP_ID, 8000)
                        if not page_changed:
                            lost_gump = True
                            break
                        current_page += 1
                    if lost_gump:
                        break  # couldn't reach the page on retry — give up
                    Wait(200)

            if not extracted:
                AddToSystemJournal(f"Warning: Pos #{bod['pos']} — drop not confirmed after retry.")
            elif inventory is not None:
                # Remove the extracted entry from the working inventory, save the
                # stripped list to disk, then do a full reindex pass so pos/drop_btn/page
                # are always recalculated from scratch after every drop.
                extracted_pos = bod['pos']
                inventory[:] = [b for b in inventory if b.get('pos') != extracted_pos]
                with _INV_LOCK:
                    tmp = INVENTORY_FILE + '.tmp'
                    try:
                        with open(tmp, 'w') as f:
                            json.dump(inventory, f, indent=4)
                        os.replace(tmp, INVENTORY_FILE)
                    except Exception as e:
                        AddToSystemJournal(f"State Management Error: save after extraction failed — {e}")
                # Full reindex: loads the stripped file, renumbers 0..N-1, saves.
                if reindex_inventory():
                    try:
                        with open(INVENTORY_FILE, 'r') as f:
                            inventory[:] = json.load(f)
                    except Exception:
                        pass

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
        except Exception:
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

    # 3. Extract all targets back-to-front.
    # Pass inventory so extract_bods() re-indexes it after each individual drop,
    # keeping the JSON in sync with the server's compacted positions throughout.
    extracted_map = extract_bods(conserva, all_target_bods, inventory)

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

    # 5. JSON is already fully re-indexed by extract_bods() after each individual drop.
    if extracted_positions:
        AddToSystemJournal(f"State Management: {len(extracted_positions)} BODs extracted and JSON re-indexed incrementally.")

    if sets_completed > 0:
        stats = read_stats()
        stats["prized_large"] = stats.get("prized_large", 0) + sets_completed
        write_stats(stats)

    return sets_completed


if __name__ == '__main__':
    run_assembler()