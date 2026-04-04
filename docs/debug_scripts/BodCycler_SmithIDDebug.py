"""
BodCycler_SmithIDDebug.py
=========================
Crafts one of each item in SMITH_ITEMS, verifies the actual graphic ID
and tooltip name against the expected values, and writes corrections to JSON.

HOW TO USE:
  1. Have Iron ingots in your backpack (1 stack of 500+ is enough).
  2. Have Tongs (0x0FBC) in your backpack (multiple — one used per smelt cleanup).
  3. Stand near an Anvil and Forge.
  4. Run the script — it will craft + smelt each item automatically.
  5. Open the output JSON to find any graphic ID corrections needed.

OUTPUT:
  <StealthPath>/Scripts/smith_id_corrections.json

NOTES:
  - Items with item_btn == 0 are skipped (not yet button-mapped).
  - Mismatches show both expected and actual IDs plus the tooltip for manual verification.
  - The smelt step reclaims ingots, so you need very few raw materials.
"""

from stealth import *
import os, sys, json
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from bod_crafting_data import SMITH_ITEMS
from BodCycler_Utils import wait_for_gump, close_all_gumps

CRAFT_GUMP_ID = 0x38920abd
TONGS_TYPE    = 0x0FBC
SETTLE_MS     = 800


def _log(msg):
    AddToSystemJournal(f"[SMITH-ID] {msg}")


def _find_tongs():
    FindType(TONGS_TYPE, Backpack())
    return FindItem() if FindCount() > 0 else 0


def _open_gump():
    close_all_gumps()
    Wait(300)
    tongs = _find_tongs()
    if tongs == 0:
        return -1
    UseObject(tongs)
    return wait_for_gump(CRAFT_GUMP_ID, 8000)


def _smelt(item_serial):
    """Open fresh gump and use Smelt Item (btn 14) on the test item."""
    tongs = _find_tongs()
    if tongs == 0:
        return
    close_all_gumps()
    Wait(200)
    UseObject(tongs)
    idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
    if idx == -1:
        return
    NumGumpButton(idx, 14)   # Smelt Item
    WaitForTarget(2000)
    TargetToObject(item_serial)
    Wait(800)
    close_all_gumps()


def run_smith_id_debug():
    _log("=== Smith Graphic ID Verifier starting ===")
    _log("Make sure you have Iron ingots + Tongs near Anvil/Forge!")

    corrections = {}
    total_checked = 0
    total_skipped = 0

    for item_name, data in SMITH_ITEMS.items():
        cat_btn     = data[0]
        item_btn    = data[1]
        expected_id = data[2]

        if cat_btn == 0 or item_btn == 0:
            _log(f"  SKIP {item_name}: item_btn not mapped")
            total_skipped += 1
            continue

        _log(f"  Testing: {item_name}  (expected {hex(expected_id)})")

        # ── Snapshot before craft ─────────────────────────────────────────────
        FindType(0xFFFF, Backpack())
        before = set(GetFoundList())

        # ── Open gump ────────────────────────────────────────────────────────
        idx = _open_gump()
        if idx == -1:
            _log(f"  [!] Could not open gump for {item_name}")
            continue

        # ── Click category ───────────────────────────────────────────────────
        NumGumpButton(idx, cat_btn)
        Wait(SETTLE_MS)
        idx = wait_for_gump(CRAFT_GUMP_ID, 5000)
        if idx == -1:
            _log(f"  [!] Gump closed after category click — {item_name}")
            continue

        # ── Click item ───────────────────────────────────────────────────────
        NumGumpButton(idx, item_btn)
        Wait(SETTLE_MS)
        wait_for_gump(CRAFT_GUMP_ID, 5000)

        # ── Snapshot after craft ─────────────────────────────────────────────
        FindType(0xFFFF, Backpack())
        after    = set(GetFoundList())
        new_items = after - before

        if not new_items:
            _log(f"  [!] {item_name}: nothing appeared — materials or anvil issue?")
            continue

        total_checked += 1
        serial    = list(new_items)[0]
        actual_id = GetType(serial)
        tooltip   = GetTooltip(serial)

        fmt_exp    = f"0x{expected_id:04X}"
        fmt_actual = f"0x{actual_id:04X}"

        if actual_id != expected_id:
            _log(f"  [MISMATCH] {item_name}: expected {fmt_exp}  got {fmt_actual}")
            _log(f"             tooltip: {tooltip[:80]}")
            corrections[item_name] = {
                "expected_id": fmt_exp,
                "actual_id":   fmt_actual,
                "tooltip":     tooltip
            }
        else:
            _log(f"  [OK] {item_name} = {fmt_actual}")

        # ── Smelt test item to reclaim ingots ─────────────────────────────────
        _smelt(serial)
        Wait(300)

    # ── Write output file ─────────────────────────────────────────────────────
    out_path = f"{StealthPath()}Scripts\\smith_id_corrections.json"
    try:
        with open(out_path, "w") as f:
            json.dump(corrections, f, indent=4)
        _log(f"=== Done: {total_checked} checked, {len(corrections)} mismatches, {total_skipped} skipped ===")
        _log(f"Output: {out_path}")
        if not corrections:
            _log("All graphic IDs match!")
    except Exception as e:
        _log(f"ERROR writing output: {e}")
        _log("Dumping corrections to journal instead:")
        for k, v in corrections.items():
            _log(f"  {k}: expected {v['expected_id']} → actual {v['actual_id']}")
            _log(f"       {v['tooltip'][:80]}")


run_smith_id_debug()
