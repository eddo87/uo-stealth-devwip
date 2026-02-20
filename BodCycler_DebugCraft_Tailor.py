from stealth import *
import time

# --- Constants ---
CRAFT_GUMP_ID = 0x38920abd
SEWING_KIT_TYPE = 0x0F9D

def print_debug(msg):
    AddToSystemJournal(f"[DEBUG] {msg}")
    print(f"[DEBUG] {msg}")

def find_button_for_text(gump_data, text_to_find):
    """
    Scans the gump for specific text/html, gets its X/Y coordinates,
    then looks for the button physically located next to it.
    """
    target_y = -1
    target_x = -1
    
    print_debug(f"Scanning for '{text_to_find}'...")

    # 1. Check Clilocs (HTML)
    if 'XmfHTMLGumpColor' in gump_data:
        for entry in gump_data['XmfHTMLGumpColor']:
            cliloc = entry.get('ClilocID', 0)
            content = GetClilocByID(cliloc).upper()
            clean_content = content.replace("<CENTER>", "").replace("</CENTER>", "")
            
            if text_to_find.upper() in clean_content:
                target_y = entry.get('Y')
                target_x = entry.get('X')
                print_debug(f" >> Found Text at X:{target_x}, Y:{target_y} (Cliloc: {cliloc})")
                break
    
    # 2. Check Plain Text (Fallback)
    if target_y == -1 and 'GumpText' in gump_data and 'Text' in gump_data:
         for entry in gump_data['GumpText']:
             tid = entry.get('TextID')
             if tid < len(gump_data['Text']):
                 content = str(gump_data['Text'][tid]).upper()
                 if text_to_find.upper() in content:
                     target_y = entry.get('Y')
                     target_x = entry.get('X')
                     print_debug(f" >> Found Text at X:{target_x}, Y:{target_y} (TextID: {tid})")
                     break

    if target_y == -1:
        print_debug(f" >> Text '{text_to_find}' NOT found on this page.")
        return None

    # 3. Find Nearest Button to the left
    best_btn_id = None
    min_dist = 1000
    
    if 'GumpButtons' in gump_data:
        for btn in gump_data['GumpButtons']:
            by = btn.get('Y')
            bx = btn.get('X')
            bid = btn.get('ReturnValue') 
            
            # Button must be to the left (bx < target_x) and roughly on same Y axis (20px tolerance)
            if bx < target_x and abs(by - target_y) < 20:
                dist = target_x - bx
                if dist < min_dist:
                    min_dist = dist
                    best_btn_id = bid
                    
    if best_btn_id is not None:
        print_debug(f" >> FOUND BUTTON ID: {best_btn_id} for '{text_to_find}'")
        return best_btn_id
    else:
        print_debug(f" >> Found text, but NO BUTTON found near X:{target_x}, Y:{target_y}")
        return None

def run_tailor_diagnostics():
    print_debug("Starting Tailoring Diagnostics...")

    # 1. Find Sewing Kit
    FindType(SEWING_KIT_TYPE, Backpack())
    if FindCount() == 0:
        print_debug("CRITICAL: No Sewing Kit found in backpack.")
        return
    
    tool = FindItem()
    print_debug(f"Found Sewing Kit: {hex(tool)}")
    
    # 2. Open Gump
    print_debug("Using tool...")
    UseObject(tool)
    Wait(1500)
    
    # 3. Find Craft Gump
    found_idx = -1
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == CRAFT_GUMP_ID:
            found_idx = i
            break
            
    if found_idx == -1:
        print_debug(f"CRITICAL: Craft Gump NOT found.")
        return
    
    print_debug("Craft Gump Opened.")
    gump_data = GetGumpInfo(found_idx)
    
    # --- TEST 1: CATEGORIES CHECK ---
    print_debug("\n--- TEST 1: VERIFYING ALL CATEGORIES ---")
    categories = ["Hats", "Shirts", "Pants", "Miscellaneous", "Footwear", "Leather Armor", "Studded Armor", "Female Armor"]
    for cat in categories:
        find_button_for_text(gump_data, cat)
    
    # --- TEST 2: HATS & STRAW HAT ---
    print_debug("\n--- TEST 2: HATS ---")
    hat_cat_btn = find_button_for_text(gump_data, "Hats")
    
    if hat_cat_btn:
        print_debug(f"Pressing 'Hats' category (Button {hat_cat_btn})...")
        NumGumpButton(found_idx, hat_cat_btn)
        Wait(1500)
        
        # Re-acquire Gump
        found_idx = -1
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == CRAFT_GUMP_ID:
                found_idx = i
                break
        if found_idx != -1:
            gump_data = GetGumpInfo(found_idx)
            find_button_for_text(gump_data, "straw hat")
        else:
            print_debug("Gump lost after pressing Hats.")

    # --- TEST 3: LEATHER ARMOR & GORGET ---
    print_debug("\n--- TEST 3: LEATHER ARMOR ---")
    if found_idx != -1:
        leather_cat_btn = find_button_for_text(gump_data, "Leather Armor")
        
        if leather_cat_btn:
            print_debug(f"Pressing 'Leather Armor' category (Button {leather_cat_btn})...")
            NumGumpButton(found_idx, leather_cat_btn)
            Wait(1500)
            
            # Re-acquire Gump
            found_idx = -1
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == CRAFT_GUMP_ID:
                    found_idx = i
                    break
            if found_idx != -1:
                gump_data = GetGumpInfo(found_idx)
                find_button_for_text(gump_data, "leather gorget")
            else:
                print_debug("Gump lost after pressing Leather Armor.")

    # --- TEST 4: SHIRTS & DOUBLET ---
    print_debug("\n--- TEST 4: SHIRTS ---")
    if found_idx != -1:
        shirts_cat_btn = find_button_for_text(gump_data, "Shirts")
        
        if shirts_cat_btn:
            print_debug(f"Pressing 'Shirts' category (Button {shirts_cat_btn})...")
            NumGumpButton(found_idx, shirts_cat_btn)
            Wait(1500)
            
            # Re-acquire Gump
            found_idx = -1
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == CRAFT_GUMP_ID:
                    found_idx = i
                    break
            if found_idx != -1:
                gump_data = GetGumpInfo(found_idx)
                find_button_for_text(gump_data, "doublet")
            else:
                print_debug("Gump lost after pressing Shirts.")

    print_debug("\nTailor Diagnostics Complete.")

if __name__ == '__main__':
    run_tailor_diagnostics()