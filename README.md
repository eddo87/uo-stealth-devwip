BOD Cycler Orchestration Architecture

Overview

The BOD Cycler is a modular automation suite for Ultima Online (Stealth Client) designed to automate the acquisition, crafting, and delivery of Bulk Order Deeds (BODs). Unlike traditional monolithic macros, this system uses a Central Orchestrator pattern with a Tkinter GUI to manage state, configuration, and execution.

Core Components

1. The Orchestrator (BodCycler_Config.py)

This is the "Brain" of the operation. It handles three critical roles:

Configuration Management: Stores serial IDs for containers, books, and runebooks in a local JSON.

State Tracking: Monitors a stats.json file to update a live dashboard (Timer, Status, Rewards).

Master Threading: Launches worker macros in a background Daemon Thread, allowing the GUI to remain responsive.

2. The Multi-Book System

The logic relies on a 5-book pipeline to organize data without complex internal lists:

Origine: The input source containing un-filled, low-tier BODs.

Conserva: High-value BODs (Large or Rare Materials) kept for assembly or rewards.

Consegna: The "Delivery Bag." Filled BODs ready to be handed to an NPC.

Riprova: A retry buffer for BODs that failed due to lack of materials.

Scartare: Automated trash for unwanted BOD types (e.g., Bone armor).

3. Logic Modules (The Workers)

Each phase of the cycle is a separate, hot-reloadable module:

CheckSupplies: Audits tool durability and material counts. Crafts tools (Tongs, Kits) on-demand.

Crafting: Extracts BODs, parses requirements, pulls resources from a crate, and fills the deed.

NPC_Trade: Handles travel, context-menu interaction with NPCs, and AutoBuy logic for cloth.

Assembler: Scans the 'Conserva' book to identify and build complete Large BOD sets.

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

Data Flow Diagram

[ GUI ] <--> [ config.json ]
  |             ^
  | (Spawns)    | (Reads/Writes)
  v             v
[ Master Thread ] --> [ CheckSupplies ] --> [ Crafting ] --> [ NPC Trade ]
