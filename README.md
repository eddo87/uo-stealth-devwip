BOD Cycling Automation Project Plan

1. Project Architecture & Assets

We have successfully built a Controller Script (BodCycler_Config.py) that orchestrates your modules using multi-threading, live hot-reloading, and JSON inter-script communication.

Core System Assets

BodCycler_Config.py: The GUI Command Center. Manages the master thread, dashboard, and global abort states.

BodCycler_CheckSupplies.py: Restocks ingots and manages tool thresholds for both Smithing and Tailoring.

BodCycler_Crafting.py: Smartly extracts BODs, assesses current fill levels, crafts missing quantities with dynamic pacing, and fills the BODs using intelligent cursors.

BodCycler_NPC_Trade.py: Handles NPC interaction (Weaver/Tailor prioritization), trading, requesting new BODs, filing to books, buying cloth via AutoBuy fallbacks, and runebook travel.

bod_crafting_data.py: Dictionary matching string names to category menus and specific shard hex IDs.

The 5-Book System

All books are fully implemented and utilized by the scripts:

0. Source (Backpack/Incoming): New BODs received from NPC.

1. Origine (The Fuel): Small, easy BODs (Iron/Cloth). 10/15/20 count.

2. Conserva (The Goal): High-tier BODs stored for rewards.

3. Riprova (The Buffer): BODs failing due to lacking materials or interruptions.

4. Consegna (The Ammo): Origine BODs that are filled and ready to trade.

5. Scartare (The Trash): BODs that are neither easy to fill nor valuable (e.g., Bone armor).

2. The Workflow (State Machine)

The BodCycler_Config.py script runs this Master Loop in a Daemon Thread:

Init (BodCycler_CheckSupplies.py):

Load Configs.

Check container caches.

Craft necessary Tinker Tools, Sewing Kits, or Tongs.

Update Live Dashboard JSON.

Restock & Prep (BodCycler_Crafting.py):

Recover from crashes (check backpack for lingering BOD).

Extract BOD from Origine.

Parse requested amounts.

Pull exact materials from Crate.

Dynamically craft items.

Route full BODs to Consegna or Conserva.

Transit & Trade (BodCycler_NPC_Trade.py):

Travel to WorkSpot -> NPC.

Prioritize Weavers. Fallback to backup locations if blocked/fizzled.

Execute loop: Hand in BOD -> Get New BOD -> Move New BOD to Origine.

Execute AutoBuy for Cloth Bolts (using fallback IDs).

Cut cloth.

Travel Home.

Process prizes (Trash garbage, store/dye cloth).

Repeat & Listen:

Loop restarts unless the global check_abort() flag catches a Stop command from the GUI.

3. Development Checklist

Phase 1: Setup (The Foundation)

[x] Config Tool: Create BodCycler_Config.py (GUI to set Serial IDs).

[x] Category Logic: Logic implemented to sort "Keep", "Fuel", or "Trash" BODs.

Phase 2: Production (The Filling)

[x] Batch Filler: Script that pulls from Book A, Crafts, Puts in Book B.

[x] Test: Verify crafting logic reliably fills Small Iron/Cloth BODs with dynamic pacing and crash recovery.

Phase 3: Interaction (The Cycling)

[x] NPC Interaction: Handle the timer, BOD hand-ins, and automated purchasing.

[x] Sorting: Ensure the script can distinguish New BODs, automatically filing them back into the Origine book.

Phase 4: Integration (Command Center & Master Loop)

[x] Master Script: Combine Home -> Fill -> Travel -> Trade -> Sort -> Return loop.

[x] Live Dashboard: GUI updates in real-time reading from JSON files.

[x] Hot-Reloading: Dynamic module imports so code can be tweaked without restarting the GUI.

[x] Safe Threading & Aborts: Non-blocking GUI thread with instant JSON-based check_abort() hooks in all worker scripts.

Phase 5: Beta Polish

[ ] Edge Case Handling (Server saves, tool breaks mid-craft, random disconnects).

[ ] Expand to Smithing BOD logic thoroughly (Verify tongs, ingots, and anvil proximity).

[ ] Long-term stability testing (Unattended overnight runs).