"""
_simple_gorget_crafter.py
─────────────────────────
Standalone port of the UOSteam studded-gorget quality-filter script.

Cycle:
  1. Ensure tinker tools (craft if low)
  2. Restock leather from MaterialCrate
  3. Ensure sewing kit (craft if missing)
  4. Craft one Studded Gorget (sewing kit → Studded Armor cat → gorget)
  5. Check resist properties — keep good ones, scissors the rest

Good thresholds (any one triggers keep):
  Fire     > 10
  Poison   > 12
  Physical > 12
  Cold     > 12
  Energy   > 15

Config:  reads MaterialCrate from BodCycler config.json.
         Set GOOD_ARMOR_CRATE manually below if not using BodCycler config.
"""

from stealth import *
import sys, os, re, time

script_dir = os.path.dirname(os.path.abspath(__file__))
repo_root  = os.path.abspath(os.path.join(script_dir, "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:
    from BodCycler_Utils import load_config, wait_for_gump
except ImportError:
    def load_config(): return {}
    def wait_for_gump(gump_id, timeout_ms):
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == gump_id:
                    return i
            Wait(50)
        return -1

# ── Overrides (set 0 to fall back to BodCycler config) ────────────────────────
GOOD_ARMOR_CRATE  = 0x4030A1D9   # serial of crate for good gorgets — set manually

# ── Item constants ─────────────────────────────────────────────────────────────
CRAFT_GUMP        = 0x38920abd
TINKER_TOOL       = 0x1EB8
SEWING_KIT        = 0x0F9D
SCISSORS          = 0x0F9E
LEATHER           = 0x1081
GORGET_TYPE       = 0x13D6   # Studded Gorget

# Tinker gump buttons
BTN_CAT_TOOLS     = 8    # "Tools" category
BTN_MAKE_TT       = 23   # Tinker Tool
BTN_MAKE_SK       = 44   # Sewing Kit

# Sewing kit gump buttons (Stealth ReturnValues, not UOSteam IDs)
BTN_CAT_STUDDED   = 50   # "Studded" category
BTN_MAKE_GORGET   = 2    # Studded Gorget (first item in Studded category)

# Stock targets
TT_MIN            = 2    # tinker tools to keep in backpack
SK_MIN            = 1    # sewing kits to keep in backpack
LEATHER_RESTOCK   = 20   # restock when bp leather drops below this
LEATHER_TARGET    = 240  # pull up to this amount when restocking

# Good resist thresholds — any one → keep
KEEP_IF = {
    "fire":     10,
    "poison":   12,
    "physical": 12,
    "cold":     12,
    "energy":   15,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _count(type_id, container, color=-1):
    if color == -1:
        FindType(type_id, container)
    else:
        FindTypeEx(type_id, color, container, False)
    return FindCount()


def _find_one(type_id, container):
    FindType(type_id, container)
    return FindItem() if FindCount() > 0 else 0


def _log(msg: str):
    AddToSystemJournal(f"[Gorget] {msg}")


def _get_resist(serial: int, resist: str) -> int:
    """Parse a resist value from the item tooltip. Returns 0 if not found."""
    tip = GetTooltip(serial).lower()
    # Handles: "fire resist 15", "fire resist: 15%", "fire: 15"
    patterns = [
        rf'{resist}\s+resist[:\s]+(\d+)',
        rf'{resist}[:\s]+(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, tip)
        if m:
            return int(m.group(1))
    return 0


def _is_good(serial: int) -> bool:
    """True if any resist on the item meets the keep threshold."""
    Wait(400)  # let tooltip cache populate after craft
    tip = GetTooltip(serial)
    if not tip or len(tip) < 10:
        # force client fetch and retry once
        ClickOnObject(serial)
        Wait(600)
        tip = GetTooltip(serial)
    _log(f"  Tooltip [{hex(serial)}]: {tip}")

    for resist, threshold in KEEP_IF.items():
        val = _get_resist(serial, resist)
        if val > threshold:
            _log(f"  KEEP — {resist} {val} > {threshold}")
            return True
    return False


def _craft_with_tinker(cat_btn: int, item_btn: int) -> bool:
    """Opens tinker tool, navigates to category, presses item button. Returns True if gump was reached."""
    tool = _find_one(TINKER_TOOL, Backpack())
    if not tool:
        _log("No tinker tool in backpack.")
        return False

    UseObject(tool)
    idx = wait_for_gump(CRAFT_GUMP, 5000)
    if idx == -1:
        _log("Tinker gump did not open.")
        return False

    NumGumpButton(idx, cat_btn)
    idx = wait_for_gump(CRAFT_GUMP, 3000)
    if idx == -1:
        return False

    NumGumpButton(idx, item_btn)
    Wait(1500)
    return True


# ── Supply checks ──────────────────────────────────────────────────────────────

def _ensure_tinker_tools(crate: int):
    bp = Backpack()
    have = _count(TINKER_TOOL, bp) + _count(TINKER_TOOL, crate)
    if have >= TT_MIN:
        return
    needed = TT_MIN - _count(TINKER_TOOL, bp)
    _log(f"Crafting {needed} tinker tool(s)...")
    for _ in range(needed):
        _craft_with_tinker(BTN_CAT_TOOLS, BTN_MAKE_TT)


def _restock_leather(crate: int):
    bp = Backpack()
    FindTypeEx(LEATHER, -1, bp, False)
    have = FindFullQuantity()
    if have >= LEATHER_RESTOCK:
        return
    pull = LEATHER_TARGET - have
    _log(f"Restocking leather ({have} in bp, pulling {pull})...")
    FindTypeEx(LEATHER, -1, crate, False)
    stack = FindItem()
    if not stack:
        _log("WARNING: No leather in MaterialCrate.")
        return
    MoveItem(stack, pull, bp, 0, 0, 0)
    Wait(800)


def _ensure_sewing_kit(crate: int):
    bp = Backpack()
    if _count(SEWING_KIT, bp) >= SK_MIN:
        return
    # try to pull from crate first
    FindType(SEWING_KIT, crate)
    if FindCount() > 0:
        kit = FindItem()
        MoveItem(kit, 1, bp, 0, 0, 0)
        Wait(800)
        if _count(SEWING_KIT, bp) >= SK_MIN:
            return
    _log("Crafting sewing kit...")
    _craft_with_tinker(BTN_CAT_TOOLS, BTN_MAKE_SK)
    Wait(500)


# ── Core craft / sort ──────────────────────────────────────────────────────────

def _craft_gorget() -> bool:
    """Opens sewing kit and crafts one studded gorget. Returns True on success."""
    FindType(SEWING_KIT, Backpack())
    if FindCount() == 0:
        _log("No sewing kit in backpack.")
        return False
    kit = FindItem()

    UseObject(kit)
    idx = wait_for_gump(CRAFT_GUMP, 5000)
    if idx == -1:
        _log("Sewing kit gump did not open.")
        return False

    # Navigate to Studded category, then gorget
    NumGumpButton(idx, BTN_CAT_STUDDED)
    idx = wait_for_gump(CRAFT_GUMP, 3000)
    if idx == -1:
        _log("Studded category did not load.")
        return False

    before = _count(GORGET_TYPE, Backpack())
    NumGumpButton(idx, BTN_MAKE_GORGET)

    # Poll for the new item
    deadline = time.time() + 4.0
    while time.time() < deadline:
        Wait(200)
        if _count(GORGET_TYPE, Backpack()) > before:
            return True
    _log("Craft timeout — gorget not detected in backpack.")
    return False


def _sort_gorgets(good_crate: int):
    """Check all gorgets in backpack; keep good ones, scissors the rest."""
    FindType(GORGET_TYPE, Backpack())
    gorgets = list(GetFoundList())
    if not gorgets:
        return

    scissors_serial = _find_one(SCISSORS, Backpack())

    for g in gorgets:
        if _is_good(g):
            if good_crate:
                MoveItem(g, 1, good_crate, 0, 0, 0)
                Wait(600)
                _log(f"  Moved good gorget {hex(g)} to crate.")
            else:
                _log(f"  Good gorget {hex(g)} — no crate set, leaving in backpack.")
        else:
            _log(f"  Cutting gorget {hex(g)} (below thresholds).")
            if not scissors_serial:
                scissors_serial = _find_one(SCISSORS, Backpack())
            if scissors_serial:
                UseObject(scissors_serial)
                WaitForTarget(2000)
                if TargetPresent():
                    TargetToObject(g)
                    Wait(600)
            else:
                _log("  WARNING: No scissors in backpack — cannot cut gorget.")


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    cfg        = load_config()
    containers = cfg.get("containers", {})
    mat_crate  = containers.get("MaterialCrate", 0)
    good_crate = GOOD_ARMOR_CRATE or containers.get("GoodArmorCrate", 0)

    if not mat_crate:
        _log("ERROR: MaterialCrate not set in config. Aborting.")
        return
    if not good_crate:
        _log("WARNING: GoodArmorCrate not configured — good gorgets stay in backpack.")

    _log("=== GORGET CRAFTER START ===")

    iteration = 0
    while True:
        iteration += 1
        _log(f"--- Iteration {iteration} ---")

        _ensure_tinker_tools(mat_crate)
        _restock_leather(mat_crate)
        _ensure_sewing_kit(mat_crate)

        if not _craft_gorget():
            _log("Craft failed — stopping.")
            break

        _sort_gorgets(good_crate)
        Wait(500)

    _log("=== GORGET CRAFTER END ===")


if __name__ == "__main__":
    run()
