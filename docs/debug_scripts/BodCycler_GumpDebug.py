"""
BodCycler_GumpDebug.py
======================
Automated Blacksmithing button mapper.
Iterates through SMITH_ITEMS grouped by category, navigates the crafting gump
using text-search (same proven approach as _debug_craftBtn.py for Tailor),
and writes a ready-to-paste SMITH_ITEMS dictionary to a .txt file.

HOW TO USE:
  1. Have Tongs (0x0FBC) in your backpack (multiple — one used per item mapped).
  2. Run this script. It will navigate the gump for every item in SMITH_ITEMS.
  3. When done, open the output file and copy the new SMITH_ITEMS dict into
     bod_crafting_data.py, replacing the placeholder (0, 0) entries.

OUTPUT FILE:
  <StealthPath>/Scripts/mapped_smith_items.txt

PRIORITY ORDER (items mapped first = most important):
  P1 — Ringmail, Chainmail, Platemail sets  (Large BOD assembly targets)
  P2 — Bascinet, Norse Helm, Female Plate, Buckler, Bronze Shield
         (standalone smalls that yield prizes 12+ when exceptional+colored)
  P3 — Mace, Maul, Dagger, Metal Shield, Kite Shields
         (fuel/junk — recognised for routing; craft if you want them)

CATEGORY NAME GUESSES:
  The script tries these category text labels in the Smith gump.
  If your shard uses different names (e.g. "Ring Armor" vs "Ringmail"),
  edit SMITH_CATEGORIES below and re-run.
"""

from stealth import *
import os, sys

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from bod_crafting_data import SMITH_ITEMS
from BodCycler_Utils import wait_for_gump, close_all_gumps

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CRAFT_GUMP_ID    = 0x38920abd
SMITH_TOOL_TYPES = [0x0FBC, 0x13E3]   # Tongs (preferred), Smith's Hammer

# Mapping: category_label_in_gump -> [item names as they appear in the gump]
# Edit these labels if your shard uses different category names.
# Items listed here must also exist as keys in SMITH_ITEMS.
SMITH_CATEGORIES = {
    # P1+P2 — All metal armor items share a single "Metal Armor" category (cat_btn=1).
    # Items span 2 visual pages but all button IDs are accessible without a separate
    # Next Page click. Page 1 items 1-10 (btns 2-65), page 2 items 11-13 (btns 72-86).
    "Metal Armor":  ["ringmail gloves", "ringmail leggings", "ringmail sleeves", "ringmail tunic",
                     "chainmail coif", "chainmail leggings", "chainmail tunic",
                     "platemail arms", "platemail gloves", "platemail gorget",
                     "platemail legs", "platemail tunic", "female plate"],
    # P2 — standalone smalls; plate helm is in Helmets (not Metal Armor)
    "Helmets":      ["bascinet", "norse helm", "plate helm"],
    "Shields":      ["buckler", "bronze shield", "metal shield",
                     "metal kite shield", "tear kite shield"],
    # P3 — Junk/fuel smalls
    "Bashing":      ["mace", "maul"],
    "Bladed":       ["dagger"],
}

SETTLE_MS = 1000   # ms to wait after each gump click

# ---------------------------------------------------------------------------
# Helpers  (same proven logic as _debug_craftBtn.py / _debug_Craft_Tailor.py)
# ---------------------------------------------------------------------------

def _log(msg):
    AddToSystemJournal(f"[SMITH-MAP] {msg}")


def _find_tool():
    for t in SMITH_TOOL_TYPES:
        FindType(t, Backpack())
        if FindCount() > 0:
            return FindItem()
    return 0


def _open_gump(tool_serial):
    close_all_gumps()
    Wait(300)
    UseObject(tool_serial)
    return wait_for_gump(CRAFT_GUMP_ID, 8000)


def find_button_for_text(gump_data, text_to_find):
    """
    Finds the ReturnValue of the button sitting to the LEFT of the given text.
    Checks Cliloc (HTML) first, then plain GumpText as fallback.
    Identical logic to the proven Tailor debug scripts.
    """
    target_x, target_y = -1, -1

    # Pass 1 — Cliloc / HTML labels
    if 'XmfHTMLGumpColor' in gump_data:
        for entry in gump_data['XmfHTMLGumpColor']:
            cliloc  = entry.get('ClilocID', 0)
            content = GetClilocByID(cliloc).upper().replace("<CENTER>", "").replace("</CENTER>", "")
            if text_to_find.upper() in content:
                target_x = entry.get('X', -1)
                target_y = entry.get('Y', -1)
                break

    # Pass 2 — Plain GumpText fallback
    if target_y == -1 and 'GumpText' in gump_data and 'Text' in gump_data:
        for entry in gump_data['GumpText']:
            tid = entry.get('TextID', 0)
            if tid < len(gump_data['Text']):
                if text_to_find.upper() in str(gump_data['Text'][tid]).upper():
                    target_x = entry.get('X', -1)
                    target_y = entry.get('Y', -1)
                    break

    if target_y == -1:
        return None

    # Find nearest button to the LEFT of the text (same Y ±20 px)
    best_btn, min_dist = None, 1000
    for btn in gump_data.get('GumpButtons', []):
        bx = btn.get('X', 0)
        by = btn.get('Y', 0)
        if bx < target_x and abs(by - target_y) < 20:
            dist = target_x - bx
            if dist < min_dist:
                min_dist = dist
                best_btn = btn.get('ReturnValue')

    return best_btn


# ---------------------------------------------------------------------------
# Main mapper
# ---------------------------------------------------------------------------

def run_smith_mapper():
    _log("=== Blacksmithy Button Mapper starting ===")

    tool = _find_tool()
    if tool == 0:
        _log("ERROR: No Tongs or Smith's Hammer in backpack. Aborting.")
        return

    mapped_lines = []
    skipped      = []
    total_mapped = 0

    for cat_label, item_names in SMITH_CATEGORIES.items():
        _log(f"--- Category: {cat_label} ---")

        for item_name in item_names:
            if item_name not in SMITH_ITEMS:
                _log(f"  SKIP {item_name}: not in SMITH_ITEMS")
                skipped.append(item_name)
                continue

            data = SMITH_ITEMS[item_name]
            graphic_id  = data[2]
            cost        = data[3]
            mat_type    = data[4]

            _log(f"  Mapping: {item_name}...")
            close_all_gumps()

            # Fresh tool each time
            tool = _find_tool()
            if tool == 0:
                _log("  Out of tools! Halting.")
                break

            # 1. Open gump
            idx = _open_gump(tool)
            if idx == -1:
                _log(f"  [!] Gump did not open for {item_name}")
                skipped.append(item_name)
                continue

            gump_data = GetGumpInfo(idx)

            # 2. Find category button
            cat_btn = find_button_for_text(gump_data, cat_label)
            if cat_btn is None:
                _log(f"  [!] Category '{cat_label}' not found for {item_name}")
                skipped.append(item_name)
                continue

            # 3. Click category
            NumGumpButton(idx, cat_btn)
            Wait(SETTLE_MS)
            idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
            if idx == -1:
                _log(f"  [!] Gump closed after clicking category for {item_name}")
                skipped.append(item_name)
                continue

            gump_data_item = GetGumpInfo(idx)

            # 4. Find item button
            item_btn = find_button_for_text(gump_data_item, item_name)
            if item_btn is None:
                _log(f"  [!] Item '{item_name}' not found inside category '{cat_label}'")
                skipped.append(item_name)
                continue

            # 5. Format output line
            hex_id  = f"0x{graphic_id:04X}"
            line    = f'    "{item_name}": ({cat_btn}, {item_btn}, {hex_id}, {cost}, "{mat_type}"),'
            mapped_lines.append(line)
            total_mapped += 1
            _log(f"  OK: cat_btn={cat_btn}  item_btn={item_btn}  → {item_name}")

    # Write output file
    output_path = f"{StealthPath()}Scripts\\mapped_smith_items.txt"
    try:
        with open(output_path, "w") as f:
            f.write("# Auto-generated by BodCycler_GumpDebug.py\n")
            f.write("# Copy into bod_crafting_data.py SMITH_ITEMS dict\n\n")
            f.write("SMITH_ITEMS = {\n")
            f.write("\n".join(mapped_lines))
            f.write("\n}\n")
            if skipped:
                f.write(f"\n# SKIPPED (not found or no tool): {skipped}\n")
        _log(f"=== Done: {total_mapped} mapped, {len(skipped)} skipped ===")
        _log(f"Output: {output_path}")
    except Exception as e:
        _log(f"ERROR writing output file: {e}")
        _log("Dumping mapped lines to journal instead:")
        for line in mapped_lines:
            _log(line)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
run_smith_mapper()
