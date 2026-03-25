# BodCycler_ConservaManager.py
# Multi-book Conserva management: scan, analyze, rebalance, and trim.

from stealth import *
import json
import os
import time
from collections import defaultdict

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

from BodCycler_Utils import (
    BOD_BOOK_TYPE, BOD_TYPE, BOOK_GUMP_ID,
    get_inventory_file, load_config, check_abort, close_all_gumps,
    is_prize_enabled, _INV_LOCK
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


def analyze_and_plan(inventories, book_serials, config, tier1_limit=10, tier2_limit=20, cycle_type="Tailor"):
    """
    Cross-references all books. Produces a tier-based reorganization plan.

    Three tiers — no Consegna/Scartare:
      - Tier 1 (Best, book[0]): max tier1_limit per item per set, wanted prizes only
      - Tier 2 (books[1:3]):    max tier2_limit per item per set, wanted prizes only
      - Overflow (books[3:]):   everything else (unwanted prizes + excess beyond tiers)

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
    tier2_books = book_serials[1:3] if len(book_serials) >= 2 else []
    overflow_books = book_serials[3:] if len(book_serials) >= 4 else []

    summary = []
    moves = []          # (bod, from_book, to_book)
    to_overflow = []    # (bod, from_book) — goes to overflow books

    def _take(bods, count, dest_book):
        """Takes `count` BODs, moves to dest_book if not already there. Returns (taken, remaining)."""
        taken, remaining = bods[:count], bods[count:]
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
    """Analyze + generate RE drops. Mode controls what goes into the drop queue:
      'all'      — moves + excess (everything)
      'overflow' — only unwanted-prize moves to overflow books
      'excess'   — only excess Smalls→Consegna + Larges→Scartare
    """
    book_serials = _get_book_serials(config, cycle_type)
    if not book_serials:
        AddToSystemJournal(f"Conserva Manager: No {cycle_type} books configured.")
        return

    inventories = load_all_inventories(book_serials)
    total_bods = sum(len(inv) for inv in inventories.values())
    tier1 = config.get("conserva_manager", {}).get("keep_tier1", 10)
    tier2 = config.get("conserva_manager", {}).get("keep_tier2", 20)

    AddToSystemJournal(f"=== CONSERVA ANALYZE: {len(book_serials)} {cycle_type} books ({total_bods} BODs) ===")

    plan = analyze_and_plan(inventories, book_serials, config, tier1, tier2, cycle_type)
    for line in plan["summary"]:
        AddToSystemJournal(line)

    # Filter plan by mode before building drop queue
    filtered_plan = dict(plan)
    if mode == "overflow":
        # Only overflow moves (unwanted prizes + excess beyond tiers)
        filtered_plan["moves"] = []  # no tier rebalancing
        AddToSystemJournal(f"  Mode: OVERFLOW ONLY — {len(filtered_plan['to_overflow'])} BODs to move")
    elif mode == "all":
        AddToSystemJournal(f"  Mode: ALL — {len(filtered_plan['moves'])} tier moves + {len(filtered_plan['to_overflow'])} overflow")

    queue = _build_drop_queue(filtered_plan, config)
    _save_drop_queue(queue, cycle_type)
    if queue:
        write_re_template_and_queue(config, cycle_type)

    AddToSystemJournal("=== ANALYZE COMPLETE (no changes made) ===")
    return plan


# ---------------------------------------------------------------------------
# RE Template System
# ---------------------------------------------------------------------------

RE_TEMPLATE_PATH = None  # set lazily on first use
BATCH_SIZE = 50          # max drops per RE run (backpack safety)


def _get_re_template_path():
    """Fixed path for the RE template script that CTRL+K triggers."""
    return f"{StealthPath()}Scripts\\conserva_drop_template.py"


def _build_drop_queue(plan, config):
    """Builds the full ordered drop queue from a plan.
    Returns list of dicts: [{book_serial, pos, drop_btn, dest_serial, dest_type, bod_info}]
    Grouped by source book, each group sorted descending by pos.
    """
    # Get overflow book serials from config (books at index 3+)
    key = "conserva_books_tailor"  # default
    for k in ("conserva_books_tailor", "conserva_books_smith"):
        if config.get(k):
            full_list = config.get(k, [])
            overflow_serials = [s for i, s in enumerate(full_list) if i >= 3 and s != 0]
            if overflow_serials:
                break
    else:
        overflow_serials = []
    overflow_dest = overflow_serials[0] if overflow_serials else 0

    by_book = defaultdict(list)

    # Tier rebalance moves (between Best/Tier2 books)
    for bod, from_book, to_book in plan.get("moves", []):
        if from_book != to_book:
            by_book[from_book].append({
                "pos": bod["pos"], "dest": to_book, "dest_type": "book",
                "bod": {"type": bod["type"], "item": bod["item"],
                        "material": bod["material"], "quality": bod["quality"],
                        "amount": bod["amount"], "category": bod.get("category", "")},
            })

    # Overflow moves (unwanted prizes + excess beyond tiers → overflow book)
    for bod, from_book in plan.get("to_overflow", []):
        if overflow_dest and from_book != overflow_dest:
            by_book[from_book].append({
                "pos": bod["pos"], "dest": overflow_dest, "dest_type": "book",
                "bod": {"type": bod["type"], "item": bod["item"],
                        "material": bod["material"], "quality": bod["quality"],
                        "amount": bod["amount"], "category": bod.get("category", "")},
            })

    # Flatten: process books in config order, each sorted descending
    queue = []
    for book_serial in by_book:
        entries = by_book[book_serial]
        entries.sort(key=lambda e: e["pos"], reverse=True)
        for e in entries:
            e["book_serial"] = book_serial
            e["drop_btn"] = 5 + (e["pos"] * 2)
            queue.append(e)

    return queue


def _save_drop_queue(queue, cycle_type):
    """Saves the full drop queue to a JSON file for batch consumption."""
    queue_file = f"{StealthPath()}Scripts\\{CharName()}_conserva_queue_{cycle_type.lower()}.json"
    try:
        with open(queue_file, "w") as f:
            json.dump(queue, f, indent=2)
        AddToSystemJournal(f"Drop queue saved: {len(queue)} total drops -> {queue_file}")
    except Exception as e:
        AddToSystemJournal(f"Failed to save drop queue: {e}")


def _load_drop_queue(cycle_type):
    """Loads the drop queue from disk."""
    queue_file = f"{StealthPath()}Scripts\\{CharName()}_conserva_queue_{cycle_type.lower()}.json"
    if not os.path.exists(queue_file):
        return []
    try:
        with open(queue_file, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _get_active_batch_path(cycle_type):
    """Path to the current batch routing info (what was dropped and where it goes)."""
    return f"{StealthPath()}Scripts\\{CharName()}_conserva_batch_{cycle_type.lower()}.json"


def _get_re_drops_path():
    """JSON file that the RE template reads all drop buttons from."""
    return f"{StealthPath()}Scripts\\conserva_drops.json"


def write_re_template_and_queue(config, cycle_type):
    """Writes the static RE template + the drops JSON it reads from.
    The RE script reads conserva_drops.json, processes up to 50 at a time,
    then shows a message to press the Stealth route button.
    Returns total drops queued, or 0 if empty.
    """
    queue = _load_drop_queue(cycle_type)
    if not queue:
        AddToSystemJournal("Conserva Manager: Drop queue is empty. Run Analyze first.")
        return 0

    # Group by source book, each sorted descending
    books_order = []
    by_book = defaultdict(list)
    for entry in queue:
        bs = entry["book_serial"]
        if bs not in by_book:
            books_order.append(bs)
        by_book[bs].append(entry)

    # Build the drops JSON: list of {book, drops: [btn, btn, ...], batch_size}
    drops_data = []
    for bs in books_order:
        entries = by_book[bs]
        entries.sort(key=lambda e: e["pos"], reverse=True)
        drop_btns = [e["drop_btn"] for e in entries]
        drops_data.append({
            "book": bs,
            "book_hex": hex(bs),
            "drops": drop_btns,
        })

    # Write the drops JSON
    drops_path = _get_re_drops_path()
    try:
        with open(drops_path, "w") as f:
            json.dump(drops_data, f, indent=2)
    except Exception as e:
        AddToSystemJournal(f"Failed to write drops JSON: {e}")
        return 0

    # Save full batch routing info (for route_dropped_bods to use)
    batch_path = _get_active_batch_path(cycle_type)
    try:
        with open(batch_path, "w") as f:
            json.dump(queue, f, indent=2)
    except Exception:
        pass

    # Write the static RE template (reads from conserva_drops.json)
    template_path = _get_re_template_path()
    # RE uses IronPython — json module available, os.path for file reading
    lines = [
        "# ConservaManager RE Drop Template",
        "# Reads conserva_drops.json, processes 50 drops per book at a time.",
        "# After each batch: route in Stealth, then press CTRL+K again.",
        "",
        "import json",
        "import os",
        "",
        f"GUMP_ID = {hex(BOOK_GUMP_ID)}",
        "PAUSE = 100",
        "BATCH = 50",
        "",
        "# Read drops file",
        f"drops_file = os.path.join(r'{StealthPath()}Scripts', 'conserva_drops.json')",
        "if not os.path.exists(drops_file):",
        "    Misc.SendMessage('No conserva_drops.json found. Run Analyze in Stealth first.')",
        "else:",
        "    with open(drops_file, 'r') as f:",
        "        all_books = json.load(f)",
        "",
        "    if not all_books:",
        "        Misc.SendMessage('All drops complete!')",
        "    else:",
        "        book_data = all_books[0]",
        "        book_serial = book_data['book']",
        "        all_drops = book_data['drops']",
        "        batch = all_drops[:BATCH]",
        "        remaining = all_drops[BATCH:]",
        "",
        "        Misc.SendMessage('Opening book {} — dropping {}/{} BODs'.format(",
        "            book_data['book_hex'], len(batch), len(all_drops)))",
        "",
        "        Items.UseItem(book_serial)",
        "        Misc.Pause(2000)",
        "",
        "        dropped = 0",
        "        for btn in batch:",
        "            Gumps.WaitForGump(GUMP_ID, 10000)",
        "            Gumps.SendAction(GUMP_ID, btn)",
        "            Misc.Pause(PAUSE)",
        "            dropped += 1",
        "",
        "        # Update the drops file: remove processed batch",
        "        if remaining:",
        "            all_books[0]['drops'] = remaining",
        "        else:",
        "            all_books.pop(0)",
        "",
        "        with open(drops_file, 'w') as f:",
        "            json.dump(all_books, f, indent=2)",
        "",
        "        Misc.SendMessage('Dropped {}. Route in Stealth, then CTRL+K for next batch.'.format(dropped))",
        "        if not remaining and all_books:",
        "            Misc.SendMessage('Next book: {}'.format(all_books[0]['book_hex']))",
        "        elif not all_books:",
        "            Misc.SendMessage('All books done! Scan All in Stealth to rebuild.')",
    ]

    try:
        with open(template_path, "w") as f:
            f.write("\n".join(lines))
    except Exception as e:
        AddToSystemJournal(f"Failed to write RE template: {e}")
        return 0

    total = sum(len(d["drops"]) for d in drops_data)
    AddToSystemJournal(f"RE template + drops.json ready: {total} total drops across {len(drops_data)} books")
    AddToSystemJournal(f"  -> Press CTRL+K in RE to start (50 at a time)")
    return total


def route_dropped_bods(config, cycle_type):
    """Called after user presses CTRL+K and RE finishes a batch.
    Routes loose BODs from backpack to their planned destinations,
    then prompts for next CTRL+K.
    """
    # Load the full batch plan
    batch_path = _get_active_batch_path(cycle_type)
    plan_entries = []
    if os.path.exists(batch_path):
        try:
            with open(batch_path, "r") as f:
                plan_entries = json.load(f)
        except Exception:
            pass

    # Find all loose BODs in backpack
    FindType(BOD_TYPE, Backpack())
    loose_bods = list(GetFoundList())

    if not loose_bods:
        AddToSystemJournal("No loose BODs in backpack to route.")
        return

    AddToSystemJournal(f"Routing {len(loose_bods)} BODs from backpack...")

    # Build destination counts from the plan (all destinations are books)
    dest_groups = defaultdict(lambda: {"serial": 0, "count": 0})
    for entry in plan_entries:
        dt = entry["dest_type"]
        dest = entry["dest"]
        dest_groups[(dt, dest)]["serial"] = dest
        dest_groups[(dt, dest)]["count"] += 1

    routed = 0
    for (dest_type, _), info in sorted(dest_groups.items()):
        dest_serial = info["serial"]
        if not dest_serial or not loose_bods:
            continue
        if check_abort():
            break

        # Route up to the planned count (or whatever's left in backpack)
        to_route = min(info["count"], len(loose_bods))
        for _ in range(to_route):
            if not loose_bods or check_abort():
                break
            bod = loose_bods.pop(0)
            world_save_guard()
            MoveItem(bod, 0, dest_serial, 0, 0, 0)
            Wait(800)
            routed += 1

    # Remove routed entries from the plan (consume from front)
    if routed > 0 and plan_entries:
        plan_entries = plan_entries[routed:]
        try:
            with open(batch_path, "w") as f:
                json.dump(plan_entries, f, indent=2)
        except Exception:
            pass

    AddToSystemJournal(f"Routed {routed} BODs.")

    # Check if more drops remain in the RE drops file
    drops_path = _get_re_drops_path()
    remaining_drops = 0
    if os.path.exists(drops_path):
        try:
            with open(drops_path, "r") as f:
                data = json.load(f)
            remaining_drops = sum(len(d["drops"]) for d in data)
        except Exception:
            pass

    if remaining_drops > 0:
        AddToSystemJournal(f"  {remaining_drops} drops remaining -> Press CTRL+K for next batch")
    else:
        AddToSystemJournal("  All drops complete! Run Scan All to rebuild inventories.")


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
        book_serials = [s for i, s in enumerate(full_list) if i >= 3 and s != 0]
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
    """Finds the first completable set, writes RE drops for JUST that set (1 Large + Smalls),
    then after user CTRL+K's, combines them and routes to Consegna.

    If overflow_only=True, only checks overflow books (index 3+).
    Flow: extract_and_combine_next_set() -> user CTRL+K -> assemble_dropped_set()
    """
    book_serials = _get_book_serials(config, cycle_type)
    if overflow_only:
        key = "conserva_books_tailor" if cycle_type == "Tailor" else "conserva_books_smith"
        full_list = config.get(key, [])
        book_serials = [s for i, s in enumerate(full_list) if i >= 3 and s != 0]
    inventories = load_all_inventories(book_serials)

    # Find first completable set across all books
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
        AddToSystemJournal("No completable sets found. Nothing to extract.")
        return False

    large = target_set['large']
    smalls = target_set['smalls']
    prize_id = large.get('prize_id')
    prize_label = prize_names.get(prize_id, f"#{prize_id}") if prize_id else "?"

    AddToSystemJournal(
        f"Extracting set: {large['category']} {large['material']} "
        f"{large['quality']} x{large['amount']} -> {prize_label}"
    )
    AddToSystemJournal(f"  From book {hex(target_book)}: 1 Large + {len(smalls)} Smalls")

    # Collect all positions, sort descending
    all_bods = [large] + smalls
    positions = sorted([b['pos'] for b in all_bods], reverse=True)
    drop_btns = [5 + (p * 2) for p in positions]

    # Write RE drops — just this one set
    drops_data = [{
        "book": target_book,
        "book_hex": hex(target_book),
        "drops": drop_btns,
    }]

    drops_path = _get_re_drops_path()
    try:
        with open(drops_path, "w") as f:
            json.dump(drops_data, f, indent=2)
    except Exception as e:
        AddToSystemJournal(f"Failed to write drops JSON: {e}")
        return False

    # Save set info so assemble_dropped_set knows what to combine + reindex
    set_info = {
        "book": target_book,
        "large": {"category": large['category'], "material": large['material'],
                  "quality": large['quality'], "amount": large['amount']},
        "small_count": len(smalls),
        "total_bods": len(all_bods),
        "extracted_positions": sorted(positions, reverse=True),  # descending, for reindex
    }
    set_info_path = f"{StealthPath()}Scripts\\{CharName()}_conserva_pending_set.json"
    try:
        with open(set_info_path, "w") as f:
            json.dump(set_info, f, indent=2)
    except Exception:
        pass

    # Ensure RE template exists
    template_path = _get_re_template_path()
    if not os.path.exists(template_path):
        write_re_template_and_queue(config, cycle_type)

    AddToSystemJournal(f"  RE ready: {len(drop_btns)} drops. Press CTRL+K, then click 'Combine Set'")
    return True


def assemble_dropped_set(config, cycle_type):
    """Called after CTRL+K dropped exactly 1 set into backpack.
    Identifies the Large + Smalls, combines them, routes to Consegna,
    then checks for the next set.
    """
    from BodCycler_Assembler import combine_and_store

    # Load pending set info
    set_info_path = f"{StealthPath()}Scripts\\{CharName()}_conserva_pending_set.json"
    if not os.path.exists(set_info_path):
        AddToSystemJournal("No pending set to assemble. Click 'Next Set' first.")
        return False

    try:
        with open(set_info_path, "r") as f:
            set_info = json.load(f)
    except Exception:
        AddToSystemJournal("Failed to read pending set info.")
        return False

    # Find all loose BODs in backpack
    FindType(BOD_TYPE, Backpack())
    loose_bods = list(GetFoundList())
    AddToSystemJournal(f"Found {len(loose_bods)} BODs in backpack. Identifying Large...")

    # Identify the Large BOD (parse each to find it)
    import BodCycler_Crafting
    large_serial = None
    small_serials = []

    for bod_serial in loose_bods:
        info = BodCycler_Crafting.parse_bod(bod_serial, cycle_type)
        if not info:
            continue
        if info.get('is_large'):
            large_serial = bod_serial
        else:
            small_serials.append(bod_serial)

    if not large_serial:
        AddToSystemJournal("ERROR: No Large BOD found in backpack. Did CTRL+K run?")
        return False

    AddToSystemJournal(f"  Large: {hex(large_serial)} | Smalls: {len(small_serials)}")

    # Combine and route to Consegna
    success = combine_and_store(large_serial, small_serials, config)

    if success:
        AddToSystemJournal("Set combined and routed to Consegna!")
        from BodCycler_Utils import read_stats, write_stats
        stats = read_stats()
        stats["prized_large"] = stats.get("prized_large", 0) + 1
        write_stats(stats)
    else:
        AddToSystemJournal("FAILED to combine set. Check backpack manually.")

    # Update the source book's inventory JSON — remove extracted positions + reindex
    extracted_positions = set(set_info.get("extracted_positions", []))
    book_serial = set_info.get("book", 0)
    if extracted_positions and book_serial:
        inv_file = get_inventory_file(book_serial)
        if os.path.exists(inv_file):
            try:
                with _INV_LOCK:
                    with open(inv_file, "r") as f:
                        inventory = json.load(f)
                    # Remove extracted entries
                    inventory = [b for b in inventory if b.get("pos") not in extracted_positions]
                    # Reindex 0..N-1
                    for new_pos, entry in enumerate(inventory):
                        entry["pos"] = new_pos
                        entry["drop_btn"] = 5 + (new_pos * 2)
                        entry["page"] = new_pos // 5
                    # Save atomically
                    tmp = inv_file + ".tmp"
                    with open(tmp, "w") as f:
                        json.dump(inventory, f, indent=4)
                    os.replace(tmp, inv_file)
                AddToSystemJournal(f"  JSON reindexed: {len(inventory)} BODs remaining in {hex(book_serial)}")
            except Exception as e:
                AddToSystemJournal(f"  WARNING: Failed to reindex JSON — {e}. Re-scan recommended.")

    # Clean up pending set file
    try:
        os.remove(set_info_path)
    except Exception:
        pass

    # Check for next set
    remaining = check_completable_sets(config, cycle_type)
    if remaining > 0:
        AddToSystemJournal("  -> Click 'Next Set' to extract the next one.")

    return success


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
    consegna = config.get("books", {}).get("Consegna", 0)
    scartare = config.get("books", {}).get("Scartare", 0)
    tier1 = config.get("conserva_manager", {}).get("keep_tier1", 10)
    tier2 = config.get("conserva_manager", {}).get("keep_tier2", 20)

    if not crate or not book_serials:
        AddToSystemJournal("Conserva Manager: Missing crate or book configuration.")
        return

    inventories = load_all_inventories(book_serials)
    plan = analyze_and_plan(inventories, book_serials, config, tier1, tier2)

    for line in plan["summary"]:
        AddToSystemJournal(line)

    # Group all actions by source book
    actions_by_book = defaultdict(list)
    for bod, from_book, to_book in plan["moves"]:
        if from_book != to_book:
            actions_by_book[from_book].append(("move", bod, to_book))
    for bod, from_book in plan["to_consegna"]:
        actions_by_book[from_book].append(("consegna", bod, consegna))
    for bod, from_book in plan["to_scartare"]:
        actions_by_book[from_book].append(("scartare", bod, scartare))

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
