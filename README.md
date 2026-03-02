BOD Cycler Orchestration Architecture

Overview

The BOD Cycler is a modular automation suite for Ultima Online (Stealth Client) designed to automate the acquisition, crafting, and delivery of Bulk Order Deeds (BODs). Unlike traditional monolithic macros, this system uses a Central Orchestrator pattern with a Tkinter GUI to manage state, configuration, and execution.

Core Components

1. The Orchestrator (BodCycler_Config.py)

This is the "Brain" of the operation. It handles three critical roles:

Configuration Management: Stores serial IDs for containers, books, and runebooks in a local JSON.

State Tracking: Monitors a stats.json file to update a live dashboard (Timer, Status, Rewards).

Master Threading: Launches worker macros in a background Daemon Thread, allowing the GUI to remain responsive.

Master Cycle Order: Crafting → Supplies → Assembly (with post-run re-scan) → Trade. Crafting runs first to fill BODs with whatever materials are on hand; Supplies restocks for the next round afterwards.

2. The Multi-Book System

The logic relies on a 5-book pipeline to organize data without complex internal lists:

Origine: The input source containing un-filled, low-tier BODs. Replenished via BodBookCrate swap when empty.

Conserva: High-value BODs (Large or Rare Materials) kept for assembly or rewards.

Consegna: The "Delivery Bag." Filled BODs ready to be handed to an NPC.

Riprova: A retry buffer for BODs that failed due to lack of materials.

Scartare: Automated trash for unwanted BOD types (e.g., Bone armor).

3. Logic Modules (The Workers)

Each phase of the cycle is a separate, hot-reloadable module:

CheckSupplies: Audits tool durability and material counts. Crafts tools (Tongs, Kits) on-demand.

Crafting: Extracts BODs, parses requirements, pulls resources from a crate, and fills the deed.

NPC_Trade: Handles travel, context-menu interaction with NPCs, AutoBuy logic for cloth, and smart BOD sorting (with filled-BOD detection).

Assembler: Scans the 'Conserva' book to identify and build complete Large BOD sets.

TakeBods: Multi-bot hourly BOD collection across collector profiles.

4. The BodBookCrate (Origine Replenishment)

When the Origine book runs out of BODs, the system performs a whole-book swap instead of fetching individual BODs:

1. The depleted Origine book is moved into the BodBookCrate container.
2. The crate is scanned for a BOD book matching the current cycle type (Tailor or Smith) with more than 50 BODs.
3. Book detection uses the tooltip format: "Bulk Order Book|Blessed|Weight: 1 stone|Deeds in book: N|Book Name: TYPE".
4. The qualifying book is moved to backpack and becomes the new Origine.
5. The call site receives a (0, new_serial) tuple, updates its 'origine' variable, and continues the crafting loop without breaking.

Config key: "BodBookCrate" (exact casing).

5. Hourly BOD Collection (BodCycler_TakeBods.py)

Collector profiles (ed2, ed3, ed5) cycle every hour to collect one BOD from a Tailor NPC and one from a Blacksmith NPC, then store them in their respective BOD books.

Trigger logic uses two gates (both must pass):
  Gate 1 — Clock window: current minute is between :55 and :05 (server-aligned to UO's hourly refresh).
  Gate 2 — Cooldown: at least 55 minutes have elapsed since the last collection (prevents re-firing mid-window).

The cycle is fully event-driven:
  - Connection: polls Connected() for up to 15 seconds instead of fixed sleeps.
  - Gump: waits up to 10 seconds for the BOD offer gump; skips the NPC on timeout.
  - As soon as ed5 disconnects, ed4 reconnects immediately — no idle window waiting.

Before handing off to the collectors, ed4 walks to the standby position (892, 537) and disconnects.
After the full collection round, run_take_bods_cycle() reconnects ed4 and stamps last_collection_time in stats.json.
reset_stats() (called on cycle start) also stamps last_collection_time to prevent immediate collection on first loop.

Critical Mechanisms

Global Abort (The Circuit Breaker)

Since Stealth scripts run synchronously, stopping a macro usually requires a hard script-stop. This system implements a Soft Abort:

The GUI writes "status": "Stopped" to the stats JSON.

All worker modules call check_abort() at the start of every internal loop (e.g., every item crafted, every step moved).

If "Stopped" is detected, the worker cleans up UI (closes gumps) and exits the thread gracefully.

Hot-Reloading

By using importlib.reload() within the Master Cycle, the orchestrator can update its logic without the user having to restart the GUI. This allows for "Live Debugging" where a developer can tweak a material ID or a delay and see the change reflected in the very next cycle.

World Save Guard

Every module integrates with checkWorldSave.py. This prevents the "Gump Freeze" common on ServUO/RunUO shards where an action performed during a world save is lost, but the script continues as if it succeeded.

BOD Routing Safety (sort_new_bods)

The NPC_Trade sorter checks qty_needed on every BOD before routing:
  - qty_needed > 0 → unfilled → Origine (for crafting)
  - qty_needed == 0, no prize → Consegna (already filled, ready to trade)
  - qty_needed == 0, has prize → Conserva (filled prize-worthy BOD)

This prevents filled BODs from contaminating the Origine book when a trade_bod() call fails silently.

Stat Ownership

  prized_small: incremented in BodCycler_Crafting.py when a small BOD is routed to Conserva.
  prized_large: incremented in BodCycler_NPC_Trade.py when a Large BOD is routed to Conserva via sort_new_bods.
  prizes_dropped: incremented in BodCycler_NPC_Trade.py when a physical prize lands in the Reward Crate.

AI Error Handling

BodCycler_AI_Debugger.py provides two active Discord functions:
  send_error_alert(): fires on crafting failures, riprova routing, and origine refill events. Uses MODEL_FAST (llama-3.1-8b-instruct-fast) to generate a 1-sentence explanation.
  send_prize_notification(): fires instantly when a prize is moved to the Reward Crate.

The DeepSeek model and end-of-session Discord report have been removed.

Data Flow Diagram

[ GUI ] <--> [ config.json ]
  |             ^
  | (Spawns)    | (Reads/Writes)
  v             v
[ Master Thread ]
  |
  |-- BOD Collection check (should_collect_bods: clock :55-:05 + 55min cooldown)
  |     └─> [ed4 walks to (892,537)] -> Disconnect -> [TakeBods: ed2/ed3/ed5] -> ed4 Reconnect
  |
  |-- STEP 1: Crafting  (Origine -> fill BODs -> Consegna/Conserva/Riprova)
  |             └─> BodBookCrate swap if Origine empty
  |
  |-- STEP 2: CheckSupplies  (restock tools & materials for next round)
  |
  |-- STEP 2.5: Assembly Check  (inventory.json -> Assembler -> re-scan)
  |
  └-- STEP 3: NPC Trade  (Consegna BODs -> Tailor -> new BODs sorted -> cloth bought)
