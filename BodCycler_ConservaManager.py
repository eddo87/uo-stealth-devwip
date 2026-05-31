# BodCycler_ConservaManager.py
# Multi-book Conserva management: scan, analyze, rebalance, and trim.

from stealth import *
import json
import os
import time
import re
from collections import defaultdict

from BodCycler_Utils import (
    BOD_BOOK_TYPE, BOD_TYPE, BOOK_GUMP_ID,
    get_inventory_file, load_config, check_abort, close_all_gumps,
    is_prize_enabled, _INV_LOCK, world_save_guard,
    wait_for_gump_serial_change
)
from BodCycler_Assembler import extract_bods, append_to_inventory, find_completable_sets
from BodCycler_Scanner import map_and_save_book_inventory
from bod_data import LARGE_COMPONENTS, get_prize_number, prize_names


# ---------------------------------------------------------------------------
# Phase A — Discover & Scan
# ---------------------------------------------------------------------------

def _get_book_serials(config, cycle_type):
    """Returns non-zero book serials for the given cycle type."""
    key = "conserva_books_tailor" if cycle_type == "Tailor" else "conserva_books_smith"
    return [s for s in config.get(key, []) if s != 0]


def scan_all_books(config, cycle_type):
    """Scans each Conserva book: pull from crate -> scan -> return to crate."""
    crate = config.get("containers", {}).get("ConservaCrate", 0)
    book_serials = _get_book_serials(config, cycle_type)

    if not crate:
        AddToSystemJournal("Conserva Manager: No ConservaCrate configured.")
        return
    if not book_serials:
        AddToSystemJournal(f"Conserva Manager: No {cycle_type} books configured.")
        return

    AddToSystemJournal(f"=== CONSERVA SCAN: {len(book_serials)} {cycle_type} books ===")

    for serial in book_serials:
        if check_abort():
            return
        world_save_guard()
        # Pull from crate if not already in backpack
        FindType(BOD_BOOK_TYPE, Backpack())
        if serial not in GetFoundList():
            AddToSystemJournal(f"Pulling book {hex(serial)} from crate...")
            MoveItem(serial, 1, Backpack(), 0, 0, 0)
            Wait(1200)

        AddToSystemJournal(f"Scanning book {hex(serial)}...")
        bods = map_and_save_book_inventory(serial)
        count = len(bods) if bods else 0
        AddToSystemJournal(f"Scanned {count} BODs in {hex(serial)}.")

    AddToSystemJournal("=== CONSERVA SCAN COMPLETE (books in backpack) ===")


# ---------------------------------------------------------------------------
# Phase B — Pure Python Analysis (no game interaction)
# ---------------------------------------------------------------------------

def load_all_inventories(book_serials):
    """Reads per-book JSONs. Returns {serial: [bod_list]}."""
    result = {}
    for serial in book_serials:
        inv_file = get_inventory_file(serial)
        if os.path.exists(inv_file):
            try:
                with open(inv_file, "r") as f:
                    result[serial] = json.load(f)
            except Exception as e:
                AddToSystemJournal(f"Warning: Failed to read {hex(serial)} inventory -- {e}")
                result[serial] = []
        else:
            AddToSystemJournal(f"Warning: No inventory for {hex(serial)} -- run Scan All first")
            result[serial] = []
    return result


def analyze_and_plan(inventories, book_serials, config, tier1_limit=4, tier2_limit=6, cycle_type="Tailor"):
    """
    Cross-references all books. Produces a tier-based reorganization plan.

    Three tiers — no Consegna/Scartare:
      - Tier 1 (Best, book[0]): max tier1_limit per item per set, wanted prizes only
      - Tier 2 (books[1]):      max tier2_limit per item per set, wanted prizes only
      - Overflow (books[2]):    everything else (unwanted prizes + excess beyond tiers)

    Returns dict with keys: moves, to_overflow, summary.
    """
    # ── Merge all BODs, annotate with source book ──
    all_bods = []
    for serial, inv in inventories.items():
        for bod in inv:
            bod_copy = dict(bod)
            bod_copy["_source"] = serial
            all_bods.append(bod_copy)

    # ── Group by (category, material, quality, amount) ──
    set_groups = defaultdict(lambda: {"larges": [], "smalls": defaultdict(list)})

    for bod in all_bods:
        if bod["type"] == "Large":
            cat = bod.get("category", "")
            if cat and cat in LARGE_COMPONENTS:
                key = (cat, bod["material"], bod["quality"], bod["amount"])
                set_groups[key]["larges"].append(bod)
        elif bod["type"] == "Small":
            item_lower = bod["item"].lower()
            for set_name, components in LARGE_COMPONENTS.items():
                if item_lower in [c.lower() for c in components]:
                    key = (set_name, bod["material"], bod["quality"], bod["amount"])
                    set_groups[key]["smalls"][item_lower].append(bod)

    # ── Destination books by tier ──
    tier1_book = book_serials[0] if len(book_serials) >= 1 else None
    tier2_books = book_serials[1:2] if len(book_serials) >= 2 else []
    overflow_books = book_serials[2:] if len(book_serials) >= 3 else []

    summary = []
    moves = []          # (bod, from_book, to_book)
    to_overflow = []    # (bod, from_book) — goes to overflow books

    def _take(bods, count, dest_book):
        """Takes `count` BODs for dest_book, preferring ones already there.
        Returns (taken, remaining). Generates moves for BODs coming from other books.
        """
        # Sort: BODs already in dest first (minimize moves), others after
        in_dest = [b for b in bods if b["_source"] == dest_book]
        others = [b for b in bods if b["_source"] != dest_book]
        sorted_bods = in_dest + others
        taken, remaining = sorted_bods[:count], sorted_bods[count:]
        for bod in taken:
            if bod["_source"] != dest_book:
                moves.append((bod, bod["_source"], dest_book))
        return taken, remaining

    # ── Prize filter ──
    filter_key = "tailor" if cycle_type == "Tailor" else "smith"
    enabled_prizes = config.get("prize_filter", {}).get(filter_key, [])

    for (cat, mat, qual, amt), group in sorted(set_groups.items()):
        larges = list(group["larges"])
        smalls_by_item = group["smalls"]
        components = [c.lower() for c in LARGE_COMPONENTS.get(cat, [])]
        if not components:
            continue

        large_count = len(larges)
        comp_counts = {c: len(smalls_by_item.get(c, [])) for c in components}
        bottleneck_item = min(comp_counts, key=comp_counts.get)
        bottleneck = comp_counts[bottleneck_item]
        completable = min(large_count, bottleneck)

        prize_id = get_prize_number(cat, mat, amt, qual)
        prize_label = prize_names.get(prize_id, f"#{prize_id}") if prize_id else "No prize"
        wanted = (prize_id in enabled_prizes) if prize_id else False

        tag = "*" if wanted else " "
        summary.append(f"\n{tag} {cat} [{mat} {qual} x{amt}] -> {prize_label}")
        summary.append(f"  Larges: {large_count} | Completable: {completable} | Bottleneck: {bottleneck_item}={bottleneck}")
        parts_str = ", ".join(f"{c}: {comp_counts[c]}" for c in components)
        summary.append(f"  Parts: {parts_str}")

        if not wanted:
            # ── Unwanted → all to Overflow ──
            for bod in larges:
                to_overflow.append((bod, bod["_source"]))
            for comp in components:
                for bod in smalls_by_item.get(comp, []):
                    to_overflow.append((bod, bod["_source"]))
            summary.append(f"  -> Unwanted: all to Overflow")
            continue

        # ── Wanted prize: Tier 1 (max tier1_limit) → Tier 2 (max tier2_limit) → Overflow ──
        t1_large = min(large_count, tier1_limit)
        t2_large = min(max(0, large_count - t1_large), tier2_limit)
        overflow_large = max(0, large_count - t1_large - t2_large)

        remaining_l = list(larges)
        if tier1_book and t1_large > 0:
            _, remaining_l = _take(remaining_l, t1_large, tier1_book)
        if tier2_books and t2_large > 0:
            per_t2 = max(1, t2_large // max(1, len(tier2_books)))
            for tb in tier2_books:
                if not remaining_l:
                    break
                _, remaining_l = _take(remaining_l, min(per_t2, len(remaining_l)), tb)
        # Anything beyond tier1+tier2 → Overflow
        for bod in remaining_l:
            to_overflow.append((bod, bod["_source"]))

        # ── Smalls: same tier limits per component ──
        overflow_smalls = 0
        for comp in components:
            comp_bods = list(smalls_by_item.get(comp, []))
            if not comp_bods:
                continue

            t1_s = min(len(comp_bods), tier1_limit)
            t2_s = min(max(0, len(comp_bods) - t1_s), tier2_limit)

            remaining_s = list(comp_bods)
            if tier1_book and t1_s > 0:
                _, remaining_s = _take(remaining_s, t1_s, tier1_book)
            if tier2_books and t2_s > 0:
                per_t2 = max(1, t2_s // max(1, len(tier2_books)))
                for tb in tier2_books:
                    if not remaining_s:
                        break
                    _, remaining_s = _take(remaining_s, min(per_t2, len(remaining_s)), tb)
            for bod in remaining_s:
                to_overflow.append((bod, bod["_source"]))
                overflow_smalls += 1

        summary.append(f"  Tier 1: {t1_large}L | Tier 2: {t2_large}L | -> Overflow: {overflow_large}L + {overflow_smalls}S")

    # ── Final summary ──
    move_count = len([m for m in moves if m[1] != m[2]])
    overflow_count = len(to_overflow)
    summary.append(f"\nPLAN SUMMARY:")
    summary.append(f"  Cross-book moves (tier rebalance): {move_count}")
    summary.append(f"  To Overflow: {overflow_count}")

    return {
        "moves": moves,
        "to_overflow": to_overflow,
        "summary": summary,
    }


def analyze_and_log(config, cycle_type, mode="all"):
    """Analyze all Conserva books. Mode controls what gets executed:
      'all'      — tier rebalancing + overflow moves
      'overflow' — only overflow moves (unwanted + excess → overflow books)
    """
    book_serials = _get_book_serials(config, cycle_type)
    if not book_serials:
        AddToSystemJournal(f"Conserva Manager: No {cycle_type} books configured.")
        return

    inventories = load_all_inventories(book_serials)
    total_bods = sum(len(inv) for inv in inventories.values())
    tier1 = config.get("conserva_manager", {}).get("keep_tier1", 4)
    tier2 = config.get("conserva_manager", {}).get("keep_tier2", 6)

    AddToSystemJournal(f"=== CONSERVA ANALYZE: {len(book_serials)} {cycle_type} books ({total_bods} BODs) ===")

    plan = analyze_and_plan(inventories, book_serials, config, tier1, tier2, cycle_type)
    for line in plan["summary"]:
        AddToSystemJournal(line)

    AddToSystemJournal("=== ANALYZE COMPLETE ===")
    return plan


# ---------------------------------------------------------------------------
# DLL-based Execution — extract + route via raw packet injection
# ---------------------------------------------------------------------------

BP_MAX_ITEMS = 125
BP_SAFETY_MARGIN = 10


def _get_batch_size():
    """Returns how many BODs we can extract into the backpack right now.
    Reads the backpack tooltip for current item count, subtracts safety margin.
    Falls back to 40 if tooltip can't be parsed.
    """
    try:
        tip = GetTooltip(Backpack())
        # Matches "45/125 Items" or "45 Items" or "Contents: 45 Items"
        m = re.search(r'(\d+)(?:/\d+)?\s*Item', tip, re.IGNORECASE)
        if m:
            current = int(m.group(1))
            free = BP_MAX_ITEMS - current - BP_SAFETY_MARGIN
            AddToSystemJournal(f"  Backpack: {current}/{BP_MAX_ITEMS} items, batch={max(1, free)}")
            return max(1, free)
    except Exception:
        pass
    return 40  # conservative fallback


def _get_overflow_dest(config, cycle_type):
    """Returns the overflow book serial — index 2 of the filtered (non-zero) list,
    matching analyze_and_plan's tier indexing (book_serials[2:] = Overflow)."""
    serials = _get_book_serials(config, cycle_type)
    return serials[2] if len(serials) >= 3 else 0


def _auto_inject_dll():
    """Attempts to auto-inject the packet injector DLL into the Stealth process.
    Returns True if injection succeeded (or was already loaded).
    """
    try:
        import inject_dll
        pid = inject_dll.find_stealth_pid()
        if not pid:
            AddToSystemJournal("PacketBridge: Cannot find stealth.exe for auto-injection.")
            return False
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dll_candidates = [
            os.path.join(script_dir, "uo_packet_injector.dll"),
            os.path.join(script_dir, "uo_packet_injector", "target", "release", "uo_packet_injector.dll"),
        ]
        dll_path = next((p for p in dll_candidates if os.path.exists(p)), None)
        if not dll_path:
            AddToSystemJournal("PacketBridge: uo_packet_injector.dll not found for auto-injection.")
            return False
        AddToSystemJournal(f"PacketBridge: Auto-injecting DLL into PID {pid}...")
        ok = inject_dll.inject(pid, dll_path)
        if ok:
            AddToSystemJournal("PacketBridge: DLL injected successfully.")
            time.sleep(1)
        return ok
    except Exception as e:
        AddToSystemJournal(f"PacketBridge: Auto-injection failed — {e}")
        return False


def _ensure_bridge():
    """Connects to the DLL packet bridge. Auto-injects the DLL if needed.
    Uses the DLL's own captured socket handle when available — only falls
    back to brute-force probe if the DLL hasn't captured one yet.
    """
    try:
        import BodCycler_PacketBridge as pb
        if not pb.is_connected():
            if not pb.connect():
                _auto_inject_dll()
                if not pb.connect():
                    AddToSystemJournal("PacketBridge: Cannot connect after auto-injection attempt.")
                    return False
        st = pb.status()
        captured = st.get("captured", False)
        dll_socket = st.get("socket", 0)
        AddToSystemJournal(f"PacketBridge: captured={captured} socket={dll_socket}")

        if captured and dll_socket:
            # DLL already knows the game socket — use it directly
            if pb.set_socket(dll_socket):
                AddToSystemJournal(f"PacketBridge: Using DLL-captured socket {dll_socket}")
                return True
            AddToSystemJournal(f"PacketBridge: DLL socket {dll_socket} rejected, falling back to probe.")

        # DLL hasn't captured a socket yet — probe for it
        h = pb.set_socket_by_probe(force=True)
        if not h:
            AddToSystemJournal("PacketBridge: Socket probe failed. Is Stealth connected?")
            return False
        AddToSystemJournal(f"PacketBridge: Using probed socket {h}")
        return True
    except ImportError:
        AddToSystemJournal("PacketBridge: Module not found.")
        return False


def _open_book_gump(book_serial):
    """Opens a BOD book and polls until the gump is confirmed present.
    Moves the book to backpack if needed.
    Returns (gump_index, gump_serial) or (-1, 0) on failure.
    """
    FindType(BOD_BOOK_TYPE, Backpack())
    if book_serial not in set(GetFoundList()):
        AddToSystemJournal(f"  Moving {hex(book_serial)} to backpack...")
        MoveItem(book_serial, 1, Backpack(), 0, 0, 0)
        Wait(1200)

    close_all_gumps()
    UseObject(book_serial)

    idx = -1
    serial = 0
    deadline = time.time() + 4
    while time.time() < deadline:
        Wait(50)
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == BOOK_GUMP_ID:
                idx = i
                serial = GetGumpInfo(i)["Serial"]
                break
        if idx != -1:
            break

    if idx == -1:
        AddToSystemJournal(f"  Failed to open book {hex(book_serial)}")
    else:
        AddToSystemJournal(f"  Book gump open: idx={idx} serial={serial}")
    return idx, serial


def _reindex_inventory(inventory, dropped_positions):
    """Remove the dropped positions and renumber the remaining entries 0..N-1,
    recomputing the global drop_btn (5+pos*2) and page to mirror UO's server-side
    compaction. Pure (no I/O) so it's unit-testable.

    Pass ONLY the positions that actually dropped — passing requested-but-undropped
    positions deletes entries still in the book and desyncs every later pos/drop_btn.
    """
    dropped = set(dropped_positions)
    remaining = [b for b in inventory if b.get("pos") not in dropped]
    for new_pos, entry in enumerate(remaining):
        entry["pos"] = new_pos
        entry["drop_btn"] = 5 + (new_pos * 2)
        entry["page"] = new_pos // 5
    return remaining


def _check_inventory_consistent(inventory):
    """Pre-drop validation: positions must be dense 0..N-1 and drop_btn == 5+pos*2.
    A drop computes its button from the recorded pos, so a gap or stale drop_btn
    means injecting the wrong global button. Returns (ok, [problems]). Pure."""
    problems = []
    for i, e in enumerate(inventory):
        if e.get("pos") != i:
            problems.append(f"pos gap at idx {i}: got {e.get('pos')}")
        if e.get("drop_btn") != 5 + i * 2:
            problems.append(f"drop_btn off at pos {i}: got {e.get('drop_btn')}")
    return (not problems), problems


def _entry_matches_filter(entry, spec):
    """True if entry matches every non-empty key in spec. Strings compare
    case-insensitively; amount compares as int. Empty/None spec values = 'any'.
    Pure — drives both the GUI preview count and the live purge selection."""
    for key, want in spec.items():
        if want is None or want == "":
            continue
        have = entry.get(key)
        if key == "amount":
            try:
                if int(have) != int(want):
                    return False
            except (TypeError, ValueError):
                return False
        else:
            if str(have).lower() != str(want).lower():
                return False
    return True


def _verify_dropped_tooltip(tooltip, entry):
    """Confirm a just-dropped BOD's tooltip matches the inventory entry it should be.
    'with <material> ingots' uses the FULL material name (Copper != Dull Copper);
    '<type> bulk order' stops a Large being mistaken for a Small. Returns
    (checks_dict, all_ok). Mirrors the validated _inject_debug.py harness."""
    low = (tooltip or "").lower()
    checks = {
        "item": entry["item"].lower() in low,
        "material": f"with {entry['material'].lower()} ingots" in low,
        "amount": f"amount to make: {entry['amount']}" in low,
        "type": f"{entry['type'].lower()} bulk order" in low,
    }
    if entry.get("quality") == "Exceptional":
        checks["quality"] = "must be exceptional" in low
    return checks, all(checks.values())


def count_matching_in_book(book_serial, spec):
    """GUI preview helper: load a book's inventory JSON and report how many entries
    match the filter spec, plus whether the JSON is drop-ready. No game interaction.
    Returns {total, matched, consistent, problems, positions}."""
    inv_file = get_inventory_file(book_serial)
    if not os.path.exists(inv_file):
        return {"total": 0, "matched": 0, "consistent": False,
                "problems": ["no inventory JSON — run Scan first"], "positions": []}
    try:
        with open(inv_file, "r") as f:
            inv = json.load(f)
    except (OSError, ValueError) as e:
        return {"total": 0, "matched": 0, "consistent": False,
                "problems": [f"failed to read JSON — {e}"], "positions": []}
    ok, problems = _check_inventory_consistent(inv)
    matches = [e for e in inv if _entry_matches_filter(e, spec)]
    matches.sort(key=lambda e: e["pos"], reverse=True)
    return {"total": len(inv), "matched": len(matches), "consistent": ok,
            "problems": problems[:10], "positions": [e["pos"] for e in matches]}


def _dll_extract_batch(book_serial, positions):
    """Extracts BODs from a book using DLL packet injection.
    Book must be in backpack. Opens it (or reuses an already-open gump),
    injects 0xB1 per position (descending), waits for serial refresh between each drop.
    Returns list of extracted BOD serials in backpack.
    """
    import BodCycler_PacketBridge as pb

    # Reuse already-open book gump if present; otherwise open it.
    idx = -1
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == BOOK_GUMP_ID:
            idx = i
            break
    if idx == -1:
        idx, _ = _open_book_gump(book_serial)
        if idx == -1:
            return []

    FindType(BOD_TYPE, Backpack())
    bp_before = set(GetFoundList())

    # Read initial gump serial
    current_serial = 0
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == BOOK_GUMP_ID:
            current_serial = GetGumpInfo(i)["Serial"]
            break

    dropped = 0
    for pos in positions:
        if check_abort():
            break

        # First drop uses the serial we already have; subsequent drops wait for change
        if dropped > 0:
            idx, current_serial, changed = wait_for_gump_serial_change(
                current_serial, BOOK_GUMP_ID, 3000
            )
            if not changed:
                AddToSystemJournal(f"  Gump serial didn't refresh after {dropped} drops.")
                break

        btn = 5 + (pos * 2)
        AddToSystemJournal(
            f"  DLL drop: pos={pos} btn={btn} serial={current_serial} "
            f"(hex={hex(current_serial)})"
        )
        result = pb.send_gump_response(current_serial, BOOK_GUMP_ID, btn)
        if result > 0:
            dropped += 1
        else:
            AddToSystemJournal(f"  Inject failed at pos {pos} (result={result})")
            break

    Wait(500)
    close_all_gumps()

    FindType(BOD_TYPE, Backpack())
    bp_after = set(GetFoundList())
    new_bods = list(bp_after - bp_before)

    if dropped > 0 and len(new_bods) == 0:
        AddToSystemJournal(
            f"  WARNING: DLL sent {dropped} packets but 0 BODs appeared — "
            f"server rejected the injected 0xB1 packets."
        )

    AddToSystemJournal(f"  DLL extracted {len(new_bods)} BODs from {hex(book_serial)}")
    return new_bods


def _numgump_extract_batch(book_serial, max_drops):
    """Fallback extractor using NumGumpButton(idx, 5) per drop.
    Slower than the DLL path (one gump-open per BOD) but works without the injector.
    Mirrors the proven pattern from BodCycler_Crafting.extract_bod_from_origine.
    """
    FindType(BOD_TYPE, Backpack())
    bp_before = set(GetFoundList())

    dropped = 0
    for _ in range(max_drops):
        if check_abort():
            break

        idx, _ = _open_book_gump(book_serial)
        if idx == -1:
            AddToSystemJournal(f"  Fallback: failed to open book {hex(book_serial)} after {dropped} drops.")
            break

        NumGumpButton(idx, 5)
        Wait(1500)
        dropped += 1

    FindType(BOD_TYPE, Backpack())
    bp_after = set(GetFoundList())
    new_bods = list(bp_after - bp_before)
    AddToSystemJournal(f"  Fallback extracted {len(new_bods)} BODs from {hex(book_serial)}")
    return new_bods


def _backpack_bods():
    """All BOD serials currently sitting in the backpack."""
    FindType(BOD_TYPE, Backpack())
    return list(GetFoundList())


def _route_bods_to_book(bod_serials, dest_book):
    """Moves extracted BODs from backpack into a destination book."""
    routed = 0
    for bod in bod_serials:
        if check_abort():
            break
        world_save_guard()
        MoveItem(bod, 0, dest_book, 0, 0, 0)
        Wait(800)
        routed += 1
    return routed


def _get_book_bod_count(book_serial):
    """Reads the tooltip to get current BOD count. Returns 0 if unreadable."""
    tip = GetTooltip(book_serial).lower()
    m = re.search(r'deeds in book[:\s]+(\d+)', tip, re.IGNORECASE)
    return int(m.group(1)) if m else 0


BOOK_MAX_DEEDS = 500  # UO bulk order book capacity


def move_all_bods(config, source_book, dest_book):
    """Empties source_book into dest_book, one backpack-sized batch at a time.

    Flow:
      1. Move any BODs already sitting in the backpack into dest_book — clears the
         backpack first so the drain item-count is accurate.
      2. Per batch: close any open gump, open source_book by serial, then fire global
         drop button 5 (always position 0 — each drop shifts the next BOD up, so btn 5
         drains the book from the top) up to the free backpack space (125 - safety).
      3. Pause, close the book gump, then move the drained BODs into dest_book.
      4. Repeat until the source book is empty, the destination is full (500), or a
         pass makes no progress.

    The destination 500-deed cap bounds each batch so BODs are never drained out of the
    source only to be stranded in a full destination. DLL packet injection (btn 5 per
    drop) when available; NumGumpButton fallback otherwise. Returns a status string.
    """
    # 1. Clear pre-existing backpack BODs into the destination first.
    pre_existing = _route_bods_to_book(_backpack_bods(), dest_book)
    if pre_existing:
        AddToSystemJournal(
            f"Move BODs: moved {pre_existing} pre-existing backpack BOD(s) -> {hex(dest_book)}"
        )

    source_total = _get_book_bod_count(source_book)
    if source_total == 0:
        AddToSystemJournal(f"Move BODs: Source book {hex(source_book)} is empty.")
        if pre_existing:
            return f"Move BODs: source empty; {pre_existing} backpack BOD(s) moved"
        return f"Move BODs: source empty ({hex(source_book)})"

    use_dll = _ensure_bridge()
    mode = "DLL" if use_dll else "NumGumpButton"
    if not use_dll:
        AddToSystemJournal("Move BODs: DLL bridge unavailable — using NumGumpButton fallback (slower).")

    AddToSystemJournal(f"Move BODs [{mode}]: {source_total} BODs from {hex(source_book)} -> {hex(dest_book)}")
    moved = 0
    aborted_reason = None

    while True:
        if check_abort():
            aborted_reason = "aborted"
            break

        remaining = _get_book_bod_count(source_book)
        if remaining == 0:
            break

        # Destination item-limit (500). Stop before draining into a full book.
        dest_count = _get_book_bod_count(dest_book)
        dest_free = BOOK_MAX_DEEDS - dest_count
        if dest_free <= 0:
            aborted_reason = f"destination full ({dest_count}/{BOOK_MAX_DEEDS})"
            break

        # Batch is bounded by free backpack space AND remaining dest room.
        batch = max(1, min(_get_batch_size(), remaining, dest_free))

        # --- DROP PHASE: close any gump, open the From book by serial, then drop. ---
        if use_dll:
            close_all_gumps()
            Wait(400)
            idx, _ = _open_book_gump(source_book)
            if idx == -1:
                aborted_reason = "could not open source book"
                break
            fast_drop_bods(source_book, [0] * batch)
        else:
            _numgump_extract_batch(source_book, batch)

        # --- MOVE PHASE: pause, close the book gump, move drained BODs to dest. ---
        Wait(500)
        close_all_gumps()
        Wait(300)
        routed = _route_bods_to_book(_backpack_bods(), dest_book)
        moved += routed
        Wait(300)

        # Guard against spinning: if a full pass didn't shrink the source, stop.
        if _get_book_bod_count(source_book) >= remaining:
            aborted_reason = "no progress (stopped to avoid loop)"
            break

    AddToSystemJournal(
        f"Move BODs complete: {moved}/{source_total} drained + moved "
        f"(dest now {_get_book_bod_count(dest_book)}/{BOOK_MAX_DEEDS})."
    )
    note = f"; +{pre_existing} from backpack" if pre_existing else ""
    if aborted_reason:
        return f"Move BODs [{mode}]: {moved}/{source_total} moved ({aborted_reason}){note}"
    return f"Move BODs [{mode}]: {moved}/{source_total} moved{note}"


def execute_trim(config, cycle_type, mode="all"):
    """Full DLL-based trim: loops analyze → extract one book → rescan → repeat until stable.
    Converges in 1 pass because each iteration uses fresh JSONs.
    """
    if not _ensure_bridge():
        return

    book_serials = _get_book_serials(config, cycle_type)
    if not book_serials:
        AddToSystemJournal("No books configured.")
        return

    tier1 = config.get("conserva_manager", {}).get("keep_tier1", 4)
    tier2 = config.get("conserva_manager", {}).get("keep_tier2", 6)
    overflow_dest = _get_overflow_dest(config, cycle_type)

    # Tier membership from the SAME filtered list passed to analyze_and_plan
    # (book_serials[0]=Tier1, [1]=Tier2, [2:]=Overflow) so the planner's moves
    # and the executor's tier filtering agree even when config slots have gaps.
    tier1_book = book_serials[0] if len(book_serials) >= 1 else None
    tier2_books = book_serials[1:2] if len(book_serials) >= 2 else []
    tier_books_set = set()
    if tier1_book: tier_books_set.add(tier1_book)
    for tb in tier2_books: tier_books_set.add(tb)

    total_moved = 0
    iteration = 0
    all_affected_books = set()
    MAX_ITERATIONS = 20  # safety limit

    while iteration < MAX_ITERATIONS:
        iteration += 1
        if check_abort():
            break

        # Fresh analysis every iteration (positions change after each extraction)
        inventories = load_all_inventories(book_serials)
        plan = analyze_and_plan(inventories, book_serials, config, tier1, tier2, cycle_type)

        if iteration == 1:
            for line in plan["summary"]:
                AddToSystemJournal(line)

        # Check book capacities (BOD books max out at 500)
        book_counts = {s: len(inv) for s, inv in inventories.items()}

        def _dest_has_room(dest, needed=1):
            return book_counts.get(dest, 0) + needed <= 500

        # Build actions for this iteration, skipping moves to full books
        actions_by_source = defaultdict(list)
        skipped_full = 0

        if mode == "pull_prizes":
            # Only move wanted prizes FROM overflow slot (2) INTO tier slots (0-1)
            # Never move anything OUT of tier slots
            for bod, from_book, to_book in plan.get("moves", []):
                if (from_book != to_book
                        and to_book in tier_books_set
                        and from_book not in tier_books_set):
                    if _dest_has_room(to_book):
                        actions_by_source[from_book].append((bod["pos"], to_book))
                        book_counts[to_book] = book_counts.get(to_book, 0) + 1
                    else:
                        skipped_full += 1

        elif mode != "overflow":
            # "all" mode: full bidirectional rebalance
            for bod, from_book, to_book in plan.get("moves", []):
                if from_book != to_book:
                    if _dest_has_room(to_book):
                        actions_by_source[from_book].append((bod["pos"], to_book))
                        book_counts[to_book] = book_counts.get(to_book, 0) + 1
                    else:
                        skipped_full += 1

        if mode == "overflow" or mode == "all":
            for bod, from_book in plan.get("to_overflow", []):
                if overflow_dest and from_book != overflow_dest:
                    if _dest_has_room(overflow_dest):
                        actions_by_source[from_book].append((bod["pos"], overflow_dest))
                        book_counts[overflow_dest] = book_counts.get(overflow_dest, 0) + 1
                    else:
                        skipped_full += 1

        if skipped_full:
            AddToSystemJournal(f"  Skipped {skipped_full} moves (destination book full at 500)")

        if not actions_by_source:
            AddToSystemJournal(f"  Iteration {iteration}: nothing to move. Stable!")
            break

        pending = sum(len(a) for a in actions_by_source.values())
        AddToSystemJournal(f"\n--- Iteration {iteration}: {pending} BODs to move ---")

        # Process ALL source books in this iteration to avoid thrashing
        # (processing one at a time causes the plan to reverse moves each iteration)
        moved_this_round = 0

        for source_book, actions in actions_by_source.items():
            if check_abort():
                break

            actions.sort(key=lambda a: a[0], reverse=True)
            all_affected_books.add(source_book)

            action_idx = 0
            while action_idx < len(actions):
                if check_abort():
                    break

                batch_size = _get_batch_size()
                if batch_size <= 0:
                    AddToSystemJournal("  Backpack too full to extract. Route first.")
                    break

                batch = actions[action_idx:action_idx + batch_size]
                positions = [a[0] for a in batch]

                AddToSystemJournal(f"  Extracting {len(batch)} from {hex(source_book)} (pos {positions[0]}..{positions[-1]})")

                extracted = _dll_extract_batch(source_book, positions)
                if not extracted:
                    AddToSystemJournal("  Extraction failed. Stopping this book.")
                    break

                # Route extracted BODs to destinations
                dest_counts = defaultdict(int)
                for _, dest in batch[:len(extracted)]:
                    dest_counts[dest] += 1
                    all_affected_books.add(dest)

                remaining_bods = list(extracted)
                for dest, count in dest_counts.items():
                    if not remaining_bods or check_abort():
                        break
                    to_route = remaining_bods[:count]
                    remaining_bods = remaining_bods[count:]
                    routed = _route_bods_to_book(to_route, dest)
                    AddToSystemJournal(f"  Routed {routed} to {hex(dest)}")
                    moved_this_round += routed

                action_idx += len(batch)

        total_moved += moved_this_round

        # Rescan affected books so next iteration has fresh positions
        if moved_this_round > 0 and not check_abort():
            for serial in all_affected_books:
                if check_abort():
                    break
                map_and_save_book_inventory(serial)

    AddToSystemJournal(f"\n=== TRIM COMPLETE: {total_moved} BODs moved in {iteration} iteration(s) ===")


# ---------------------------------------------------------------------------
# Quick Scanner — scan any book and report prizes + filled BODs
# ---------------------------------------------------------------------------

def quick_scan_report(config, cycle_type, book_serial=0):
    """Scans a targeted book and reports:
      - BODs with wanted prizes (should be in Conserva, not Scartare/overflow)
      - Completable sets

    Args:
        book_serial: specific book to scan (0 = scan all in backpack)
    """
    filter_key = "tailor" if cycle_type == "Tailor" else "smith"
    enabled_prizes = config.get("prize_filter", {}).get(filter_key, [])

    if book_serial:
        bp_books = [book_serial]
    else:
        FindType(BOD_BOOK_TYPE, Backpack())
        bp_books = list(GetFoundList())

    configured = set(_get_book_serials(config, cycle_type))

    AddToSystemJournal(f"=== QUICK SCAN: {len(bp_books)} book(s) ===")

    total_prizes = 0

    for book_serial in bp_books:
        if check_abort():
            break

        is_configured = book_serial in configured
        tag = "configured" if is_configured else "NOT configured (overflow/scartare?)"

        AddToSystemJournal(f"\nBook {hex(book_serial)} [{tag}]:")

        # Scan the book
        bods = map_and_save_book_inventory(book_serial)
        if not bods:
            AddToSystemJournal(f"  Empty or scan failed.")
            continue

        smalls = [b for b in bods if b['type'] == 'Small']
        larges = [b for b in bods if b['type'] == 'Large']
        AddToSystemJournal(f"  {len(bods)} BODs ({len(smalls)}S + {len(larges)}L)")

        # Check for wanted prizes
        prize_bods = []
        for bod in bods:
            cat = bod.get('category', '')
            if not cat or cat not in LARGE_COMPONENTS:
                # Try categorize from item name
                cat = categorize_items(bod.get('item', ''))
            prize_id = get_prize_number(cat, bod.get('material', ''),
                                        bod.get('amount', 0),
                                        bod.get('quality', 'Normal'))
            if prize_id and prize_id in enabled_prizes:
                prize_label = prize_names.get(prize_id, f"#{prize_id}")
                prize_bods.append((bod, prize_label))

        if prize_bods:
            AddToSystemJournal(f"  WANTED PRIZES: {len(prize_bods)}")
            # Group by prize
            by_prize = defaultdict(int)
            for bod, label in prize_bods:
                by_prize[label] += 1
            for label, count in sorted(by_prize.items()):
                AddToSystemJournal(f"    {label}: {count}")
            total_prizes += len(prize_bods)

        # Check for filled BODs (Small BODs where tooltip shows X/X completed)
        # In the JSON, filled BODs don't have qty info from Scanner (it's visual only).
        # But we can check: if a Small BOD was already filled and ended up here,
        # it should have been routed to Consegna. Flag any Large BODs too.
        # Since Scanner doesn't track fill state, we use a different approach:
        # parse_bod on each to check qty_needed == 0
        # BUT that would be slow (tooltip for each). Instead, check for completable sets.
        sets = find_completable_sets(bods)
        if sets:
            AddToSystemJournal(f"  COMPLETABLE SETS: {len(sets)}")
            for s in sets:
                large = s['large']
                prize_id = get_prize_number(large.get('category', ''),
                                            large.get('material', ''),
                                            large.get('amount', 0),
                                            large.get('quality', 'Normal'))
                prize_label = prize_names.get(prize_id, f"#{prize_id}") if prize_id else "?"
                AddToSystemJournal(
                    f"    {large['category']} {large['material']} "
                    f"{large['quality']} x{large['amount']} -> {prize_label}"
                )

    AddToSystemJournal(f"\n=== QUICK SCAN COMPLETE: {total_prizes} wanted-prize BODs found ===")
    if total_prizes > 0:
        AddToSystemJournal("  Run Trim All to pull these into the correct tier books.")


def categorize_items(item_name):
    """Local import wrapper for bod_data.categorize_items."""
    from bod_data import categorize_items as _cat
    return _cat(item_name)


# ---------------------------------------------------------------------------
# Fill Backpack BODs — craft + combine loose BODs one at a time
# ---------------------------------------------------------------------------

def fill_next_backpack_bod(config, cycle_type):
    """Finds the first unfilled Small BOD in backpack, crafts items to fill it,
    then checks if a matching Large BOD is present to combine.

    Processes ONE BOD per click. Returns True if a BOD was filled.
    """
    import BodCycler_Crafting
    from BodCycler_Assembler import combine_and_store
    from bod_crafting_data import MATERIAL_MAP

    crate = config.get("containers", {}).get("MaterialCrate", 0)

    # Find all loose BODs in backpack
    FindType(BOD_TYPE, Backpack())
    all_bods = list(GetFoundList())
    if not all_bods:
        AddToSystemJournal("No BODs in backpack.")
        return False

    # Find first unfilled Small BOD
    target_bod = None
    target_info = None
    large_bod = None
    large_info = None

    for bod_serial in all_bods:
        info = BodCycler_Crafting.parse_bod(bod_serial, cycle_type)
        if not info:
            continue
        if info.get('is_large'):
            large_bod = bod_serial
            large_info = info
            continue
        if info.get('qty_needed', 0) > 0:
            target_bod = bod_serial
            target_info = info
            break  # take the first unfilled Small

    if not target_bod:
        # No unfilled Smalls — check if we have a Large + filled Smalls to combine
        if large_bod:
            AddToSystemJournal("All Smalls filled. Checking if Large can be combined...")
            small_serials = []
            for bod_serial in all_bods:
                if bod_serial == large_bod:
                    continue
                info = BodCycler_Crafting.parse_bod(bod_serial, cycle_type)
                if info and not info.get('is_large') and info.get('qty_needed', 0) <= 0:
                    small_serials.append(bod_serial)

            if small_serials:
                success = combine_and_store(large_bod, small_serials, config)
                if success:
                    AddToSystemJournal("Combined and routed to Consegna!")
                    from BodCycler_Utils import read_stats, write_stats
                    stats = read_stats()
                    stats["prized_large"] = stats.get("prized_large", 0) + 1
                    write_stats(stats)
                return success
        AddToSystemJournal("No unfilled BODs in backpack.")
        return False

    # We have an unfilled Small BOD — craft it
    AddToSystemJournal(
        f"Filling: {target_info['item_name']} ({target_info['material']}) "
        f"{target_info['qty_needed']} remaining"
    )

    cat_id, item_id_btn, item_gfx, tool_type, item_cost = BodCycler_Crafting.get_craft_info(
        target_info['item_name'], cycle_type
    )
    if cat_id is None:
        AddToSystemJournal(f"  Not in craft dictionary: {target_info['item_name']}")
        return False

    # Pull materials
    to_make = target_info['qty_needed']
    if not BodCycler_Crafting.check_and_pull_materials(
            target_info['material'], to_make, item_cost, crate, cycle_type):
        AddToSystemJournal(f"  Insufficient materials for {target_info['material']}.")
        return False

    # Craft
    mat_btn = MATERIAL_MAP[target_info['material'].lower()]['btn']
    success = BodCycler_Crafting.craft_items_until_done(
        target_bod, tool_type, cat_id, item_id_btn,
        target_info['item_name'], item_gfx,
        target_info['qty_needed'], target_info['is_except'], mat_btn
    )
    close_all_gumps()

    if not success:
        AddToSystemJournal(f"  Crafting failed for {target_info['item_name']}.")
        return False

    # Fill the BOD
    is_full = BodCycler_Crafting.fill_bod_completely(
        target_bod, item_gfx, target_info['qty_needed'],
        target_info['item_name'], target_info['is_except']
    )
    close_all_gumps()

    if is_full:
        AddToSystemJournal(f"  Filled! {target_info['item_name']} ({target_info['material']})")

        # Check remaining unfilled count
        FindType(BOD_TYPE, Backpack())
        remaining_unfilled = 0
        for bs in GetFoundList():
            bi = BodCycler_Crafting.parse_bod(bs, cycle_type)
            if bi and not bi.get('is_large') and bi.get('qty_needed', 0) > 0:
                remaining_unfilled += 1

        AddToSystemJournal(f"  {remaining_unfilled} unfilled BOD(s) remaining in backpack.")

        # If all smalls filled and a Large is present, offer to combine
        if remaining_unfilled == 0 and large_bod:
            AddToSystemJournal("  All Smalls filled + Large present — combining!")
            small_serials = []
            FindType(BOD_TYPE, Backpack())
            for bs in GetFoundList():
                if bs == large_bod:
                    continue
                bi = BodCycler_Crafting.parse_bod(bs, cycle_type)
                if bi and not bi.get('is_large'):
                    small_serials.append(bs)
            if small_serials:
                combine_and_store(large_bod, small_serials, config)
                AddToSystemJournal("  Combined and routed to Consegna!")
        return True
    else:
        AddToSystemJournal(f"  Fill failed for {target_info['item_name']}.")
        return False


# ---------------------------------------------------------------------------
# Set Extraction — find completable sets and prepare RE drops
# ---------------------------------------------------------------------------

def check_completable_sets(config, cycle_type, overflow_only=False):
    """Checks Conserva books for completable sets. Logs what's available.
    If overflow_only=True, only checks books at index 3+ (Overflow tier).
    Does NOT write RE drops — use extract_next_set() for that.
    """
    book_serials = _get_book_serials(config, cycle_type)
    if overflow_only:
        # Overflow = indices 3+ in the config list
        key = "conserva_books_tailor" if cycle_type == "Tailor" else "conserva_books_smith"
        full_list = config.get(key, [])
        book_serials = [s for i, s in enumerate(full_list) if i >= 2 and s != 0]
    if not book_serials:
        AddToSystemJournal(f"Conserva Manager: No {cycle_type} books configured.")
        return 0

    inventories = load_all_inventories(book_serials)
    total_sets = 0

    scope = "OVERFLOW" if overflow_only else "ALL"
    AddToSystemJournal(f"=== CHECKING COMPLETABLE SETS ({cycle_type} — {scope}) ===")

    for serial in book_serials:
        inv = inventories.get(serial, [])
        if not inv:
            continue
        sets = find_completable_sets(inv)
        if sets:
            for s in sets:
                large = s['large']
                prize_id = get_prize_number(large['category'], large['material'],
                                           large['amount'], large['quality'])
                prize_label = prize_names.get(prize_id, f"#{prize_id}") if prize_id else "No prize"
                n_smalls = len(s['smalls'])
                AddToSystemJournal(
                    f"  Book {hex(serial)}: {large['category']} {large['material']} "
                    f"{large['quality']} x{large['amount']} -> {prize_label} ({1 + n_smalls} BODs)"
                )
            total_sets += len(sets)

    if total_sets == 0:
        AddToSystemJournal("  No completable sets found.")
    else:
        AddToSystemJournal(f"  TOTAL: {total_sets} set(s). Click 'Combine Set' to extract + combine one.")
    return total_sets


def extract_and_combine_next_set(config, cycle_type, overflow_only=False):
    """Finds the first completable set, extracts BODs, combines, routes to Consegna.
    Uses DLL packet injection when available; falls back to page-flip extraction otherwise.

    If overflow_only=True, only checks overflow books (index 3+).
    """
    from BodCycler_Assembler import combine_and_store
    import BodCycler_Crafting

    use_dll = _ensure_bridge()
    AddToSystemJournal(f"Combine Set: DLL={'yes' if use_dll else 'no'}, cycle={cycle_type}, overflow={overflow_only}")

    book_serials = _get_book_serials(config, cycle_type)
    AddToSystemJournal(f"Combine Set: {len(book_serials)} books configured")
    if overflow_only:
        key = "conserva_books_tailor" if cycle_type == "Tailor" else "conserva_books_smith"
        full_list = config.get(key, [])
        book_serials = [s for i, s in enumerate(full_list) if i >= 2 and s != 0]
        AddToSystemJournal(f"Combine Set: overflow filter -> {len(book_serials)} books")
    inventories = load_all_inventories(book_serials)
    AddToSystemJournal(f"Combine Set: loaded inventories for {len(inventories)} books")

    # Find first completable set
    target_set = None
    target_book = None
    for serial in book_serials:
        inv = inventories.get(serial, [])
        if not inv:
            continue
        sets = find_completable_sets(inv)
        if sets:
            target_set = sets[0]
            target_book = serial
            break

    if not target_set:
        AddToSystemJournal("No completable sets found.")
        return False

    large = target_set['large']
    smalls = target_set['smalls']
    prize_id = get_prize_number(large['category'], large['material'],
                                large['amount'], large['quality'])
    prize_label = prize_names.get(prize_id, f"#{prize_id}") if prize_id else "?"

    AddToSystemJournal(
        f"Set: {large['category']} {large['material']} "
        f"{large['quality']} x{large['amount']} -> {prize_label}"
    )
    AddToSystemJournal(f"  From {hex(target_book)}: 1 Large + {len(smalls)} Smalls")

    # Open the book now so it's visible in-game before extraction starts
    idx, gump_serial = _open_book_gump(target_book)
    if idx == -1:
        return False

    # Extract specific set BODs by position (descending so indices don't shift)
    all_set_bods = [large] + smalls
    positions = sorted([b['pos'] for b in all_set_bods], reverse=True)

    if use_dll:
        extracted = _dll_extract_batch(target_book, positions)
        # Drops are descending and stop at the first failure, so the BODs that
        # actually landed are the first len(extracted) of the requested positions.
        dropped_positions = positions[:len(extracted)]
        mode_label = "DLL"
    else:
        AddToSystemJournal("  DLL unavailable — using page-flip extraction (slower).")
        FindType(BOD_BOOK_TYPE, Backpack())
        if target_book not in set(GetFoundList()):
            AddToSystemJournal(f"  Moving {hex(target_book)} to backpack...")
            MoveItem(target_book, 1, Backpack(), 0, 0, 0)
            Wait(1200)
        extracted_map = extract_bods(target_book, list(all_set_bods))
        extracted = list(extracted_map.values())
        # extracted_map is keyed by the positions that actually dropped.
        dropped_positions = list(extracted_map.keys())
        mode_label = "page-flip"

    if not extracted:
        AddToSystemJournal("  Extraction failed.")
        return False

    AddToSystemJournal(f"  Extracted {len(extracted)} BODs via {mode_label}.")

    # Identify Large vs Smalls from extracted serials
    large_serial = None
    small_serials = []
    for bod_serial in extracted:
        info = BodCycler_Crafting.parse_bod(bod_serial, cycle_type)
        if not info:
            continue
        if info.get('is_large'):
            large_serial = bod_serial
        else:
            small_serials.append(bod_serial)

    if not large_serial:
        AddToSystemJournal("  ERROR: No Large BOD in extracted set.")
        return False

    AddToSystemJournal(f"  Large: {hex(large_serial)} | Smalls: {len(small_serials)}")

    # Combine and route to Consegna; leftover smalls go back to source book
    success = combine_and_store(large_serial, small_serials, config, source_book=target_book)

    if success:
        AddToSystemJournal("  Combined and routed to Consegna!")
        from BodCycler_Utils import read_stats, write_stats
        stats = read_stats()
        stats["prized_large"] = stats.get("prized_large", 0) + 1
        write_stats(stats)
    else:
        AddToSystemJournal("  FAILED to combine. Check backpack.")

    # Reindex source book JSON — remove only the positions that ACTUALLY dropped,
    # not every requested position. A partial extraction (e.g. serial stuck after
    # 2 of 4 drops) would otherwise delete entries still in the book and shift
    # every later pos/drop_btn out of sync with the live gump.
    inv_file = get_inventory_file(target_book)
    if os.path.exists(inv_file):
        try:
            with _INV_LOCK:
                with open(inv_file, "r") as f:
                    inventory = json.load(f)
                inventory = _reindex_inventory(inventory, dropped_positions)
                tmp = inv_file + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(inventory, f, indent=4)
                os.replace(tmp, inv_file)
            AddToSystemJournal(
                f"  JSON reindexed: removed {len(dropped_positions)}, "
                f"{len(inventory)} remaining in {hex(target_book)}"
            )
        except Exception as e:
            AddToSystemJournal(f"  WARNING: Reindex failed — {e}")

    # Check for more sets
    remaining = check_completable_sets(config, cycle_type)
    if remaining > 0:
        AddToSystemJournal(f"  {remaining} more set(s) available.")

    return success


def purge_set_from_book(config, book_serial, spec):
    """Drop every BOD matching `spec` out of `book_serial` into the backpack,
    one at a time, following the validated per-drop loop:
      check JSON -> pick highest matching pos -> inject 0xB1 -> verify tooltip
      -> reindex+save that single pos.
    Stops the instant a tooltip mismatches (the live book has diverged from the
    JSON) so it never injects off stale data.

    `spec` keys: category, material, quality, amount, type (any blank = wildcard).
    Dropped BODs are LEFT in the backpack — purge only removes them from the book.
    Returns a one-line status string.
    """
    if not book_serial:
        AddToSystemJournal("Purge Set: No book targeted.")
        return "Purge: no book"

    spec = {k: v for k, v in spec.items() if v not in (None, "")}
    if not spec:
        AddToSystemJournal("Purge Set: Empty filter — refusing to drop everything.")
        return "Purge: empty filter (refused)"

    inv_file = get_inventory_file(book_serial)
    if not os.path.exists(inv_file):
        AddToSystemJournal(f"Purge Set: No inventory for {hex(book_serial)} — run Scan first.")
        return "Purge: no inventory JSON"

    # Pre-flight: validate JSON + confirm there's something to drop before touching the game.
    with open(inv_file, "r") as f:
        inv = json.load(f)
    ok, problems = _check_inventory_consistent(inv)
    if not ok:
        AddToSystemJournal(f"Purge Set: JSON inconsistent — NOT dropping. {problems[:3]}")
        return "Purge: JSON inconsistent (rescan)"
    matches = [e for e in inv if _entry_matches_filter(e, spec)]
    if not matches:
        AddToSystemJournal(f"Purge Set: 0 entries match {spec} in {hex(book_serial)}.")
        return "Purge: 0 matches"
    AddToSystemJournal(
        f"Purge Set: {len(matches)} match {spec} in {hex(book_serial)} -> backpack"
    )

    if not _ensure_bridge():
        AddToSystemJournal("Purge Set: DLL bridge unavailable — aborting.")
        return "Purge: DLL unavailable"
    import BodCycler_PacketBridge as pb

    idx, _ = _open_book_gump(book_serial)
    if idx == -1:
        return "Purge: failed to open book"

    prev_serial = None
    dropped = 0
    # Drop highest pos first. A high drop never shifts a lower pos, so after each
    # reindex the next matching entry is still at its recorded pos.
    while True:
        if check_abort():
            AddToSystemJournal("Purge Set: aborted.")
            break

        # Re-read + re-check the JSON every iteration (check-before-every-drop).
        with open(inv_file, "r") as f:
            inv = json.load(f)
        ok, problems = _check_inventory_consistent(inv)
        if not ok:
            AddToSystemJournal(f"Purge Set: JSON drifted mid-run — stopping. {problems[:3]}")
            break
        targets = sorted(
            [e for e in inv if _entry_matches_filter(e, spec)],
            key=lambda e: e["pos"], reverse=True,
        )
        if not targets:
            break
        entry = targets[0]
        pos = entry["pos"]
        btn = 5 + pos * 2

        # Current gump serial — re-read before EVERY inject (it changes per drop);
        # wait for it to advance after the previous drop.
        cur_serial = 0
        for i in range(GetGumpsCount()):
            if GetGumpID(i) == BOOK_GUMP_ID:
                cur_serial = GetGumpInfo(i).get("Serial", 0)
                break
        if not cur_serial:
            AddToSystemJournal("Purge Set: book gump closed — stopping.")
            break
        if prev_serial is not None and cur_serial == prev_serial:
            _, cur_serial, changed = wait_for_gump_serial_change(prev_serial, BOOK_GUMP_ID, 3000)
            if not changed:
                AddToSystemJournal(f"Purge Set: gump serial stuck after {dropped} drops — stopping.")
                break

        FindType(BOD_TYPE, Backpack())
        before = set(GetFoundList())
        result = pb.send_gump_response(cur_serial, BOOK_GUMP_ID, btn)
        Wait(1500)
        prev_serial = cur_serial
        if result <= 0:
            AddToSystemJournal(f"Purge Set: inject failed at pos {pos} (result={result}) — stopping.")
            break

        FindType(BOD_TYPE, Backpack())
        new_bods = set(GetFoundList()) - before
        if not new_bods:
            AddToSystemJournal(f"Purge Set: no BOD appeared after pos {pos} — stopping.")
            break

        s_drop = next(iter(new_bods))
        tip = GetTooltip(s_drop) or ""
        checks, verified = _verify_dropped_tooltip(tip, entry)
        if not verified:
            AddToSystemJournal(
                f"Purge Set: tooltip MISMATCH at pos {pos} (checks={checks}) — "
                f"JSON left intact, stopping (live book diverged)."
            )
            break

        # Verified — reindex that single pos and persist atomically.
        with _INV_LOCK:
            with open(inv_file, "r") as f:
                inv = json.load(f)
            inv = _reindex_inventory(inv, [pos])
            tmp = inv_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(inv, f, indent=4)
            os.replace(tmp, inv_file)
        dropped += 1
        AddToSystemJournal(
            f"Purge Set: dropped {entry['type']} {entry['material']} {entry['item']} "
            f"(pos {pos}) -> {hex(s_drop)}; {len(inv)} left in book."
        )

    close_all_gumps()
    final = count_matching_in_book(book_serial, spec)
    status = f"Purge done: {dropped} dropped, {final['matched']} still match"
    AddToSystemJournal(f"Purge Set: {status}")
    return status


# ---------------------------------------------------------------------------
# Fast Drop via DLL Injection (bypasses page flipping)
# ---------------------------------------------------------------------------

def fast_drop_bods(book_serial, positions):
    """Drops BODs from a book using raw 0xB1 packets via the injected DLL.
    Book must already be open (UseObject called). Re-reads the current gump
    serial before each drop (it changes after every drop), and presses the
    global drop button btn = 5 + pos*2 for each position. Page is irrelevant —
    the server honors the global index regardless of the displayed page.
    Returns number of successful drops.
    """
    try:
        import BodCycler_PacketBridge as pb
        if not pb.is_connected():
            if not pb.connect():
                AddToSystemJournal("PacketBridge: Not connected. Is DLL injected?")
                return 0

        st = pb.status()
        if not st.get("captured"):
            AddToSystemJournal("PacketBridge: Socket not captured yet. Send any action in Stealth first.")
            return 0
    except ImportError:
        AddToSystemJournal("PacketBridge: Module not found. DLL injection not available.")
        return 0

    # Read initial gump serial
    gump_serial = 0
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == BOOK_GUMP_ID:
            gump_serial = GetGumpInfo(i).get("Serial", 0)
            break
    if not gump_serial:
        AddToSystemJournal("FastDrop: No book gump open.")
        return 0

    AddToSystemJournal(
        f"FastDrop: book={hex(book_serial)} gumpID={hex(BOOK_GUMP_ID)} "
        f"initial_serial={gump_serial}"
    )

    current_serial = gump_serial
    dropped = 0
    for pos in positions:
        if check_abort():
            break

        if dropped > 0:
            _, current_serial, changed = wait_for_gump_serial_change(
                current_serial, BOOK_GUMP_ID, 3000
            )
            if not changed:
                AddToSystemJournal(f"FastDrop: gump serial stuck after {dropped} drops.")
                break

        btn = 5 + (pos * 2)
        result = pb.send_gump_response(current_serial, BOOK_GUMP_ID, btn)
        if result > 0:
            dropped += 1
        else:
            AddToSystemJournal(f"FastDrop: inject failed at pos {pos} (result={result})")
            break

    AddToSystemJournal(f"FastDrop: {dropped}/{len(positions)} BODs dropped.")
    return dropped
