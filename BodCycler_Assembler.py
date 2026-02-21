from stealth import *
import json
import os
import sys
import re
import time

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from bod_crafting_data import TAILOR_ITEMS, MATERIAL_MAP
from BodCycler_Scanner import extract_bod_from_book, parse_universal_bod, close_all_gumps

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

CONFIG_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_config.json"
STATS_FILE = f"{StealthPath()}Scripts\\{CharName()}_bodcycler_stats.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None

def check_abort():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
                if data.get("status") == "Stopped": return True
        except: pass
    return False

def combine_bods(large_serial, small_serial):
    """Opens Large BOD, presses combine, and targets the Small BOD."""
    close_all_gumps()
    UseObject(large_serial)
    Wait(1500)
    
    idx = -1
    for i in range(GetGumpsCount()):
        g = GetGumpInfo(i)
        if 'GumpButtons' in g:
            for btn in g['GumpButtons']:
                if btn.get('ReturnValue') == 2: idx = i; break
        if idx != -1: break
        
    if idx != -1:
        NumGumpButton(idx, 2)
        if WaitForTarget(5000):
            world_save_guard()
            TargetToObject(small_serial)
            Wait(1000)
            return True
    
    if TargetPresent(): CancelTarget()
    return False

def run_assembler():
    config = load_config()
    if not config: return
    conserva = config['books']['Conserva']
    consegna = config['books']['Consegna']
    
    AddToSystemJournal("=== Starting Large BOD Assembly ===")
    
    pulled_bods = []
    # Pull up to 30 BODs to hunt for combinations
    for _ in range(30):
        if check_abort(): break
        bod = extract_bod_from_book(conserva)
        if bod == 0: break
        pulled_bods.append(bod)
        
    large_bods = []
    small_full_bods = []
    
    for bod in pulled_bods:
        data = parse_universal_bod(bod)
        if data['is_large']: large_bods.append(data)
        elif data['is_full']: small_full_bods.append(data)

    assembled_count = 0
    
    for lbod in large_bods:
        if check_abort(): break
        if lbod['is_full']: continue
            
        for req in lbod['reqs']:
            if req['amt_done'] < req['needed']:
                # Find matching small bod
                match_idx = -1
                for i, sm in enumerate(small_full_bods):
                    if (sm['reqs'][0]['item'] == req['item'] and 
                        sm['qty_total'] == lbod['qty_total'] and 
                        sm['is_except'] == lbod['is_except'] and 
                        sm['material'] == lbod['material']):
                        match_idx = i
                        break
                
                if match_idx != -1:
                    sm_data = small_full_bods[match_idx]
                    qual = "Exc" if lbod['is_except'] else "Norm"
                    AddToSystemJournal(f"Combining: {req['item'].title()} into {lbod['qty_total']}x {qual} {lbod['material'].title()} Large BOD...")
                    
                    if combine_bods(lbod['serial'], sm_data['serial']):
                        # Remove used small bod from our memory list
                        small_full_bods.pop(match_idx)
                        req['amt_done'] = req['needed'] # Artificially update memory state
                        assembled_count += 1
                        
        # Re-evaluate if Large BOD is now completely full after loop
        lbod['is_full'] = all(r['amt_done'] >= r['needed'] for r in lbod['reqs'])

    # Cleanup and Routing
    AddToSystemJournal("Routing BODs to destination books...")
    for bod_serial in pulled_bods:
        world_save_guard()
        # Ensure we don't try to move a Small BOD that was destroyed in the combination
        if not FindType(0x2258, Backpack()) or bod_serial not in GetFoundList():
            continue 
            
        data = parse_universal_bod(bod_serial)
        if data['is_large'] and data['is_full']:
            AddToSystemJournal(f"-> Moving COMPLETELY FULL Large BOD to Consegna for Reward!")
            MoveItem(bod_serial, 0, consegna, 0,0,0)
        else:
            MoveItem(bod_serial, 0, conserva, 0,0,0)
        Wait(800)
        
    close_all_gumps()
    AddToSystemJournal(f"=== Assembly Complete. Actions taken: {assembled_count} ===")

if __name__ == '__main__':
    run_assembler()