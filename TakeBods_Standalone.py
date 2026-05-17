from stealth import *
import time
from datetime import datetime, timedelta


# ===== USER CONFIGURATION — edit these before running =====
COLLECTOR_PROFILES = ["ed2", "ed3", "ed5"]   # Stealth profile names for collectors
NPCB = 0x0002D23A   # Blacksmith NPC serial — find yours via Stealth object inspector
NPCT = 0x0002D1D4   # Tailor NPC serial
# ==========================================================


# ---- BOD / Book Constants ----
BOD_TYPE          = 0x2258
BOD_BOOK_TYPE     = 0x2259
BOD_TAILOR_COLOR  = 0x0483
BOD_SMITH_COLOR   = 0x044E
CTX_BOD           = 3
BTN_ACCEPT_BOD    = 1
BOD_GUMP_ID_SMALL = 0x9BADE6EA

BOOK_TAILOR_NAME  = 'Tailor'
BOOK_SMITH_NAME   = 'Black'
CLOSE_TO_FULL     = ['495', '498', '499']

# ---- Timing ----
MIN_PAUSE       = 600
MED_PAUSE       = 1200
GUMP_TIMEOUT    = 10_000   # ms — max wait for BOD gump before skipping NPC
CONNECT_TIMEOUT = 15       # seconds
POLL_INTERVAL   = 60_000   # ms — how often to probe NPC while waiting

# ---- Server restart window ----
RESTART_HOUR     = 6
RESTART_MINUTE   = 55
RECONNECT_HOUR   = 7
RECONNECT_MINUTE = 5

_last_restart_date = None


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def connection_guard():
    """Blocks until Connected(). Calls Connect() in a loop if offline."""
    if Connected():
        return
    AddToSystemJournal("Connection lost — reconnecting...")
    while not Connected():
        Connect()
        Wait(10000)
    AddToSystemJournal("Reconnected. Settling...")
    Wait(5000)


def _seen_in_journal(text, lookback_sec=20) -> bool:
    now = datetime.now()
    since = now - timedelta(seconds=lookback_sec)
    return InJournalBetweenTimes(text, since, now) > 0


def world_save_guard():
    """Pauses execution during a world save. Call before any game action."""
    if _seen_in_journal("The world will save in 15 seconds", 30):
        AddToSystemJournal("World save imminent — holding...")
        deadline = time.time() + 30
        while time.time() < deadline:
            if _seen_in_journal("World save complete", 20):
                break
            Wait(500)
        Wait(1000)
    elif _seen_in_journal("The world is saving, please wait", 20):
        AddToSystemJournal("World save in progress — waiting...")
        deadline = time.time() + 20
        while time.time() < deadline:
            if _seen_in_journal("World save complete", 20):
                break
            Wait(500)
        Wait(1000)


def check_server_restart():
    """
    Handles the daily server restart window (6:55–7:05).
    Disconnects, sleeps until past 7:05, then reconnects. Fires once per day.
    """
    global _last_restart_date
    now = datetime.now()
    mins_now     = now.hour * 60 + now.minute
    restart_start = RESTART_HOUR * 60 + RESTART_MINUTE
    restart_end   = RECONNECT_HOUR * 60 + RECONNECT_MINUTE

    if not (restart_start <= mins_now < restart_end):
        return
    if _last_restart_date and _last_restart_date.date() == now.date():
        return  # already handled today

    AddToSystemJournal(f"Server restart window — disconnecting until {RECONNECT_HOUR:02d}:{RECONNECT_MINUTE:02d}.")
    if Connected():
        Disconnect()

    while True:
        Wait(5000)
        if datetime.now().hour * 60 + datetime.now().minute >= restart_end:
            break

    _last_restart_date = datetime.now()
    AddToSystemJournal("Restart window over — reconnecting.")
    Connect()
    connection_guard()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_connect(timeout=CONNECT_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Connected():
            return True
        Wait(200)
    return False


def _wait_for_gump(gump_id, timeout_ms=3000) -> int:
    t = time.time()
    while (time.time() - t) * 1000 < timeout_ms:
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == gump_id:
                return i
        Wait(50)
    return -1


def _find_book(book_name: str):
    FindType(BOD_BOOK_TYPE, Backpack())
    for book in GetFoundList():
        tooltip = GetTooltip(book)
        if tooltip and book_name in tooltip:
            return book
    return 0


def _get_bod(npc_serial: int) -> bool:
    world_save_guard()
    connection_guard()
    if GetDistance(npc_serial) > 2:
        newMoveXY(GetX(npc_serial), GetY(npc_serial), False, 2, True)
        Wait(MIN_PAUSE)
    world_save_guard()
    SetContextMenuHook(npc_serial, CTX_BOD)
    RequestContextMenu(npc_serial)
    Wait(MED_PAUSE)
    idx = _wait_for_gump(BOD_GUMP_ID_SMALL, GUMP_TIMEOUT)
    if idx == -1:
        AddToSystemJournal("_get_bod: No gump — skipping NPC.")
        return False
    Wait(300)
    NumGumpButton(idx, BTN_ACCEPT_BOD)
    Wait(MIN_PAUSE)
    return True


def _store_bods():
    for book_name, color in [(BOOK_TAILOR_NAME, BOD_TAILOR_COLOR), (BOOK_SMITH_NAME, BOD_SMITH_COLOR)]:
        book = _find_book(book_name)
        if not book:
            continue
        tooltip = GetTooltip(book) or ""
        if any(x in tooltip for x in CLOSE_TO_FULL):
            AddToSystemJournal(f"WARNING: {book_name} book nearly full!")
        FindTypeEx(BOD_TYPE, color, Backpack())
        for bod in GetFoundList():
            MoveItem(bod, 1, book, 0, 0, 0)
            Wait(MIN_PAUSE)


def _poll_until_bod_available():
    """
    Probes the Tailor NPC every minute until a BOD is offered.
    Reads the journal for the exact wait time and logs it each check.
    Accepts the BOD when available and returns.
    """
    AddToSystemJournal(f"TakeBods [{COLLECTOR_PROFILES[0]}]: Waiting for next BOD...")
    while True:
        j_start = datetime.now()
        if _get_bod(NPCT):
            AddToSystemJournal("TakeBods: BOD available — starting cycle.")
            return
        j_now = datetime.now()
        for mins in range(60, 0, -1):
            if InJournalBetweenTimes(f"about {mins} minute", j_start, j_now) > 0:
                AddToSystemJournal(f"TakeBods: ~{mins} min until next BOD.")
                break
        Wait(POLL_INTERVAL)


def _run_profile(profile: str):
    """Connect as profile, collect both BODs, store them, walk home, disconnect."""
    check_server_restart()
    AddToSystemJournal(f"Switching to: {profile}")
    ChangeProfile(profile)
    Wait(MIN_PAUSE)
    Connect()
    if not _wait_for_connect():
        AddToSystemJournal(f"{profile}: Could not connect — skipping.")
        Disconnect()
        return
    _get_bod(NPCT)
    _get_bod(NPCB)
    _store_bods()
    Wait(MIN_PAUSE)
    newMoveXY(988, 523, False, 1, True)
    Wait(MED_PAUSE)
    AddToSystemJournal(f"{profile}: Done. Disconnecting...")
    Wait(MED_PAUSE)
    Disconnect()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    AddToSystemJournal(f"TakeBods: Started — {len(COLLECTOR_PROFILES)} collectors.")
    while True:
        check_server_restart()
        # Stay on first collector and probe every minute until their BOD is ready
        ChangeProfile(COLLECTOR_PROFILES[0])
        Wait(MED_PAUSE)
        Connect()
        _wait_for_connect()
        _poll_until_bod_available()   # blocks here; accepts tailor BOD when ready

        # First collector: tailor BOD already in backpack — just get blacksmith + store
        _get_bod(NPCB)
        _store_bods()
        Wait(MIN_PAUSE)
        newMoveXY(988, 523, False, 1, True)
        Wait(MED_PAUSE)
        AddToSystemJournal(f"{COLLECTOR_PROFILES[0]}: Done. Disconnecting...")
        Wait(MED_PAUSE)
        Disconnect()

        # Remaining collectors: both NPCs
        AddToSystemJournal(f"=== BOD COLLECTION CYCLE START {COLLECTOR_PROFILES[1:]} ===")
        for profile in COLLECTOR_PROFILES[1:]:
            _run_profile(profile)
        AddToSystemJournal("=== CYCLE COMPLETE ===")
