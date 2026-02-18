from stealth import *
import sys
sys.path.insert(1, StealthPath() + "Scripts")
from Utilities import *
from autoloot import *
import time 
from datetime import datetime, time, timedelta
from dhooks import Webhook

hook = Webhook('[DISCORD_WEB_HOOK')

#hook.send('Bod test')
 
#Personal changes
 
pgList = ['ed2', 'ed3', 'ed5']
bookTName = 'Tailor'    # Names must be the same across all chars
bookBName = 'Black'     # note this is case sensitive
closeToFull = ['490', '495', '498', '499']
 
# Personal
BWC = 0x4034B9A0
HOME_BOX = 0x4030C346
HOMEBOOK = 0x40927C7C
RBS = [0x40927C7C, 0x401893C2]
HOME_RUNE = 1
RUNE_START = 2
RUNE_COUNT = 16
MAX_WEIGHT = 400
 

 
#ServerCostants
 
NPCB = 0x0002D23A            # Here we need the Blacksmith's NPC ID
NPCT = 0x0002D1D4            # Here the one for the Tailor's  NPC ID
bodGumpID_Small = 0x9bade6ea # static type for small BodGumps on Runuo
gumpReturnValue = 1          # PacketValue to send "OK-Button"
contextMenuEntryValue = 3    # Entrypoint for Context on Runuo Sample [4th row]
bodType = 0x2258             # Small Bod Type
bulkBookType = 0x2259        # Bulk order book type
bodBCol = 0x044E             # Colour for Blacksmith's bods
bodTCol = 0x0483             # Colour for Tailor's bods
min_pause = 500              # You can edit those to make the script go slower /
med_pause = 990              # or faster, depending on your connection
long_pause = 1900            #

#SHARD
GUMP_ID = 0x554b87f3
RECALL_CHIVALRY_OFFSET = 7  # Adjusted to start from 7
RUNE_INCREMENT = 6  # The difference between consecutive rune indices


# Universal
mobs = [0x00DD, 0x0022, 0x0040, 0x00ED, 0x00D8, 0x00D1, 0x00E9, 0x0024, 0x0023, 0x0025, 0x0E7, 0x00EA, 0x00DC, 0x00E8, 0x00E7, 0x00D5, 0x00E8]
CORPSE_ID = 0x2006
IGNORE_CORPSES = []
DISTANCE = 12
MED_WAIT = 1000
SHORT_WAIT = 500
TINY_WAIT = 300
TARGET_ID = 0 
 
 
#Functions 
 
def setupBooks(bookNeeded):
   FindType(bulkBookType,Backpack())
   while FindCount() > 1:
       FindType(bulkBookType,Backpack())
       info = GetTooltip(FindType(bulkBookType,Backpack())) 
       if bookNeeded in info: 
           bookNeeded = str(FindItem())
           Ignore(FindItem()) 
       else:  
           Ignore(FindItem())
           Wait(200)      
   IgnoreReset()
   return(bookNeeded)
    
    
def bodToBook():
    TBook = setupBooks(bookTName) 
    if len(TBook) > 9:         
        FindTypeEx(bodType,bodTCol,Backpack())
        for BdCnt in range(FindCount()): 
            Tinfo = GetTooltip(TBook) 
            if any(Tinfo.find(s)>=0 for s in closeToFull): 
                hook.send(CharName() +': '+ Tinfo)
                FindTypeEx(bodType,bodTCol,Backpack())
                MoveItem(FindItem(),FindQuantity(),TBook,0,0,0)
                Wait(200) 
            elif '500' in Tinfo:
                hook.send(CharName() +' needs a new Tailor book')
                break
            else:
                FindTypeEx(bodType,bodTCol,Backpack())
                MoveItem(FindItem(),FindQuantity(),TBook,0,0,0)
                Wait(200) 
    else: hook.send(CharName() +' Tailor book is not set') 
     
    BBook = setupBooks(bookBName)
    if len(BBook) > 9:
        FindTypeEx(bodType,bodBCol,Backpack())
        for BdCnt in range(FindCount()):   
            Binfo = GetTooltip(BBook)
            if any(Binfo.find(s)>=0 for s in closeToFull): 
                hook.send(CharName() +' '+ Binfo)
                FindTypeEx(bodType,bodBCol,Backpack())
                MoveItem(FindItem(),FindQuantity(),BBook,0,0,0)
                Wait(200)    
            elif '500' in Binfo:
                hook.send(CharName() +' needs a new Black book')
                break
            else:
                FindTypeEx(bodType,bodBCol,Backpack())
                MoveItem(FindItem(),FindQuantity(),BBook,0,0,0)
                Wait(200)     
    else: hook.send(CharName() +' Black book is not set')
 
 
 
def getBod(npcID):
    Flag = False
    while Flag is not True: 
        while Connected() is not True:
            Wait(20000)
            print('Waiting to reconnect...')
        if GetDistance(npcID) > 2:
            newMoveXY( GetX(npcID) , GetY(npcID) , False , 2 , True )  #Moves to NPC tolerance 2 Tiles
            Wait(min_pause) 
        #ClearContextMenu()
        Wait(min_pause) 
        start = datetime.now() 
        RequestContextMenu(npcID)
        Wait(med_pause)
        SetContextMenuHook(npcID,contextMenuEntryValue)
        Wait(long_pause)
        for gmp in range(GetGumpsCount()):
           if GetGumpID(gmp) == bodGumpID_Small: 
               Wait(min_pause)
               NumGumpButton(gmp,gumpReturnValue) 
               Wait(min_pause)
               #ClearContextMenu()
               Flag = True 
        if InJournalBetweenTimes('You can get an order now.', start, datetime.now()) != -1:
            return
        else:
            LeatherBreak = False
            print('going pelling')
            Wait(min_pause)
            stopLeather = datetime.now() + timedelta(minutes=59)
            while LeatherBreak is not True:
                for runebook in RBS:
                    print('for runebooks in rbs')
                    for i in range(RUNE_START, RUNE_COUNT):
                        if Dead():
                            hook.send(CharName() +' sono morto come un imbecille')
                        if Weight() >= MAX_WEIGHT:
                            deposit(HOMEBOOK, HOME_RUNE, HOME_BOX, 'chiv')
                        if datetime.now() >= stopLeather:
                            print('time is up!')
                            useRB(RBS[1], HOME_RUNE, 'chiv')
                            Wait(min_pause)
                            LeatherBreak = True
                            break
                            
                        Wait(min_pause)
                        useRB(runebook, i, 'chiv')
                        current_datetime = datetime.now()
                        remaining_time = stopLeather - current_datetime
                        print(f"Time remaining: {remaining_time}")
                        while mobFound():
                            Wait(med_pause)
                            moveToBoss()
                            doBattle()
        print('out of pelling')
        ClearJournal()
        Wait(med_pause)
  
             
 
def login(pgProfile):
    ChangeProfile(pgProfile)
    Wait(long_pause)
    Connect()     
    Wait(long_pause)
    
"""
Leather Farmer functions
"""
# Run from PK
def goHome():
    useRB(RBS[0], HOME_RUNE)
    exit
    
# Check if a buff is active
def buffActive(buff_list, buff):
    active = False

    for icon in buff_list:
        if(icon["Attribute_ID"] == buff):
            active = True
            break

    return active

# Set LS
def checkStrike(buff_list):
    if not buffActive(buff_list, 1096) and GetMana(Self()) > 3:
        AddToSystemJournal("Casting LS")
        Cast("Lightning Strike")
        Wait(300)

# Check Counter Attack
def checkCA(buff_list):
    AddToSystemJournal("Checking CA")

    if GetMana(Self()) >= 4 and not buffActive(buff_list, 1095):
        Cast("Counter Attack")
        Wait(300)

# Find mob
def mobFound():
    global TARGET_ID

    is_found = False
    FindTypesArrayEx(mobs, [0xFFFF], [Ground()], False)
    TARGET_ID = FindItem()

    if TARGET_ID > 0:
        is_found = True

    return is_found

# Any PKs around?
def findPKs():
    AddToSystemJournal("Checking for PKs")
    FindNotoriety(-1, 6)

    for x in GetFoundList():
        if not IsNPC(x):
            sendMessage(WEBHOOK, CharName() + " - PK found, going home!")
            goHome()
            


# Move to mob
def moveToBoss():
    mX = GetX(TARGET_ID)
    mY = GetY(TARGET_ID)
    #AddToSystemJournal("Moving to mob @ " + str(mX) + " and " + str(mY))
    newMoveXY(mX, mY, 1, 1, True)
    Attack(TARGET_ID)

 
# Do battle!
def doBattle():
    while IsObjectExists(TARGET_ID):
        if Weight() >= MAX_WEIGHT:
            deposit(HOMEBOOK, HOME_RUNE, HOME_BOX, 'chiv')
            break
        moveToBoss()
        #Attack(TARGET_ID)
        #checkCons()



    #checkEquip(WEBHOOK)
    SetFindDistance(1)
    FindTypeEx(CORPSE_ID, 0xFFFF, Ground(), True)

    for corpse in GetFoundList():
        if corpse not in IGNORE_CORPSES:
            IGNORE_CORPSES.append(corpse)
            UseObject(BWC)
            WaitForTarget(15000)
            TargetToObject(corpse)
            Wait(SHORT_WAIT)
    
    SetFindDistance(DISTANCE)
    
                     
"""
Main
"""
SetMoveBetweenTwoCorners(True)
SetMoveThroughNPC(1)
SetFindDistance(DISTANCE)
SetFindVertical(DISTANCE)
Wait(med_pause)
 
while True:
    for pgs in pgList:
        login(pgs)   
        newMoveXY( 976 , 519 , False , 1 , True )
        Wait(min_pause)     
        getBod(NPCT)
        Wait(med_pause)
        newMoveXY( 976 , 519 , False , 1 , True )
        Wait(min_pause)
        getBod(NPCB)
        Wait(min_pause)
        bodToBook()  
        newMoveXY( 988 , 523 , False , 1 , True )
        Wait(min_pause)
        Disconnect()
        Wait(med_pause)