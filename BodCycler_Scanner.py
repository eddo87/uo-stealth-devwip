from stealth import *
import re
import json
import os
import time
from bod_data import *

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False


from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE,
    BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID, NEXT_PAGE_BTN,
    load_config, check_abort, close_all_gumps,
    wait_for_gump, wait_for_gump_serial_change,
    read_stats, write_stats, set_status
)

def get_all_elements(g):
    elements = []
    if 'XmfHTMLGumpColor' in g:
        for entry in g['XmfHTMLGumpColor']:
            try:
                raw = GetClilocByID(entry['ClilocID'])
                text = re.sub(r'<[^>]+>', '', raw).strip()
                if text:
                    elements.append({'x': entry.get('X', 0), 'y': entry.get('Y', 0), 'text': text})
            except: pass
    if 'GumpText' in g and 'Text' in g:
        for entry in g['GumpText']:
            try:
                text_id = entry.get('TextID', -1)
                if text_id >= 0 and text_id < len(g['Text']):
                    text = str(g['Text'][text_id]).strip()
                    if text:
                        elements.append({'x': entry.get('X', 0), 'y': entry.get('Y', 0), 'text': text})
            except: pass
    return elements

def infer_material(item_name, current_mat):
    if current_mat != "Iron":
        return current_mat
    cat = categorize_items(item_name)
    if cat == "Town Crier Set": return "Cloth"
    if cat in ["Male Leather Set", "Female Leather Set", "Studded Set"]: return "Leather"
    return current_mat

def parse_page_visually(g):
    """Parses text from the Gump to extract accurate BOD properties."""
    elements = get_all_elements(g)
    rows = {}
    TOLERANCE_Y = 10 

    ignore = ['bulk order book', 'type', 'item', 'quality', 'material', 'amount', 'set filter', 'price', 'exit', 'previous page', 'next page', 'drop', 'set']
    filtered = [e for e in elements if e['y'] > 80 and e['text'].lower() not in ignore]

    for e in filtered:
        y = e['y']
        found_y = None
        for key in rows.keys():
            if abs(key - y) <= TOLERANCE_Y:
                found_y = key
                break
        if found_y is not None:
            rows[found_y].append(e)
        else:
            rows[y] = [e]

    raw_bods = []

    for y in sorted(rows.keys()):
        cols = sorted(rows[y], key=lambda k: k['x'])
        
        b_type = "Unknown"
        b_item = "Unknown" 
        b_qual = "Normal"
        b_mat = "Iron"
        b_amt = "0"
        
        for col in cols:
            x = col['x']
            txt = col['text']
            clean_txt = txt.replace("['", "").replace("']", "").replace("'", "")
            low_txt = clean_txt.lower()

            if x < 90:
                if "Small" in clean_txt: b_type = "Small"
                elif "Large" in clean_txt: b_type = "Large"
            elif 90 <= x < 220:
                b_item = clean_txt
            elif 220 <= x < 300:
                if "exceptional" in low_txt: b_qual = "Exceptional"
            elif 300 <= x < 400:
                b_mat = normalize_material(clean_txt)
            elif 400 <= x < 500:
                if re.search(r'\d', clean_txt):
                    if "/" in clean_txt:
                        b_amt = clean_txt
                    elif clean_txt in ["10", "15", "20"] and (b_amt == "0" or "/" not in b_amt):
                        b_amt = clean_txt

        qty = 0
        if "/" in b_amt:
            try: qty = int(b_amt.split('/')[1].strip())
            except: pass
        elif b_amt.isdigit():
            qty = int(b_amt)

        b_mat = infer_material(b_item, b_mat)

        raw_bods.append({
            "type": b_type,
            "item": b_item.lower(),
            "quality": b_qual,
            "material": b_mat,
            "amount": qty,
            "amt_str": b_amt
        })

    final_bods = []
    last_large_idx = -1

    for bod in raw_bods:
        if bod['type'] == 'Large':
            cat = categorize_items(bod['item'])
            
            bod_obj = {
                "type": "Large",
                "item": bod['item'],
                "quality": bod['quality'],
                "material": bod['material'],
                "amount": bod['amount'],
                "category": cat
            }
            final_bods.append(bod_obj)
            last_large_idx = len(final_bods) - 1

        elif bod['type'] == 'Unknown':
            if last_large_idx >= 0:
                parent = final_bods[last_large_idx]
                if parent['amount'] == 0 and bod['amount'] > 0:
                    parent['amount'] = bod['amount']
            continue

        elif bod['type'] == 'Small':
            last_large_idx = -1 
            cat = categorize_items(bod['item'])
            if cat in ["Male Leather Set", "Female Leather Set", "Studded Set", "Town Crier Set"]:
                cat = "Small Bods"
            
            bod_obj = {
                "type": "Small",
                "item": bod['item'],
                "quality": bod['quality'],
                "material": bod['material'],
                "amount": bod['amount'],
                "category": cat
            }
            final_bods.append(bod_obj)

    return final_bods

def map_and_save_book_inventory(book_serial):
    """Fast-polls the book, assigns global positions, and saves to JSON."""
    close_all_gumps()
    UseObject(book_serial)
    
    t_start = time.time()
    current_serial = 0
    idx = -1
    while time.time() - t_start < 3:
        Wait(10)
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == BOOK_GUMP_ID:
                idx = i
                current_serial = GetGumpInfo(i)['Serial']
                break
        if idx != -1: break
        
    if idx == -1: 
        AddToSystemJournal("Scanner Error: Failed to open Conserva book.")
        return []
    
    inventory = []
    page_num = 1
    global_pos = 0  
    
    while True:
        if check_abort(): break
        world_save_guard()
        
        gumps = [GetGumpInfo(i) for i in range(GetGumpsCount())]
        g = next((x for x in gumps if x and x.get("GumpID") == BOOK_GUMP_ID), None)
        if not g: break
        
        bods_on_page = parse_page_visually(g)
        
        for bod in bods_on_page:
            bod['page'] = page_num
            bod['pos'] = global_pos
            bod['drop_btn'] = 5 + (global_pos * 2)
            inventory.append(bod)
            global_pos += 1
            
        
        NumGumpButton(idx, NEXT_PAGE_BTN)
        idx, current_serial, page_changed = wait_for_gump_serial_change(current_serial, BOOK_GUMP_ID, 8000)
        if not page_changed:
            break

        page_num += 1
        
    # Write the entire freshly mapped array to JSON
    if not check_abort():
        try:
            with open(INVENTORY_FILE, "w") as f:
                json.dump(inventory, f, indent=4)
            AddToSystemJournal(f"State Management: Successfully saved {len(inventory)} BODs to JSON.")
        except Exception as e:
            AddToSystemJournal(f"State Management Error: Could not save JSON. {e}")
        
    return inventory

def generate_progress_report(all_bods):
    small_inv = {} 
    large_inv = {}
    
    for b in all_bods:
        if b['type'] == 'Small':
            key = (b['item'], b['material'], b['quality'], b['amount'])
            small_inv[key] = small_inv.get(key, 0) + 1
        elif b['type'] == 'Large':
            key = (b['category'], b['material'], b['quality'], b['amount'])
            large_inv[key] = large_inv.get(key, 0) + 1

    targets = [
        ("Male Leather Set", "Spined", 20, "Exceptional", "Barbed Kit"),
        ("Male Leather Set", "Horned", 20, "Exceptional", "Barbed Kit"),
        ("Male Leather Set", "Barbed", 20, "Exceptional", "Barbed Kit"),
        ("Female Leather Set", "Spined", 20, "Exceptional", "Barbed Kit"),
        ("Female Leather Set", "Horned", 20, "Exceptional", "Barbed Kit"),
        ("Female Leather Set", "Barbed", 20, "Exceptional", "Barbed Kit"),
        ("Male Leather Set", "Leather", 20, "Normal", "CBD"),        
        ("Female Leather Set", "Leather", 20, "Normal", "CBD"),      
        ("Studded Set", "Leather", 20, "Exceptional", "CBD"),
        ("Studded Set", "Spined", 10, "Exceptional", "CBD"),
        ("Town Crier Set", "Cloth", 20, "Exceptional", "CBD")
    ]
    
    AddToSystemJournal("=== SET PROGRESS REPORT ===")
    
    for set_name, mat, amt, qual, reward_label in targets:
        components = LARGE_COMPONENTS.get(set_name, [])
        if not components: continue
        
        large_count = large_inv.get((set_name, mat, qual, amt), 0)
        
        comp_counts = {}
        has_any_small = False
        min_comp = 999999
        
        for c in components:
            count = 0
            
            # Bulletproof check: accept BOTH Cloth and Leather for Town Crier parts
            if set_name == "Town Crier Set":
                count = small_inv.get((c.lower(), "Cloth", qual, amt), 0) + \
                        small_inv.get((c.lower(), "Leather", qual, amt), 0)
            else:
                s_key = (c.lower(), mat, qual, amt)
                count = small_inv.get(s_key, 0)

            comp_counts[c] = count
            if count > 0: has_any_small = True
            if count < min_comp: min_comp = count
            
        if large_count == 0 and not has_any_small:
            continue
            
        can_fill = min(large_count, min_comp)
        
        AddToSystemJournal(f"SET: {set_name} [{mat} {qual} {amt}] -> {reward_label}")
        AddToSystemJournal(f"   Larges Owned: {large_count}")
        AddToSystemJournal(f"   Can Complete: {can_fill}")
        
        parts_list = []
        for c, count in comp_counts.items():
            if count == 0:
                parts_list.append(f"[{c}: 0]")
            else:
                parts_list.append(f"{c}: {count}")
        
        chunk_str = ""
        for p in parts_list:
            if len(chunk_str) + len(p) > 60:
                AddToSystemJournal(f"   Parts: {chunk_str}")
                chunk_str = ""
            chunk_str += p + ", "
        if chunk_str:
            AddToSystemJournal(f"   Parts: {chunk_str.strip(', ')}")
            
        AddToSystemJournal("----------------------------------------")
        
    AddToSystemJournal("===========================")

def run_scanner():
    """Main entry point, triggered by GUI."""
    # Set status to Scanning to clear any stale "Stopped" states and update the GUI
    set_status("Scanning")
    
    config = load_config()
    if not config:
        AddToSystemJournal("Scanner Error: Config not found. Please save first.")
        set_status("Idle")
        return

    conserva_serial = config.get("books", {}).get("Conserva", 0)
    if conserva_serial == 0:
        AddToSystemJournal("Scanner Error: Conserva book not configured.")
        set_status("Idle")
        return

    AddToSystemJournal("Scanning Conserva Book & Rebuilding JSON Database... Please Wait.")
    
    all_bods = map_and_save_book_inventory(conserva_serial)
    
    if check_abort():
        AddToSystemJournal("Scanner aborted by user.")
        return
        
    total_smalls = sum(1 for b in all_bods if b['type'] == 'Small')
    total_larges = sum(1 for b in all_bods if b['type'] == 'Large')

    AddToSystemJournal("========================================")
    AddToSystemJournal(f"SCAN COMPLETED: {len(all_bods)} Valid BODs")
    AddToSystemJournal(f"Inventory: {total_smalls} Smalls | {total_larges} Larges")
    
    generate_progress_report(all_bods)
    
    # Reset status back to Idle after a successful manual scan
    if not check_abort():
        set_status("Idle")

if __name__ == '__main__':
    run_scanner()