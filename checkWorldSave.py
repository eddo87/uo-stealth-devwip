import json
import os
from stealth import *
from datetime import datetime as dt, timedelta

# ---- tune these if needed ----
SAVE_MINUTES = (1, 31)          # saves are around :01 and :31
START_WATCH_SECOND = 35         # start checking journal near the warning (~:41)
SCAN_EVERY_MS = 250             # throttle journal scanning
LOOKBACK_WARNING_SEC = 30       # how far back we search for warning
LOOKBACK_SAVE_SEC = 20          # how far back we search for saving/complete
SAVE_COMPLETE_TIMEOUT_MS = 12000  # safety timeout
POST_SAVE_GRACE_MS = 150        # small buffer after save
COOLDOWN_AFTER_SAVE_SEC = 20    # prevents re-triggering immediately

# ---- Server Restart Config ----
RESTART_HOUR = 6
RESTART_MINUTE = 55
RECONNECT_HOUR = 7
RECONNECT_MINUTE = 5

# ---- internal state ----
_state = "idle"                 # idle -> armed -> saving
_next_scan_at = dt.min
_armed_at = dt.min
_cooldown_until = dt.min
_last_restart_date = None


def _seen(text: str, lookback_sec: int) -> bool:
    """True if 'text' appeared in journal within last lookback_sec seconds."""
    now = dt.now()
    since = now - timedelta(seconds=lookback_sec)
    return InJournalBetweenTimes(text, since, now) > 0


def _wait_until_complete(timeout_ms: int) -> bool:
    """Blocks until 'World save complete' appears, or timeout."""
    deadline = dt.now() + timedelta(milliseconds=timeout_ms)
    while dt.now() < deadline:
        if _seen("World save complete", LOOKBACK_SAVE_SEC):
            return True
        Wait(50)  # poll fast; save window is short
    return False


def check_server_restart() -> bool:
    """
    Call this BETWEEN processing BODs for a clean exit.
    It will safely go home, wait for the server to kick the player, 
    and reconnect when the server is back up.
    Returns True if a restart was handled (so you can break your loop to start a new cycle).
    """
    global _last_restart_date
    now = dt.now()
    
    minutes_now = now.hour * 60 + now.minute
    restart_start = RESTART_HOUR * 60 + RESTART_MINUTE
    restart_end = RECONNECT_HOUR * 60 + RECONNECT_MINUTE

    # If we are in the restart window
    if restart_start <= minutes_now < restart_end:
        # Prevent double-triggering on the same day
        if _last_restart_date and _last_restart_date.date() == now.date():
            return False

        AddToSystemJournal("Server restart imminent. Engaging clean exit protocol...")
        
        # Dynamically determine character prefix for files
        try:
            prefix = f"{StealthPath()}Scripts\\{CharName()}_"
        except Exception:
            prefix = ""
            
        config_file = f"{prefix}bodcycler_config.json"
        stats_file = f"{prefix}bodcycler_stats.json"
        
        config = {}
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
            except Exception:
                pass

        # Travel to WorkSpot1
        rb_serial = config.get("travel", {}).get("RuneBook", 0)
        method = config.get("travel", {}).get("Method", "Recall")
        ws1_idx = config.get("travel", {}).get("Runes", {}).get("WorkSpot1", 1)
        
        if rb_serial > 0:
            AddToSystemJournal(f"Recalling to WorkSpot1 (Rune {ws1_idx}) for safety.")
            offset = 5 if method == "Recall" else 7
            btn_id = offset + (ws1_idx - 1) * 6
            
            UseObject(rb_serial)
            Wait(1500)
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == 0x554B87F3:
                    NumGumpButton(i, btn_id)
                    break
            Wait(5000) # Give it 5 seconds to complete travel and load world

        # Move to exact Home coordinates
        home_x = config.get("home", {}).get("X", 0)
        home_y = config.get("home", {}).get("Y", 0)
        if home_x > 0 and home_y > 0:
            AddToSystemJournal(f"Walking to Home Spot ({home_x}, {home_y})")
            newMoveXY(home_x, home_y, True, 0, True)
            Wait(1000)

        AddToSystemJournal("Acknowledging Sleep Mode. Waiting for server to disconnect...")
        
        # Wait for the server to kick us instead of disconnecting manually
        while Connected():
            Wait(1000)
            
        _last_restart_date = dt.now() 
        
        AddToSystemJournal(f"Disconnected. Sleeping until player is online ({RECONNECT_HOUR:02d}:{RECONNECT_MINUTE:02d})...")
        
        # Wait for the server to come back up
        while True:
            Wait(5000)
            
            # Allow the GUI "Stop" button to abort the sleep loop
            if os.path.exists(stats_file):
                try:
                    with open(stats_file, "r") as f:
                        if json.load(f).get("status") == "Stopped":
                            return True
                except Exception: 
                    pass

            curr_time = dt.now()
            curr_mins = curr_time.hour * 60 + curr_time.minute
            if curr_mins >= restart_end:
                break

        # Reconnect
        AddToSystemJournal("Time reached. Reconnecting...")
        while not Connected():
            Connect()
            Wait(10000)
            
        AddToSystemJournal("Reconnected! Waiting for world to settle...")
        Wait(5000) 
        
        AddToSystemJournal("Starting a new cycle...")
        return True
        
    return False


def world_save_guard() -> bool:
    """
    Call this every iteration of your main loop.
    Returns True if it paused for a world save.
    """
    global _state, _next_scan_at, _armed_at, _cooldown_until

    now = dt.now()

    # cooldown (avoid repeated triggers)
    if now < _cooldown_until:
        return False

    # throttle scanning so we don't hammer journal every loop tick
    if now < _next_scan_at:
        return False
    _next_scan_at = now + timedelta(milliseconds=SCAN_EVERY_MS)

    m, s = now.minute, now.second

    # Only watch near expected save time unless already armed/saving
    in_time_window = (m in SAVE_MINUTES and s >= START_WATCH_SECOND)
    if _state == "idle" and not in_time_window:
        return False

    # 1) Arm on warning (do NOT pause yet)
    if _state == "idle":
        if _seen("The world will save in 15 seconds", LOOKBACK_WARNING_SEC):
            _state = "armed"
            _armed_at = now
            return False

        # If we missed the warning but caught saving, handle it anyway
        if _seen("The world is saving, please wait", LOOKBACK_SAVE_SEC):
            _state = "saving"

    # 2) While armed, keep scanning until saving actually starts
    if _state == "armed":
        if _seen("The world is saving, please wait", LOOKBACK_SAVE_SEC):
            _state = "saving"
        elif now - _armed_at > timedelta(seconds=90):
            # server restart / schedule shift / missed message → disarm safely
            _state = "idle"
        return False

    # 3) Saving → pause until complete (this is your 4–5 sec stop)
    if _state == "saving":
        _wait_until_complete(SAVE_COMPLETE_TIMEOUT_MS)
        Wait(POST_SAVE_GRACE_MS)

        _state = "idle"
        _cooldown_until = dt.now() + timedelta(seconds=COOLDOWN_AFTER_SAVE_SEC)
        return True

    return False