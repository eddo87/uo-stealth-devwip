from stealth import *
import os
import json
import copy
import threading
import time
import BodCycler_AI_Debugger
from tkinter import *
from datetime import datetime
from BodCycler_Utils import (
    set_status, read_stats, write_stats, save_performance_snapshot,
    get_inventory_file, load_config,
    CONFIG_FILE, STATS_FILE, INVENTORY_FILE, SUPPLY_FILE
)

# Import the logic modules
try:
    import BodCycler_CheckSupplies
except ImportError as e:
    AddToSystemJournal(f"[WARN] Failed to import BodCycler_CheckSupplies: {e}")

try:
    import BodCycler_Crafting
except ImportError as e:
    AddToSystemJournal(f"[WARN] Failed to import BodCycler_Crafting: {e}")

try:
    import BodCycler_NPC_Trade
except ImportError as e:
    AddToSystemJournal(f"[WARN] Failed to import BodCycler_NPC_Trade: {e}")

try:
    import BodCycler_Scanner
except ImportError as e:
    AddToSystemJournal(f"[WARN] Failed to import BodCycler_Scanner: {e}")

try:
    import BodCycler_Assembler
except ImportError as e:
    AddToSystemJournal(f"[WARN] Failed to import BodCycler_Assembler: {e}")

try:
    import BodCycler_TakeBods
except ImportError as e:
    AddToSystemJournal(f"[WARN] Failed to import BodCycler_TakeBods: {e}")



# --- Configuration & Globals ---
ICON_FILE = f"{StealthPath()}Scripts\\bod_cycler.ico"

STATS = {
    "start_time": None,
    "status": "Idle"
}
_STATS_LOCK = threading.Lock()

DEFAULT_CONFIG = {
    "cycle_type": "Tailor", 
    "trade": {
        "target_trades": 2,
        "buy_cloth_amount": 80,
        "buy_cloth_enabled": True
    },
    "books": {
        "Origine": 0,   "Conserva": 0,  "Riprova": 0,   "Consegna": 0,  "Scartare": 0
    },
    "books_tailor": {
        "Origine": 0,   "Conserva": 0,  "Riprova": 0,   "Consegna": 0,  "Scartare": 0
    },
    "books_smith": {
        "Origine": 0,   "Conserva": 0,  "Riprova": 0,   "Consegna": 0,  "Scartare": 0
    },
    "talismans": {
        "Tailor": 0,
        "Smith":  0
    },
    "containers": {
        "MaterialCrate": 0, "TrashBarrel": 0, "ClothDyeTub": 0, "RewardCrate": 0,
        "BodBookCrate": 0, "ConservaCrate": 0, "ProspectorCrate": 0, "PowderCrate": 0
    },
    "conserva_books_tailor": [0, 0, 0, 0, 0],
    "conserva_books_smith":  [0, 0, 0, 0, 0],
    "conserva_manager": {"keep_tier1": 8, "keep_tier2": 20},
    "travel": {
        "RuneBook": 0, "Method": "Recall",
        "Runes": {
            "WorkSpot1": 1, "WorkSpot2": 2, "Tailor1": 3,
            "Tailor2": 7,   "Smith1": 8,    "Smith2": 9
        }
    },
    "home": { "X": 0, "Y": 0, "Z": 0 },
    "bots": {
        "crafter_profile": "ed4",
        "collector_profiles": ["ed2", "ed3", "ed5"]
    },
    "prize_filter": {
        "tailor": [23, 24],
        "smith": [12, 17, 19, 20, 21, 22]
    }
}

class BodCyclerGUI(threading.Thread):
    def __init__(self):
        super(BodCyclerGUI, self).__init__(daemon=True)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.root = None
        self.vars = {} 
        self.running = True
        self.last_supply_mtime = 0
        self.last_stats_mtime = 0

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception:
                pass
        for key in DEFAULT_CONFIG:
            if key not in self.config: self.config[key] = DEFAULT_CONFIG[key]
        for k in DEFAULT_CONFIG["containers"]:
            if k not in self.config["containers"]: self.config["containers"][k] = 0
        if "home" not in self.config: self.config["home"] = {"X": 0, "Y": 0, "Z": 0}
        if "cycle_type" not in self.config: self.config["cycle_type"] = "Tailor"
        if "trade" not in self.config: self.config["trade"] = {"target_trades": 2, "buy_cloth_amount": 80, "buy_cloth_enabled": True}
        if "buy_cloth_enabled" not in self.config["trade"]: self.config["trade"]["buy_cloth_enabled"] = True
        # Migrate legacy single 'books' dict into books_tailor if not yet split
        if "books_tailor" not in self.config:
            self.config["books_tailor"] = dict(self.config.get("books", copy.deepcopy(DEFAULT_CONFIG["books_tailor"])))
        if "books_smith" not in self.config:
            self.config["books_smith"] = copy.deepcopy(DEFAULT_CONFIG["books_smith"])
        if "talismans" not in self.config:
            self.config["talismans"] = copy.deepcopy(DEFAULT_CONFIG["talismans"])
        if "bots" not in self.config: self.config["bots"] = {"crafter_profile": "ed4", "collector_profiles": ["ed2", "ed3", "ed5"]}
        if "crafter_profile" not in self.config["bots"]: self.config["bots"]["crafter_profile"] = "ed4"
        if "collector_profiles" not in self.config["bots"]: self.config["bots"]["collector_profiles"] = ["ed2", "ed3", "ed5"]
        if "conserva_books_tailor" not in self.config: self.config["conserva_books_tailor"] = [0, 0, 0, 0, 0]
        if "conserva_books_smith" not in self.config: self.config["conserva_books_smith"] = [0, 0, 0, 0, 0]
        if "conserva_manager" not in self.config: self.config["conserva_manager"] = {"keep_tier1": 8, "keep_tier2": 20}
        if self.config.get("conserva_manager", {}).get("keep_tier1") == 10: self.config["conserva_manager"]["keep_tier1"] = 8

    def save_config(self):
        for name, var in self.vars.items():
            if name.startswith("rune_"):
                key = name.replace("rune_", "")
                try: self.config["travel"]["Runes"][key] = int(var.get())
                except ValueError: pass
        if "travel_method" in self.vars:
            self.config["travel"]["Method"] = self.vars["travel_method"].get()
        if "cycle_type" in self.vars:
            self.config["cycle_type"] = self.vars["cycle_type"].get()
            
        if "target_trades" in self.vars:
            try: self.config["trade"]["target_trades"] = int(self.vars["target_trades"].get())
            except ValueError: pass
        if "buy_cloth_amount" in self.vars:
            try: self.config["trade"]["buy_cloth_amount"] = int(self.vars["buy_cloth_amount"].get())
            except ValueError: pass
        if "buy_cloth_enabled" in self.vars:
            self.config["trade"]["buy_cloth_enabled"] = bool(self.vars["buy_cloth_enabled"].get())
        if "crafter_profile" in self.vars:
            self.config.setdefault("bots", {})["crafter_profile"] = self.vars["crafter_profile"].get().strip()
        if "collector_profiles" in self.vars:
            raw = self.vars["collector_profiles"].get()
            self.config.setdefault("bots", {})["collector_profiles"] = [p.strip() for p in raw.split(",") if p.strip()]

        # Sync active 'books' from the correct per-mode sub-dict before writing
        cycle = self.config.get("cycle_type", "Tailor")
        active_key = "books_tailor" if cycle == "Tailor" else "books_smith"
        self.config["books"] = dict(self.config.get(active_key, {}))

        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

    def get_target(self, category, key, label_widget=None):
        ClientPrintEx(Self(), 1, 1, f"Target the {key}...")
        ClientRequestObjectTarget()
        start = time.time()
        while not ClientTargetResponsePresent():
            time.sleep(0.1)
            if time.time() - start > 15: return
        
        response = ClientTargetResponse()
        if response["ID"] > 0:
            serial = response["ID"]
            if category in ("books_tailor", "books_smith"): self.config[category][key] = serial
            elif category == "talismans": self.config["talismans"][key] = serial
            elif category == "books": self.config["books"][key] = serial
            elif category == "containers": self.config["containers"][key] = serial
            elif category == "travel": self.config["travel"][key] = serial
            elif category in ("conserva_books_tailor", "conserva_books_smith"):
                idx = int(key)
                self.config[category][idx] = serial
            
            if label_widget:
                label_widget.config(text=f"{key}: {hex(serial)}", fg="blue")

    def set_home_spot(self, label_widget):
        x, y, z = GetX(Self()), GetY(Self()), GetZ(Self())
        self.config["home"].update({"X": x, "Y": y, "Z": z})
        label_widget.config(text=f"Home: {x}, {y}, {z}", fg="blue")
        
    def go_to_home_spot(self):
        hx = self.config["home"].get("X", 0)
        hy = self.config["home"].get("Y", 0)
        if hx != 0 and hy != 0:
            threading.Thread(target=lambda: newMoveXY(hx, hy, True, 0, True)).start()

    # --- Single Trigger Methods (Manual Testing) ---
    def trigger_supply_check(self):
        self.save_config()
        self.set_global_status("Running (Supplies)", force=True)
        ClientPrintEx(Self(), 1, 1, "Starting Supply Check...")
        threading.Thread(target=BodCycler_CheckSupplies.check_supplies, daemon=True).start()

    def trigger_crafting(self):
        self.save_config()
        self.set_global_status("Running (Crafting)", force=True)
        ClientPrintEx(Self(), 1, 1, "Starting Crafting Engine...")
        threading.Thread(target=BodCycler_Crafting.run_crafting_cycle, daemon=True).start()

    def trigger_trade(self):
        self.save_config()
        self.set_global_status("Running (Trade)", force=True)
        ClientPrintEx(Self(), 1, 1, "Starting NPC Trade Loop...")
        threading.Thread(target=BodCycler_NPC_Trade.execute_trade_loop, daemon=True).start()

    def trigger_scan(self):
        self.save_config()
        self.set_global_status("Running (Scan)", force=True)
        ClientPrintEx(Self(), 1, 1, "Scanning Conserva Book...")
        threading.Thread(target=BodCycler_Scanner.run_scanner, daemon=True).start()

    def trigger_assemble(self):
        self.save_config()
        self.set_global_status("Running (Assembling)", force=True)
        ClientPrintEx(Self(), 1, 1, "Assembling Large BODs...")
        threading.Thread(target=BodCycler_Assembler.run_assembler, daemon=True).start()

    def trigger_take_bods(self):
        self.save_config()
        self.set_global_status("Running (BOD Collection)", force=True)
        ClientPrintEx(Self(), 1, 1, "Starting BOD Collection round...")
        threading.Thread(target=self._take_bods_thread, daemon=True).start()

    def _take_bods_thread(self):
        try:
            _home = self.config.get("home", {})
            _hx, _hy = _home.get("X", 0), _home.get("Y", 0)
            AddToSystemJournal(f"Manual BOD Collection: walking to standby ({_hx},{_hy})...")
            if _hx and _hy:
                newMoveXY(_hx, _hy, False, 1, True)
            time.sleep(2)
            Disconnect()
            BodCycler_TakeBods.run_take_bods_cycle()
            AddToSystemJournal("Manual BOD Collection complete.")
            self.set_global_status("Idle")
        except Exception as e:
            AddToSystemJournal(f"BOD Collection error: {e}")
            self.set_global_status("Error (See Journal)")

    # --- Conserva Manager Triggers ---
    def trigger_conserva_scan(self):
        self.save_config()
        self.set_global_status("Scanning Conserva Books...")
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                if self.vars["trim_tailor"].get():
                    cm.scan_all_books(self.config, "Tailor")
                if self.vars["trim_smith"].get():
                    cm.scan_all_books(self.config, "Smith")
                self.set_global_status("Idle")
            except Exception as e:
                AddToSystemJournal(f"Conserva Scan error: {e}")
                self.set_global_status("Error (See Journal)")
        threading.Thread(target=_run, daemon=True).start()

    def trigger_conserva_pull_prizes(self):
        """One-way: pull wanted prizes FROM overflow/later slots INTO Best/Tier2. Never pushes out."""
        self.save_config()
        self.set_global_status("Pulling prizes...")
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                cycle = "Tailor" if self.vars["trim_tailor"].get() else "Smith"
                cm.execute_trim(self.config, cycle, mode="pull_prizes")
                self.set_global_status("Idle")
            except Exception as e:
                AddToSystemJournal(f"Pull Prizes error: {e}")
                self.set_global_status("Error (See Journal)")
        threading.Thread(target=_run, daemon=True).start()

    def trigger_conserva_analyze(self):
        self.save_config()
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                if self.vars["trim_tailor"].get():
                    cm.analyze_and_log(self.config, "Tailor")
                if self.vars["trim_smith"].get():
                    cm.analyze_and_log(self.config, "Smith")
            except Exception as e:
                AddToSystemJournal(f"Conserva Analyze error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _clear_conserva_book(self, list_key, idx, label_widget, tier):
        self.config[list_key][idx] = 0
        label_widget.config(text=f"{idx+1}. {tier}: Not Set", fg="#888")

    def trigger_conserva_check_overflow(self):
        self._conserva_overflow_mode = True
        self.save_config()
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                cycle = "Tailor" if self.vars["trim_tailor"].get() else "Smith"
                cm.check_completable_sets(self.config, cycle, overflow_only=True)
            except Exception as e:
                AddToSystemJournal(f"Conserva Overflow Check error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def trigger_conserva_check(self):
        self._conserva_overflow_mode = False
        self.save_config()
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                cycle = "Tailor" if self.vars["trim_tailor"].get() else "Smith"
                cm.check_completable_sets(self.config, cycle)
            except Exception as e:
                AddToSystemJournal(f"Conserva Check Sets error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def trigger_conserva_next_set(self):
        """DLL extract + combine + route to Consegna in one click."""
        self.save_config()
        self.set_global_status("Combining set...")
        overflow = getattr(self, '_conserva_overflow_mode', False)
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                cycle = "Tailor" if self.vars["trim_tailor"].get() else "Smith"
                cm.extract_and_combine_next_set(self.config, cycle, overflow_only=overflow)
                self.set_global_status("Idle")
            except Exception as e:
                AddToSystemJournal(f"Conserva Combine error: {e}")
                self.set_global_status("Error (See Journal)")
        threading.Thread(target=_run, daemon=True).start()

    def _target_quick_scan_book(self):
        ClientPrintEx(Self(), 1, 1, "Target a BOD book to scan...")
        ClientRequestObjectTarget()
        start = time.time()
        while not ClientTargetResponsePresent():
            time.sleep(0.1)
            if time.time() - start > 15:
                return
        response = ClientTargetResponse()
        if response["ID"] > 0:
            self._quick_scan_serial = response["ID"]
            self._qs_label.config(text=f"Scan Book: {hex(self._quick_scan_serial)}", fg="navy")

    def _clear_quick_scan_book(self):
        self._quick_scan_serial = 0
        self._qs_label.config(text="Scan Book: Not Set", fg="#888")

    def trigger_fill_backpack_bod(self):
        """Fills 1 unfilled Small BOD in backpack. Auto-combines if Large is present."""
        self.save_config()
        self.set_global_status("Filling BOD...", force=True)
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                cycle = self.config.get("cycle_type", "Tailor")
                cm.fill_next_backpack_bod(self.config, cycle)
                self.set_global_status("Idle")
            except Exception as e:
                AddToSystemJournal(f"Fill BOD error: {e}")
                self.set_global_status("Error (See Journal)")
        threading.Thread(target=_run, daemon=True).start()

    def trigger_conserva_quick_scan(self):
        serial = getattr(self, '_quick_scan_serial', 0)
        if not serial:
            AddToSystemJournal("Quick Scan: No book targeted. Click Target first.")
            return
        self.save_config()
        self.set_global_status("Quick scanning...")
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                cycle = "Tailor" if self.vars["trim_tailor"].get() else "Smith"
                cm.quick_scan_report(self.config, cycle, book_serial=serial)
                self.set_global_status("Idle")
            except Exception as e:
                AddToSystemJournal(f"Quick Scan error: {e}")
                self.set_global_status("Error (See Journal)")
        threading.Thread(target=_run, daemon=True).start()

    def trigger_conserva_trim(self):
        """DLL-based: analyze + extract + route in one go."""
        self.save_config()
        self.set_global_status("Executing trim...")
        def _run():
            try:
                import importlib, BodCycler_ConservaManager as cm; importlib.reload(cm)
                cycle = "Tailor" if self.vars["trim_tailor"].get() else "Smith"
                cm.execute_trim(self.config, cycle, mode="all")
                self.set_global_status("Idle")
            except Exception as e:
                AddToSystemJournal(f"Conserva Route error: {e}")
                self.set_global_status("Error (See Journal)")
        threading.Thread(target=_run, daemon=True).start()

    # --- Navigation Helpers ---
    def test_travel(self, rune_key_name):
        threading.Thread(target=self._test_travel_thread, args=(rune_key_name,)).start()

    def _test_travel_thread(self, rune_key_name):
        rb_serial = self.config["travel"].get("RuneBook", 0)
        if rb_serial == 0: return
        try: rune_idx = int(self.vars[f"rune_{rune_key_name}"].get())
        except ValueError: return
        
        method = self.vars["travel_method"].get()
        offset = 5 if method == "Recall" else 7
        btn_id = offset + (rune_idx - 1) * 6
        
        UseObject(rb_serial)
        for _ in range(20):
            time.sleep(0.1)
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == 0x554B87F3:
                    NumGumpButton(i, btn_id)
                    return

    def _recall_home(self):
        """Recalls to WorkSpot1 rune then walks to config["home"] if not already there.
        - Concentration disturbed → retry same rune.
        - Location blocked → fall back to WorkSpot2 (backup rune).
        """
        home = self.config.get("home", {})
        hx, hy = home.get("X", 0), home.get("Y", 0)
        if not hx or not hy:
            AddToSystemJournal("_recall_home: home position not set — skipping.")
            return

        if GetX(Self()) == hx and GetY(Self()) == hy:
            return  # already home

        rb_serial = self.config.get("travel", {}).get("RuneBook", 0)
        if not rb_serial:
            AddToSystemJournal("_recall_home: no RuneBook configured.")
            return

        travel    = self.config.get("travel", {})
        runes_cfg = travel.get("Runes", {})
        method    = travel.get("Method", "Recall")
        offset    = 5 if method == "Recall" else 7

        # Try primary rune first, fall back to the "2" variant if blocked
        rune_sequence = ["WorkSpot1", "WorkSpot2"]
        rune_idx_iter = iter(rune_sequence)
        current_rune  = next(rune_idx_iter)

        start_x, start_y = GetX(Self()), GetY(Self())
        AddToSystemJournal(f"Not at home ({start_x},{start_y} vs {hx},{hy}). Recalling via {current_rune}...")

        while GetX(Self()) == start_x and GetY(Self()) == start_y:
            rune_idx = runes_cfg.get(current_rune, 1)
            btn_id   = offset + (rune_idx - 1) * 6

            cast_start = datetime.now()
            UseObject(rb_serial)
            Wait(450)

            gump_found = False
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == 0x554B87F3:
                    NumGumpButton(i, btn_id)
                    gump_found = True
                    break

            if not gump_found:
                AddToSystemJournal("_recall_home: runebook gump did not appear — retrying.")
                Wait(1000)
                continue

            # Wait up to 3s for landing or a journal error
            deadline = time.time() + 3.0
            while time.time() < deadline:
                Wait(100)
                now = datetime.now()
                if InJournalBetweenTimes("That location is blocked", cast_start, now) != -1:
                    next_rune = next(rune_idx_iter, None)
                    if next_rune:
                        AddToSystemJournal(f"_recall_home: {current_rune} blocked — trying {next_rune}.")
                        current_rune = next_rune
                    else:
                        AddToSystemJournal("_recall_home: all runes blocked — aborting.")
                        return
                    break
                if InJournalBetweenTimes("Your concentration is disturbed", cast_start, now) != -1:
                    AddToSystemJournal(f"_recall_home: concentration disturbed — retrying {current_rune}.")
                    Wait(1500)
                    break  # retry same rune
                if GetX(Self()) != start_x or GetY(Self()) != start_y:
                    break  # moved — recall succeeded

        newMoveXY(hx, hy, False, 1, True)
        Wait(600)

    # --- Live Dashboard Parsers ---
    def read_supplies_file(self):
        try:
            if os.path.exists(SUPPLY_FILE):
                mtime = os.path.getmtime(SUPPLY_FILE)
                if mtime > self.last_supply_mtime:
                    with open(SUPPLY_FILE, "r") as f:
                        data = json.load(f)
                        res = data.get("resources", {})
                        
                        self.vars["sup_iron"].set(f"Iron: {res.get('Ingots', 0)}")
                        self.vars["sup_dullcopper"].set(f"D.Copper: {res.get('DullCopper', 0)}")
                        self.vars["sup_shadowiron"].set(f"Shadow: {res.get('ShadowIron', 0)}")
                        self.vars["sup_copper"].set(f"Copper: {res.get('Copper', 0)}")
                        self.vars["sup_bronze"].set(f"Bronze: {res.get('Bronze', 0)}")
                        self.vars["sup_gold"].set(f"Gold: {res.get('Gold', 0)}")
                        self.vars["sup_agapite"].set(f"Agapite: {res.get('Agapite', 0)}")
                        self.vars["sup_verite"].set(f"Verite: {res.get('Verite', 0)}")
                        self.vars["sup_valorite"].set(f"Valorite: {res.get('Valorite', 0)}")
                        self.vars["sup_cloth"].set(f"Cloth: {res.get('Cloth', 0)}")
                        self.vars["sup_leather"].set(f"Leather: {res.get('Leather', 0)}")
                        self.vars["sup_spined"].set(f"Spined: {res.get('Spined', 0)}")
                        self.vars["sup_horned"].set(f"Horned: {res.get('Horned', 0)}")
                        self.vars["sup_barbed"].set(f"Barbed: {res.get('Barbed', 0)}")
                        
                    self.last_supply_mtime = mtime
        except Exception:
            pass

    def read_stats_file(self):
        try:
            if os.path.exists(STATS_FILE):
                mtime = os.path.getmtime(STATS_FILE)
                if mtime > self.last_stats_mtime:
                    with open(STATS_FILE, "r") as f:
                        data = json.load(f)
                        self.vars["stat_crafted"].set(f"BODs Filled: {data.get('crafted', 0)}")
                        self.vars["stat_small"].set(f"Small Prizes: {data.get('prized_small', 0)}")
                        self.vars["stat_large"].set(f"Large Prizes: {data.get('prized_large', 0)}")
                        self.vars["stat_prizes"].set(f"Prizes: {data.get('prizes_dropped', 0)}")
                    self.last_stats_mtime = mtime
        except Exception:
            pass

    def reset_stats(self):
        data = read_stats()
        data["crafted"] = 0
        data["prized_small"] = 0
        data["prized_large"] = 0
        data["prizes_dropped"] = 0
        data["bods_traded"] = 0
        data["mats_used"] = {}
        data["recovery_success"] = 0
        data["session_start"] = time.time()
        data["last_collection_time"] = time.time()   # prevent immediate collection on cycle start
        write_stats(data)
        self.read_stats_file()

    def update_timer(self):
        if not self.root: return
        self.read_supplies_file()
        self.read_stats_file()

        with _STATS_LOCK:
            start_time = STATS["start_time"]
            current_status = STATS["status"]

        if start_time:
            elapsed = datetime.now() - start_time
            self.vars["timer"].set(f"Time: {str(elapsed).split('.')[0]}")
        else:
            self.vars["timer"].set("Time: 00:00:00")

        self.vars["status"].set(f"Status: {current_status}")
        if self.running: self.root.after(1000, self.update_timer)

    # --- ORCHESTRATION: The Master Loop ---

    def set_global_status(self, status_text, force=False):
        """Updates the GUI and writes status to the stats file for worker scripts to read.
        Pass force=True when intentionally starting/stopping to bypass the stop guard."""
        with _STATS_LOCK:
            # Never let a "Running" sub-step overwrite an explicit Stop signal.
            # force=True bypasses this — used by start_cycling() to resume from Stopped.
            if not force and STATS["status"] == "Stopped" and "Running" in status_text:
                return
            STATS["status"] = status_text
        if self.root:
            self.root.after(0, lambda: self.vars["status"].set(f"Status: {status_text}"))
        set_status(status_text)

    def _is_stopped(self):
        with _STATS_LOCK:
            return STATS["status"] == "Stopped"

    def master_cycle_thread(self):
        AddToSystemJournal("=== MASTER CYCLE INITIATED ===")
        while not self._is_stopped():
            try:
                # STEP 0: Ensure character is at home before doing anything
                self._recall_home()

                # STEP 1: Check Supplies & Maintain Tools (must run before crafting)
                if self._is_stopped(): break
                self.set_global_status("Running (Supplies)")
                ClientPrintEx(Self(), 1, 1, "Master: Checking Supplies...")
                BodCycler_CheckSupplies.check_supplies()

                # STEP 2: Craft Items & Fill BODs
                if self._is_stopped(): break
                self.set_global_status("Running (Crafting)")
                ClientPrintEx(Self(), 1, 1, "Master: Filling BODs...")
                BodCycler_Crafting.run_crafting_cycle()

                # STEP 2.2: BOD Collection (if window is open)
                if self._is_stopped(): break
                try:
                    if BodCycler_TakeBods.should_collect_bods():
                        self.set_global_status("Running (BOD Collection)")
                        _home = load_config().get("home", {})
                        _hx, _hy = _home.get("X", 0), _home.get("Y", 0)
                        AddToSystemJournal(f"BOD collection due! Pausing ed4 → walking to standby ({_hx},{_hy})...")
                        if _hx and _hy:
                            newMoveXY(_hx, _hy, False, 1, True)
                        time.sleep(2)
                        Disconnect()
                        BodCycler_TakeBods.run_take_bods_cycle()
                        AddToSystemJournal("BOD Collection complete. Resuming crafting cycle.")
                except Exception as _te:
                    AddToSystemJournal(f"TakeBods check skipped: {_te}")

                # STEP 2.5: Assembly Check
                if self._is_stopped(): break

                try:
                    _cfg = load_config()
                    _conserva = _cfg.get("books", {}).get("Conserva", 0)
                    _inv_file = get_inventory_file(_conserva) if _conserva else None
                    if _inv_file and os.path.exists(_inv_file):
                        self.set_global_status("Running (Assembly Check)")
                        ClientPrintEx(Self(), 1, 1, "Master: Checking local inventory for sets...")

                        with open(_inv_file, "r") as _f:
                            _inv = json.load(_f)

                        _sets = BodCycler_Assembler.find_completable_sets(_inv)

                        if _sets:
                            sets_expected = len(_sets)
                            AddToSystemJournal(f"Assembly: {sets_expected} set(s) ready in JSON. Running Assembler...")
                            self.set_global_status("Running (Assembling)")
                            sets_completed = BodCycler_Assembler.run_assembler()
                            # Only re-scan when the assembly was incomplete (partial extraction
                            # failure leaves the actual book with more items than the JSON
                            # re-index assumes, causing append_to_inventory() to mis-number
                            # new items in future cycles). A clean run trusts the re-index.
                            if sets_completed < sets_expected:
                                AddToSystemJournal(f"Assembly: Only {sets_completed}/{sets_expected} set(s) completed — re-scanning to correct positions.")
                                BodCycler_Scanner.run_scanner()
                            else:
                                AddToSystemJournal(f"Assembly: All {sets_completed} set(s) completed. Positions re-indexed.")
                        else:
                            AddToSystemJournal("Assembly: No complete sets found in local records.")
                    else:
                        AddToSystemJournal("Assembly: Inventory file missing. Running one-time scan...")
                        BodCycler_Scanner.run_scanner()

                except Exception as _e:
                    AddToSystemJournal(f"Assembly step failed: {_e}")

                # STEP 3: Travel, Trade, & Return
                if self._is_stopped(): break
                self.set_global_status("Running (Trading)")
                ClientPrintEx(Self(), 1, 1, "Master: Commencing NPC Trade...")
                BodCycler_NPC_Trade.execute_trade_loop()

                # LOOP PAUSE
                if self._is_stopped(): break
                self.set_global_status("Running (Cooldown)")
                AddToSystemJournal("Cycle complete. Fumando una sigaretta...")

                for _ in range(3):
                    if self._is_stopped(): break
                    time.sleep(1)

            except Exception as e:
                AddToSystemJournal(f"CRITICAL ERROR in Master Cycle: {e}")
                self.set_global_status("Error (See Journal)")
                # Continue the loop rather than permanently breaking on transient errors

        save_performance_snapshot()
        AddToSystemJournal("=== MASTER CYCLE STOPPED ===")

    def start_cycling(self):
        with _STATS_LOCK:
            if "Running" in STATS["status"]:
                AddToSystemJournal("Cycle is already running!")
                return
            STATS["start_time"] = datetime.now()

        self.set_global_status("Running", force=True)
        self.save_config()
        self.reset_stats()

        # Launch the orchestrator in the background so the GUI doesn't freeze
        threading.Thread(target=self.master_cycle_thread, daemon=True).start()

    def stop_cycling(self):
        with _STATS_LOCK:
            STATS["start_time"] = None
        # Writing 'Stopped' to the file will trigger the check_abort() breaks in the worker scripts
        self.set_global_status("Stopped")
        ClientPrintEx(Self(), 1, 1, "Cycle Stopped")
        AddToSystemJournal("User requested cycle stop. Safely aborting scripts...")

    def run(self):
        from tkinter import ttk
        self.load_config()
        self.root = Tk()
        self.root.title(f"{CharName()} — BOD Cycler")

        BG = "#ECE9D8"
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.update_idletasks()
        self.root.geometry("")   # let Tk size to fit content
        self.root.minsize(660, 470)

        try:
            if os.path.exists(ICON_FILE): self.root.iconbitmap(ICON_FILE)
        except Exception:
            pass

        def _btn(parent, text, cmd, color=None, **kw):
            props = dict(font=("Tahoma", 8), relief=RAISED, bd=2,
                         bg=color or BG, activebackground=color or BG)
            props.update(kw)
            return Button(parent, text=text, command=cmd, **props)

        def _lbl(parent, text="", textvariable=None, bold=False, **kw):
            props = dict(bg=BG, fg="black", font=("Tahoma", 8, "bold") if bold else ("Tahoma", 8))
            props.update(kw)
            if textvariable:
                return Label(parent, textvariable=textvariable, **props)
            return Label(parent, text=text, **props)

        # ── Status bar ────────────────────────────────────────────────
        self.vars["status"] = StringVar(value="Status: Idle")
        self.vars["timer"]  = StringVar(value="Time: 00:00:00")
        f_status = Frame(self.root, bg="#003399", pady=4)
        f_status.pack(fill="x")
        Label(f_status, textvariable=self.vars["status"],
              bg="#003399", fg="white", font=("Tahoma", 9, "bold")).pack(side=LEFT, padx=10)
        Label(f_status, textvariable=self.vars["timer"],
              bg="#003399", fg="#AADDFF", font=("Courier", 9)).pack(side=RIGHT, padx=10)

        # ── Notebook ─────────────────────────────────────────────────
        style = ttk.Style()
        try:    style.theme_use("xpnative")
        except Exception:
            try: style.theme_use("winnative")
            except Exception: pass
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=(4, 2))

        # ═══════════════════════════════════════════════
        # TAB 1 — Actions
        # ═══════════════════════════════════════════════
        t1 = Frame(nb, bg=BG, padx=8, pady=6)
        nb.add(t1, text=" Actions ")

        # Mode + Trades/Cycle row
        f_top = Frame(t1, bg=BG)
        f_top.pack(fill="x", pady=(0, 3))
        _lbl(f_top, "Mode:").pack(side=LEFT)
        self.vars["cycle_type"] = StringVar(value=self.config.get("cycle_type", "Tailor"))
        for val in ("Tailor", "Smith"):
            Radiobutton(f_top, text=val, variable=self.vars["cycle_type"], value=val,
                        bg=BG, font=("Tahoma", 8)).pack(side=LEFT, padx=2)
        _lbl(f_top, "   Trades/Cycle:").pack(side=LEFT)
        self.vars["target_trades"] = StringVar(
            value=str(self.config.get("trade", {}).get("target_trades", 2)))
        Entry(f_top, textvariable=self.vars["target_trades"],
              width=4, font=("Tahoma", 8)).pack(side=LEFT, padx=(3, 0))

        # Action buttons row
        f_act = Frame(t1, bg=BG)
        f_act.pack(fill="x", pady=2)
        _btn(f_act, "Trade",         self.trigger_trade,            "#90EE90").pack(side=LEFT, padx=2)
        _btn(f_act, "Craft",         self.trigger_crafting,         "#FFD700").pack(side=LEFT, padx=2)
        _btn(f_act, "Scan",          self.trigger_scan,             "#FFB6C1").pack(side=LEFT, padx=2)
        _btn(f_act, "Assemble",      self.trigger_assemble,         "#DDA0DD").pack(side=LEFT, padx=2)
        _btn(f_act, "Check Prizes",  self.check_assembly_readiness, "#B0E0E6").pack(side=LEFT, padx=2)
        _btn(f_act, "Prize Filter…", self.open_prize_filter,        "#FFA07A").pack(side=LEFT, padx=2)

        # Buy Cloth row
        f_cloth = Frame(t1, bg=BG)
        f_cloth.pack(fill="x", pady=2)
        _lbl(f_cloth, "Buy Cloth:").pack(side=LEFT)
        self.vars["buy_cloth_enabled"] = BooleanVar(
            value=bool(self.config.get("trade", {}).get("buy_cloth_enabled", True)))
        for text, val in (("ON", True), ("OFF", False)):
            Radiobutton(f_cloth, text=text, variable=self.vars["buy_cloth_enabled"], value=val,
                        bg=BG, font=("Tahoma", 8)).pack(side=LEFT, padx=2)
        self.vars["buy_cloth_amount"] = StringVar(
            value=str(self.config.get("trade", {}).get("buy_cloth_amount", 80)))
        Entry(f_cloth, textvariable=self.vars["buy_cloth_amount"],
              width=5, font=("Tahoma", 8)).pack(side=LEFT, padx=(8, 0))

        # Supplies panel
        f_sup = Frame(t1, bg="#DDD8CC", relief=SUNKEN, bd=1)
        f_sup.pack(fill="x", pady=(6, 2))
        for col in range(3):
            f_sup.columnconfigure(col, weight=1)
        for k, v in [
            ("sup_iron",       "Iron: 0"),
            ("sup_cloth",      "Cloth: 0"),
            ("sup_leather",    "Leather: 0"),
            ("sup_dullcopper", "D.Copper: 0"),
            ("sup_shadowiron", "Shadow: 0"),
            ("sup_copper",     "Copper: 0"),
            ("sup_bronze",     "Bronze: 0"),
            ("sup_gold",       "Gold: 0"),
            ("sup_agapite",    "Agapite: 0"),
            ("sup_verite",     "Verite: 0"),
            ("sup_valorite",   "Valorite: 0"),
            ("sup_spined",     "Spined: 0"),
            ("sup_horned",     "Horned: 0"),
            ("sup_barbed",     "Barbed: 0"),
        ]:
            self.vars[k] = StringVar(value=v)
        # Row 0: Iron | Cloth | Leather (bold totals)
        for c, (k, fg) in enumerate([("sup_iron","#555555"),("sup_cloth","#222"),("sup_leather","#222")]):
            Label(f_sup, textvariable=self.vars[k], bg="#DDD8CC",
                  font=("Tahoma", 8, "bold"), fg=fg).grid(row=0, column=c, padx=10, pady=2)
        # Rows 1-3: colored ores (3×3 grid)
        for row_idx, row_items in enumerate([
            [("sup_dullcopper","#777777"), ("sup_shadowiron","#333333"), ("sup_copper",  "#B87333")],
            [("sup_bronze",    "#8B7355"), ("sup_gold",      "#B8860B"), ("sup_agapite", "#8B2500")],
            [("sup_verite",    "#005500"), ("sup_valorite",  "#00008B")],
        ], start=1):
            for c, (k, fg) in enumerate(row_items):
                Label(f_sup, textvariable=self.vars[k], bg="#DDD8CC",
                      font=("Tahoma", 8), fg=fg).grid(row=row_idx, column=c, padx=10, pady=1)
        # Row 4: leather grades — Spined=blue, Horned=dark red, Barbed=green (matches in-game)
        for c, (k, fg) in enumerate([("sup_spined","#000066"),("sup_horned","#660000"),("sup_barbed","#004400")]):
            Label(f_sup, textvariable=self.vars[k], bg="#DDD8CC",
                  font=("Tahoma", 8), fg=fg).grid(row=4, column=c, padx=10, pady=1)

        # Live Stats section
        lf_stats = LabelFrame(t1, text="Live Stats", bg=BG,
                              font=("Tahoma", 8, "bold"), relief=GROOVE, bd=2)
        lf_stats.pack(fill="x", pady=(6, 2))
        self.vars["stat_crafted"] = StringVar(value="BODs Filled: 0")
        self.vars["stat_small"]   = StringVar(value="Small Prizes: 0")
        self.vars["stat_large"]   = StringVar(value="Large Prizes: 0")
        self.vars["stat_prizes"]  = StringVar(value="Prizes: 0")
        f_srow = Frame(lf_stats, bg=BG)
        f_srow.pack(fill="x", pady=2)
        for (k, c) in [("stat_crafted","darkblue"),("stat_small","darkgreen"),
                       ("stat_large","darkmagenta"),("stat_prizes","darkorange")]:
            Label(f_srow, textvariable=self.vars[k], fg=c,
                  font=("Tahoma", 9, "bold"), bg=BG).pack(side=LEFT, expand=True)
        f_sbtns = Frame(lf_stats, bg=BG)
        f_sbtns.pack(pady=4)
        _btn(f_sbtns, "Reset Stats", self.reset_stats).pack(side=LEFT, padx=4)
        _btn(f_sbtns, "Save Report", save_performance_snapshot, "#C8E6C9").pack(side=LEFT, padx=4)

        # ═══════════════════════════════════════════════
        # TAB 2 — Books
        # ═══════════════════════════════════════════════
        t2 = Frame(nb, bg=BG, padx=8, pady=8)
        nb.add(t2, text=" Books ")

        for section_label, cat_key in [("Tailor Books", "books_tailor"), ("Smith Books", "books_smith")]:
            Label(t2, text=f"── {section_label} ──", bg=BG,
                  font=("Tahoma", 8, "bold"), fg="#555").pack(fill="x", pady=(8, 2))
            for key in ["Origine", "Conserva", "Riprova", "Consegna", "Scartare"]:
                s      = self.config.get(cat_key, {}).get(key, 0)
                t_text = f"{key}: {hex(s)}" if s else f"{key}: Not Set"
                fg_c   = "navy" if s else "red"
                f_row  = Frame(t2, bg=BG)
                f_row.pack(fill="x", pady=2)
                lw = _lbl(f_row, t_text, fg=fg_c, width=24, anchor="w")
                lw.pack(side=LEFT)
                _btn(f_row, "Target",
                     lambda k=key, c=cat_key, l=lw: self.get_target(c, k, l),
                     width=8).pack(side=LEFT, padx=6)

        # ═══════════════════════════════════════════════
        # TAB 3 — Setup
        # ═══════════════════════════════════════════════
        t3 = Frame(nb, bg=BG, padx=8, pady=8)
        nb.add(t3, text=" Setup ")

        setup_targets = [
            ("containers", "MaterialCrate",  "Material Crate"),
            ("containers", "TrashBarrel",    "Trash Barrel"),
            ("containers", "ClothDyeTub",    "Cloth Dye Tub"),
            ("containers", "RewardCrate",    "Reward Crate"),
            ("containers", "BodBookCrate",     "BodBook Crate"),
            ("containers", "ProspectorCrate", "Prospector Crate"),
            ("containers", "PowderCrate",     "Powder Crate"),
            ("travel",     "RuneBook",        "Rune Book"),
        ]
        for cat, key, label in setup_targets:
            s      = self.config[cat].get(key, 0)
            t_text = f"{label}: {hex(s)}" if s else f"{label}: Not Set"
            fg_c   = "navy" if s else "red"
            f_row  = Frame(t3, bg=BG)
            f_row.pack(fill="x", pady=3)
            lw = _lbl(f_row, t_text, fg=fg_c, width=24, anchor="w")
            lw.pack(side=LEFT)
            _btn(f_row, "Target",
                 lambda k=key, ca=cat, l=lw: self.get_target(ca, k, l),
                 width=8).pack(side=LEFT, padx=6)

        # ── Talisman Swap ──────────────────────────────────────────────────────
        Label(t3, text="── Talisman Swap ──", bg=BG,
              font=("Tahoma", 8, "bold"), fg="#555").pack(fill="x", pady=(10, 2))
        Label(t3, text="Keep BOTH talismans in backpack. Auto-equip fires on cycle start.",
              bg=BG, font=("Tahoma", 7, "italic"), fg="#884400",
              wraplength=220, justify="left").pack(fill="x", pady=(0, 4))
        for mode in ("Tailor", "Smith"):
            s      = self.config.get("talismans", {}).get(mode, 0)
            t_text = f"{mode} Talisman: {hex(s)}" if s else f"{mode} Talisman: Not Set"
            fg_c   = "navy" if s else "red"
            f_row  = Frame(t3, bg=BG)
            f_row.pack(fill="x", pady=2)
            lw = _lbl(f_row, t_text, fg=fg_c, width=24, anchor="w")
            lw.pack(side=LEFT)
            _btn(f_row, "Target",
                 lambda m=mode, l=lw: self.get_target("talismans", m, l),
                 width=8).pack(side=LEFT, padx=6)

        hx       = self.config["home"].get("X", 0)
        home_txt = f"Home: {hx}, ..." if hx != 0 else "Home: Not Set"
        home_fg  = "navy" if hx != 0 else "red"
        f_home   = Frame(t3, bg=BG)
        f_home.pack(fill="x", pady=3)
        lbl_spot = _lbl(f_home, home_txt, fg=home_fg, width=24, anchor="w")
        lbl_spot.pack(side=LEFT)
        _btn(f_home, "Set",   lambda: self.set_home_spot(lbl_spot), width=4).pack(side=LEFT, padx=2)
        _btn(f_home, "Go To", self.go_to_home_spot, width=5).pack(side=LEFT, padx=2)

        # ═══════════════════════════════════════════════
        # TAB 4 — Travel
        # ═══════════════════════════════════════════════
        t4 = Frame(nb, bg=BG, padx=8, pady=8)
        nb.add(t4, text=" Travel ")

        f_meth = Frame(t4, bg=BG)
        f_meth.pack(fill="x", pady=(0, 8))
        _lbl(f_meth, "Method:").pack(side=LEFT)
        self.vars["travel_method"] = StringVar(value=self.config["travel"].get("Method", "Recall"))
        for text, val in (("Recall", "Recall"), ("Sacred Journey", "SacredJourney")):
            Radiobutton(f_meth, text=text, variable=self.vars["travel_method"], value=val,
                        bg=BG, font=("Tahoma", 8)).pack(side=LEFT, padx=4)

        f_runes = Frame(t4, bg=BG)
        f_runes.pack()
        r_keys = ["WorkSpot1", "WorkSpot2", "Tailor1", "Tailor2", "Smith1", "Smith2"]
        for idx, key in enumerate(r_keys):
            row_r, col_r = divmod(idx, 2)
            f_r = Frame(f_runes, bg=BG)
            f_r.grid(row=row_r, column=col_r, padx=12, pady=4, sticky="w")
            _lbl(f_r, f"{key}:", width=10, anchor="w").pack(side=LEFT)
            var = StringVar(value=str(self.config["travel"]["Runes"].get(key, 1)))
            self.vars[f"rune_{key}"] = var
            Entry(f_r, textvariable=var, width=3, font=("Tahoma", 8)).pack(side=LEFT, padx=3)
            _btn(f_r, "Go", lambda k=key: self.test_travel(k), width=3).pack(side=LEFT, padx=2)

        # ═══════════════════════════════════════════════
        # TAB 5 — Bots
        # ═══════════════════════════════════════════════
        t5 = Frame(nb, bg=BG, padx=8, pady=8)
        nb.add(t5, text=" Bots ")

        bots_cfg = self.config.get("bots", {})
        for var_key, label, default in [
            ("crafter_profile",    "Crafter Profile:",    bots_cfg.get("crafter_profile", "ed4")),
            ("collector_profiles", "Collector Profiles:", ", ".join(bots_cfg.get("collector_profiles", []))),
        ]:
            f_r = Frame(t5, bg=BG)
            f_r.pack(fill="x", pady=4)
            _lbl(f_r, label, width=18, anchor="w").pack(side=LEFT)
            self.vars[var_key] = StringVar(value=default)
            Entry(f_r, textvariable=self.vars[var_key], width=22,
                  font=("Tahoma", 8)).pack(side=LEFT, padx=4)
        _lbl(t5, "(collectors: comma-separated)", fg="#888").pack(anchor="w", padx=4)
        _btn(t5, "Take BODs Now", self.trigger_take_bods, "#87CEEB",
             font=("Tahoma", 9, "bold"), width=16).pack(pady=(10, 4))

        # ═══════════════════════════════════════════════
        # TAB 6 — Conserva Manager
        # ═══════════════════════════════════════════════
        t6 = Frame(nb, bg=BG, padx=8, pady=6)
        nb.add(t6, text=" Conserva ")

        # Row 1: Action buttons (left) + Conserva Crate target (right)
        f_top6 = Frame(t6, bg=BG)
        f_top6.pack(fill="x", pady=(0, 4))
        _btn(f_top6, "Scan All",      self.trigger_conserva_scan,              "#FFB6C1").pack(side=LEFT, padx=2)
        _btn(f_top6, "Analyze",      self.trigger_conserva_analyze,          "#B0E0E6").pack(side=LEFT, padx=2)
        _btn(f_top6, "Pull Prizes",  self.trigger_conserva_pull_prizes,      "#E8D0FF").pack(side=LEFT, padx=2)
        _btn(f_top6, "Trim All",     self.trigger_conserva_trim,             "#90EE90").pack(side=LEFT, padx=2)

        # Row 2: Set assembly + quick scan
        f_sets6 = Frame(t6, bg=BG)
        f_sets6.pack(fill="x", pady=(0, 4))
        _btn(f_sets6, "Check Sets",  self.trigger_conserva_check,    "#DDA0DD").pack(side=LEFT, padx=2)
        _btn(f_sets6, "Combine Set", self.trigger_conserva_next_set, "#FFD700").pack(side=LEFT, padx=2)
        _btn(f_sets6, "Fill BOD",    self.trigger_fill_backpack_bod, "#98FB98").pack(side=LEFT, padx=2)
        # Quick scan: target a book + scan it for prizes/filled BODs
        Label(f_sets6, text="  ", bg=BG).pack(side=LEFT)  # spacer
        self._quick_scan_serial = 0
        qs_text = "Scan Book: Not Set"
        self._qs_label = _lbl(f_sets6, qs_text, fg="#888", width=18, anchor="w")
        self._qs_label.pack(side=LEFT)
        _btn(f_sets6, "Target",
             lambda: self._target_quick_scan_book(),
             width=6).pack(side=LEFT, padx=2)
        _btn(f_sets6, "X",
             lambda: self._clear_quick_scan_book(),
             width=2, bg="#FFAAAA").pack(side=LEFT, padx=1)
        _btn(f_sets6, "Scan",
             self.trigger_conserva_quick_scan, "#FFE4B5",
             width=5).pack(side=LEFT, padx=2)
        cc_serial = self.config["containers"].get("ConservaCrate", 0)
        cc_text = f"Crate: {hex(cc_serial)}" if cc_serial else "Crate: Not Set"
        cc_fg = "navy" if cc_serial else "red"
        _btn(f_top6, "Target",
             lambda: self.get_target("containers", "ConservaCrate", lw_cc),
             width=6).pack(side=RIGHT, padx=2)
        lw_cc = _lbl(f_top6, cc_text, fg=cc_fg, anchor="e")
        lw_cc.pack(side=RIGHT, padx=2)

        # Tailor section: toggle + 5 book rows
        for section_label, list_key, trim_var_key in [
            ("Tailor", "conserva_books_tailor", "trim_tailor"),
            ("Smith",  "conserva_books_smith",  "trim_smith"),
        ]:
            f_hdr = Frame(t6, bg=BG)
            f_hdr.pack(fill="x", pady=(6, 1))
            self.vars[trim_var_key] = BooleanVar(value=(section_label == "Tailor"))
            Checkbutton(f_hdr, text=f"Trim {section_label}", variable=self.vars[trim_var_key],
                        bg=BG, font=("Tahoma", 8, "bold")).pack(side=LEFT)

            book_list = self.config.get(list_key, [0]*5)
            for i in range(5):
                s = book_list[i] if i < len(book_list) else 0
                tier = "Best" if i == 0 else ("Tier 2" if i <= 2 else "Overflow")
                t_text = f"{i+1}. {tier}: {hex(s)}" if s else f"{i+1}. {tier}: Not Set"
                fg_c = "navy" if s else "#888"
                f_row = Frame(t6, bg=BG)
                f_row.pack(fill="x", pady=1)
                lw = _lbl(f_row, t_text, fg=fg_c, width=24, anchor="w")
                lw.pack(side=LEFT)
                _btn(f_row, "Target",
                     lambda idx=i, c=list_key, l=lw: self.get_target(c, str(idx), l),
                     width=6).pack(side=LEFT, padx=2)
                _btn(f_row, "X",
                     lambda idx=i, c=list_key, l=lw, t=tier: self._clear_conserva_book(c, idx, l, t),
                     width=2, bg="#FFAAAA").pack(side=LEFT, padx=1)

        # ── Bottom controls ────────────────────────────────────────────
        f_ctl = Frame(self.root, bg=BG, pady=6)
        f_ctl.pack(fill="x", padx=10)
        _btn(f_ctl, "Save Config", self.save_config, width=12).pack(side=LEFT, padx=4)
        Button(f_ctl, text="START CYCLE", command=self.start_cycling,
               bg="#1A7A1A", fg="white", font=("Tahoma", 9, "bold"),
               relief=RAISED, bd=2, width=14).pack(side=LEFT, padx=4)
        Button(f_ctl, text="STOP", command=self.stop_cycling,
               bg="#BB0000", fg="white", font=("Tahoma", 9, "bold"),
               relief=RAISED, bd=2, width=10).pack(side=LEFT, padx=4)

        self.read_supplies_file()
        self.read_stats_file()
        self.update_timer()
        self.root.mainloop()

    def open_prize_filter(self):
        from tkinter import ttk
        try:
            from bod_data import prize_names
        except ImportError:
            prize_names = {}

        BG = "#ECE9D8"
        popup = Toplevel(self.root)
        popup.title("Prize Filter")
        popup.geometry("300x480")
        popup.resizable(False, True)
        popup.grab_set()
        popup.configure(bg=BG)

        prize_filter = self.config.get("prize_filter", DEFAULT_CONFIG.get("prize_filter", {}))
        tailor_on = set(prize_filter.get("tailor", [23, 24]))
        smith_on  = set(prize_filter.get("smith",  [12, 17, 19, 20, 21, 22]))
        tailor_vars = {}
        smith_vars  = {}

        # Scrollable content area
        canvas = Canvas(popup, bg=BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(popup, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=RIGHT, fill="y")
        canvas.pack(fill="both", expand=True, padx=6, pady=4)
        inner = Frame(canvas, bg=BG)
        _cw   = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_resize(e):
            canvas.itemconfig(_cw, width=e.width)
        inner.bind("<Configure>", _on_inner_resize)
        canvas.bind("<Configure>", _on_canvas_resize)

        # Tailor section
        Label(inner, text="── Tailor ──", bg=BG,
              font=("Tahoma", 9, "bold"), fg="#003399").pack(anchor="w", pady=(4, 2), padx=6)
        for pid in (23, 24):
            name = prize_names.get(pid, f"Prize #{pid}")
            v = IntVar(value=1 if pid in tailor_on else 0)
            tailor_vars[pid] = v
            Checkbutton(inner, text=f"#{pid}: {name}", variable=v,
                        bg=BG, font=("Tahoma", 8)).pack(anchor="w", padx=14)

        # Smith section
        Label(inner, text="── Smith ──", bg=BG,
              font=("Tahoma", 9, "bold"), fg="#8B0000").pack(anchor="w", pady=(8, 2), padx=6)
        for pid in range(1, 23):
            name = prize_names.get(pid, f"Prize #{pid}")
            v = IntVar(value=1 if pid in smith_on else 0)
            smith_vars[pid] = v
            Checkbutton(inner, text=f"#{pid}: {name}", variable=v,
                        bg=BG, font=("Tahoma", 8)).pack(anchor="w", padx=14)

        # Buttons
        f_btns = Frame(popup, bg=BG, pady=6)
        f_btns.pack(fill="x", padx=8)

        def _save_close():
            self.config.setdefault("prize_filter", {})
            self.config["prize_filter"]["tailor"] = [pid for pid, v in tailor_vars.items() if v.get()]
            self.config["prize_filter"]["smith"]  = [pid for pid, v in smith_vars.items()  if v.get()]
            self.save_config()
            popup.destroy()

        Button(f_btns, text="Save & Close", command=_save_close,
               bg="#1A7A1A", fg="white", font=("Tahoma", 9, "bold"),
               relief=RAISED, bd=2).pack(side=RIGHT, padx=4)
        Button(f_btns, text="Cancel", command=popup.destroy,
               font=("Tahoma", 8), relief=RAISED, bd=2, bg=BG).pack(side=RIGHT, padx=2)

    def check_assembly_readiness(self):
        """
        Reads inventory.json and reports completable sets WITHOUT touching the game client.
        Sets and their components are reported in reverse-position order (mirrors Assembler sweep).
        """
        import json, os
        from bod_data import LARGE_COMPONENTS, prize_names, get_prize_number

        _conserva = self.config.get("books", {}).get("Conserva", 0)
        _inv_file = get_inventory_file(_conserva) if _conserva else None
        if not _inv_file or not os.path.exists(_inv_file):
            AddToSystemJournal("Assembly Check: inventory.json not found. Run a Scan first.")
            return

        try:
            with open(_inv_file, "r") as f:
                inventory = json.load(f)
        except Exception as e:
            AddToSystemJournal(f"Assembly Check: Failed to read inventory.json — {e}")
            return

        try:
            sets = BodCycler_Assembler.find_completable_sets(inventory)
        except Exception as e:
            AddToSystemJournal(f"Assembly Check: Error running find_completable_sets — {e}")
            return

        AddToSystemJournal("========================================")
        AddToSystemJournal(f"ASSEMBLY CHECK: {len(sets)} completable set(s) found in JSON")
        AddToSystemJournal("========================================")

        if not sets:
            AddToSystemJournal("No complete sets ready. Keep collecting small BODs.")
        else:
            # --- FIX 2: sort sets by large pos descending (mirrors Reverse Sweep order) ---
            sets.sort(key=lambda s: s['large'].get('pos', 0), reverse=True)

            for i, s in enumerate(sets, 1):
                large = s['large']
                smalls = s['smalls']

                # --- FIX 1: compute prize_id live from bod_data if not stored ---
                prize_id = large.get('prize_id')
                if not prize_id:
                    cat      = large.get('category', '')
                    mat      = large.get('material', '')
                    amt      = large.get('amount', 0)
                    qual     = large.get('quality', 'Normal')
                    prize_id = get_prize_number(cat, mat, amt, qual)
                    

                reward_label = prize_names.get(prize_id, f"Prize #{prize_id}") if prize_id else "No Prize"
                cat  = large.get('category', large.get('item', '?'))
                mat  = large.get('material', '?')
                qual = large.get('quality', '?')
                amt  = large.get('amount', '?')

                # --- FIX 2: sort smalls descending by pos (mirrors Reverse Sweep order) ---
                smalls_sorted = sorted(smalls, key=lambda x: x.get('pos', 0), reverse=True)
                small_positions = ', '.join(str(x.get('pos', '?')) for x in smalls_sorted)

                AddToSystemJournal(
                    f"  Set #{i}: {cat} | {mat} {qual} x{amt} "
                    f"-> {reward_label} "
                    f"[Large @ pos {large.get('pos', '?')} | "
                    f"Smalls (high->low): {small_positions}]"
                )

        AddToSystemJournal("========================================")


if __name__ == '__main__':
    app = BodCyclerGUI()
    app.run()