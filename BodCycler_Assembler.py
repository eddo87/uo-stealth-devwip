try:
    from stealth import *
except ImportError:
    pass  # Linux native Stealth: the py_stealth launcher injects the API into builtins
import json
import os
import re
import time
import datetime
from bod_data import LARGE_COMPONENTS

from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps, get_inventory_file,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status,
    _INV_LOCK, world_save_guard
)

COMBINE_BTN = 2

def append_to_inventory(bod_obj, conserva_serial):
    """
    Appends a new BOD to the per-book inventory JSON.
    conserva_serial identifies which Conserva book's file to write to.
    """
    inv_file = get_inventory_file(conserva_serial)
    with _INV_LOCK:
        if not os.path.exists(inv_file):
            AddToSystemJournal("State Management: Inventory JSON not found. Run a manual Conserva Scan first!")
            return

        try:
            with open(inv_file, "r") as f:
                inventory = json.load(f)
        except Exception as e:
            AddToSystemJournal(f"State Management Error reading inventory: {e}")
            return

        bod_obj['pos'] = len(inventory)
        bod_obj['drop_btn'] = 5 + (bod_obj['pos'] * 2)
        bod_obj['page'] = (bod_obj['pos'] // 10) + 1

        inventory.append(bod_obj)

        tmp = inv_file + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(inventory, f, indent=4)
            os.replace(tmp, inv_file)
            item_name = bod_obj.get('item', bod_obj.get('category', 'BOD')).title()
            mat_name = bod_obj.get('material', '')
            AddToSystemJournal(f"State Management: Added {mat_name} {item_name} to Pos #{bod_obj['pos']}")
        except Exception as e:
            AddToSystemJournal(f"State Management Error: Failed to write to JSON — {e}")

def reindex_inventory(conserva_serial):
    """Re-calculates pos, drop_btn, and page for every entry in the inventory JSON.

    Entries are sorted by their current pos value to preserve relative order,
    then renumbered 0..N-1.  Useful after a manual scanner re-scan or any
    out-of-band edit that left the file with gaps or stale page numbers.

    Formulas (same as append_to_inventory and extract_bods):
        drop_btn = 5 + (pos * 2)
        page     = (pos // 10) + 1
    """
    inv_file = get_inventory_file(conserva_serial)
    with _INV_LOCK:
        if not os.path.exists(inv_file):
            AddToSystemJournal("Reindex Error: Inventory JSON not found.")
            return False

        try:
            with open(inv_file, "r") as f:
                inventory = json.load(f)
        except Exception as e:
            AddToSystemJournal(f"Reindex Error reading inventory: {e}")
            return False

        inventory.sort(key=lambda b: b.get('pos', 0))

        for new_pos, bod in enumerate(inventory):
            bod['pos']      = new_pos
            bod['drop_btn'] = 5 + (new_pos * 2)
            # Page is approximate (assumes ~10 items/page). Extraction uses
            # button-search via _navigate_to_button(), not page numbers.
            bod['page']     = (new_pos // 10) + 1

        tmp = inv_file + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(inventory, f, indent=4)
            os.replace(tmp, inv_file)
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

def _navigate_to_button(idx, current_serial, target_btn):
    """Flips through book pages until target_btn appears in the gump's button list.

    The Scanner stores actual button IDs read from each page's gump, so each
    button is unique across the entire book.  We just flip until we find it.

    Returns (idx, current_serial, found).
    """
    MAX_PAGES = 200  # safety limit (~500 BODs / ~3 per page)
    for _ in range(MAX_PAGES):
        g = GetGumpInfo(idx)
        btn_ids = [b.get('ReturnValue', 0) for b in g.get('GumpButtons', [])]
        if target_btn in btn_ids:
            return idx, current_serial, True
        NumGumpButton(idx, NEXT_PAGE_BTN)
        idx, current_serial, page_changed = wait_for_gump_serial_change(
            current_serial, BOOK_GUMP_ID, 8000)
        if not page_changed:
            break  # no more pages
    return idx, current_serial, False


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
            # Navigate to the page containing this button by flipping until found
            idx, current_serial, found = _navigate_to_button(
                idx, current_serial, bod['drop_btn'])

            if not found:
                AddToSystemJournal(f"Warning: Could not find button {bod['drop_btn']} for Pos #{bod['pos']}. Skipping.")
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
                    # First attempt failed — re-open the book and search again
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
                    idx, current_serial, found = _navigate_to_button(
                        idx, current_serial, bod['drop_btn'])
                    if not found:
                        break  # couldn't find button on retry — give up
                    Wait(200)

            if not extracted:
                AddToSystemJournal(f"Warning: Pos #{bod['pos']} — drop not confirmed after retry.")
            elif inventory is not None:
                # Remove extracted entry, reindex in-place, and save atomically
                extracted_pos = bod['pos']
                inventory[:] = [b for b in inventory if b.get('pos') != extracted_pos]
                with _INV_LOCK:
                    for new_pos, entry in enumerate(inventory):
                        entry['pos'] = new_pos
                        entry['drop_btn'] = 5 + (new_pos * 2)
                        entry['page'] = 0  # approximate — extraction uses button-search
                    inv_file = get_inventory_file(book_serial)
                    tmp = inv_file + '.tmp'
                    try:
                        with open(tmp, 'w') as f:
                            json.dump(inventory, f, indent=4)
                        os.replace(tmp, inv_file)
                    except Exception as e:
                        AddToSystemJournal(f"State Management Error: save+reindex failed — {e}")

    return extracted_map

def _count_combined_smalls(large_serial):
    """Reads the Large BOD tooltip and counts how many component lines show a non-zero count.
    Returns (combined_count, total_components).
    E.g. 'studded gorget: 1' means 1 combined; 'studded gorget: 0' means not yet combined.
    """
    ClickOnObject(large_serial)
    Wait(400)
    tooltip = GetTooltip(large_serial).lower()
    lines = [l.strip() for l in tooltip.split('|') if l.strip()]

    combined = 0
    total = 0
    for line in lines:
        # Component lines look like "studded gorget: 0" or "studded gorget: 1"
        m = re.search(r':\s*(\d+)\s*$', line)
        if not m:
            continue
        # Skip non-component lines (amount to make, weight, etc.)
        if any(kw in line for kw in ['amount to make', 'weight', 'deeds', 'blessed']):
            continue
        val = int(m.group(1))
        total += 1
        if val > 0:
            combined += 1

    return combined, total


def _open_large_and_combine_target(large_serial):
    """Opens a Large BOD gump, presses Combine, waits for target cursor.
    Returns True if target appeared, False otherwise.
    """
    close_all_gumps()
    UseObject(large_serial)

    t_gump = time.time()
    idx = -1
    while time.time() - t_gump < 3:
        Wait(10)
        for i in range(GetGumpsCount()):
            g = GetGumpInfo(i)
            if g and 'GumpButtons' in g:
                for btn in g['GumpButtons']:
                    if btn.get('ReturnValue') == COMBINE_BTN:
                        idx = i
                        break
            if idx != -1:
                break
        if idx != -1:
            break

    if idx == -1:
        AddToSystemJournal("  Combine: Large BOD gump did not open.")
        return False

    NumGumpButton(idx, COMBINE_BTN)
    WaitForTarget(5000)
    return TargetPresent()


def combine_and_store(large_serial, small_serials, config, source_book=0):
    """Combines smalls into a Large BOD and routes to Consegna.
    Leftover (rejected/duplicate) smalls are returned to source_book.

    Game mechanic:
      - Open Large → press Combine → target cursor appears
      - Target a valid small → consumed → target RETURNS for the next one
      - Target a duplicate/already-combined small → target DROPS (server rejects)
      - All components filled → target drops naturally
    """
    if not large_serial:
        return False

    # Pre-check: how full is the Large already?
    before_combined, total_components = _count_combined_smalls(large_serial)
    if before_combined > 0:
        if before_combined >= total_components:
            AddToSystemJournal(
                f"Large BOD {hex(large_serial)} already full "
                f"({before_combined}/{total_components}). Routing to Consegna."
            )
            close_all_gumps()
            consegna_serial = config.get("books", {}).get("Consegna", 0)
            if consegna_serial:
                MoveItem(large_serial, 1, consegna_serial, 0, 0, 0)
                Wait(1000)
                return True
            return False
        AddToSystemJournal(
            f"Large BOD has {before_combined}/{total_components} smalls already. "
            f"Combining {len(small_serials)} more..."
        )
    else:
        AddToSystemJournal(f"Filling Large BOD with {len(small_serials)} smalls...")

    # Open gump and press Combine once — target persists across valid combines
    if not _open_large_and_combine_target(large_serial):
        AddToSystemJournal("  Failed to open Large BOD gump.")
        return False

    combined_count = 0
    for i, small in enumerate(small_serials):
        if check_abort():
            if TargetPresent():
                CancelTarget()
            close_all_gumps()
            return False

        world_save_guard()

        # Already consumed (e.g. duplicate serial in list)?
        FindType(BOD_TYPE, Backpack())
        if small not in list(GetFoundList()):
            AddToSystemJournal(f"  Small {i+1}/{len(small_serials)}: already consumed.")
            continue

        # If target dropped (rejected small or Large became full), re-press Combine
        if not TargetPresent():
            if not _open_large_and_combine_target(large_serial):
                AddToSystemJournal(f"  Small {i+1}: could not re-open Combine target. Stopping.")
                break

        TargetToObject(small)
        Wait(500)

        # Did the small leave the backpack?
        FindType(BOD_TYPE, Backpack())
        if small not in list(GetFoundList()):
            combined_count += 1
            AddToSystemJournal(f"  Small {i+1}/{len(small_serials)}: combined OK.")
            # Target should still be present for the next small (unless Large is now full)
            continue

        # Small still in backpack — server rejected it. Check journal for reason.
        now = datetime.datetime.now()
        since = now - datetime.timedelta(seconds=3)

        if InJournalBetweenTimes("maximum amount", since, now) > 0:
            AddToSystemJournal(
                f"  Small {i+1} ({hex(small)}): already combined into this Large. Skipping."
            )
        elif InJournalBetweenTimes("different requested amounts", since, now) > 0:
            AddToSystemJournal(
                f"  Small {i+1} ({hex(small)}): amount mismatch. Skipping."
            )
        elif InJournalBetweenTimes("same leather type", since, now) > 0:
            AddToSystemJournal(
                f"  Small {i+1} ({hex(small)}): material mismatch. Skipping."
            )
        elif InJournalBetweenTimes("not a bulk order", since, now) > 0:
            AddToSystemJournal(
                f"  Small {i+1} ({hex(small)}): not a bulk order. Skipping."
            )
        else:
            AddToSystemJournal(
                f"  Small {i+1} ({hex(small)}): rejected (unknown reason). Skipping."
            )

    # Clean up
    if TargetPresent():
        CancelTarget()
        Wait(300)
    close_all_gumps()

    # Find leftover smalls still in backpack
    FindType(BOD_TYPE, Backpack())
    bp_bods = set(GetFoundList())
    leftover_smalls = [s for s in small_serials if s in bp_bods]

    # Final tooltip verification
    final_combined, final_total = _count_combined_smalls(large_serial)
    AddToSystemJournal(f"  Combine result: {final_combined}/{final_total} components filled.")

    # Route Large to Consegna if full
    is_full = final_total > 0 and final_combined >= final_total
    consegna_serial = config.get("books", {}).get("Consegna", 0)
    if is_full and consegna_serial:
        AddToSystemJournal("Dropping filled Large BOD into Consegna book...")
        MoveItem(large_serial, 1, consegna_serial, 0, 0, 0)
        Wait(1000)
    elif not is_full:
        AddToSystemJournal("  Large BOD NOT full — leaving in backpack.")

    # Route leftover smalls back to Conserva
    if leftover_smalls:
        conserva_serial = source_book
        if conserva_serial:
            AddToSystemJournal(
                f"  Returning {len(leftover_smalls)} leftover small(s) to Conserva {hex(conserva_serial)}..."
            )
            for s in leftover_smalls:
                if check_abort():
                    break
                world_save_guard()
                MoveItem(s, 1, conserva_serial, 0, 0, 0)
                Wait(800)
        else:
            AddToSystemJournal(f"  WARNING: {len(leftover_smalls)} leftover smalls in backpack (no source book).")

    return is_full

def run_assembler():
    """Reads JSON to find targets, extracts them via Reverse Sweep, and re-indexes the JSON."""
    config = load_config()
    conserva = config.get("books", {}).get("Conserva", 0)
    if not conserva: return 0

    inv_file = get_inventory_file(conserva)
    if not os.path.exists(inv_file):
        AddToSystemJournal("Assembler Error: Inventory JSON not found. Please run a manual Scan first.")
        return 0

    # 1. Load the Live Inventory State
    with open(inv_file, "r") as f:
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