from stealth import *
import json
import os
import time
from bod_data import *

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): pass

CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
STATS_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_stats.json"
BOOK_GUMP_ID = 0x54F555DF
NEXT_PAGE_BTN = 3
COMBINE_BTN = 2  
BOD_TYPE = 0x2258 

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {}

def check_abort():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
                return data.get("status") == "Stopped"
        except: pass
    return False

def close_all_gumps():
    for i in range(GetGumpsCount() - 1, -1, -1):
        CloseSimpleGump(i)
        Wait(100)

def map_book_inventory(book_serial):
    """Maps all BODs, tracking their global Position for direct extraction."""
    close_all_gumps()
    UseObject(book_serial)
    Wait(1500)
    
    inventory = []
    page_num = 1
    global_pos = 0  
    
    while True:
        if check_abort(): break
        world_save_guard()
        gumps = [GetGumpInfo(i) for i in range(GetGumpsCount())]
        g = next((x for x in gumps if x and x.get("GumpID") == BOOK_GUMP_ID), None)
        
        if not g: break
        
        from BodCycler_Scanner import parse_page_visually 
        bods_on_page = parse_page_visually(g)
        
        for bod in bods_on_page:
            bod['page'] = page_num
            bod['pos'] = global_pos
            bod['drop_btn'] = 5 + (global_pos * 2)
            inventory.append(bod)
            global_pos += 1
            
        prev_serial = g['Serial']
        idx = next(i for i, x in enumerate(gumps) if x.get("GumpID") == BOOK_GUMP_ID)
        
        NumGumpButton(idx, NEXT_PAGE_BTN)
        Wait(150) 
        
        t = time.time()
        page_changed = False
        while time.time() - t < 3:
            Wait(100)
            new_gumps = [GetGumpInfo(i) for i in range(GetGumpsCount())]
            g2 = next((x for x in new_gumps if x and x.get("GumpID") == BOOK_GUMP_ID), None)
            if g2 and g2['Serial'] != prev_serial:
                page_changed = True
                break
                
        if not page_changed: break
        page_num += 1
        
    return inventory

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
                if (small['item'] == comp.lower() and 
                    small['material'] == mat and 
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
    target_bods.sort(key=lambda x: x['pos'], reverse=True)
    extracted_serials = []
    
    for bod in target_bods:
        if check_abort(): break
        world_save_guard()
        
        close_all_gumps()
        FindType(BOD_TYPE, Backpack()) 
        before_bods = list(GetFoundList())
        
        UseObject(book_serial)
        
        t = time.time()
        idx = -1
        while time.time() - t < 3:
            Wait(100)
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == BOOK_GUMP_ID:
                    idx = i
                    break
            if idx != -1: break
                
        if idx != -1:
            target_page = bod['page']
            current_page = 1
            
            while current_page < target_page:
                if check_abort(): return extracted_serials
                NumGumpButton(idx, NEXT_PAGE_BTN)
                Wait(250)
                
                t_flip = time.time()
                idx = -1
                while time.time() - t_flip < 2:
                    Wait(100)
                    for i in range(GetGumpsCount()):
                        if GetGumpID(i) == BOOK_GUMP_ID:
                            idx = i
                            break
                    if idx != -1: break
                current_page += 1
                
            if idx == -1:
                continue
                
            Wait(500) 
            NumGumpButton(idx, bod['drop_btn'])
            Wait(500)
            
            t = time.time()
            while time.time() - t < 3:
                Wait(200)
                FindType(BOD_TYPE, Backpack())
                after_bods = list(GetFoundList())
                new_bods = [b for b in after_bods if b not in before_bods]
                
                if new_bods:
                    extracted_serials.append(new_bods[0])
                    break
    return extracted_serials

def combine_and_store(target_bods, extracted_serials, config):
    large_serial = None
    small_serials = []
    
    for i, serial in enumerate(extracted_serials):
        if i < len(target_bods):
            if target_bods[i]['type'] == 'Large':
                large_serial = serial
            else:
                small_serials.append(serial)

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
                Wait(1500)
                
                idx = -1
                for i in range(GetGumpsCount()):
                    g = GetGumpInfo(i)
                    if g and 'GumpButtons' in g:
                        for btn in g['GumpButtons']:
                            if btn.get('ReturnValue') == COMBINE_BTN:
                                idx = i
                                break
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
    """Iteratively scans and builds one set at a time to preserve accurate indexes."""
    config = load_config()
    conserva = config.get("books", {}).get("Conserva", 0)
    
    if not conserva: return 0
        
    sets_completed = 0
    
    while True:
        if check_abort(): break
        
        close_all_gumps()
        AddToSystemJournal("Scanning Conserva for completable sets...")
        inventory = map_book_inventory(conserva)
        sets_to_build = find_completable_sets(inventory)
        
        if not sets_to_build:
            AddToSystemJournal("No complete sets remaining in Conserva.")
            break
            
        bod_set = sets_to_build[0] # Take strictly the FIRST available set
        target_bods = [bod_set['large']] + bod_set['smalls']
        
        AddToSystemJournal(f"Extracting 1 Set. Components: {len(target_bods)}")
        extracted_serials = extract_bods(conserva, target_bods)
        
        if len(extracted_serials) == len(target_bods):
            if combine_and_store(target_bods, extracted_serials, config):
                sets_completed += 1
            else:
                AddToSystemJournal("Combine failed. Aborting further set extraction.")
                break
        else:
            AddToSystemJournal("Extraction mismatch! Aborting to prevent data corruption.")
            break
            
        # Optimization: Prevent a final redundant scan if there are no more sets left
        if len(sets_to_build) == 1:
            AddToSystemJournal("All known sets assembled. Skipping final redundant scan.")
            break

    return sets_completed

if __name__ == '__main__':
    run_assembler()