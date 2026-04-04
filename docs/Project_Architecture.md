# **BOD Cycler Orchestration Architecture**

This document outlines the structural design of the UO Stealth BOD Cycler. The project uses a **Central Orchestrator** pattern where a primary GUI (Tkinter) manages multiple specialized daemon threads (Worker Modules).

## **1\. Core Component Map**

| **File** | **Role** | **Key Responsibility** |

| **BodCycler\_Config.py** | **The Brain** | Orchestrates the master loop, manages GUI state, and handles hot-reloading. |

| **BodCycler\_Utils.py** | **Infrastructure** | Single source of truth for file paths, JSON I/O, and shared Gump helpers. |

| **BodCycler\_Crafting.py** | **The Producer** | Extracts BODs, crafts items, and fills deeds. Handles the "Origine" book replenishment. |

| **BodCycler\_NPC\_Trade.py** | **The Merchant** | Handles travel, trading filled BODs for new ones, and automated material purchasing. |

| **BodCycler\_Scanner.py** | **The Data Entry** | Visually parses BOD books to build the inventory.json database. |

| **BodCycler\_Assembler.py** | **The Builder** | Matches Small BODs to Large BODs using JSON logic and builds complete sets. |

| **BodCycler\_TakeBods.py** | **The Collector** | Hourly multi-bot profile switcher for BOD acquisition. |

| **BodCycler\_AI\_Debugger.py** | **The Sentinel** | Cloudflare AI integration and Discord alerting for prizes and errors. |

| **checkWorldSave.py** | **The Guard** | Prevents macro failure during server world-saves and manages server restarts. |

## **2\. The 5-Book Pipeline (State Management)**

The system moves physical items through a "Pipeline" represented by different BOD books:

1. **Origine:** Input (Unfilled BODs).  
2. **Conserva:** High-value/Prize-worthy items (kept for sets or rewards).  
3. **Consegna:** Output (Filled items ready for trade).  
4. **Riprova:** Buffer (Items requiring materials currently out of stock).  
5. **Scartare:** Filter (Items determined to be "junk").

## **3\. Critical Orchestration Mechanics**

### **The "Circuit Breaker" (Soft Abort)**

Because Stealth Client runs scripts synchronously, a hard "Stop" can corrupt game state. This system uses a **Soft Abort pattern**:

* **UI Trigger:** When the user clicks "Stop" in BodCycler\_Config.py, the variable status in stats.json is set to "Stopped".  
* **Worker Polling:** Every worker module (Crafting, Trade, etc.) calls check\_abort() inside its internal loops.  
* **Graceful Exit:** If True, the worker closes gumps, stops its loop, and lets the thread die naturally.

### **BodBookCrate Replenishment**

Instead of fetching individual BODs when the Origine book is empty, the system performs a **Whole-Book Swap**:

1. Moves the empty book to the BodBookCrate.  
2. Scans tooltips in the crate for a new book (matching "Tailor" or "Blacksmith") with \>50 deeds.  
3. Moves the new book to the backpack and resumes the loop immediately.

### **Event-Driven BOD Collection**

BodCycler\_TakeBods.py does not use hard sleeps for character switching. It uses:

* **Connection Polling:** Waits for the Connected() signal (max 15s).  
* **Gump Detection:** Uses wait\_for\_gump with a 10s timeout to detect if an NPC has a BOD available.  
* **Standby Position:** Moves the main crafter to a specific coordinate (892, 537\) before handing off to the collector bots.

## **4\. Data Flow**

1. **GUI** ![][image1] writes config.json  
2. **Master Loop** ![][image1] reads config.json ![][image1] spawns **Worker Thread**  
3. **Worker** ![][image1] performs game action ![][image1] writes progress to stats.json  
4. **GUI** ![][image1] polls stats.json ![][image1] updates live Dashboard display.

## **5\. Function Reference by Module**

### **BodCycler\_Config.py (Main Orchestrator)**

* \_\_init\_\_(): Initializes the GUI thread, default configuration map, and thread-safe variables.  
* load\_config(): Reads config.json and maps saved values to the UI, applying defaults if missing.  
* save\_config(): Serializes active GUI variable states into config.json.  
* get\_target(): A generalized prompt handler asking the user to target items/containers in-game to save their serial IDs.  
* set\_home\_spot(): Captures the player's current X, Y, Z coordinates and designates it as the safe "Home" location.  
* go\_to\_home\_spot(): Actively moves the character to the configured Home spot.  
* trigger\_supply\_check() / trigger\_crafting() / trigger\_trade() / trigger\_scan() / trigger\_assemble(): Discrete handlers to manually launch specific worker modules in background threads for isolated testing.  
* test\_travel() / \_test\_travel\_thread(): Initiates a background thread to test a specific runebook index to verify routing paths.  
* read\_supplies\_file(): Polls supplies.json for modifications and updates the material dashboard GUI elements.  
* read\_stats\_file(): Polls stats.json for modifications and updates the session statistics dashboard (BODs filled, prizes).  
* reset\_stats(): Wipes the session metrics in stats.json and resets the timer logic.  
* update\_timer(): A recursive Tkinter after() loop that ticks the active session clock and triggers the JSON polling methods.  
* set\_global\_status(): Updates the GUI status string and commits the status text to stats.json (triggering the Soft Abort if set to "Stopped").  
* \_is\_stopped(): Safely checks the thread-locked status state to determine if the loop should break.  
* master\_cycle\_thread(): The core orchestration loop running the sequence: Crafting ![][image1] Supplies ![][image1] TakeBods ![][image1] Assembly Check ![][image1] Trading.  
* start\_cycling(): Initializes the session metrics and launches the master\_cycle\_thread in the background.  
* stop\_cycling(): Flips the global status to "Stopped" to safely abort the orchestrator and all active worker threads.  
* run(): Builds the physical Tkinter UI layout, packs frames/labels, and initiates the mainloop().  
* check\_assembly\_readiness(): Analyzes inventory.json locally and prints completable Large BOD sets to the Stealth Journal without moving items in-game.

### **BodCycler\_Utils.py (Shared Infrastructure)**

* load\_config(): Loads the master JSON config file, returning a dictionary or None on failure.  
* check\_abort(): Polls the stats.json file to check if the GUI has issued a "Stopped" command, acting as the global circuit breaker.  
* read\_stats(): Thread-safe reader for the stats.json file that provides safe default values if the file is locked or missing.  
* write\_stats(data): Thread-safe, atomic writer for the stats.json file utilizing a temporary file to prevent corruption during rapid updates.  
* set\_status(status\_text): Helper function to update only the 'status' key in the stats file without clobbering other operational metrics.  
* close\_all\_gumps(): Iterates through all open UI gumps in reverse index order and closes them safely.  
* wait\_for\_gump(gump\_id, timeout\_ms): A polling loop integrated with the world save guard that waits for a specific gump ID to appear.  
* save\_performance\_snapshot(): Calculates hourly completion and trade rates, appending a structured record to performance.json at the end of a cycle.  
* wait\_for\_gump\_serial\_change(current\_serial, gump\_id, timeout\_ms): Specialized polling function that detects when a gump's serial ID changes, used to accurately verify that a BOD book page has fully loaded.

### **BodCycler\_Crafting.py (BOD Fulfillment)**

* update\_stats(): Updates the persistent stats JSON file for GUI tracking.  
* consolidate\_materials(): Scans the backpack for loose materials (cloth, leather, iron, etc.) and moves them back to the resource crate.  
* find\_button\_for\_text(): Locates specific crafting buttons in gump data using an exact text match or a regex word-boundary fallback.  
* \_parse\_book\_count(): Extracts the exact BOD count from a BOD book tooltip.  
* \_refill\_origine\_from\_book\_crate(): Performs the core logic for swapping depleted Origine BOD books for fresh ones from the storage crate.  
* extract\_bod\_from\_origine(): Pulls a BOD from the Origine book or triggers the automatic refill swap if the book is empty.  
* parse\_bod(): Intelligent tooltip parser that identifies item requirements, quantities needed, materials, and potential prizes.  
* is\_item\_exceptional(): Safely checks if an item is exceptional by reading its server tooltip.  
* count\_valid\_backpack\_items(): Counts the number of valid (normal or exceptional) crafted items currently in the backpack.  
* get\_craft\_info(): Retrieves crafting parameters (category, item ID, tool type, resource cost) from the dictionary data.  
* check\_and\_pull\_materials(): Verifies if enough materials are in the backpack to craft the needed amount, automatically pulling from the crate if short.  
* recycle\_invalid\_items(): Automatically cuts (scissors) or smelts (tongs) items that failed to meet the exceptional quality requirement.  
* craft\_items\_until\_done(): Navigates the crafting gump, handles material selection, crafts the required quantity, and uses AI logic/verification for ID mismatches.  
* is\_bod\_full(): Parses the BOD tooltip to check if the 'amount to make' strictly matches the finished amount.  
* fill\_bod\_completely(): Automates the "Combine" process to move valid crafted items from the backpack into the deed.  
* run\_crafting\_cycle(): The main entry point that processes a batch of BODs, managing their complete lifecycle and routing to Conserva/Consegna/Scartare/Riprova.

### **BodCycler\_NPC\_Trade.py (Trade & Logistics)**

* find\_tailor(): Locates a single tailor or weaver NPC within the immediate vicinity.  
* find\_all\_tailors(): Locates all tailor/weaver NPCs in the area to build a list for cooldown rotation.  
* move\_to\_npc(npc): Walks the character to within 1 tile of the target NPC to ensure interactions succeed.  
* sort\_new\_bods(config): The smart routing engine. Parses loose BODs in the backpack and directs them to Origine (unfilled), Conserva (valuable/large), Consegna (already filled), or Scartare (junk/bone). Synchronizes Conserva drops with the Assembler's JSON inventory.  
* extract\_bod\_from\_book(book\_serial): Opens a designated BOD book and drops the first BOD into the backpack for trading.  
* trade\_bod(npc, bod\_serial): Physically drops a filled BOD onto the NPC and verifies the item left the backpack.  
* find\_bod\_offer\_gump(): Scans active gumps to detect if the NPC has offered a small or large BOD.  
* request\_new\_bod(npc): Triggers the "Bulk Order Info" context menu on the NPC and automatically accepts the incoming BOD offer gump.  
* buy\_and\_cut\_cloth(npc, amount): Automated procurement logic that sets up AutoBuy for cloth bolts, interacts with the NPC, and uses scissors to process the bolts into raw cloth.  
* travel\_to(runebook\_serial, travel\_method, rune\_index): Handles runebook navigation using either Recall or Sacred Journey, blocking until the character's coordinates successfully change.  
* process\_prizes\_at\_home(trash, crate, dye\_tub, reward\_crate): Post-cycle cleanup script. Trashes junk rewards (sandals/oil cloths), dyes colored cloth to normalize stacks, stashes high-value rewards (Runics/CBDs) into the reward crate, and fires Discord prize notifications.  
* execute\_trade\_loop(): The main entry point. Orchestrates the full cycle: traveling to tailors, dropping filled BODs, handling NPC cooldown rotations, requesting new BODs, sorting them, buying cloth, traveling home, and cleaning up the backpack.

### **BodCycler\_Scanner.py (Inventory Mapping)**

* get\_all\_elements(g): Extracts raw text elements and their X/Y coordinates from both standard GumpText and HTML gump data.  
* infer\_material(item\_name, current\_mat): Fallback logic that corrects the base material for specific item sets (e.g., assigning "Leather" to Studded sets if the gump implicitly defaults to "Iron").  
* parse\_page\_visually(g): The core visual parser. Groups gump text elements by Y-coordinate (rows) and reads X-coordinates (columns) to extract exact BOD properties (type, item, quality, material, amount).  
* map\_and\_save\_book\_inventory(book\_serial): Opens the Conserva book, iterates through every page, parses the visual data, assigns global array positions (pos, drop\_btn, page), and saves the complete database to inventory.json.  
* generate\_progress\_report(all\_bods): Compares the mapped inventory against target reward sets (from bod\_data.py) and prints a detailed progress report to the Stealth Journal, showing exact missing components for valuable Large BODs.  
* run\_scanner(): The main entry point triggered by the GUI or Master Loop. Orchestrates the full book scan, handles UI status updates, and triggers the final progress report.

### **BodCycler\_Assembler.py (Set Builder)**

* append\_to\_inventory(): Appends a newly added BOD to the inventory JSON, automatically calculating and tracking its exact server array position (pos, drop\_btn, and page).  
* find\_completable\_sets(): Analytical function that scans the inventory.json database to match Small BODs to their corresponding Large BOD requirements using the component dictionaries.  
* extract\_bods(): Performs a batch "Reverse Sweep" to pull specific sets out of the Conserva book. It targets BODs in descending position order to prevent server index shifting during extraction.  
* combine\_and\_store(): Physically combines the extracted Small BODs into the Large BOD within the backpack, then moves the completed set to the Consegna book.  
* run\_assembler(): The main entry point that reads the live JSON state, identifies completable sets, initiates batch extraction, orchestrates the combination, and re-indexes the JSON database once elements are removed.

### **BodCycler\_TakeBods.py (Bot Collection)**

* run\_take\_bods\_cycle(): Orchestrates the multi-profile rotation of collector characters.  
* should\_collect\_bods(): Time-gate logic checking the hourly window and a 55-minute cooldown.  
* \_get\_bod(): Interacts with NPCs via context menus and accepts offered BODs using event-driven polling.

### **BodCycler\_AI\_Debugger.py (Intelligence & Alerts)**

* send\_error\_alert(): Sends AI-summarized failure reports to Discord.  
* send\_prize\_notification(): Fires real-time alerts when high-tier prizes (Runics/CBDs) are secured.  
* log\_failure() / should\_trash(): Persistent learning engine to track and avoid difficult-to-craft items.

### **checkWorldSave.py (Guard Logic)**

* world\_save\_guard(): Hooks into journal events to pause macro execution during server saves, preventing gump-stalls.  
* connection\_guard(): Automated reconnection loop that blocks until the character is back online.  
* check\_server\_restart(): Detects proximity to daily maintenance and moves the character to a safe "WorkSpot" before disconnecting.

## **6\. Development Guidelines**

* **Shared Constants:** Always use BodCycler\_Utils.py for global paths and gump IDs.  
* **Material Safety:** When crafting, the system must navigate to the "Materials" tab to reset hues, preventing "Normal" items from being crafted using "Rare" materials.  
* **JSON indexing:** BodCycler\_Scanner.py creates a visual map of books; if you move items manually, you must run a "Scan" to update the pos and drop\_btn indices.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAXCAYAAADpwXTaAAAAt0lEQVR4XmNgGAWjgDpAQUGBQ05OLk1UVJQHXY4cwCgvL98KNNAYXYIsADIIaGAvkMmCLkcOYAR6twBoaByIjSIDlBAA2iRJClZSUgKaJTcfyJ6soqLCBzZIXFycGyhQDcSzSMVAw3YA6a9A3Aw0kB3FhaQAWVlZE6Ahq6WlpWXQ5UgCQAOEgQYtVlRUlEeXIxkADcoChnMEujjJAJRogYZNlZGRkUaXIwcwqqur84JodIlRMMAAAJV7J+RoCL8jAAAAAElFTkSuQmCC>