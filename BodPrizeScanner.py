from stealth import *
import re
from bod_data import *

# --- Configuration ---
# Update these if your shard/setup differs
BOOK_SERIAL = 0x405EA983   
BOD_BOOK_TYPE = 0x2259     
BOOK_GUMP_ID = 0x54F555DF  
NEXT_PAGE_BTN = 3          

def close_all_gumps():
    """Closes all active gumps to start fresh."""
    count = GetGumpsCount()
    for i in range(count - 1, -1, -1):
        CloseSimpleGump(i)
        Wait(100)

def find_and_open_book():
    """Finds BOD book in backpack or ground and opens it."""
    target_serial = BOOK_SERIAL
    
    # 1. Search Backpack if not found by serial
    if not IsObjectExists(target_serial):
        FindType(BOD_BOOK_TYPE, Backpack())
        if FindCount() > 0:
            target_serial = FindItem()
        else:
            AddToSystemJournal("Error: No BOD Book found.")
            return None

    # 2. Open it
    UseObject(target_serial)
    
    # 3. Wait for Gump
    for _ in range(20): 
        Wait(100)
        for i in range(GetGumpsCount()):
            g = GetGumpInfo(i)
            if g and g.get("GumpID") == BOOK_GUMP_ID:
                return i
    return None

def get_bod_book_gump():
    """Returns index and gump info for the open BOD book."""
    for i in range(GetGumpsCount()):
        g = GetGumpInfo(i)
        if g and g.get("GumpID") == BOOK_GUMP_ID:
            return i, g
    return None, None

def get_all_elements(g):
    """Extracts text elements from the Gump."""
    elements = []
    
    # HTML Text
    if 'XmfHTMLGumpColor' in g:
        for entry in g['XmfHTMLGumpColor']:
            try:
                raw = GetClilocByID(entry['ClilocID'])
                text = re.sub(r'<[^>]+>', '', raw).strip()
                if text:
                    elements.append({'x': entry.get('X', 0), 'y': entry.get('Y', 0), 'text': text})
            except: pass

    # Plain Text
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

def parse_page_visually(g):
    """Parses the visual layout of the BOD book page."""
    elements = get_all_elements(g)
    rows = {}
    TOLERANCE_Y = 6 

    # Filter UI noise
    ignore = ['bulk order book', 'type', 'item', 'quality', 'material', 'amount', 'set filter', 'price', 'exit', 'previous page', 'next page', 'drop', 'set']
    filtered = [e for e in elements if e['y'] > 80 and e['text'].lower() not in ignore]

    # Group by Row (Y-coordinate)
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

    page_bods = []

    # Sort rows and columns
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
                if clean_txt in ["Small", "Large"]: b_type = clean_txt
            elif 90 <= x < 220:
                b_item = clean_txt
            elif 220 <= x < 300:
                if "exceptional" in low_txt: b_qual = "Exceptional"
            elif 300 <= x < 400:
                b_mat = normalize_material(clean_txt)
            elif 400 <= x < 500:
                if re.search(r'\d', clean_txt):
                    b_amt = clean_txt

        # Parse Amount (e.g., "0 / 20" or "20")
        qty = 0
        if "/" in b_amt:
            parts = b_amt.split('/')
            qty = int(parts[1].strip())
        elif b_amt.isdigit():
            qty = int(b_amt)

        # Identify Reward
        # 1. Categorize (Identify Set)
        cat = categorize_items(b_item)
        
        # 2. Get Prize ID
        pid = get_prize_number(cat, b_mat, qty, b_qual)
        
        # 3. Build Object
        bod_obj = {
            "type": b_type,
            "item": b_item.lower(),
            "quality": b_qual,
            "material": b_mat,
            "amount": qty,
            "prize_id": pid,
            "category": cat
        }
        
        # Logging (Debug)
        reward_str = ""
        # FIX: Check if pid is not None before comparison
        if pid and pid in prize_names:
            reward_str = f"-> REWARD: {prize_names[pid]}"
            
        AddToSystemJournal(f"{b_type} | {b_item} | {b_qual} | {b_mat} | {b_amt} {reward_str}")
        
        page_bods.append(bod_obj)

    return page_bods

def scanBook():
    """Main function to loop through pages and summarize results."""
    close_all_gumps()
    
    idx = find_and_open_book()
    if idx is None: return

    _, g = get_bod_book_gump()
    prev_serial = 0
    all_bods = []
    
    AddToSystemJournal("Scanning BOD Book... Please Wait.")
    page_num = 1
    
    while True:
        AddToSystemJournal(f"Scanning Page {page_num}...")
        results = parse_page_visually(g)
        all_bods.extend(results)
        
        prev_serial = g['Serial']
        
        # Next Page
        NumGumpButton(idx, NEXT_PAGE_BTN)
        Wait(1000)
        
        idx2, g2 = get_bod_book_gump()
        
        # Stop if closed or page didn't change (end of book)
        if idx2 is None or g2['Serial'] == prev_serial:
            break
            
        idx, g = idx2, g2
        page_num += 1

    # --- Generate Summary ---
    smalls_23 = 0
    smalls_24 = 0
    larges_23 = 0
    larges_24 = 0
    
    for b in all_bods:
        pid = b.get('prize_id')
        if pid == 23:
            if b['type'] == 'Small': smalls_23 += 1
            else: larges_23 += 1
        elif pid == 24:
            if b['type'] == 'Small': smalls_24 += 1
            else: larges_24 += 1
            
    # Calculate Fill Capacity using bod_data logic
    fill_stats = compute_large_fill_capacity(all_bods)
    fillable_23 = sum(1 for x in fill_stats if x['prize_id'] == 23 and x['can_fill'])
    fillable_24 = sum(1 for x in fill_stats if x['prize_id'] == 24 and x['can_fill'])

    AddToSystemJournal("========================================")
    AddToSystemJournal(f"SCAN COMPLETED: {len(all_bods)} BODs found")
    AddToSystemJournal("========================================")
    AddToSystemJournal("PRIZE SUMMARY (Target 23 & 24):")
    AddToSystemJournal(f"Prize 23 (CBD): Small={smalls_23} | Large={larges_23} (Fillable: {fillable_23})")
    AddToSystemJournal(f"Prize 24 (Kit): Small={smalls_24} | Large={larges_24} (Fillable: {fillable_24})")
    AddToSystemJournal("========================================")
    
    if fillable_24 > 0:
        AddToSystemJournal("--- READY TO FILL (Barbed Kit) ---")
        for f in fill_stats:
            if f['prize_id'] == 24 and f['can_fill']:
                AddToSystemJournal(f"YES: {f['large_name']} ({f['material']} {f['quality']})")

    if fillable_23 > 0:
        AddToSystemJournal("--- READY TO FILL (CBD) ---")
        for f in fill_stats:
            if f['prize_id'] == 23 and f['can_fill']:
                AddToSystemJournal(f"YES: {f['large_name']} ({f['material']} {f['quality']})")

if __name__ == '__main__':
    scanBook()