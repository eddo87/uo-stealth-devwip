from stealth import *
import json
import os
import sys
import time
import re

# Force Python to look in the current script's directory for custom modules
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import external modules
from bod_data import categorize_items, get_prize_number
from bod_crafting_data import TAILOR_ITEMS, SMITH_ITEMS, MATERIAL_MAP
import BodCycler_Assembler

from BodCycler_Utils import (
    CONFIG_FILE, STATS_FILE, BOD_TYPE, BOD_BOOK_TYPE, BOOK_GUMP_ID,
    load_config, check_abort, close_all_gumps, wait_for_gump, is_prize_enabled,
    read_stats, write_stats, CRAFT_GUMP_ID, SCISSORS, log_event,
    world_save_guard
)

# --- Config ---
# Fallback count if Config file is unreadable
BODS_TO_PROCESS = 5


def update_stats(crafted=0, prized_small=0, prized_large=0):
    stats = read_stats()
    stats["crafted"] = stats.get("crafted", 0) + crafted
    stats["prized_small"] = stats.get("prized_small", 0) + prized_small
    stats["prized_large"] = stats.get("prized_large", 0) + prized_large
    write_stats(stats)


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
            #AddToSystemJournal("Consolidating leftover materials into crate...")
            found_any = True
            
        for item in items:
            world_save_guard()
            MoveItem(item, 0, crate_serial, 0, 0, 0)
            Wait(800)


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


def _parse_book_count(tooltip: str) -> int:
    """Extract the BOD count from a BOD book tooltip. Returns -1 if not found.
    Confirmed format: 'Bulk Order Book|Blessed|Weight: 1 stone|Deeds in book: 392|Book Name: TAILOR'
    """
    m = re.search(r'deeds in book[:\s]+(\d+)', tooltip, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return -1


def _swap_full_book(bbcrate, book_serial, cycle_type, config=None, config_key=None):
    """Swaps a full book (e.g. Scartare at 480+) with an empty one from BodBookCrate.
    Looks for a book named 'tailor'/'black' with 0 BODs.
    Persists the new serial to config if config and config_key are provided.
    Returns new book serial, or the original if no swap happened.
    """
    if not bbcrate or not book_serial:
        return book_serial

    tooltip = GetTooltip(book_serial).lower()
    count = _parse_book_count(tooltip)
    if count < 480:
        return book_serial

    AddToSystemJournal(f"Book {hex(book_serial)} is near full ({count}/500). Swapping from crate...")
    UseObject(bbcrate)
    Wait(400)

    # Put full book in crate
    MoveItem(book_serial, 1, bbcrate, 0, 0, 0)
    Wait(600)

    # Find an empty book (0 BODs) of the right type
    book_keyword = "tailor" if cycle_type == "Tailor" else "black"
    FindTypeEx(BOD_BOOK_TYPE, 0xFFFF, bbcrate, False)
    all_books = list(GetFoundList())

    for book in all_books:
        if book == book_serial:
            continue
        tip = GetTooltip(book).lower()
        if book_keyword not in tip:
            continue
        bcount = _parse_book_count(tip)
        if bcount == 0:
            AddToSystemJournal(f"  Found empty book {hex(book)}. Swapping.")
            MoveItem(book, 1, Backpack(), 0, 0, 0)
            Wait(600)
            # Persist to config
            if config and config_key:
                config["books"][config_key] = book
                try:
                    import json as _json
                    with open(CONFIG_FILE, "r") as f:
                        disk_config = _json.load(f)
                    disk_config["books"][config_key] = book
                    with open(CONFIG_FILE, "w") as f:
                        _json.dump(disk_config, f, indent=4)
                    AddToSystemJournal(f"  Config updated: books.{config_key} = {hex(book)}")
                except Exception as e:
                    AddToSystemJournal(f"  WARNING: Could not persist config — {e}")
            return book
        Wait(50)

    # No empty book found — take the full book back
    AddToSystemJournal("  No empty book found in crate. Taking full book back.")
    MoveItem(book_serial, 1, Backpack(), 0, 0, 0)
    Wait(600)
    return book_serial


def _refill_origine_from_book_crate(bbcrate, origine, cycle_type):
    """
    Scans BodBookCrate for a BodBook matching the current cycle type with > 50 BODs.
    Extracts 1 BodBook
    """
    bod_book_crate = bbcrate
    if not bod_book_crate:
        return 0
    book_keyword = "tailor" if cycle_type == "Tailor" else "black"

    # Open crate first so Stealth caches all contents and tooltips
    UseObject(bod_book_crate)
    Wait(1000)

    FindTypeEx(BOD_BOOK_TYPE, 0xFFFF, bod_book_crate, False)
    all_books = list(GetFoundList())
    source_book = 0
    for book in all_books:
        if book == origine:
            continue
        tooltip = GetTooltip(book).lower()
        if not tooltip:
            ClickOnObject(book)
            Wait(400)
            tooltip = GetTooltip(book).lower()
        if book_keyword not in tooltip:
            continue
        count = _parse_book_count(tooltip)
        if count > 50:
            source_book = book
            break
        Wait(50)

    if not source_book:
        AddToSystemJournal(f"BODBookCrate: No {cycle_type} book with >50 BODs found.")
        log_event("ORIGINE_EMPTY", f"No reserve {cycle_type} book with >50 BODs found in BODBookCrate — Origine cannot be refilled.")
        return 0

    # Found replacement — now swap: deposit old, pull new
    AddToSystemJournal(f"BODBookCrate: Found {cycle_type} book {hex(source_book)} — swapping.")
    MoveItem(origine, 1, bbcrate, 0, 0, 0)
    Wait(600)
    MoveItem(source_book, 1, Backpack(), 0, 0, 0)
    Wait(600)
    return source_book



def extract_bod_from_origine(origine_serial, bbcrate=0, cycle_type="Tailor"):
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
        # AddToSystemJournal("Debug: Failed to open Origine book gump.")
        # Auto-replenish Origine from BODBookCrate if low
        new_serial = _refill_origine_from_book_crate(bbcrate, origine_serial, cycle_type)
        return (0, new_serial)
    
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


def parse_bod(bod_serial, cycle_type="Tailor"):
    tooltip = GetTooltip(bod_serial)
    if not tooltip or len(tooltip) < 10:
        # Tooltip not yet cached — force a client fetch then retry once
        ClickOnObject(bod_serial)
        Wait(400)
        tooltip = GetTooltip(bod_serial)
    tooltip = tooltip.lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]

    is_large = "large bulk order" in tooltip
    is_except = "exceptional" in tooltip

    qty_total = 0
    qty_finished = 0
    item_name = "unknown"

    items_dict = SMITH_ITEMS if cycle_type == "Smith" else TAILOR_ITEMS

    # 1. Find the Item Name using dict
    sorted_keys = sorted(items_dict.keys(), key=len, reverse=True)
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
        if item_name in items_dict and len(items_dict[item_name]) >= 5:
            mat = items_dict[item_name][4]

        # Step 3c: Fallback to smart parsing if the dictionary isn't updated yet
        else:
            if cycle_type == "Smith":
                mat = "iron"
            elif item_name in items_dict:
                item_cat = items_dict[item_name][0]
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
        "material": mat_proper,
        "cat": cat,
        "prize_id": prize_id
    }


def is_item_exceptional(item_serial):
    """Checks if item is exceptional. Waits for the server tooltip to arrive before checking."""
    tt = GetTooltip(item_serial)
    if not tt:
        Wait(250)
        tt = GetTooltip(item_serial)
    if not tt:
        AddToSystemJournal(f"[DEBUG] is_item_exceptional: tooltip still empty for {hex(item_serial)}")
        return False
    return "exceptional" in tt.lower()
    



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


def get_craft_info(item_name, cycle_type="Tailor"):
    """Retrieves Crafting parameters, supporting both String names and exact Button IDs."""
    item_lower = item_name.lower()
    items_dict = SMITH_ITEMS if cycle_type == "Smith" else TAILOR_ITEMS
    tool_type  = 0x0FBC if cycle_type == "Smith" else 0x0F9D  # Tongs vs Sewing Kit
    if item_lower in items_dict:
        data = items_dict[item_lower]
        if data[0] == 0 or data[1] == 0:
            return None, None, None, None, None  # placeholder — item_btn not yet mapped
        return (
            data[0],    # Category (Text OR Button ID)
            data[1],    # Item (Text OR Button ID)
            data[2],    # Graphic ID
            tool_type,  # Tool Type
            data[3]     # Resource Cost
        )
    return None, None, None, None, None


def check_and_pull_materials(material, qty_to_craft, item_cost, crate_serial, cycle_type="Tailor"):
    material = material.lower()
    if material not in MATERIAL_MAP:
        return False

    mat_info  = MATERIAL_MAP[material]
    mat_types = list(mat_info["types"])
    mat_color = mat_info["color"]
    if mat_color == -1:
        mat_color = 0xFFFF

    required_units = int((qty_to_craft * item_cost) * 1.2)
    pull_buffer    = required_units + (140 if cycle_type == "Smith" else 40)

    def _bp_count(t):
        FindTypeEx(t, mat_color, Backpack(), False)
        return FindFullQuantity()

    def _combined_bp():
        return sum(_bp_count(t) for t in mat_types)

    # Fast path: backpack already has enough (single or combined)
    if _combined_bp() >= required_units:
        return True

    if crate_serial == 0:
        AddToSystemJournal(f"Material check: No crate configured — cannot pull {material}.")
        return False

    #AddToSystemJournal(f"Pulling {material} from crate...")
    UseObject(crate_serial)
    Wait(1000)

    # For multi-type materials (e.g. cloth 0x1766/0x1767): sort so the type
    # with the most combined availability goes first, then check the combined
    # backpack total after every pull.  This keeps a single type in the backpack
    # when possible and avoids pulling from both when one alone is sufficient.
    if len(mat_types) > 1:
        def _available(t):
            FindTypeEx(t, mat_color, crate_serial, False)
            return _bp_count(t) + FindFullQuantity()
        mat_types.sort(key=_available, reverse=True)

    for t in mat_types:
        if check_abort():
            return False

        FindTypeEx(t, mat_color, crate_serial, False)
        for stack in list(GetFoundList()):
            if check_abort():
                return False
            world_save_guard()
            if _combined_bp() >= required_units:
                return True
            MoveItem(stack, pull_buffer, Backpack(), 0, 0, 0)
            Wait(1200)

        # After exhausting this type's stacks, check combined before moving on
        if _combined_bp() >= required_units:
            return True

    if _combined_bp() >= required_units:
        return True

    AddToSystemJournal(f"CRITICAL: Out of {material} in Crate!")
    return False


def _get_bod_progress(bod_serial, item_name):
    tooltip = GetTooltip(bod_serial).lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]
    for line in lines:
        if item_name.lower() in line and ":" in line:
            match = re.search(r':\s*(\d+)', line)
            if match:
                return int(match.group(1))
    return 0


def test_item_acceptance(bod_serial, item_serial, item_name):
    """Combines one item into the BOD to verify it's accepted; returns True if count increases."""
    initial_count = _get_bod_progress(bod_serial, item_name)
    AddToSystemJournal(f"Verifying acceptance... BOD current count: {initial_count}")

    count = GetGumpsCount()
    for i in reversed(range(count)):
        CloseSimpleGump(i)
    Wait(500)

    UseObject(bod_serial)
    Wait(1500)

    combine_btn_idx = -1
    for i in range(GetGumpsCount()):
        g = GetGumpInfo(i)
        if 'GumpButtons' in g:
            for btn in g['GumpButtons']:
                if btn.get('ReturnValue') == 2:
                    combine_btn_idx = i
                    break
        if combine_btn_idx != -1:
            break

    if combine_btn_idx != -1:
        NumGumpButton(combine_btn_idx, 2)
        if WaitForTarget(5000):
            TargetToObject(item_serial)
            Wait(1000)
    else:
        AddToSystemJournal("Verification Error: Could not find Combine button.")
        return False

    for _ in range(3):
        new_count = _get_bod_progress(bod_serial, item_name)
        if new_count > initial_count:
            AddToSystemJournal(f"SUCCESS: BOD accepted the item ({new_count}/{initial_count}). Proceeding.")
            return True
        Wait(500)

    AddToSystemJournal("FAILURE: BOD rejected the item ID.")
    return False


def _recycle_single(item_serial, tool_type):
    """Smelts or scissors a single non-exceptional item immediately."""
    world_save_guard()
    if tool_type == 0x0F9D:  # Scissors (Tailor)
        FindType(SCISSORS, Backpack())
        if FindCount() > 0:
            UseObject(FindItem())
            WaitForTarget(1500)
            TargetToObject(item_serial)
            Wait(800)
    elif tool_type == 0x0FBC:  # Tongs (Smith)
        FindType(tool_type, Backpack())
        if FindCount() > 0:
            tongs = FindItem()
            close_all_gumps()
            Wait(200)
            UseObject(tongs)
            idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
            if idx == -1:
                return
            NumGumpButton(idx, 14)  # Smelt Item
            WaitForTarget(2000)
            if TargetPresent():
                TargetToObject(item_serial)
                Wait(800)
            close_all_gumps()


def recycle_invalid_items(item_id, is_except, tool_type):
    """Safety-net sweep — recycles any non-exceptional items still in backpack."""
    # Tailor Normal BODs: don't scissors valid normal items.
    # Smith: always smelt non-exceptionals to recoup ingots, regardless of BOD quality.
    if not is_except and tool_type != 0x0FBC:
        return

    FindTypeEx(item_id, 0x0000, Backpack(), False)
    items = GetFoundList()

    for it in items:
        if check_abort():
            break
        if not is_item_exceptional(it):
            _recycle_single(it, tool_type)


def craft_items_until_done(bod_serial, tool_type, cat_identifier, item_identifier, item_name, item_id, qty_needed, is_except, mat_btn):
    """Crafts items utilizing either exact Button IDs or intelligent text fallback."""
    current_target_id = item_id 
    made_valid = count_valid_backpack_items(current_target_id, is_except)
    attempts = 0
    make_last_ready = False
    AddToSystemJournal(f"Crafing {item_name}")
    
    while made_valid < qty_needed and attempts < (qty_needed * 3):
        if check_abort(): 
            AddToSystemJournal("Abort detected. Stopping tool crafting.")
            return False
            
        world_save_guard()
        attempts += 1
        
        FindTypeEx(tool_type, 0x0000, Backpack())
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
                if test_item_acceptance(bod_serial, new_serial, item_name):
                    current_target_id = actual_graphic
                    make_last_ready = True
                else:
                    AddToSystemJournal("Item REJECTED by BOD. Tripping Circuit Breaker.")
                    log_event("MISMATCH", f"BOD rejected item '{item_name}': expected graphic {hex(current_target_id)}, got {hex(actual_graphic)} (category: {cat_identifier})")
                    return False
            else:
                make_last_ready = True

            # Smelt/scissors immediately — don't let non-exceptionals accumulate weight.
            if (is_except or tool_type == 0x0FBC) and not is_item_exceptional(new_serial):
                AddToSystemJournal("[Recycle] Not exceptional — recycling immediately.")
                _recycle_single(new_serial, tool_type)

        recycle_invalid_items(current_target_id, is_except, tool_type)
        made_valid = count_valid_backpack_items(current_target_id, is_except)
        #AddToSystemJournal(f"Crafting check: {made_valid}/{qty_needed} in bag.")
        
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
    ClickOnObject(bod_serial)
    Wait(500)
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
    trash = config.get('containers', {}).get('TrashBarrel', 0)
    bbcrate = config.get('containers', {}).get('BodBookCrate', 0)
    cycle_type = config.get("cycle_type", "Tailor")
    trash_dc = config.get("trade", {}).get("trash_dc_bods", False)

    try:
        target_trades = int(config.get("trade", {}).get("target_trades", BODS_TO_PROCESS))
    except ValueError: 
        target_trades = BODS_TO_PROCESS
        
    session_crafted = 0
    session_small = 0
    
    AddToSystemJournal(f"=== Starting Crafting Cycle ({target_trades} BODs) ===")
    
    if crate != 0:
        UseObject(crate)
        Wait(1000)


    try:
        import BodCycler_TakeBods as _tb
    except Exception:
        _tb = None

    bods_processed = 0
    while bods_processed < target_trades:
        if check_abort():
            break

        if _tb and _tb.should_collect_bods():
            AddToSystemJournal("BOD collection window opened mid-cycle — stopping early for collectors.")
            break

        # Swap Scartare if nearly full (>=480 BODs)
        new_scartare = _swap_full_book(bbcrate, scartare, cycle_type, config, "Scartare")
        if new_scartare != scartare:
            scartare = new_scartare

        close_all_gumps()
        consolidate_materials(crate) 
        
        FindType(BOD_TYPE, Backpack())
        if FindCount() > 0:
            bod = FindItem()
            AddToSystemJournal(f"Found existing BOD in backpack: {hex(bod)}")
        else:
            result = extract_bod_from_origine(origine, bbcrate, cycle_type)
            if isinstance(result, tuple):
                bod, origine = result       # swap: bod=0, origine=new book serial
                if origine == 0:
                    break                   # no replacement book found
                # Persist the new Origine serial so subsequent cycles open the correct book.
                # Update both the runtime alias (books) AND the mode-specific source
                # (books_tailor / books_smith) so a re-sync by the GUI never reverts it.
                try:
                    cfg = load_config() or {}
                    active_key = 'books_smith' if cycle_type == 'Smith' else 'books_tailor'
                    cfg.setdefault('books', {})['Origine'] = origine
                    cfg.setdefault(active_key, {})['Origine'] = origine
                    tmp = CONFIG_FILE + '.tmp'
                    with open(tmp, 'w') as f:
                        json.dump(cfg, f, indent=4)
                    os.replace(tmp, CONFIG_FILE)
                    AddToSystemJournal(f"Config: Origine ({active_key}) updated to {hex(origine)}")
                except Exception as e:
                    AddToSystemJournal(f"Config: Failed to persist new Origine serial — {e}")
                continue                    # retry with new Origine
            elif result == 0:
                break
            else:
                bod = result
            
        info = parse_bod(bod, cycle_type)

        if trash_dc and info.get('material', '').lower() == 'dull copper':
            dest = trash if trash else scartare
            AddToSystemJournal(f"[DC Killswitch] Trashing Dull Copper BOD {hex(bod)} ({info.get('item_name','?')}).")
            log_event("DC_TRASH", f"Dull Copper BOD {hex(bod)} ({info.get('item_name','?')}) moved to trash in crafting cycle.")
            MoveItem(bod, 0, dest, 0, 0, 0)
            Wait(600)
            continue

        if info['qty_needed'] <= 0:
            # BOD is already filled — still counts as a processed BOD for the cycle.
            session_crafted += 1
            dest = conserva if is_prize_enabled(info['prize_id'], config) else consegna
            _small = 0
            if dest == conserva and not info['is_large']:
                session_small += 1
                _small = 1
                BodCycler_Assembler.append_to_inventory({"type": "Small", "category": info['cat'], "item": info['item_name'], "material": info['material'].title(), "quality": "Exceptional" if info['is_except'] else "Normal", "amount": info['qty_total']}, conserva)
                AddToSystemJournal(f"[Conserva] {info['item_name']} {info['material']} x{info['qty_total']} → prize #{info['prize_id']}")
            MoveItem(bod, 0, dest, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            update_stats(1, _small)
            continue

        BONE_ITEM_NAMES = {"bone helmet", "bone gloves", "bone arms", "bone leggings", "bone armor"}
        if info['material'] == "bone" or info['is_large'] or info['item_name'] in BONE_ITEM_NAMES:
            dest = conserva if is_prize_enabled(info['prize_id'], config) else scartare
            if dest == conserva and not info['is_large']:
                session_small += 1
                BodCycler_Assembler.append_to_inventory({"type": "Small", "category": info['cat'], "item": info['item_name'], "material": info['material'].title(), "quality": "Exceptional" if info['is_except'] else "Normal", "amount": info['qty_total']}, conserva)
                AddToSystemJournal(f"[Conserva] {info['item_name']} {info['material']} x{info['qty_total']} → prize #{info['prize_id']}")
            MoveItem(bod, 0, dest, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            continue

        cat_identifier, item_identifier, item_id, tool_type, item_cost = get_craft_info(info['item_name'], cycle_type)
        
        if cat_identifier is None:
            AddToSystemJournal(f"[Riprova] {info['item_name']} — not in craft dictionary. Manual review needed.")
            MoveItem(bod, 0, riprova, 0, 0, 0)
            Wait(1000)
            close_all_gumps()
            continue
            
        in_bag = count_valid_backpack_items(item_id, info['is_except'])
        to_make = info['qty_needed'] - in_bag
        
        if to_make > 0:
            if not check_and_pull_materials(info['material'], to_make, item_cost, crate, cycle_type):
                AddToSystemJournal(f"[Riprova] {info['item_name']} ({info['material']}) — insufficient materials.")
                MoveItem(bod, 0, riprova, 0, 0, 0)
                Wait(1000)
                close_all_gumps()
                continue

            mat_btn = MATERIAL_MAP[info['material'].lower()]['btn']
            success = craft_items_until_done(bod, tool_type, cat_identifier, item_identifier, info['item_name'], item_id, info['qty_needed'], info['is_except'], mat_btn)
            close_all_gumps()

            if not success:
                # Check if resources are still available — if so, retry once (likely input lag)
                has_resources = check_and_pull_materials(info['material'], to_make, item_cost, crate, cycle_type)
                if has_resources:
                    AddToSystemJournal(f"Crafting failed but resources available — retrying {info['item_name']}...")
                    success = craft_items_until_done(bod, tool_type, cat_identifier, item_identifier, info['item_name'], item_id, info['qty_needed'], info['is_except'], mat_btn)
                    close_all_gumps()
                    if not success:
                        # Still failed after retry — send to Riprova
                        AddToSystemJournal(f"[Riprova] {info['item_name']} ({info['material']}) — craft failed after retry.")
                        MoveItem(bod, 0, riprova, 0, 0, 0)
                        Wait(1000)
                        close_all_gumps()
                        continue
                else:
                    # Resources missing — true shortage
                    AddToSystemJournal(f"[Riprova] {info['item_name']} ({info['material']}) — materials exhausted mid-craft.")
                    log_event("RIPROVA", f"Materials exhausted mid-craft: {info['item_name']} ({info['material']}) — BOD moved back to Riprova.")
                    MoveItem(bod, 0, riprova, 0, 0, 0)
                    Wait(1000)
                    close_all_gumps()
                    continue
            
        is_full = fill_bod_completely(bod, item_id, info['qty_needed'], info['item_name'], info['is_except'])

        close_all_gumps()
        _crafted = 0
        _small = 0
        if is_full:
            session_crafted += 1
            _crafted = 1
            dest = conserva if is_prize_enabled(info['prize_id'], config) else consegna
            if dest == conserva and not info['is_large']:
                session_small += 1
                _small = 1
                BodCycler_Assembler.append_to_inventory({"type": "Small", "category": info['cat'], "item": info['item_name'], "material": info['material'].title(), "quality": "Exceptional" if info['is_except'] else "Normal", "amount": info['qty_total']}, conserva)
                AddToSystemJournal(f"[Conserva] {info['item_name']} {info['material']} x{info['qty_total']} → prize #{info['prize_id']}")
        else:
            # BOD fill returned False — check if items were already consumed (tooltip was empty/stale)
            FindType(item_id, Backpack())
            items_remain = FindCount() > 0
            if not items_remain:
                # Items consumed but tooltip was cleared — force refresh and recheck
                AddToSystemJournal(f"BOD fill returned False but items consumed — refreshing tooltip for {info['item_name']}...")
                ClickOnObject(bod)
                Wait(600)
                is_full = is_bod_full(bod, info['item_name'])
            else:
                # Items still in backpack — genuine fill failure, retry once
                AddToSystemJournal(f"BOD fill failed for {info['item_name']} — retrying once...")
                is_full = fill_bod_completely(bod, item_id, info['qty_needed'], info['item_name'], info['is_except'])
            close_all_gumps()
            if is_full:
                session_crafted += 1
                _crafted = 1
                dest = conserva if is_prize_enabled(info['prize_id'], config) else consegna
                if dest == conserva and not info['is_large']:
                    session_small += 1
                    _small = 1
                    BodCycler_Assembler.append_to_inventory({"type": "Small", "category": info['cat'], "item": info['item_name'], "material": info['material'].title(), "quality": "Exceptional" if info['is_except'] else "Normal", "amount": info['qty_total']}, conserva)
                    AddToSystemJournal(f"[Conserva] {info['item_name']} {info['material']} x{info['qty_total']} → prize #{info['prize_id']}")
            else:
                # Retry also failed — send to Riprova
                AddToSystemJournal(f"[Riprova] {info['item_name']} ({info['material']}) — BOD fill failed after retry.")
                dest = riprova

        MoveItem(bod, 0, dest, 0, 0, 0)
        Wait(1000)
        close_all_gumps()
        if _crafted:
            update_stats(1, _small)

        bods_processed += 1

    AddToSystemJournal("=== Crafting Cycle Complete ===")


if __name__ == '__main__':
    run_crafting_cycle()