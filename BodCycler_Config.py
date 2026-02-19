from stealth import *
import os
import json
import threading
import time
from tkinter import *
from datetime import datetime, timedelta

# --- Configuration & Globals ---
CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
ACTIVE_COLOR = "#55DD55"
INACTIVE_COLOR = "#AA5555"

# Global Stats (Main script will update these)
STATS = {
    "start_time": None,
    "bods_taken": 0,
    "bods_given": 0,
    "status": "Idle"
}

# Default Config Structure
DEFAULT_CONFIG = {
    "books": {
        "Origine": 0,   # Fuel (Small Iron/Cloth)
        "Conserva": 0,  # Keep (Prize candidates)
        "Riprova": 0,   # Retry (Missing Mats)
        "Consegna": 0,  # Trade Ready (Filled)
        "Scartare": 0   # Trash
    },
    "containers": {
        "MaterialCrate": 0,
        "TrashBarrel": 0,
        "ClothDyeTub": 0
    },
    "travel": {
        "RuneBook": 0,
        "Method": "Recall",
        "Runes": {
            "WorkSpot1": 1, "WorkSpot2": 2, "Tailor1": 3,
            "Tailor2": 7,   "Smith1": 8,    "Smith2": 9
        }
    },
    "home": {
        "X": 0, "Y": 0, "Z": 0
    }
}

class BodCyclerGUI(threading.Thread):
    def __init__(self):
        super(BodCyclerGUI, self).__init__(daemon=True)
        self.config = DEFAULT_CONFIG.copy()
        self.root = None
        self.vars = {} # Tkinter variables
        self.running = True

    def load_config(self):
        """Loads config from JSON or uses defaults."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception as e:
                AddToSystemJournal(f"Error loading config: {e}")
        
        # Ensure structure integrity
        for key in DEFAULT_CONFIG:
            if key not in self.config:
                self.config[key] = DEFAULT_CONFIG[key]
        
        for r_key in DEFAULT_CONFIG["travel"]["Runes"]:
            if r_key not in self.config["travel"]["Runes"]:
                 self.config["travel"]["Runes"][r_key] = DEFAULT_CONFIG["travel"]["Runes"][r_key]

        if "Method" not in self.config["travel"]:
            self.config["travel"]["Method"] = "Recall"
            
        if "TrashBarrel" not in self.config["containers"]:
            self.config["containers"]["TrashBarrel"] = 0

        if "ClothDyeTub" not in self.config["containers"]:
            self.config["containers"]["ClothDyeTub"] = 0
            
        if "home" not in self.config:
            self.config["home"] = {"X": 0, "Y": 0, "Z": 0}

    def save_config(self):
        """Saves current config to JSON."""
        # Update config object from Tkinter vars for Inputs (Runes)
        for name, var in self.vars.items():
            if name.startswith("rune_"):
                key = name.replace("rune_", "")
                try:
                    self.config["travel"]["Runes"][key] = int(var.get())
                except:
                    pass 
        
        if "travel_method" in self.vars:
            self.config["travel"]["Method"] = self.vars["travel_method"].get()
            
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
            AddToSystemJournal("Configuration Saved.")
        except Exception as e:
            AddToSystemJournal(f"Error saving config: {e}")

    def get_target(self, category, key, label_widget=None):
        """Generic targeting function for Books and Containers."""
        ClientPrintEx(Self(), 1, 1, f"Target the {key}...")
        ClientRequestObjectTarget()
        
        start_wait = time.time()
        while not ClientTargetResponsePresent():
            time.sleep(0.1)
            if time.time() - start_wait > 15: # Timeout
                ClientPrintEx(Self(), 1, 1, "Target cancelled (Timeout).")
                return

        response = ClientTargetResponse()
        if response["ID"] > 0:
            serial = response["ID"]
            
            if category == "books":
                self.config["books"][key] = serial
            elif category == "containers":
                self.config["containers"][key] = serial
            elif category == "travel":
                self.config["travel"][key] = serial
            
            if label_widget:
                label_widget.config(text=f"{key}: {hex(serial)}")
                label_widget.config(fg="blue")
            
            ClientPrintEx(Self(), 1, 1, f"Set {key} to {hex(serial)}")
        else:
            ClientPrintEx(Self(), 1, 1, "Target cancelled.")

    def set_home_spot(self, label_widget):
        """Captures current location as Home spot."""
        x, y, z = GetX(Self()), GetY(Self()), GetZ(Self())
        self.config["home"]["X"] = x
        self.config["home"]["Y"] = y
        self.config["home"]["Z"] = z
        
        label_widget.config(text=f"Home: {x}, {y}, {z}", fg="blue")
        ClientPrintEx(Self(), 1, 1, f"Home spot set to {x}, {y}, {z}")
        
    def test_travel(self, rune_key_name):
        """Spawns a thread to test the travel logic for a specific rune slot."""
        threading.Thread(target=self._test_travel_thread, args=(rune_key_name,)).start()

    def _test_travel_thread(self, rune_key_name):
        rb_serial = self.config["travel"].get("RuneBook", 0)
        if rb_serial == 0:
            ClientPrintEx(Self(), 0x23, 1, "Runebook not set! Please target it first.")
            return

        try:
            rune_idx = int(self.vars[f"rune_{rune_key_name}"].get())
        except ValueError:
             ClientPrintEx(Self(), 0x23, 1, "Invalid Rune Index!")
             return

        method = self.vars["travel_method"].get()
        
        offset = 5 if method == "Recall" else 7
        btn_id = offset + (rune_idx - 1) * 6
        
        # ClientPrintEx(Self(), 0, 1, f"Testing {method} to Rune {rune_idx} (Btn {btn_id})...")
        
        UseObject(rb_serial)
        
        rb_gump_id = 0x554B87F3 
        found_idx = -1
        
        for _ in range(20): 
            time.sleep(0.1)
            for i in range(GetGumpsCount()):
                if GetGumpID(i) == rb_gump_id:
                    found_idx = i
                    break
            if found_idx != -1: break
            
        if found_idx != -1:
            NumGumpButton(found_idx, btn_id)
            # ClientPrintEx(Self(), 0, 1, "Button pressed.")
        else:
             ClientPrintEx(Self(), 0x23, 1, "Runebook Gump not found/timed out.")

    def update_timer(self):
        """Updates the elapsed time and stats labels."""
        if not self.root: return

        if STATS["start_time"]:
            elapsed = datetime.now() - STATS["start_time"]
            time_str = str(elapsed).split('.')[0] 
            self.vars["timer"].set(f"Time: {time_str}")
        else:
            self.vars["timer"].set("Time: 00:00:00")

        self.vars["taken"].set(f"Taken: {STATS['bods_taken']}")
        self.vars["given"].set(f"Given: {STATS['bods_given']}")
        self.vars["status"].set(f"Status: {STATS['status']}")

        if self.running:
            self.root.after(1000, self.update_timer)

    def start_cycling(self):
        """Signal the main script to start."""
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
        self.root.geometry("450x750") 
        self.root.resizable(False, False)

        # --- Frames ---
        
        # 1. Books Frame
        lf_books = LabelFrame(self.root, text="BOD Books Setup", padx=5, pady=5)
        lf_books.pack(fill="x", padx=10, pady=5)

        book_keys = ["Origine", "Conserva", "Riprova", "Consegna", "Scartare"]
        for i, key in enumerate(book_keys):
            serial = self.config["books"].get(key, 0)
            txt = f"{key}: {hex(serial)}" if serial else f"{key}: Not Set"
            fg = "blue" if serial else "red"
            
            lbl = Label(lf_books, text=txt, fg=fg, width=25, anchor="w")
            lbl.grid(row=i, column=0, padx=5, pady=2)
            
            btn = Button(lf_books, text="Target", width=10, 
                         command=lambda k=key, l=lbl: self.get_target("books", k, l))
            btn.grid(row=i, column=1, padx=5, pady=2)

        # 2. Logistics Frame
        lf_logistics = LabelFrame(self.root, text="Logistics Setup", padx=5, pady=5)
        lf_logistics.pack(fill="x", padx=10, pady=5)

        # Material Crate
        c_serial = self.config["containers"].get("MaterialCrate", 0)
        c_txt = f"Material Crate: {hex(c_serial)}" if c_serial else "Material Crate: Not Set"
        c_fg = "blue" if c_serial else "red"
        lbl_crate = Label(lf_logistics, text=c_txt, fg=c_fg, width=25, anchor="w")
        lbl_crate.grid(row=0, column=0, padx=5)
        Button(lf_logistics, text="Target", width=10, 
               command=lambda: self.get_target("containers", "MaterialCrate", lbl_crate)).grid(row=0, column=1, padx=5)

        # Trash Barrel
        t_serial = self.config["containers"].get("TrashBarrel", 0)
        t_txt = f"Trash Barrel: {hex(t_serial)}" if t_serial else "Trash Barrel: Not Set"
        t_fg = "blue" if t_serial else "red"
        lbl_trash = Label(lf_logistics, text=t_txt, fg=t_fg, width=25, anchor="w")
        lbl_trash.grid(row=1, column=0, padx=5)
        Button(lf_logistics, text="Target", width=10, 
               command=lambda: self.get_target("containers", "TrashBarrel", lbl_trash)).grid(row=1, column=1, padx=5)

        # Cloth Dye Tub
        d_serial = self.config["containers"].get("ClothDyeTub", 0)
        d_txt = f"Cloth Dye Tub: {hex(d_serial)}" if d_serial else "Cloth Dye Tub: Not Set"
        d_fg = "blue" if d_serial else "red"
        lbl_dye = Label(lf_logistics, text=d_txt, fg=d_fg, width=25, anchor="w")
        lbl_dye.grid(row=2, column=0, padx=5)
        Button(lf_logistics, text="Target", width=10, 
               command=lambda: self.get_target("containers", "ClothDyeTub", lbl_dye)).grid(row=2, column=1, padx=5)

        # RuneBook
        r_serial = self.config["travel"].get("RuneBook", 0)
        r_txt = f"RuneBook: {hex(r_serial)}" if r_serial else "RuneBook: Not Set"
        r_fg = "blue" if r_serial else "red"
        lbl_rb = Label(lf_logistics, text=r_txt, fg=r_fg, width=25, anchor="w")
        lbl_rb.grid(row=3, column=0, padx=5)
        Button(lf_logistics, text="Target", width=10, 
               command=lambda: self.get_target("travel", "RuneBook", lbl_rb)).grid(row=3, column=1, padx=5)
               
        # Set Spot
        hx = self.config["home"].get("X", 0)
        hy = self.config["home"].get("Y", 0)
        hz = self.config["home"].get("Z", 0)
        spot_txt = f"Home: {hx}, {hy}, {hz}" if hx != 0 else "Home: Not Set"
        spot_fg = "blue" if hx != 0 else "red"
        lbl_spot = Label(lf_logistics, text=spot_txt, fg=spot_fg, width=25, anchor="w")
        lbl_spot.grid(row=4, column=0, padx=5)
        Button(lf_logistics, text="Set Spot", width=10,
               command=lambda: self.set_home_spot(lbl_spot)).grid(row=4, column=1, padx=5)

        # 3. Runes Frame
        lf_runes = LabelFrame(self.root, text="Travel & Runes (1-16)", padx=5, pady=5)
        lf_runes.pack(fill="x", padx=10, pady=5)
        
        f_method = Frame(lf_runes)
        f_method.grid(row=0, column=0, columnspan=4, pady=5)
        
        self.vars["travel_method"] = StringVar(value=self.config["travel"].get("Method", "Recall"))
        Label(f_method, text="Method:").pack(side=LEFT)
        Radiobutton(f_method, text="Recall", variable=self.vars["travel_method"], value="Recall").pack(side=LEFT)
        Radiobutton(f_method, text="Sacred Journey", variable=self.vars["travel_method"], value="SacredJourney").pack(side=LEFT)

        rune_keys = ["WorkSpot1", "WorkSpot2", "Tailor1", "Tailor2", "Smith1", "Smith2"]
        r_row = 1
        r_col = 0
        for key in rune_keys:
            Label(lf_runes, text=key).grid(row=r_row, column=r_col, padx=5)
            
            var = StringVar(value=str(self.config["travel"]["Runes"].get(key, 1)))
            self.vars[f"rune_{key}"] = var
            Entry(lf_runes, textvariable=var, width=5).grid(row=r_row, column=r_col+1, padx=5, pady=2)
            
            Button(lf_runes, text="Go", width=3,
                   command=lambda k=key: self.test_travel(k)).grid(row=r_row, column=r_col+2, padx=2)
            
            r_col += 3
            if r_col > 5:
                r_col = 0
                r_row += 1

        # 4. Dashboard / Stats Frame
        lf_stats = LabelFrame(self.root, text="Dashboard", padx=5, pady=5, font=("Arial", 10, "bold"))
        lf_stats.pack(fill="x", padx=10, pady=10)

        self.vars["timer"] = StringVar(value="Time: 00:00:00")
        self.vars["taken"] = StringVar(value="Taken: 0")
        self.vars["given"] = StringVar(value="Given: 0")
        self.vars["status"] = StringVar(value="Status: Idle")

        Label(lf_stats, textvariable=self.vars["status"], font=("Arial", 12)).pack(anchor="center")
        Label(lf_stats, textvariable=self.vars["timer"], font=("Courier", 12)).pack(anchor="center", pady=5)
        
        f_counts = Frame(lf_stats)
        f_counts.pack()
        Label(f_counts, textvariable=self.vars["taken"], fg="green", font=("Arial", 10)).pack(side=LEFT, padx=20)
        Label(f_counts, textvariable=self.vars["given"], fg="blue", font=("Arial", 10)).pack(side=LEFT, padx=20)

        # 5. Control Buttons
        f_controls = Frame(self.root, pady=10)
        f_controls.pack()

        Button(f_controls, text="Save Config", command=self.save_config, bg="#DDDDDD", width=12).pack(side=LEFT, padx=5)
        Button(f_controls, text="START Cycle", command=self.start_cycling, bg="green", fg="white", width=12).pack(side=LEFT, padx=5)
        Button(f_controls, text="Stop", command=self.stop_cycling, bg="red", fg="white", width=12).pack(side=LEFT, padx=5)

        self.update_timer()
        
        self.root.mainloop()

if __name__ == '__main__':
    app = BodCyclerGUI()
    app.run()