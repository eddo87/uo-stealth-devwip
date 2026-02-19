from stealth import *
import os
import json
import threading
import time
from tkinter import *
from datetime import datetime, timedelta

# Import the logic for the Check Supplies button
try:
    import BodCycler_CheckSupplies
except ImportError:
    pass

# --- Configuration & Globals ---
CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
SUPPLY_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_supplies.json"
ICON_FILE = f"{StealthPath()}Scripts\\icon.ico" # Place icon.ico here if you want an app icon

# Global Stats
STATS = {
    "start_time": None,
    "bods_taken": 0,
    "bods_given": 0,
    "status": "Idle"
}

# Default Config Structure
DEFAULT_CONFIG = {
    "cycle_type": "Tailor", # Tailor or Smith
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

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception as e:
                AddToSystemJournal(f"Error loading config: {e}")
        
        # Ensure Defaults
        for key in DEFAULT_CONFIG:
            if key not in self.config: self.config[key] = DEFAULT_CONFIG[key]
        for k in DEFAULT_CONFIG["containers"]:
            if k not in self.config["containers"]: self.config["containers"][k] = 0
        if "home" not in self.config: self.config["home"] = {"X": 0, "Y": 0, "Z": 0}
        if "cycle_type" not in self.config: self.config["cycle_type"] = "Tailor"

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

        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
            AddToSystemJournal("Configuration Saved.")
        except Exception as e:
            AddToSystemJournal(f"Error saving config: {e}")

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
            ClientPrintEx(Self(), 1, 1, f"Set {key} to {hex(serial)}")

    def set_home_spot(self, label_widget):
        x, y, z = GetX(Self()), GetY(Self()), GetZ(Self())
        self.config["home"].update({"X": x, "Y": y, "Z": z})
        label_widget.config(text=f"Home: {x}, {y}, {z}", fg="blue")
        
    def go_to_home_spot(self):
        """Commands character to walk to the saved Home Coordinates."""
        hx = self.config["home"].get("X", 0)
        hy = self.config["home"].get("Y", 0)
        
        if hx != 0 and hy != 0:
            ClientPrintEx(Self(), 1, 1, f"Walking to Home Spot ({hx}, {hy})...")
            # Run in background to prevent freezing GUI
            threading.Thread(target=lambda: newMoveXY(hx, hy, True, 0, True)).start()
        else:
            ClientPrintEx(Self(), 0x23, 1, "Home spot is not set!")

    def trigger_supply_check(self):
        """Spawns the supply check logic from BodCycler_CheckSupplies."""
        self.save_config() # Save cycle_type before checking
        ClientPrintEx(Self(), 1, 1, "Starting Supply Check...")
        try:
            threading.Thread(target=BodCycler_CheckSupplies.check_supplies).start()
        except NameError:
            AddToSystemJournal("BodCycler_CheckSupplies module not found/loaded.")

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

    def read_supplies_file(self):
        """Reads the supplies JSON and updates the GUI visual counters."""
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
            pass # Ignore read conflicts if script is writing at exact same time

    def update_timer(self):
        if not self.root: return
        
        # Read supply updates if they changed
        self.read_supplies_file()
        
        # General Status Updates
        if STATS["start_time"]:
            elapsed = datetime.now() - STATS["start_time"]
            self.vars["timer"].set(f"Time: {str(elapsed).split('.')[0]}")
        else: self.vars["timer"].set("Time: 00:00:00")
        self.vars["taken"].set(f"Taken: {STATS['bods_taken']}")
        self.vars["given"].set(f"Given: {STATS['bods_given']}")
        self.vars["status"].set(f"Status: {STATS['status']}")
        
        if self.running: self.root.after(1000, self.update_timer)

    def start_cycling(self):
        STATS["start_time"] = datetime.now()
        STATS["status"] = "Running"
        STATS["bods_taken"] = 0
        STATS["bods_given"] = 0
        self.save_config()
        AddToSystemJournal("BOD Cycle Started (Stats Reset)")

    def stop_cycling(self):
        STATS["status"] = "Stopped"
        STATS["start_time"] = None
        AddToSystemJournal("BOD Cycle Stopped")

    def run(self):
        self.load_config()
        self.root = Tk()
        self.root.title(f"{CharName()} - BOD Cycler Config")
        self.root.geometry("460x900") # Increased height to fit new Crate Counters
        self.root.resizable(False, False)
        
        # --- App Icon Logic ---
        try:
            if os.path.exists(ICON_FILE):
                self.root.iconbitmap(ICON_FILE)
        except Exception:
            pass # Fail gracefully if icon is missing or invalid

        # 1. Logistics & Supply Checking Frame
        lf_log = LabelFrame(self.root, text="Logistics & Type", padx=5, pady=5)
        lf_log.pack(fill="x", padx=10, pady=5)

        # Cycle Type Radio & Run Checks Button
        f_type = Frame(lf_log)
        f_type.pack(fill="x", pady=5)
        self.vars["cycle_type"] = StringVar(value=self.config.get("cycle_type", "Tailor"))
        Label(f_type, text="Mode:").pack(side=LEFT, padx=5)
        Radiobutton(f_type, text="Tailor", variable=self.vars["cycle_type"], value="Tailor").pack(side=LEFT)
        Radiobutton(f_type, text="Smith", variable=self.vars["cycle_type"], value="Smith").pack(side=LEFT)
        Button(f_type, text="Run Supply Check", command=self.trigger_supply_check, bg="#ADD8E6").pack(side=RIGHT, padx=5)

        # Crate Materials Dashboard
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

        # Targets
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

        # Set & Go Home Spot
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

        # 4. Dashboard
        lf_stats = LabelFrame(self.root, text="Status", padx=5, pady=5)
        lf_stats.pack(fill="x", padx=10, pady=10)
        self.vars["timer"] = StringVar(value="Time: 00:00:00")
        self.vars["taken"] = StringVar(value="Taken: 0")
        self.vars["given"] = StringVar(value="Given: 0")
        self.vars["status"] = StringVar(value="Status: Idle")
        Label(lf_stats, textvariable=self.vars["status"], font=("Arial", 12)).pack()
        Label(lf_stats, textvariable=self.vars["timer"], font=("Courier", 12)).pack()
        
        f_counts = Frame(lf_stats)
        f_counts.pack()
        Label(f_counts, textvariable=self.vars["taken"], fg="green", font=("Arial", 10)).pack(side=LEFT, padx=20)
        Label(f_counts, textvariable=self.vars["given"], fg="blue", font=("Arial", 10)).pack(side=LEFT, padx=20)

        # 5. Controls
        f_ctl = Frame(self.root, pady=10)
        f_ctl.pack()
        Button(f_ctl, text="Save", command=self.save_config, bg="#DDD", width=10).pack(side=LEFT, padx=5)
        Button(f_ctl, text="START", command=self.start_cycling, bg="green", fg="white", width=10).pack(side=LEFT, padx=5)
        Button(f_ctl, text="Stop", command=self.stop_cycling, bg="red", fg="white", width=10).pack(side=LEFT, padx=5)

        # Force initial supply read on launch
        self.read_supplies_file()
        self.update_timer()
        
        self.root.mainloop()

if __name__ == '__main__':
    app = BodCyclerGUI()
    app.run()