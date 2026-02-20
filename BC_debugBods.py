from stealth import *
import time
import re
import sys
import os

# Force Python to look in the current script's directory for custom modules
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    from bod_crafting_data import TAILOR_ITEMS
except ImportError:
    AddToSystemJournal("CRITICAL: Cannot find bod_crafting_data.py")
    TAILOR_ITEMS = {}

BOD_TYPE = 0x2258

def print_debug(msg):
    AddToSystemJournal(f"[DEBUG] {msg}")
    print(f"[DEBUG] {msg}")

def debug_fill_bod():
    print_debug("=== Starting Debug BOD Filler ===")
    
    # 1. Find a BOD in the main backpack
    FindType(BOD_TYPE, Backpack())
    if FindCount() == 0:
        print_debug("No BOD found in your backpack! Please put one in.")
        return
        
    bod_serial = FindItem()
    print_debug(f"Found BOD: {hex(bod_serial)}")
    
    # 2. Parse the BOD to find out what item we need to target
    tooltip = GetTooltip(bod_serial).lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]
    
    qty = 0
    for line in lines:
        if "amount to make" in line or "amount" in line:
            match = re.search(r'\d+', line)
            if match: qty = int(match.group())
        elif re.match(r'^\d+$', line):
            qty = int(line)
            
    item_name = "unknown"
    sorted_keys = sorted(TAILOR_ITEMS.keys(), key=len, reverse=True)
    for line in lines:
        for key in sorted_keys:
            if key in line:
                item_name = key
                break
        if item_name != "unknown":
            break
            
    if item_name == "unknown" or item_name not in TAILOR_ITEMS:
        print_debug(f"Could not determine item name from tooltip. Is it a tailor BOD?")
        return
        
    item_id = TAILOR_ITEMS[item_name][2]
    print_debug(f"BOD requires: {qty}x '{item_name}' (Graphic ID: {hex(item_id)})")
    
    # 3. Find the crafted items in your backpack
    FindType(item_id, Backpack())
    items = GetFoundList()
    if not items:
        print_debug(f"You don't have any {item_name}s in your backpack to fill with!")
        return
        
    print_debug(f"Found {len(items)} matching items in backpack. Ready to fill.")
    
    # 4. Open the BOD and press Combine (Button 2)
    print_debug("Opening BOD gump...")
    UseObject(bod_serial)
    Wait(1500)
    
    idx = -1
    for i in range(GetGumpsCount()):
        g = GetGumpInfo(i)
        if 'GumpButtons' in g:
            for btn in g['GumpButtons']:
                if btn.get('ReturnValue') == 2:
                    idx = i
                    break
        if idx != -1: break
        
    if idx != -1:
        print_debug("Pressing Combine (Button 2)...")
        NumGumpButton(idx, 2)
        
        # Replicating Razor: Wait for the first target cursor
        WaitForTarget(1000)
    else:
        print_debug("CRITICAL: Could not find Combine button on BOD gump.")
        return
        
    # 5. The Target Loop
    filled = 0
    for item in items:
        if filled >= qty: 
            print_debug("Reached required quantity!")
            break
            
        if TargetPresent():
            print_debug(f"-> Targeting item {filled + 1}: {hex(item)}")
            TargetToObject(item)
            
            # Replicating Razor: Do NOT wait blindly. Wait exclusively for the NEXT target cursor.
            WaitForTarget(1000) 
            
            filled += 1
            print_debug(f"   Target executed. TargetPresent is now: {TargetPresent()}")
        else:
            print_debug("-> Target cursor disappeared! BOD might be full or server lagged.")
            break
            
    # Clean up
    if TargetPresent():
        print_debug("Canceling leftover target cursor.")
        CancelTarget()
        Wait(500)
        
    print_debug(f"Debug Fill Complete. Items targeted: {filled}")
    print_debug("Check the BOD to see if it actually filled!")

if __name__ == '__main__':
    debug_fill_bod()