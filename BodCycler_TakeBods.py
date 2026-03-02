from stealth import *
import time
from datetime import datetime
from BodCycler_Utils import read_stats, write_stats, wait_for_gump

# ---- Profile Config ----
COLLECTOR_PROFILES = ['ed2', 'ed3', 'ed5']
CRAFTER_PROFILE    = 'ed4'

# ---- NPC Serials ----
NPCB = 0x0002D23A   # Blacksmith NPC
NPCT = 0x0002D1D4   # Tailor NPC

# ---- BOD / Book Constants ----
BOD_GUMP_ID       = 0x9bade6ea  # Small BOD offer gump
CONTEXT_MENU_ENTRY = 3           # "Bulk Order Info" context menu entry
GUMP_ACCEPT_BTN   = 1           # Accept button on BOD gump
BOD_TYPE          = 0x2258
BOD_BOOK_TYPE     = 0x2259
BOD_TAILOR_COLOR  = 0x0483
BOD_SMITH_COLOR   = 0x044E
BOOK_TAILOR_NAME  = 'Tailor'
BOOK_SMITH_NAME   = 'Black'

# ---- Timing ----
MIN_PAUSE         = 600
MED_PAUSE         = 1200
GUMP_TIMEOUT      = 10_000   # ms — max wait for BOD offer gump before skipping NPC
CONNECT_TIMEOUT   = 15       # seconds — max wait for Connected() after Connect()

# ---- Collection Window ----
COLLECT_START_MINUTE = 55    # window opens at :55 (server-aligned to hourly BOD refresh)
COLLECT_END_MINUTE   = 5     # window closes at :05
COLLECTION_COOLDOWN  = 3300  # 55 min in seconds — prevents re-firing in same window


def should_collect_bods() -> bool:
    """True when inside the hourly window (:55–:05) AND ≥55 min since last collection."""
    m = datetime.now().minute
    if not (m >= COLLECT_START_MINUTE or m < COLLECT_END_MINUTE):
        return False
    stats = read_stats()
    last_col = stats.get("last_collection_time", 0)
    return time.time() - last_col >= COLLECTION_COOLDOWN


def _wait_for_connect(timeout=CONNECT_TIMEOUT) -> bool:
    """Polls until Connected() or timeout (seconds). Returns True if connected."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Connected():
            return True
        Wait(200)
    return False


def _find_book(book_name: str):
    """Finds a BOD book in the backpack by name substring. Returns serial or 0."""
    FindType(BOD_BOOK_TYPE, Backpack())
    for book in GetFoundList():
        if book_name in GetTooltip(book):
            return book
    return 0


def _get_bod(npc_serial: int) -> bool:
    """
    Request a BOD from the given NPC.
    Event-driven: polls for the gump up to GUMP_TIMEOUT ms, then skips.
    Returns True if a BOD gump appeared and was accepted.
    """
    if not Connected():
        return False

    if GetDistance(npc_serial) > 2:
        newMoveXY(GetX(npc_serial), GetY(npc_serial), False, 2, True)
        Wait(MIN_PAUSE)

    RequestContextMenu(npc_serial)
    Wait(MED_PAUSE)
    SetContextMenuHook(npc_serial, CONTEXT_MENU_ENTRY)

    # Event-driven: poll for gump up to GUMP_TIMEOUT, then skip NPC
    idx = wait_for_gump(BOD_GUMP_ID, GUMP_TIMEOUT)
    if idx == -1:
        AddToSystemJournal(f"_get_bod: No gump within {GUMP_TIMEOUT // 1000}s — skipping NPC.")
        return False

    Wait(300)
    NumGumpButton(idx, GUMP_ACCEPT_BTN)
    Wait(MIN_PAUSE)
    return True


def _store_bods():
    """Move tailor and blacksmith BODs from backpack into their respective books."""
    tailor_book = _find_book(BOOK_TAILOR_NAME)
    smith_book  = _find_book(BOOK_SMITH_NAME)

    for color, book in [(BOD_TAILOR_COLOR, tailor_book), (BOD_SMITH_COLOR, smith_book)]:
        if not book:
            continue
        FindTypeEx(BOD_TYPE, color, Backpack())
        for bod in GetFoundList():
            MoveItem(bod, 1, book, 0, 0, 0)
            Wait(MIN_PAUSE)


def run_take_bods_cycle():
    """
    Cycles through COLLECTOR_PROFILES sequentially.
    Event-driven: polls for connection instead of fixed sleeps.
    As soon as the last collector logs out, ed4 reconnects immediately.
    Writes last_collection_time to stats on completion.
    """
    AddToSystemJournal("=== BOD COLLECTION CYCLE START ===")

    for profile in COLLECTOR_PROFILES:
        AddToSystemJournal(f"Switching to profile: {profile}")
        ChangeProfile(profile)
        Wait(MIN_PAUSE)   # brief pause for profile switch
        Connect()

        if not _wait_for_connect():
            AddToSystemJournal(f"{profile}: Could not connect within {CONNECT_TIMEOUT}s. Skipping.")
            Disconnect()
            continue

        AddToSystemJournal(f"{profile}: Getting BOD from Tailor...")
        _get_bod(NPCT)

        AddToSystemJournal(f"{profile}: Getting BOD from Blacksmith...")
        _get_bod(NPCB)

        _store_bods()
        newMoveXY(988, 523, False, 1, True)  # Safe spot for disconnect — Top Luna Bank

        AddToSystemJournal(f"{profile}: Done. Disconnecting...")
        Wait(MED_PAUSE)
        Disconnect()

    # Restore crafter immediately — no fixed wait window
    AddToSystemJournal(f"Switching back to crafter profile: {CRAFTER_PROFILE}")
    ChangeProfile(CRAFTER_PROFILE)
    Wait(MIN_PAUSE)
    Connect()

    if not _wait_for_connect():
        AddToSystemJournal("WARNING: Crafter could not reconnect within timeout!")

    # Stamp the collection time so should_collect_bods() won't fire again for 60 min
    stats = read_stats()
    stats["last_collection_time"] = time.time()
    write_stats(stats)

    AddToSystemJournal("=== BOD COLLECTION CYCLE COMPLETE ===")


if __name__ == '__main__':
    run_take_bods_cycle()
