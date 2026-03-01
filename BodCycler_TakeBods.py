from stealth import *
from datetime import datetime

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
MIN_PAUSE  = 600
MED_PAUSE  = 1200
LONG_PAUSE = 2500

# ---- Collection Window ----
COLLECT_START_MINUTE = 55   # :55 of any hour (widened to catch cycles that finish late)
COLLECT_END_MINUTE   = 5    # :05 of next hour


def should_collect_bods() -> bool:
    """Returns True during the hourly BOD collection window (:59 – :05)."""
    m = datetime.now().minute
    return m >= COLLECT_START_MINUTE or m < COLLECT_END_MINUTE


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
    Wait(LONG_PAUSE)

    for i in range(GetGumpsCount()):
        if GetGumpID(i) == BOD_GUMP_ID:
            Wait(300)
            NumGumpButton(i, GUMP_ACCEPT_BTN)
            Wait(MIN_PAUSE)
            return True

    return False


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
    Cycles through COLLECTOR_PROFILES, getting one BOD from Tailor + Blacksmith per character,
    then switches back to CRAFTER_PROFILE and reconnects.
    """
    AddToSystemJournal("=== BOD COLLECTION CYCLE START ===")

    for profile in COLLECTOR_PROFILES:
        AddToSystemJournal(f"Switching to profile: {profile}")
        ChangeProfile(profile)
        Wait(LONG_PAUSE)
        Connect()
        Wait(LONG_PAUSE * 2)

        if not Connected():
            AddToSystemJournal(f"{profile}: Could not connect. Skipping.")
            Disconnect()
            Wait(MED_PAUSE)
            continue

        AddToSystemJournal(f"{profile}: Getting BOD from Tailor...")
        _get_bod(NPCT)
        Wait(MED_PAUSE)

        AddToSystemJournal(f"{profile}: Getting BOD from Blacksmith...")
        _get_bod(NPCB)
        Wait(MIN_PAUSE)

        _store_bods()
        Wait(MED_PAUSE)
        newMoveXY( 988 , 523 , False , 1 , True )  # Safe spot for quick disconnect Top Luna Bank

        AddToSystemJournal(f"{profile}: Done. Disconnecting...")
        Wait(MED_PAUSE)
        Disconnect()

    # Restore crafter
    AddToSystemJournal(f"Switching back to crafter profile: {CRAFTER_PROFILE}")
    ChangeProfile(CRAFTER_PROFILE)
    Wait(LONG_PAUSE)
    Connect()
    Wait(LONG_PAUSE * 2)
    AddToSystemJournal("=== BOD COLLECTION CYCLE COMPLETE ===")


if __name__ == '__main__':
    run_take_bods_cycle()
