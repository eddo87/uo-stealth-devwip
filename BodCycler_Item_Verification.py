from stealth import *
import re
import time

def get_bod_progress(bod_serial, item_name):
    """Parses the BOD tooltip specifically for current progress."""
    tooltip = GetTooltip(bod_serial).lower()
    lines = [line.strip() for line in tooltip.split('|') if line.strip()]
    amt_finished = 0

    # Use the same regex logic as the main parser
    for line in lines:
        if item_name.lower() in line and ":" in line:
            match = re.search(r':\s*(\d+)', line)
            if match:
                amt_finished = int(match.group(1))
                break
    return amt_finished

def test_item_acceptance(bod_serial, item_serial, item_name):
    """
    Attempts to combine a single item into the BOD to see if it's accepted.
    Returns True if the BOD's 'amount finished' increases.
    """
    # 1. Get initial progress
    initial_count = get_bod_progress(bod_serial, item_name)
    AddToSystemJournal(f"Verifying acceptance... BOD current count: {initial_count}")

    # 2. Trigger 'Combine' button on the BOD gump
    # We close gumps first to ensure we aren't clicking a stale index
    count = GetGumpsCount()
    for i in reversed(range(count)):
        CloseSimpleGump(i)
    Wait(500)

    UseObject(bod_serial)
    Wait(1500)

    combine_btn_idx = -1
    for i in range(GetGumpsCount()):
        g = GetGumpInfo(i)
        if 'GumpButtons' in g:
            for btn in g['GumpButtons']:
                if btn.get('ReturnValue') == 2: # Combine button is usually 2
                    combine_btn_idx = i
                    break
        if combine_btn_idx != -1: break

    if combine_btn_idx != -1:
        NumGumpButton(combine_btn_idx, 2)
        if WaitForTarget(5000):
            TargetToObject(item_serial)
            Wait(1000) # Wait for server processing
    else:
        AddToSystemJournal("Verification Error: Could not find Combine button.")
        return False

    # 3. Check if count increased
    # Tooltips might be laggy, so we give it a few tries
    for _ in range(3):
        new_count = get_bod_progress(bod_serial, item_name)
        if new_count > initial_count:
            AddToSystemJournal(f"SUCCESS: BOD accepted the item ({new_count}/{initial_count}). Proceeding.")
            return True
        Wait(500)

    AddToSystemJournal("FAILURE: BOD rejected the item ID.")
    return False
