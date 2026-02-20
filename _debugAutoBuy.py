from stealth import *

try:
    from checkWorldSave import world_save_guard
except ImportError:
    def world_save_guard(): return False

def debug_autobuy():
    # Targets & IDs
    npc = 0x00002CEB
    BOLT_OF_CLOTH = 0x0F97
    CTX_BUY = 1
    
    AddToSystemJournal("--- Debug AutoBuy Started ---")
    
    # 1. Move to NPC
    if npc > 0 and GetDistance(npc) > 1:
        AddToSystemJournal("Moving to NPC...")
        newMoveXY(GetX(npc), GetY(npc), False, 1, True)
        Wait(500)
        
    # Check initial backpack count
    FindType(BOLT_OF_CLOTH, Backpack())
    initial_count = FindFullQuantity()
    AddToSystemJournal(f"Initial Bolts of Cloth in backpack: {initial_count}")
        
    AddToSystemJournal("Setting AutoBuy hook for 2 Bolts of Cloth...")
    
        
    # 2. Set buy hook for exactly 2 items
    AutoBuy(BOLT_OF_CLOTH, 0xFFFF, 2)
        
    # 3. Trigger Context Menu with requested pauses
    world_save_guard()
    SetContextMenuHook(npc, CTX_BUY)
    Wait(600)
    RequestContextMenu(npc)
    Wait(1200)
        
    # 4. Unset buy hook
    AutoBuy(BOLT_OF_CLOTH, 0xFFFF, 0)
    
        
    AddToSystemJournal("Context menu sequence executed.")
        
    # 5. Check if we actually got them
    Wait(1000) # Quick pause for item to appear in bag
    FindType(BOLT_OF_CLOTH, Backpack())
    new_count = FindFullQuantity()
    AddToSystemJournal(f"New Bolts of Cloth in backpack: {new_count}")
        
    if new_count > initial_count:
        AddToSystemJournal("SUCCESS: Bought cloth!")
    else:
        AddToSystemJournal("FAILED: Did not detect new cloth.")
            


if __name__ == '__main__':
    debug_autobuy()