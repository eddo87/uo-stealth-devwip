from stealth import *
import time

# --- Constants to Test ---
CRAFT_GUMP_ID = 0x38920abd
TINKER_TOOL_TYPE = 0x1EB8

# Buttons we are assuming work (to navigate)
BTN_CATEGORY_TOOLS = 8

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

    # 1. Find Text Coordinates (HTML/Cliloc)
    if 'XmfHTMLGumpColor' in gump_data:
        for entry in gump_data['XmfHTMLGumpColor']:
            cliloc = entry.get('ClilocID', 0)
            content = GetClilocByID(cliloc).upper()
            # Clean content just in case
            clean_content = content.replace("<CENTER>", "").replace("</CENTER>", "")
            
            if text_to_find.upper() in clean_content:
                target_y = entry.get('Y')
                target_x = entry.get('X')
                print_debug(f" >> Found Text at X:{target_x}, Y:{target_y} (Cliloc: {cliloc})")
                break
    
    # 2. Find Text Coordinates (Plain Text) - Fallback
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

    # 3. Find Nearest Button
    # Logic: Button should be to the LEFT of the text (X < target_x) 
    # and roughly on the same line (abs(Y - target_y) < small tolerance)
    best_btn_id = None
    min_dist = 1000
    
    if 'GumpButtons' in gump_data:
        for btn in gump_data['GumpButtons']:
            by = btn.get('Y')
            bx = btn.get('X')
            bid = btn.get('ReturnValue') 
            
            # Tolerance: 20 pixels vertical, Button must be left of text
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

def run_diagnostics():
    print_debug("Starting Smart Crafting Diagnostics...")

    # 1. Find Tool
    FindType(TINKER_TOOL_TYPE, Backpack())
    if FindCount() == 0:
        print_debug("CRITICAL: No Tinker Tools found in backpack.")
        return
    
    tool = FindItem()
    print_debug(f"Found Tinker Tool: {hex(tool)}")
    
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
        print_debug(f"CRITICAL: Craft Gump {hex(CRAFT_GUMP_ID)} NOT found.")
        return
    
    print_debug("Craft Gump Opened.")
    
    # 4. Navigate to TOOLS (Button 8)
    # We assume we might not be on the right page, so press it.
    print_debug(f"Pressing 'Tools' category (Button {BTN_CATEGORY_TOOLS})...")
    NumGumpButton(found_idx, BTN_CATEGORY_TOOLS)
    Wait(1500)
    
    # 5. Re-acquire Gump
    found_idx = -1
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == CRAFT_GUMP_ID:
            found_idx = i
            break
            
    if found_idx == -1:
        print_debug("CRITICAL: Gump closed/lost after navigation.")
        return
        
    gump_data = GetGumpInfo(found_idx)
    
    # 6. Analyze Buttons
    print_debug("--- ANALYZING TARGETS ---")
    
    # Check for Tongs
    tongs_btn = find_button_for_text(gump_data, "tongs")
    
    # Check for Sewing Kit
    sewing_btn = find_button_for_text(gump_data, "sewing kit")
    
    # Check for Tinker Tools (Self-crafting)
    tinker_btn = find_button_for_text(gump_data, "tinker's tools") # Note: Cliloc says "tinker's tools"
    
    print_debug("--- SUMMARY ---")
    print_debug(f"Tongs Button: {tongs_btn} (Expected: 90?)")
    print_debug(f"Sewing Kit Button: {sewing_btn} (Expected: 67?)")
    print_debug(f"Tinker Tools Button: {tinker_btn} (Expected: 23?)")
    print_debug("Diagnostics Complete.")

if __name__ == '__main__':
    run_diagnostics()