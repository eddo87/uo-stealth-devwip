# **UO Stealth BOD Cycler**

## **🎯 Project Context (WHAT & WHY)**

Automated Ultima Online crafting and trading macro system built on top of UO Stealth Client.

It uses a **Central Orchestrator** pattern where a primary Python Tkinter GUI manages multiple specialized daemon threads (Worker Modules) to cycle Bulk Order Deeds (BODs).

## **📚 Deep Reference Documentation**

*If you need to understand specific function signatures, historical bug fixes, or detailed data flow, search these files:*

* **README.md**: General architecture and data flow diagrams.  
* **docs/Project\_Architecture.md**: Exhaustive function reference and module responsibilities.  
* **docs/knowledge01.json**: Historical bug fixes, Stealth API quirks (e.g., FindCount vs GetFindCount), and exact NPC/Gump hex IDs.

## **🚀 Commands (HOW)**

* **Run the Application:** python BodCycler\_Config.py  
* *Note: Code runs synchronously against the Stealth API. GUI runs on the main thread, workers run on background threads.*

## **🗺️ Component Map**

* BodCycler\_Config.py: **The Brain.** Master loop, GUI state, hot-reloading.  
* BodCycler\_Utils.py: **Infrastructure.** Paths, JSON I/O, thread-safe writers, gump helpers.  
* BodCycler\_Crafting.py: **The Producer.** BOD extraction, item crafting, book replenishment.  
* BodCycler\_NPC\_Trade.py: **The Merchant.** Travel, NPC trading, auto-purchasing.  
* BodCycler\_Scanner.py: **The Data Entry.** Visual parser for BOD books \-\> inventory.json.  
* BodCycler\_Assembler.py: **The Builder.** Matches Small to Large BODs using JSON logic.  
* BodCycler\_TakeBods.py: **The Collector.** Multi-bot profile switcher.  
* BodCycler\_AI\_Debugger.py: **The Sentinel.** Cloudflare AI \+ Discord alerts.  
* checkWorldSave.py: **The Guard.** Pauses execution during server saves/restarts.

## **🏗️ Architecture & State Pipeline**

Physical items move through a strict 5-Book Pipeline:

1. **Origine:** Input (Unfilled BODs). Refilled via Whole-Book Swap from BodBookCrate.  
2. **Conserva:** High-value/Prize-worthy items.  
3. **Consegna:** Output (Filled items ready for trade).  
4. **Riprova:** Buffer (Waiting on out-of-stock materials).  
5. **Scartare:** Filter (Junk items/Bone armor).

**Data Flow:**

GUI \-\> writes config.json \-\> Master Loop reads \-\> Spawns Worker \-\> Worker acts & writes to stats.json \-\> GUI polls stats.json to update Dashboard.

## **🛑 CRITICAL RULES (YOU MUST FOLLOW THESE)**

### **1\. The "Circuit Breaker" (Soft Aborts ONLY)**

**IMPORTANT:** Never use hard exits, thread kills, or sys.exit() in worker threads. Stealth Client requires graceful exists to prevent game-state corruption.

* If a loop needs to stop, check BodCycler\_Utils.check\_abort().  
* If True, gracefully close gumps and let the thread die naturally.  
* GUI triggers this by setting the status in stats.json to "Stopped".

### **2\. Event-Driven Polling vs. Hard Sleeps**

**IMPORTANT:** Do not use hard sleep() commands for UI or Connection waits.

* Use BodCycler\_Utils.wait\_for\_gump(gump\_id, timeout\_ms) to detect UI elements.  
* Use connection polling (Connected()) before executing actions.  
* Use wait\_for\_gump\_serial\_change to verify book pages have actually loaded.

### **3\. Shared Infrastructure**

* All file paths, Gump IDs, and JSON I/O **MUST** be imported from BodCycler\_Utils.py.  
* Never write standard open(file, 'w') for stats/config data. Always use the atomic, thread-safe writers in BodCycler\_Utils.py to prevent corruption while the GUI polls.

### **4\. Crafting & Material Safety**

* **Material Hues:** When crafting, you MUST navigate to the "Materials" tab in the crafting gump to reset hues. Failure to do this results in wasting rare materials on normal items.  
* Always handle exceptional quality checks via BodCycler\_Crafting.is\_item\_exceptional().

### **5\. JSON Index Integrity**

* BodCycler\_Scanner.py relies on a visual map. If items are moved physically in the game without using the automated systems, the pos and drop\_btn indices in inventory.json will break.  
* Any code that moves items out of a scanned book MUST trigger an array re-index or a prompt to rescan.