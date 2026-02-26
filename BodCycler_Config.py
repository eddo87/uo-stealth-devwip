from stealth import *
import os
import json
import threading
import time
import importlib
import BodCycler_AI_Debugger
from tkinter import *
from datetime import datetime
from BodCycler_Utils import set_status

# Import the logic modules
try:
    import BodCycler_CheckSupplies
except ImportError:
    pass

try:
    import BodCycler_Crafting
except ImportError:
    pass

try:
    import BodCycler_NPC_Trade
except ImportError:
    pass

try:
    import BodCycler_Scanner
except ImportError:
    pass

try:
    import BodCycler_Assembler
except ImportError:
    pass



# --- Configuration & Globals ---
CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
SUPPLY_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_supplies.json"
STATS_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_stats.json"
INVENTORY_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_inventory.json"

STATS = {
    "start_time": None,
    "status": "Idle"
}

DEFAULT_CONFIG = {
    "cycle_type": "Tailor", 
    "trade": {
        "target_trades": 2,
        "buy_cloth_amount": 80
    },
    "books": {
        "Origine": 0,   "Conserva": 0,  "Riprova": 0,   "Consegna": 0,  "Scartare": 0
    },
    "containers": {
        "MaterialCrate": 0, "TrashBarrel": 0, "ClothDyeTub": 0
    },
    "travel": {
        "RuneBook": 0, "Method": "Recall",
        "Runes": {
            "WorkSpot1": 1, "WorkSpot2": 2, "Tailor1": 3,
            "Tailor2": 7,   "Smith1": 8,    "Smith2": 9
        }
    },
    "home": { "X": 0, "Y": 0, "Z": 0 }
}

class BodCyclerGUI(threading.Thread):
    def __init__(self):
        super(BodCyclerGUI, self).__init__(daemon=True)
        self.config = DEFAULT_CONFIG.copy()
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
        if "trade" not in self.config: self.config["trade"] = {"target_trades": 2, "buy_cloth_amount": 80}

    def save_config(self):
        for name, var in self.vars.items():
            if name.startswith("rune_"):
                key = name.replace("rune_", "")
                try: self.config["travel"]["Runes"][key] = int(var.get())
                except: pass
        if "travel_method" in self.vars:
            self.config["travel"]["Method"] = self.vars["travel_method"].get()
        if "cycle_type" in self.vars:
            self.config["cycle_type"] = self.vars["cycle_type"].get()
            
        if "target_trades" in self.vars:
            try: self.config["trade"]["target_trades"] = int(self.vars["target_trades"].get())
            except: pass
        if "buy_cloth_amount" in self.vars:
            try: self.config["trade"]["buy_cloth_amount"] = int(self.vars["buy_cloth_amount"].get())
            except: pass

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
            if category == "books": self.config["books"][key] = serial
            elif category == "containers": self.config["containers"][key] = serial
            elif category == "travel": self.config["travel"][key] = serial
            
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
        ClientPrintEx(Self(), 1, 1, "Starting Supply Check...")
        try:
            import BodCycler_CheckSupplies
            importlib.reload(BodCycler_CheckSupplies) 
            threading.Thread(target=BodCycler_CheckSupplies.check_supplies, daemon=True).start()
        except Exception as e:
            AddToSystemJournal(f"Failed to load BodCycler_CheckSupplies: {e}")
            
    def trigger_crafting(self):
        self.save_config()
        ClientPrintEx(Self(), 1, 1, "Starting Crafting Engine...")
        try:
            import BodCycler_Crafting
            importlib.reload(BodCycler_Crafting) 
            threading.Thread(target=BodCycler_Crafting.run_crafting_cycle, daemon=True).start()
        except Exception as e:
            AddToSystemJournal(f"Failed to load BodCycler_Crafting: {e}")

    def trigger_trade(self):
        self.save_config()
        ClientPrintEx(Self(), 1, 1, "Starting NPC Trade Loop...")
        try:
            import BodCycler_NPC_Trade
            importlib.reload(BodCycler_NPC_Trade) 
            threading.Thread(target=BodCycler_NPC_Trade.execute_trade_loop, daemon=True).start()
        except Exception as e:
            AddToSystemJournal(f"Failed to load BodCycler_NPC_Trade: {e}")

    def trigger_scan(self):
        self.save_config()
        ClientPrintEx(Self(), 1, 1, "Scanning Conserva Book...")
        try:
            import BodCycler_Scanner
            importlib.reload(BodCycler_Scanner) 
            threading.Thread(target=BodCycler_Scanner.run_scanner, daemon=True).start()
        except Exception as e:
            AddToSystemJournal(f"Failed to load BodCycler_Scanner: {e}")

    def trigger_assemble(self):
        self.save_config()
        ClientPrintEx(Self(), 1, 1, "Assembling Large BODs...")
        try:
            import BodCycler_Assembler
            importlib.reload(BodCycler_Assembler) 
            threading.Thread(target=BodCycler_Assembler.run_assembler, daemon=True).start()
        except Exception as e:
            AddToSystemJournal(f"Failed to load BodCycler_Assembler: {e}")

    # --- Navigation Helpers ---
    def test_travel(self, rune_key_name):
        threading.Thread(target=self._test_travel_thread, args=(rune_key_name,)).start()

    def _test_travel_thread(self, rune_key_name):
        rb_serial = self.config["travel"].get("RuneBook", 0)
        if rb_serial == 0: return
        try: rune_idx = int(self.vars[f"rune_{rune_key_name}"].get())
        except: return
        
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
                    self.last_stats_mtime = mtime
        except Exception:
            pass

    def reset_stats(self):
        data = read_stats()
        data["crafted"] = 0
        data["prized_small"] = 0
        data["prized_large"] = 0
        data["mats_used"] = {}
        data["recovery_success"] = 0
        write_stats(data)
        self.read_stats_file()

    def update_timer(self):
        if not self.root: return
        self.read_supplies_file()
        self.read_stats_file()
        
        if STATS["start_time"]:
            elapsed = datetime.now() - STATS["start_time"]
            self.vars["timer"].set(f"Time: {str(elapsed).split('.')[0]}")
        else: self.vars["timer"].set("Time: 00:00:00")
        
        self.vars["status"].set(f"Status: {STATS['status']}")
        if self.running: self.root.after(1000, self.update_timer)

    # --- ORCHESTRATION: The Master Loop ---

    def set_global_status(self, status_text):
        """Updates the GUI and writes status to the stats file for worker scripts to read."""
        STATS["status"] = status_text
        self.vars["status"].set(f"Status: {status_text}")
        set_status(status_text)

    def master_cycle_thread(self):
        AddToSystemJournal("=== MASTER CYCLE INITIATED ===")
        while STATS["status"] != "Stopped":
            try:
                # STEP 1: Check Supplies & Maintain Tools
                if STATS["status"] == "Stopped": break
                self.set_global_status("Running (Supplies)")
                ClientPrintEx(Self(), 1, 1, "Master: Checking Supplies...")
                import BodCycler_CheckSupplies
                importlib.reload(BodCycler_CheckSupplies)
                BodCycler_CheckSupplies.check_supplies()
                
                # STEP 2: Craft Items & Fill BODs
                if STATS["status"] == "Stopped": break
                self.set_global_status("Running (Crafting)")
                ClientPrintEx(Self(), 1, 1, "Master: Filling BODs...")
                import BodCycler_Crafting
                importlib.reload(BodCycler_Crafting)
                BodCycler_Crafting.run_crafting_cycle()
                
                # STEP 3: Travel, Trade, & Return
                if STATS["status"] == "Stopped": break
                self.set_global_status("Running (Trading)")
                ClientPrintEx(Self(), 1, 1, "Master: Commencing NPC Trade...")
                import BodCycler_NPC_Trade
                importlib.reload(BodCycler_NPC_Trade)
                BodCycler_NPC_Trade.execute_trade_loop()
            
                
                # LOOP PAUSE
                if STATS["status"] == "Stopped": break
                self.set_global_status("Running (Cooldown)")
                AddToSystemJournal("Cycle complete. Fumando una sigaretta...")
                
                # Sleep in increments so we can interrupt it instantly if Stop is pressed
                for _ in range(3):
                    if STATS["status"] == "Stopped": break
                    time.sleep(1)
                
            except Exception as e:
                AddToSystemJournal(f"CRITICAL ERROR in Master Cycle: {e}")
                self.set_global_status("Error (See Journal)")
                break
                
        AddToSystemJournal("=== MASTER CYCLE STOPPED ===")
        BodCycler_AI_Debugger.send_discord_session_report()

    def start_cycling(self):
        if STATS["status"] != "Idle" and STATS["status"] != "Stopped" and "Running" in STATS["status"]:
            AddToSystemJournal("Cycle is already running!")
            return
            
        STATS["start_time"] = datetime.now()
        self.set_global_status("Running")
        self.save_config()
        
        # Launch the orchestrator in the background so the GUI doesn't freeze
        threading.Thread(target=self.master_cycle_thread, daemon=True).start()

    def stop_cycling(self):
        STATS["start_time"] = None
        # Writing 'Stopped' to the file will trigger the check_abort() breaks in the worker scripts
        self.set_global_status("Stopped")
        ClientPrintEx(Self(), 1, 1, "Cycle Stopped")
        AddToSystemJournal("User requested cycle stop. Safely aborting scripts...")

    def run(self):
        self.load_config()
        self.root = Tk()
        self.root.title(f"{CharName()} - BOD Cycler Config")
        self.root.geometry("480x980") 
        self.root.resizable(False, False)
        
        try:
            if os.path.exists(ICON_FILE): self.root.iconbitmap(ICON_FILE)
        except Exception: pass

        # 1. Logistics Frame
        lf_log = LabelFrame(self.root, text="Logistics & Actions", padx=5, pady=5)
        lf_log.pack(fill="x", padx=10, pady=5)

        f_type = Frame(lf_log)
        f_type.pack(fill="x", pady=5)
        Button(lf_log, text="Check Assembly (JSON only)", command=self.check_assembly_readiness, bg="#B0E0E6", font=("Arial", 8)).pack(fill="x", padx=5, pady=(0, 4))
        self.vars["cycle_type"] = StringVar(value=self.config.get("cycle_type", "Tailor"))
        Label(f_type, text="Mode:").pack(side=LEFT, padx=2)
        Radiobutton(f_type, text="Tailor", variable=self.vars["cycle_type"], value="Tailor").pack(side=LEFT)
        Radiobutton(f_type, text="Smith", variable=self.vars["cycle_type"], value="Smith").pack(side=LEFT)
        
        # Action Buttons
        Button(f_type, text="Trade", command=self.trigger_trade, bg="#90EE90").pack(side=RIGHT, padx=1)
        Button(f_type, text="Craft", command=self.trigger_crafting, bg="#FFD700").pack(side=RIGHT, padx=1)
        Button(f_type, text="Assemble", command=self.trigger_assemble, bg="#DDA0DD").pack(side=RIGHT, padx=1)
        Button(f_type, text="Scan", command=self.trigger_scan, bg="#FFB6C1").pack(side=RIGHT, padx=1)
        

        # Configurable Variables for Trading
        f_trade_vars = Frame(lf_log)
        f_trade_vars.pack(fill="x", pady=2)
        
        Label(f_trade_vars, text="Trades/Cycle:").pack(side=LEFT, padx=2)
        self.vars["target_trades"] = StringVar(value=str(self.config.get("trade", {}).get("target_trades", 2)))
        Entry(f_trade_vars, textvariable=self.vars["target_trades"], width=4).pack(side=LEFT, padx=2)
        
        Label(f_trade_vars, text="Buy Cloth:").pack(side=LEFT, padx=(15,2))
        self.vars["buy_cloth_amount"] = StringVar(value=str(self.config.get("trade", {}).get("buy_cloth_amount", 80)))
        Entry(f_trade_vars, textvariable=self.vars["buy_cloth_amount"], width=5).pack(side=LEFT, padx=2)

        f_supplies = Frame(lf_log, bg="#eef")
        f_supplies.pack(fill="x", pady=5, padx=5)
        
        self.vars["sup_iron"] = StringVar(value="Iron: 0")
        self.vars["sup_cloth"] = StringVar(value="Cloth: 0")
        self.vars["sup_leather"] = StringVar(value="Leather: 0")
        self.vars["sup_spined"] = StringVar(value="Spined: 0")
        self.vars["sup_horned"] = StringVar(value="Horned: 0")
        self.vars["sup_barbed"] = StringVar(value="Barbed: 0")
        
        Label(f_supplies, textvariable=self.vars["sup_iron"], bg="#eef", font=("Arial", 9, "bold")).grid(row=0, column=0, padx=10)
        Label(f_supplies, textvariable=self.vars["sup_cloth"], bg="#eef", font=("Arial", 9, "bold")).grid(row=0, column=1, padx=10)
        Label(f_supplies, textvariable=self.vars["sup_leather"], bg="#eef", font=("Arial", 9)).grid(row=0, column=2, padx=10)
        Label(f_supplies, textvariable=self.vars["sup_spined"], bg="#eef", fg="#004400").grid(row=1, column=0, padx=10)
        Label(f_supplies, textvariable=self.vars["sup_horned"], bg="#eef", fg="#440000").grid(row=1, column=1, padx=10)
        Label(f_supplies, textvariable=self.vars["sup_barbed"], bg="#eef", fg="#000044").grid(row=1, column=2, padx=10)

        targets = [
            ("MaterialCrate", "Material Crate"),
            ("TrashBarrel", "Trash Barrel"),
            ("ClothDyeTub", "Cloth Dye Tub"),
            ("RuneBook", "RuneBook")
        ]
        
        f_targets = Frame(lf_log)
        f_targets.pack(fill="x")
        
        for i, (key, label) in enumerate(targets):
            cat = "travel" if key == "RuneBook" else "containers"
            s = self.config[cat].get(key, 0)
            t = f"{label}: {hex(s)}" if s else f"{label}: Not Set"
            c = "blue" if s else "red"
            lbl = Label(f_targets, text=t, fg=c, width=25, anchor="w")
            lbl.grid(row=i, column=0, padx=5, pady=2)
            Button(f_targets, text="Target", width=8, 
                   command=lambda k=key, c=cat, l=lbl: self.get_target(c, k, l)).grid(row=i, column=1, padx=5, pady=2)

        hx = self.config["home"].get("X", 0)
        spot_txt = f"Home: {hx}, ..." if hx != 0 else "Home: Not Set"
        spot_fg = "blue" if hx != 0 else "red"
        lbl_spot = Label(f_targets, text=spot_txt, fg=spot_fg, width=25, anchor="w")
        lbl_spot.grid(row=4, column=0, padx=5, pady=5)
        
        f_home_btns = Frame(f_targets)
        f_home_btns.grid(row=4, column=1, padx=5, pady=5)
        Button(f_home_btns, text="Set", width=4, command=lambda: self.set_home_spot(lbl_spot)).pack(side=LEFT, padx=1)
        Button(f_home_btns, text="Go To", width=5, command=self.go_to_home_spot).pack(side=LEFT, padx=1)

        # 2. Books Frame
        lf_books = LabelFrame(self.root, text="BOD Books", padx=5, pady=5)
        lf_books.pack(fill="x", padx=10, pady=5)
        book_keys = ["Origine", "Conserva", "Riprova", "Consegna", "Scartare"]
        for i, key in enumerate(book_keys):
            s = self.config["books"].get(key, 0)
            t = f"{key}: {hex(s)}" if s else f"{key}: Not Set"
            c = "blue" if s else "red"
            lbl = Label(lf_books, text=t, fg=c, width=25, anchor="w")
            lbl.grid(row=i, column=0, padx=5)
            Button(lf_books, text="Target", width=8, 
                   command=lambda k=key, l=lbl: self.get_target("books", k, l)).grid(row=i, column=1, padx=5)

        # 3. Runes Frame
        lf_runes = LabelFrame(self.root, text="Travel", padx=5, pady=5)
        lf_runes.pack(fill="x", padx=10, pady=5)
        
        f_method = Frame(lf_runes)
        f_method.grid(row=0, column=0, columnspan=4)
        self.vars["travel_method"] = StringVar(value=self.config["travel"].get("Method", "Recall"))
        Radiobutton(f_method, text="Recall", variable=self.vars["travel_method"], value="Recall").pack(side=LEFT)
        Radiobutton(f_method, text="Sacred Journey", variable=self.vars["travel_method"], value="SacredJourney").pack(side=LEFT)

        r_keys = ["WorkSpot1", "WorkSpot2", "Tailor1", "Tailor2", "Smith1", "Smith2"]
        r_row, r_col = 1, 0
        for key in r_keys:
            Label(lf_runes, text=key).grid(row=r_row, column=r_col, padx=5)
            var = StringVar(value=str(self.config["travel"]["Runes"].get(key, 1)))
            self.vars[f"rune_{key}"] = var
            Entry(lf_runes, textvariable=var, width=3).grid(row=r_row, column=r_col+1)
            Button(lf_runes, text="Go", width=2, command=lambda k=key: self.test_travel(k)).grid(row=r_row, column=r_col+2)
            r_col += 3
            if r_col > 5: r_col=0; r_row+=1

        # 4. Dashboard (Stats & Info)
        lf_stats = LabelFrame(self.root, text="Live Stats Dashboard", padx=5, pady=5)
        lf_stats.pack(fill="x", padx=10, pady=10)
        
        self.vars["stat_crafted"] = StringVar(value="BODs Filled: 0")
        self.vars["stat_small"] = StringVar(value="Small Prizes: 0")
        self.vars["stat_large"] = StringVar(value="Large Prizes: 0")
        
        f_metric = Frame(lf_stats)
        f_metric.pack(fill="x", pady=2)
        Label(f_metric, textvariable=self.vars["stat_crafted"], fg="darkblue", font=("Arial", 10, "bold")).pack(side=LEFT, expand=True)
        Label(f_metric, textvariable=self.vars["stat_small"], fg="darkgreen", font=("Arial", 10, "bold")).pack(side=LEFT, expand=True)
        Label(f_metric, textvariable=self.vars["stat_large"], fg="darkmagenta", font=("Arial", 10, "bold")).pack(side=LEFT, expand=True)
        
        Button(lf_stats, text="Reset Stats", command=self.reset_stats, font=("Arial", 8)).pack(pady=4)

        self.vars["timer"] = StringVar(value="Time: 00:00:00")
        self.vars["status"] = StringVar(value="Status: Idle")
        Label(lf_stats, textvariable=self.vars["status"], font=("Arial", 11, "bold")).pack(pady=(5,0))
        Label(lf_stats, textvariable=self.vars["timer"], font=("Courier", 10)).pack()

        # 5. Controls
        f_ctl = Frame(self.root, pady=10)
        f_ctl.pack()
        Button(f_ctl, text="Save", command=self.save_config, bg="#DDD", width=10).pack(side=LEFT, padx=5)
        Button(f_ctl, text="START CYCLE", command=self.start_cycling, bg="green", fg="white", font=("Arial", 9, "bold"), width=14).pack(side=LEFT, padx=5)
        Button(f_ctl, text="Stop", command=self.stop_cycling, bg="red", fg="white", font=("Arial", 9, "bold"), width=10).pack(side=LEFT, padx=5)

        self.read_supplies_file()
        self.read_stats_file()
        self.update_timer()
        self.root.mainloop()

    def check_assembly_readiness(self):
        """
        Reads inventory.json and reports completable sets WITHOUT touching the game client.
        Sets and their components are reported in reverse-position order (mirrors Assembler sweep).
        """
        import json, os
        from bod_data import LARGE_COMPONENTS, prize_names, get_prize_number

        if not os.path.exists(INVENTORY_FILE):
            AddToSystemJournal("Assembly Check: inventory.json not found. Run a Scan first.")
            return

        try:
            with open(INVENTORY_FILE, "r") as f:
                inventory = json.load(f)
        except Exception as e:
            AddToSystemJournal(f"Assembly Check: Failed to read inventory.json — {e}")
            return

        try:
            import BodCycler_Assembler
            importlib.reload(BodCycler_Assembler)
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