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
    is_prize_enabled, _INV_LOCK, world_save_guard
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
    """Returns the overflow book serial (index 2)."""
    key = "conserva_books_tailor" if cycle_type == "Tailor" else "conserva_books_smith"
    full_list = config.get(key, [])
    if len(full_list) >= 3 and full_list[2] != 0:
        return full_list[2]
    return 0


def _ensure_bridge():
    """Connects to the DLL packet bridge and sets the game socket handle.
    Reuses cached handle from previous successful probe; only force-probes
    on first call or after a failed injection.
    """
    try:
        import BodCycler_PacketBridge as pb
        if not pb.is_connected():
            if not pb.connect():
                AddToSystemJournal("PacketBridge: Cannot connect. Is DLL injected? (python inject_dll.py)")
                return False
        st = pb.status()
        AddToSystemJournal(f"PacketBridge pre-probe status: captured={st.get('captured')} socket={st.get('socket')}")
        h = pb.set_socket_by_probe()  # reuses cached handle if available
        if not h:
            AddToSystemJournal("PacketBridge: Socket probe failed. Is Stealth connected to the server?")
            return False
        AddToSystemJournal(f"PacketBridge: Using socket handle {h}")
        return True
    except ImportError:
        AddToSystemJournal("PacketBridge: Module not found.")
        return False


def _dll_extract_batch(book_serial, positions):
    """Extracts BODs from a book using DLL packet injection.
    Book must be in backpack. Opens it, injects 0xB1 per position (descending),
    waits for serial refresh between each drop.
    Returns list of extracted BOD serials in backpack.
    """
    import BodCycler_PacketBridge as pb

    # Book must be directly in backpack for UseObject to open the gump reliably.
    # If it's in a crate or closed container, move it first.
    FindType(BOD_BOOK_TYPE, Backpack())
    if book_serial not in set(GetFoundList()):
        AddToSystemJournal(f"  Moving {hex(book_serial)} to backpack for extraction...")
        MoveItem(book_serial, 1, Backpack(), 0, 0, 0)
        Wait(1200)

    close_all_gumps()
    UseObject(book_serial)
    Wait(2000)

    idx = -1
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == BOOK_GUMP_ID:
            idx = i
            break
    if idx == -1:
        AddToSystemJournal(f"  Failed to open book {hex(book_serial)}")
        return []

    FindType(BOD_TYPE, Backpack())
    bp_before = set(GetFoundList())

    dropped = 0
    for pos in positions:
        if check_abort():
            break

        # Wait for gump to be present (serial stays constant — it's the book serial)
        serial = 0
        timeout = time.time() + 3
        while time.time() < timeout:
            if check_abort():
                break
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == BOOK_GUMP_ID:
                    serial = GetGumpInfo(i)["Serial"]
                    break
            if serial:
                break
            Wait(100)

        if not serial:
            AddToSystemJournal(f"  Gump lost after {dropped} drops.")
            break

        btn = 5 + (pos * 2)
        result = pb.send_gump_response(serial, BOOK_GUMP_ID, btn)
        if result > 0:
            dropped += 1
            Wait(300)  # let server process the drop before next inject
        else:
            AddToSystemJournal(f"  Inject failed at pos {pos}")
            break

    Wait(500)
    close_all_gumps()

    FindType(BOD_TYPE, Backpack())
    bp_after = set(GetFoundList())
    new_bods = list(bp_after - bp_before)

    AddToSystemJournal(f"  Extracted {len(new_bods)} BODs from {hex(book_serial)}")
    return new_bods


def _numgump_extract_batch(book_serial, max_drops):
    """Fallback extractor using NumGumpButton(idx, 5) per drop.
    Slower than the DLL path (one gump-open per BOD) but works without the injector.
    Mirrors the proven pattern from BodCycler_Crafting.extract_bod_from_origine.
    """
    # Ensure book is in backpack before any UseObject call.
    FindType(BOD_BOOK_TYPE, Backpack())
    if book_serial not in set(GetFoundList()):
        AddToSystemJournal(f"  Moving {hex(book_serial)} to backpack for extraction...")
        MoveItem(book_serial, 1, Backpack(), 0, 0, 0)
        Wait(1200)

    FindType(BOD_TYPE, Backpack())
    bp_before = set(GetFoundList())

    dropped = 0
    for _ in range(max_drops):
        if check_abort():
            break

        close_all_gumps()
        UseObject(book_serial)

        idx = -1
        deadline = time.time() + 3
        while time.time() < deadline:
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == BOOK_GUMP_ID:
                    idx = i
                    break
            if idx != -1:
                break
            Wait(100)
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


def move_all_bods(config, source_book, dest_book):
    """Extracts all BODs from source_book and routes them to dest_book.
    Uses DLL packet injection when available; falls back to NumGumpButton otherwise.
    Returns a status string describing the outcome.
    """
    total = _get_book_bod_count(source_book)
    if total == 0:
        AddToSystemJournal(f"Move BODs: Source book {hex(source_book)} is empty.")
        return f"Move BODs: source empty ({hex(source_book)})"

    # DLL preferred (batch ~60 per open); NumGumpButton fallback (1 per open).
    if _ensure_bridge():
        extract_fn = lambda book, batch: _dll_extract_batch(book, [0] * batch)
        mode = "DLL"
    else:
        AddToSystemJournal("Move BODs: DLL bridge unavailable — using NumGumpButton fallback (slower).")
        extract_fn = _numgump_extract_batch
        mode = "NumGumpButton"

    AddToSystemJournal(f"Move BODs [{mode}]: {total} BODs from {hex(source_book)} -> {hex(dest_book)}")
    moved = 0
    aborted_reason = None

    while True:
        if check_abort():
            aborted_reason = "aborted"
            break

        remaining = _get_book_bod_count(source_book)
        if remaining == 0:
            break

        batch_size = min(_get_batch_size(), remaining)
        if batch_size <= 0:
            AddToSystemJournal("  Backpack full.")
            aborted_reason = "backpack full"
            break

        extracted = extract_fn(source_book, batch_size)
        if not extracted:
            AddToSystemJournal("  Extraction failed.")
            aborted_reason = "extraction failed"
            break

        routed = _route_bods_to_book(extracted, dest_book)
        moved += routed

    AddToSystemJournal(f"Move BODs complete: {moved}/{total} moved.")
    if aborted_reason:
        return f"Move BODs [{mode}]: {moved}/{total} moved ({aborted_reason})"
    return f"Move BODs [{mode}]: {moved}/{total} moved"


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

    # Tier membership from CONFIG slot positions (not filtered array indices)
    config_key = "conserva_books_tailor" if cycle_type == "Tailor" else "conserva_books_smith"
    config_list = config.get(config_key, [0]*3)
    tier1_book = config_list[0] if len(config_list) > 0 and config_list[0] != 0 else None
    tier2_books = [s for i, s in enumerate(config_list) if i == 1 and s != 0]
    overflow_config_books = set(s for i, s in enumerate(config_list) if i >= 2 and s != 0)
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
        AddToSystemJournal(f"  TOTAL: {total_sets} set(s). Click 'Next Set' to extract + combine one.")
    return total_sets


def extract_and_combine_next_set(config, cycle_type, overflow_only=False):
    """Finds the first completable set, extracts BODs, combines, routes to Consegna.
    Uses DLL packet injection when available; falls back to page-flip extraction otherwise.

    If overflow_only=True, only checks overflow books (index 3+).
    """
    from BodCycler_Assembler import combine_and_store
    import BodCycler_Crafting

    use_dll = _ensure_bridge()

    book_serials = _get_book_serials(config, cycle_type)
    if overflow_only:
        key = "conserva_books_tailor" if cycle_type == "Tailor" else "conserva_books_smith"
        full_list = config.get(key, [])
        book_serials = [s for i, s in enumerate(full_list) if i >= 2 and s != 0]
    inventories = load_all_inventories(book_serials)

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

    # Extract specific set BODs by position (descending so indices don't shift)
    all_set_bods = [large] + smalls
    positions = sorted([b['pos'] for b in all_set_bods], reverse=True)

    if use_dll:
        extracted = _dll_extract_batch(target_book, positions)
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

    # Combine and route to Consegna
    success = combine_and_store(large_serial, small_serials, config)

    if success:
        AddToSystemJournal("  Combined and routed to Consegna!")
        from BodCycler_Utils import read_stats, write_stats
        stats = read_stats()
        stats["prized_large"] = stats.get("prized_large", 0) + 1
        write_stats(stats)
    else:
        AddToSystemJournal("  FAILED to combine. Check backpack.")

    # Reindex source book JSON
    extracted_positions = set(positions)
    inv_file = get_inventory_file(target_book)
    if os.path.exists(inv_file):
        try:
            with _INV_LOCK:
                with open(inv_file, "r") as f:
                    inventory = json.load(f)
                inventory = [b for b in inventory if b.get("pos") not in extracted_positions]
                for new_pos, entry in enumerate(inventory):
                    entry["pos"] = new_pos
                    entry["drop_btn"] = 5 + (new_pos * 2)
                    entry["page"] = new_pos // 5
                tmp = inv_file + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(inventory, f, indent=4)
                os.replace(tmp, inv_file)
            AddToSystemJournal(f"  JSON reindexed: {len(inventory)} remaining in {hex(target_book)}")
        except Exception as e:
            AddToSystemJournal(f"  WARNING: Reindex failed — {e}")

    # Check for more sets
    remaining = check_completable_sets(config, cycle_type)
    if remaining > 0:
        AddToSystemJournal(f"  {remaining} more set(s) available.")

    return success


# ---------------------------------------------------------------------------
# Fast Drop via DLL Injection (bypasses page flipping)
# ---------------------------------------------------------------------------

def fast_drop_bods(book_serial, positions, pause_ms=300):
    """Drops BODs from a book using raw 0xB1 packets via the injected DLL.
    Book must be open (UseObject already called). Reads gump serial once
    (stable on this shard) and loops btn=5 with a fixed pause between drops.
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

    # Read gump serial once — stable across drops on this shard
    gump_serial = 0
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == BOOK_GUMP_ID:
            gump_serial = GetGumpInfo(i).get("Serial", 0)
            break
    if not gump_serial:
        AddToSystemJournal("FastDrop: No book gump open.")
        return 0

    dropped = 0
    for pos in positions:
        if check_abort():
            break
        btn = 5 + (pos * 2)
        result = pb.send_gump_response(gump_serial, BOOK_GUMP_ID, btn)
        if result > 0:
            dropped += 1
            Wait(pause_ms)
        else:
            AddToSystemJournal(f"FastDrop: inject failed at pos {pos} (result={result})")
            break

    AddToSystemJournal(f"FastDrop: {dropped}/{len(positions)} BODs dropped.")
    return dropped


# ---------------------------------------------------------------------------
# Phase C — Execute Reorganization (game interaction)
# ---------------------------------------------------------------------------

MAX_BATCH = 20  # Extract at most this many BODs before routing them (backpack safety)


def _extract_from_book(book_serial, target_bods, crate_serial):
    """Pulls a book from crate, extracts target BODs via reverse sweep, returns book.
    target_bods are already sorted descending by pos (extract_bods does this too).
    Returns dict mapping original pos -> extracted serial in backpack.
    """
    world_save_guard()
    MoveItem(book_serial, 1, Backpack(), 0, 0, 0)
    Wait(1200)

    inv_file = get_inventory_file(book_serial)
    inventory = []
    if os.path.exists(inv_file):
        try:
            with open(inv_file, "r") as f:
                inventory = json.load(f)
        except Exception:
            pass

    extracted = extract_bods(book_serial, target_bods, inventory)

    world_save_guard()
    MoveItem(book_serial, 1, crate_serial, 0, 0, 0)
    Wait(1200)

    return extracted


def _route_extracted(extracted_map, actions, consegna, scartare, crate):
    """Routes extracted BODs to their destinations. Works through actions one by one.
    For 'move' actions, batches inserts per destination book.
    """
    dest_batches = defaultdict(lambda: ([], []))

    for action_type, bod, dest in actions:
        orig_pos = bod.get("pos")
        extracted_serial = extracted_map.get(orig_pos)
        if not extracted_serial:
            continue

        if action_type == "move":
            dest_batches[dest][0].append(extracted_serial)
            dest_batches[dest][1].append(bod)
        elif action_type == "consegna" and consegna:
            world_save_guard()
            MoveItem(extracted_serial, 0, consegna, 0, 0, 0)
            Wait(800)
        elif action_type == "scartare" and scartare:
            world_save_guard()
            MoveItem(extracted_serial, 0, scartare, 0, 0, 0)
            Wait(800)

    # Insert moves into destination books (pull book, insert, return)
    for dest_book, (serials, data_list) in dest_batches.items():
        if not serials or check_abort():
            continue
        AddToSystemJournal(f"Inserting {len(serials)} BODs into {hex(dest_book)}...")
        world_save_guard()
        MoveItem(dest_book, 1, Backpack(), 0, 0, 0)
        Wait(1200)

        for bod_serial, bod_data in zip(serials, data_list):
            if check_abort():
                break
            world_save_guard()
            MoveItem(bod_serial, 0, dest_book, 0, 0, 0)
            Wait(1000)
            clean = {
                "type": bod_data["type"],
                "item": bod_data["item"],
                "quality": bod_data["quality"],
                "material": bod_data["material"],
                "amount": bod_data["amount"],
                "category": bod_data.get("category", "Small Bods"),
            }
            if bod_data["type"] == "Large":
                clean["prize_id"] = bod_data.get("prize_id")
            append_to_inventory(clean, dest_book)

        world_save_guard()
        MoveItem(dest_book, 1, crate, 0, 0, 0)
        Wait(1200)


def run_smart_trim(config, cycle_type):
    """Main entry: analyze, then execute in small batches to respect backpack limits."""
    crate = config.get("containers", {}).get("ConservaCrate", 0)
    book_serials = _get_book_serials(config, cycle_type)
    tier1 = config.get("conserva_manager", {}).get("keep_tier1", 4)
    tier2 = config.get("conserva_manager", {}).get("keep_tier2", 6)
    overflow_dest = _get_overflow_dest(config, cycle_type)

    if not crate or not book_serials:
        AddToSystemJournal("Conserva Manager: Missing crate or book configuration.")
        return

    inventories = load_all_inventories(book_serials)
    plan = analyze_and_plan(inventories, book_serials, config, tier1, tier2, cycle_type)

    for line in plan["summary"]:
        AddToSystemJournal(line)

    # Group all actions by source book
    actions_by_book = defaultdict(list)
    for bod, from_book, to_book in plan["moves"]:
        if from_book != to_book:
            actions_by_book[from_book].append(("move", bod, to_book))
    for bod, from_book in plan.get("to_overflow", []):
        if overflow_dest and from_book != overflow_dest:
            actions_by_book[from_book].append(("move", bod, overflow_dest))

    total_processed = 0

    for source_book, actions in actions_by_book.items():
        if check_abort():
            break

        # Process in batches of MAX_BATCH to keep backpack under control
        for batch_start in range(0, len(actions), MAX_BATCH):
            if check_abort():
                break

            batch = actions[batch_start:batch_start + MAX_BATCH]
            target_bods = [a[1] for a in batch]

            AddToSystemJournal(
                f"Batch {batch_start // MAX_BATCH + 1}: "
                f"extracting {len(target_bods)} from {hex(source_book)}..."
            )

            # Extract (reverse sweep — descending pos, handled by extract_bods)
            extracted_map = _extract_from_book(source_book, target_bods, crate)

            # Route extracted BODs before next batch
            _route_extracted(extracted_map, batch, consegna, scartare, crate)
            total_processed += len(extracted_map)

    AddToSystemJournal(f"=== TRIM COMPLETE: {total_processed} BODs processed ===")


# ---------------------------------------------------------------------------
# Diagnostic — test if GetGumpInfo returns all pages at once
# ---------------------------------------------------------------------------

def test_gump_pages(config, cycle_type):
    """Tests NumGumpTextEntry + NumGumpButton to drop a BOD by index."""
    crate = config.get("containers", {}).get("ConservaCrate", 0)
    book_serials = _get_book_serials(config, cycle_type)
    if not book_serials:
        AddToSystemJournal("Test: No books configured.")
        return
    serial = book_serials[0]

    AddToSystemJournal(f"=== TEXT ENTRY DROP TEST: {hex(serial)} ===")

    # Pull book from crate
    if crate:
        MoveItem(serial, 1, Backpack(), 0, 0, 0)
        Wait(1200)

    close_all_gumps()
    UseObject(serial)
    Wait(2000)

    idx = -1
    for i in range(GetGumpsCount()):
        if GetGumpID(i) == BOOK_GUMP_ID:
            idx = i
            break
    if idx == -1:
        AddToSystemJournal("Test: Failed to open book gump.")
        if crate:
            MoveItem(serial, 1, crate, 0, 0, 0)
        return

    g = GetGumpInfo(idx)

    # Dump ALL gump element types and counts
    for key in g:
        val = g[key]
        if isinstance(val, list):
            AddToSystemJournal(f"  {key}: {len(val)} entries")
        else:
            AddToSystemJournal(f"  {key}: {val}")

    # Dump TextEntries (input fields)
    text_entries = g.get('TextEntries', [])
    AddToSystemJournal(f"  TextEntries detail:")
    for te in text_entries:
        AddToSystemJournal(f"    {te}")

    # Dump ALL buttons (not just >= 5)
    all_btns = g.get('GumpButtons', [])
    AddToSystemJournal(f"  All buttons:")
    for b in all_btns:
        AddToSystemJournal(f"    RetVal={b.get('ReturnValue')} Page={b.get('Page')} PageID={b.get('PageID')} X={b.get('X')} Y={b.get('Y')}")

    # Now try: enter a position in text entry and press a button
    # Use LAST position (safest — descending extraction principle)
    FindType(BOD_TYPE, Backpack())
    bp_before = list(GetFoundList())

    # Target last item in the book — use a high index
    test_pos = "398"  # 0-indexed last item in a 399-BOD book
    AddToSystemJournal(f"  Trying: NumGumpTextEntry({idx}, 3, '{test_pos}') + NumGumpButton({idx}, 50)")

    NumGumpTextEntry(idx, 3, test_pos)
    Wait(300)
    NumGumpButton(idx, 50)
    Wait(2000)

    FindType(BOD_TYPE, Backpack())
    bp_after = list(GetFoundList())
    new_in_bp = [b for b in bp_after if b not in bp_before]

    if new_in_bp:
        AddToSystemJournal(f"  SUCCESS! BOD extracted: {hex(new_in_bp[0])}")
        # Put it back
        MoveItem(new_in_bp[0], 0, serial, 0, 0, 0)
        Wait(1000)
        AddToSystemJournal(f"  Returned BOD to book.")
    else:
        AddToSystemJournal(f"  No BOD dropped. Trying alternative button IDs...")
        # Try a few other button values
        for try_btn in [1, 2, 4, 0]:
            close_all_gumps()
            Wait(500)
            UseObject(serial)
            Wait(2000)
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == BOOK_GUMP_ID:
                    idx = i
                    break

            NumGumpTextEntry(idx, 3, test_pos)
            Wait(300)
            NumGumpButton(idx, try_btn)
            Wait(2000)

            FindType(BOD_TYPE, Backpack())
            bp_after2 = list(GetFoundList())
            new2 = [b for b in bp_after2 if b not in bp_before]
            if new2:
                AddToSystemJournal(f"  SUCCESS with button {try_btn}! BOD: {hex(new2[0])}")
                MoveItem(new2[0], 0, serial, 0, 0, 0)
                Wait(1000)
                break
            else:
                AddToSystemJournal(f"  Button {try_btn}: no drop")

    # Cleanup
    close_all_gumps()
    if crate:
        MoveItem(serial, 1, crate, 0, 0, 0)
        Wait(1000)

    AddToSystemJournal("=== TEXT ENTRY DROP TEST COMPLETE ===")
