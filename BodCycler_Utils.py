# BodCycler_Utils.py
# Single source of truth for shared constants, file I/O, and UI helpers.

try:
    from stealth import *
except ImportError:
    pass  # Linux native Stealth: the py_stealth launcher injects the API into builtins
import json
import os
import time
import threading
import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

_STATS_LOCK = threading.Lock()
_INV_LOCK   = threading.Lock()

# ---------------------------------------------------------------------------
# World Save Guard + Connection Guard + Server Restart
# ---------------------------------------------------------------------------

_ws_state = "idle"
_ws_next_scan_at = datetime.datetime.min
_ws_armed_at = datetime.datetime.min
_ws_cooldown_until = datetime.datetime.min
_ws_last_restart_date = None

# Save timing: check minutes 0-2 and 30-32 (covers drift from :31 down to :00)
_SAVE_MINUTES = (0, 1, 2, 30, 31, 32)
_SCAN_EVERY_MS = 250
_LOOKBACK_WARNING_SEC = 30
_LOOKBACK_SAVE_SEC = 20
_SAVE_COMPLETE_TIMEOUT_MS = 12000
_POST_SAVE_GRACE_MS = 500
_COOLDOWN_AFTER_SAVE_SEC = 20

# Server restart window
_RESTART_HOUR = 6
_RESTART_MINUTE = 55
_RECONNECT_HOUR = 7
_RECONNECT_MINUTE = 5


def _seen(text, lookback_sec):
    """True if 'text' appeared in journal within last lookback_sec seconds."""
    now = datetime.datetime.now()
    since = now - datetime.timedelta(seconds=lookback_sec)
    return InJournalBetweenTimes(text, since, now) > 0


def _wait_until_save_complete(timeout_ms):
    """Blocks until 'World save complete' appears, or timeout."""
    deadline = datetime.datetime.now() + datetime.timedelta(milliseconds=timeout_ms)
    while datetime.datetime.now() < deadline:
        if _seen("World save complete", _LOOKBACK_SAVE_SEC):
            return True
        Wait(50)
    return False


def connection_guard():
    """Blocks until Connected(). Returns True if a reconnection was needed."""
    if Connected():
        return False
    AddToSystemJournal("Connection lost! Reconnecting...")
    while not Connected():
        Connect()
        Wait(10000)
    AddToSystemJournal("Reconnected. Settling...")
    Wait(5000)
    return True


def check_server_restart():
    """Call between BODs. Handles the daily server restart window (recall home, sleep, reconnect)."""
    global _ws_last_restart_date
    now = datetime.datetime.now()
    minutes_now = now.hour * 60 + now.minute
    restart_start = _RESTART_HOUR * 60 + _RESTART_MINUTE
    restart_end = _RECONNECT_HOUR * 60 + _RECONNECT_MINUTE

    if restart_start <= minutes_now < restart_end:
        if _ws_last_restart_date and _ws_last_restart_date.date() == now.date():
            return False

        AddToSystemJournal("Server restart imminent. Clean exit protocol...")
        config = load_config() or {}

        rb_serial = config.get("travel", {}).get("RuneBook", 0)
        method = config.get("travel", {}).get("Method", "Recall")
        ws1_idx = config.get("travel", {}).get("Runes", {}).get("WorkSpot1", 1)

        if rb_serial > 0:
            AddToSystemJournal(f"Recalling to WorkSpot1 (Rune {ws1_idx}).")
            offset = 5 if method == "Recall" else 7
            btn_id = offset + (ws1_idx - 1) * 6
            UseObject(rb_serial)
            Wait(1500)
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == 0x554B87F3:
                    NumGumpButton(i, btn_id)
                    break
            Wait(5000)

        home_x = config.get("home", {}).get("X", 0)
        home_y = config.get("home", {}).get("Y", 0)
        if home_x > 0 and home_y > 0:
            NewMoveXY(home_x, home_y, True, 0, True)
            Wait(1000)

        AddToSystemJournal("Waiting for server disconnect...")
        while Connected():
            Wait(1000)
        _ws_last_restart_date = datetime.datetime.now()

        AddToSystemJournal(f"Sleeping until {_RECONNECT_HOUR:02d}:{_RECONNECT_MINUTE:02d}...")
        while True:
            Wait(5000)
            if os.path.exists(STATS_FILE):
                try:
                    with open(STATS_FILE, "r") as f:
                        if json.load(f).get("status") == "Stopped":
                            return True
                except Exception:
                    pass
            curr_mins = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute
            if curr_mins >= restart_end:
                break

        connection_guard()
        return True

    return False


def world_save_guard():
    """Call before each game action. Handles connection, world saves, and server restarts.
    Returns True if a save/restart was handled (caller should re-check state).
    """
    global _ws_state, _ws_next_scan_at, _ws_armed_at, _ws_cooldown_until

    connection_guard()

    now = datetime.datetime.now()

    if now < _ws_cooldown_until:
        return False
    if now < _ws_next_scan_at:
        return False
    _ws_next_scan_at = now + datetime.timedelta(milliseconds=_SCAN_EVERY_MS)

    m = now.minute
    in_time_window = (m in _SAVE_MINUTES)
    if _ws_state == "idle" and not in_time_window:
        return False

    if _ws_state == "idle":
        if _seen("The world will save in 15 seconds", _LOOKBACK_WARNING_SEC):
            AddToSystemJournal("[WorldSave] 15s warning detected — armed.")
            _ws_state = "armed"
            _ws_armed_at = now
            return False

        if _seen("The world is saving, please wait", _LOOKBACK_SAVE_SEC):
            _ws_state = "saving"

    if _ws_state == "armed":
        if _seen("The world is saving, please wait", _LOOKBACK_SAVE_SEC):
            _ws_state = "saving"
        elif (now - _ws_armed_at).total_seconds() >= 13:
            AddToSystemJournal("[WorldSave] Save imminent — holding.")
            while not _seen("The world is saving, please wait", _LOOKBACK_SAVE_SEC):
                if (datetime.datetime.now() - _ws_armed_at).total_seconds() > 25:
                    AddToSystemJournal("[WorldSave] Warning expired without save — back to idle.")
                    _ws_state = "idle"
                    return False
                Wait(100)
            _ws_state = "saving"
        elif (now - _ws_armed_at).total_seconds() > 25:
            AddToSystemJournal("[WorldSave] Warning expired without save — back to idle.")
            _ws_state = "idle"
            return False
        else:
            return False

    if _ws_state == "saving":
        AddToSystemJournal("[WorldSave] Save in progress — waiting...")
        Wait(2000)
        _wait_until_save_complete(_SAVE_COMPLETE_TIMEOUT_MS)
        Wait(_POST_SAVE_GRACE_MS)
        AddToSystemJournal("[WorldSave] Save complete — resuming.")
        _ws_state = "idle"
        _ws_cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=_COOLDOWN_AFTER_SAVE_SEC)
        return True

    return False

# ---------------------------------------------------------------------------
# Shared File Paths
# All scripts must use these — never re-declare them locally.
# ---------------------------------------------------------------------------
def _scripts_file(name):
    """Path to a file in Stealth's Scripts dir. os.path.join keeps separators
    correct on both Windows (backslash) and Linux (forward slash)."""
    return os.path.join(StealthPath(), "Scripts", name)

CONFIG_FILE      = _scripts_file(f"{CharName()}_bodcycler_config.json")
STATS_FILE       = _scripts_file(f"{CharName()}_bodcycler_stats.json")
INVENTORY_FILE   = _scripts_file(f"{CharName()}_bodcycler_inventory.json")  # legacy fallback

def get_inventory_file(book_serial):
    """Returns a per-book inventory JSON path keyed by the Conserva book serial.
    One file per physical book — Tailor and Smith never share the same database.
    """
    return _scripts_file(f"{CharName()}_bodcycler_inventory_{hex(book_serial)}.json")
SUPPLY_FILE      = _scripts_file(f"{CharName()}_bodcycler_supplies.json")
PERFORMANCE_FILE = _scripts_file(f"{CharName()}_bodcycler_performance.json")
LOG_FILE         = _scripts_file(f"{CharName()}_bodcycler_log.txt")

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
SMITH_JUNK_TYPES  = [0x0F39, 0x0E86, 0x13D5, 0x13EB, 0x13C6]

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


def send_prize_notification(prize_name, prize_id, config):
    """Sends a Discord alert when a prize is moved to the Reward Crate.
    Only fires if prize_id is in config['discord_notify_prizes'] and DISCORD_WEBHOOK is set in .env.
    """
    if not prize_id:
        return
    cycle_type = config.get("cycle_type", "Tailor")
    key = "tailor" if cycle_type == "Tailor" else "smith"
    notify_list = config.get("discord_notify_prizes", {}).get(key, [])
    if prize_id not in notify_list:
        return
    webhook = os.getenv("DISCORD_WEBHOOK", "")
    if not webhook:
        return
    payload = {
        "username": "BOD Cycler",
        "embeds": [{
            "title": "\U0001f3c6 Prize Secured!",
            "description": f"**{prize_name}** dropped into the Reward Crate.",
            "color": 16766720,
            "footer": {"text": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        }]
    }
    try:
        requests.post(webhook, json=payload, timeout=10)
    except Exception:
        pass

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
        log_event("TALISMAN_FAIL", msg)
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
    log_event("TALISMAN_FAIL", msg)
    return False