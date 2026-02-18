from stealth import InJournalBetweenTimes, Wait
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

# ---- internal state ----
_state = "idle"                 # idle -> armed -> saving
_next_scan_at = dt.min
_armed_at = dt.min
_cooldown_until = dt.min


def _seen(text: str, lookback_sec: int) -> bool:
    """True if 'text' appeared in journal within last lookback_sec seconds."""
    now = dt.now()
    since = now - timedelta(seconds=lookback_sec)
    # InJournalBetweenTimes returns index of latest match, or 0 if none. :contentReference[oaicite:1]{index=1}
    return InJournalBetweenTimes(text, since, now) > 0


def _wait_until_complete(timeout_ms: int) -> bool:
    """Blocks until 'World save complete' appears, or timeout."""
    deadline = dt.now() + timedelta(milliseconds=timeout_ms)
    while dt.now() < deadline:
        if _seen("World save complete", LOOKBACK_SAVE_SEC):
            return True
        Wait(50)  # poll fast; save window is short
    return False


def world_save_guard() -> bool:
    """
    Call this every iteration of your main loop.
    Returns True if it paused for a save.
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
