# BodCycler_Utils.py
# Single source of truth for shared constants, file I/O, and UI helpers.

from stealth import *
import json
import os
import time
import threading
import datetime

_STATS_LOCK = threading.Lock()
_INV_LOCK   = threading.Lock()

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

# ---------------------------------------------------------------------------
# Shared File Paths
# All scripts must use these — never re-declare them locally.
# ---------------------------------------------------------------------------
CONFIG_FILE      = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
STATS_FILE       = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_stats.json"
INVENTORY_FILE   = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_inventory.json"  # legacy fallback

def get_inventory_file(book_serial):
    """Returns a per-book inventory JSON path keyed by the Conserva book serial.
    One file per physical book — Tailor and Smith never share the same database.
    """
    return f"{StealthPath()}Scripts\\{CharName()}_bodcycler_inventory_{hex(book_serial)}.json"
SUPPLY_FILE      = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_supplies.json"
PERFORMANCE_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_performance.json"
LOG_FILE         = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_log.txt"

# ---------------------------------------------------------------------------
# Shared Game Constants
# ---------------------------------------------------------------------------
BOD_TYPE     = 0x2258
BOD_BOOK_TYPE = 0x2259
BOOK_GUMP_ID = 0x54F555DF
NEXT_PAGE_BTN = 3

# BOD color/hue identifiers
BOD_TAILOR_COLOR = 0x0483
BOD_SMITH_COLOR  = 0x044E

# NPC & context menu
NPC_TYPES    = [0x0190, 0x0191]   # male/female human
CTX_BUY      = 1
CTX_BOD      = 3

# Gump button IDs
BTN_ACCEPT_BOD = 1
BTN_DROP_BOD_1 = 5
COMBINE_BTN    = 2

# Gump IDs
BOD_GUMP_ID_SMALL = 0x9BADE6EA
BOD_GUMP_ID_LARGE = 0xBE0DAD1E
CRAFT_GUMP_ID     = 0x38920ABD

# Material / item types
CLOTH_1           = 0x1766
CLOTH_2           = 0x1767
BOLT_OF_CLOTH_IDS = [0x0F95, 0x0F97, 0x0F9B, 0x0F9C]
INGOT_TYPE        = 0x1BF2
LEATHER_TYPE      = 0x1081
SEWING_KIT_TYPE   = 0x0F9D
TONGS_TYPE        = 0x0FBC
SCISSORS          = 0x0F9E
OIL_CLOTH         = 0x175D
SANDALS           = 0x170D

# Junk items auto-trashed after smithing BOD turn-in
SMITH_JUNK_TYPES  = [0x0F39, 0x0E86, 0x13D5, 0x13EB]

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
# Event Logging
# ---------------------------------------------------------------------------

def log_event(event_type, message):
    """Appends a timestamped entry to the cycle log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{event_type.upper()}] {message}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        AddToSystemJournal(f"log_event: failed to write — {e}")

# ---------------------------------------------------------------------------
# Abort Signal
# ---------------------------------------------------------------------------

def check_abort():
    """Returns True if the GUI has written 'Stopped' to the stats file."""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f).get("status") == "Stopped"
        except Exception:
            pass
    return False

# ---------------------------------------------------------------------------
# Stats File Helpers
# ---------------------------------------------------------------------------

def read_stats():
    """Reads the stats file. Returns a dict with safe defaults."""
    defaults = {
        "crafted": 0, "prized_small": 0, "prized_large": 0,
        "prizes_dropped": 0, "recovery_success": 0, "mats_used": {}, "status": "Idle"
    }
    with _STATS_LOCK:
        if os.path.exists(STATS_FILE):
            for _ in range(3):
                try:
                    with open(STATS_FILE, "r") as f:
                        content = f.read()
                    if content.strip():
                        defaults.update(json.loads(content))
                    break
                except Exception:
                    time.sleep(0.1)
    return defaults

def write_stats(data):
    """Writes a stats dict to the stats file atomically."""
    tmp = STATS_FILE + ".tmp"
    with _STATS_LOCK:
        try:
            with open(tmp, "w") as f:
                json.dump(data, f, indent=4)
            os.replace(tmp, STATS_FILE)
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

def save_performance_snapshot():
    """
    Appends a per-hour performance entry to PERFORMANCE_FILE at the end of every cycle
    (user-stopped or error-stopped). Reads current stats to calculate rates.
    The AI debugger can load this file to spot efficiency trends over time.
    """
    stats = read_stats()
    session_start = stats.get("session_start", 0)
    if not session_start:
        return

    elapsed_seconds = time.time() - session_start
    elapsed_hours = elapsed_seconds / 3600.0
    if elapsed_hours < (1 / 60):  # skip snapshots shorter than 1 minute
        return

    bods_filled = stats.get("crafted", 0)
    bods_traded = stats.get("bods_traded", 0)
    filled_per_hour = round(bods_filled / elapsed_hours, 2) if elapsed_hours > 0 else 0.0
    traded_per_hour = round(bods_traded / elapsed_hours, 2) if elapsed_hours > 0 else 0.0

    entry = {
        "date": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_hours": round(elapsed_hours, 3),
        "bods_filled": bods_filled,
        "bods_traded": bods_traded,
        "filled_per_hour": filled_per_hour,
        "traded_per_hour": traded_per_hour,
    }

    db = {"sessions": []}
    if os.path.exists(PERFORMANCE_FILE):
        try:
            with open(PERFORMANCE_FILE, "r") as f:
                db = json.load(f)
        except Exception:
            pass

    db.setdefault("sessions", []).append(entry)

    tmp = PERFORMANCE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(db, f, indent=4)
        os.replace(tmp, PERFORMANCE_FILE)
        AddToSystemJournal(
            f"Performance snapshot saved: {bods_filled} filled ({filled_per_hour}/h), "
            f"{bods_traded} traded ({traded_per_hour}/h) over {round(elapsed_hours, 2)}h"
        )
    except Exception as e:
        AddToSystemJournal(f"Utils: Failed to write performance snapshot — {e}")


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


def is_prize_enabled(prize_id, config):
    """Returns True if prize_id is in the user's prize_filter for the current cycle type."""
    if not prize_id:
        return False
    cycle_type = config.get("cycle_type", "Tailor")
    key = "tailor" if cycle_type == "Tailor" else "smith"
    enabled = config.get("prize_filter", {}).get(key, [])
    return prize_id in enabled


TALISMAN_TYPE = 0x2F5B

def swap_talisman(cycle_type, config):
    """Equips the correct talisman for the given cycle_type.
    Lookup order: stored serial in config → tooltip keyword scan in backpack.
    Logs + Discord alert if not found; returns True on success, False on failure.
    """
    import BodCycler_AI_Debugger

    keyword       = "tailoring" if cycle_type == "Tailor" else "blacksmithing"
    target_serial = config.get("talismans", {}).get(cycle_type, 0)
    layer         = TalismanLayer()

    # Fallback: scan backpack by tooltip keyword if serial not configured
    if not target_serial:
        FindType(TALISMAN_TYPE, Backpack())
        for item in GetFoundList():
            if keyword in GetTooltip(item).lower():
                target_serial = item
                break

    if not target_serial:
        msg = f"[Talisman] No {cycle_type} talisman found — continuing without swap."
        AddToSystemJournal(msg)
        try:
            #BodCycler_AI_Debugger.send_error_alert("talisman_missing", cycle_type, msg, False)
            Misc.Pause(10)
        except Exception:
            pass
        return False

    # Already wearing the right one
    if ObjAtLayer(layer) == target_serial:
        return True

    # Unequip current talisman, equip new one
    UnEquip(layer)
    Wait(600)
    Equip(layer, target_serial)
    Wait(600)

    if ObjAtLayer(layer) == target_serial:
        AddToSystemJournal(f"[Talisman] Equipped {cycle_type} talisman ({hex(target_serial)}).")
        return True

    msg = f"[Talisman] Failed to equip {cycle_type} talisman ({hex(target_serial)})."
    AddToSystemJournal(msg)
    try:
        BodCycler_AI_Debugger.send_error_alert("talisman_equip_fail", cycle_type, msg, False)
    except Exception:
        pass
    return False