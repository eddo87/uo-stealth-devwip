# BodCycler_Utils.py
# Single source of truth for shared constants, file I/O, and UI helpers.

from stealth import *
import json
import os
import time

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): pass

# ---------------------------------------------------------------------------
# Shared File Paths
# All scripts must use these — never re-declare them locally.
# ---------------------------------------------------------------------------
CONFIG_FILE    = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
STATS_FILE     = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_stats.json"
INVENTORY_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_inventory.json"
SUPPLY_FILE    = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_supplies.json"

# ---------------------------------------------------------------------------
# Shared Game Constants
# ---------------------------------------------------------------------------
BOD_TYPE     = 0x2258
BOD_BOOK_TYPE = 0x2259
BOOK_GUMP_ID = 0x54F555DF
NEXT_PAGE_BTN = 3

# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def load_config():
    """Loads the JSON config. Returns dict on success, None on failure."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            AddToSystemJournal(f"Utils: Failed to load config — {e}")
    return None

# ---------------------------------------------------------------------------
# Abort Signal
# ---------------------------------------------------------------------------

def check_abort():
    """Returns True if the GUI has written 'Stopped' to the stats file."""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f).get("status") == "Stopped"
        except:
            pass
    return False

# ---------------------------------------------------------------------------
# Stats File Helpers
# ---------------------------------------------------------------------------

def read_stats():
    """Reads the stats file. Returns a dict with safe defaults."""
    defaults = {
        "crafted": 0, "prized_small": 0, "prized_large": 0,
        "recovery_success": 0, "mats_used": {}, "status": "Idle"
    }
    if os.path.exists(STATS_FILE):
        for _ in range(5):          # retry loop for write-lock races
            try:
                with open(STATS_FILE, "r") as f:
                    content = f.read()
                if content.strip():
                    defaults.update(json.loads(content))
                break
            except Exception:
                time.sleep(0.2)
    return defaults

def write_stats(data):
    """Writes a stats dict to the stats file safely."""
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        AddToSystemJournal(f"Utils: Failed to write stats — {e}")

def set_status(status_text):
    """
    Updates the 'status' key in the stats file without clobbering other fields.
    Worker scripts call this; Config.py's set_global_status() also calls this
    after updating the GUI StringVar.
    """
    data = read_stats()
    data["status"] = status_text
    write_stats(data)

# ---------------------------------------------------------------------------
# Gump Helpers
# ---------------------------------------------------------------------------

def close_all_gumps():
    """
    Closes every open gump in reverse index order.
    Uses a 100ms Wait per close (safe for all contexts).
    """
    for i in range(GetGumpsCount() - 1, -1, -1):
        CloseSimpleGump(i)
        Wait(100)

def wait_for_gump(gump_id, timeout_ms=3000):
    """
    Polls until a gump with the given ID appears or timeout expires.
    Returns the gump index on success, -1 on timeout.
    """
    t = time.time()
    while (time.time() - t) * 1000 < timeout_ms:
        world_save_guard()
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == gump_id:
                return i
        Wait(50)
    return -1

def wait_for_gump_serial_change(current_serial, gump_id, timeout_ms=8000):
    """
    After clicking Next Page on a BOD book, polls until the gump's serial
    changes (meaning the new page has loaded).

    Returns (new_idx, new_serial, True) on success,
            (-1, current_serial, False) on timeout.

    Used by: BodCycler_Scanner.map_and_save_book_inventory()
             BodCycler_Assembler.extract_bods()
    """
    t = time.time()
    while (time.time() - t) * 1000 < timeout_ms:
        Wait(10)
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == gump_id:
                info = GetGumpInfo(i)
                if info["Serial"] != current_serial:
                    return i, info["Serial"], True
    return -1, current_serial, False