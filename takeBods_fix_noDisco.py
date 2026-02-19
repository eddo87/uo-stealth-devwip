import re
import datetime
import os

 
#Personal changes
 
pgList = ['ed2', 'ed3', 'ed5']
bookTName = 'Tailor'    # Names must be the same across all chars
bookBName = 'Black'     # note this is case sensitive
closeToFull = ['495', '498', '499']
 
 

 
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
 
 
 
#Functions 
 
def setupBooks(bookNeeded):
    FindType(bulkBookType, Backpack())
    books = GetFoundList()

    for book in books:
        tooltip = GetTooltip(book)
        if tooltip and bookNeeded in tooltip:
            return book

    print(f"{CharName()}: Cannot find {bookNeeded} book in backpack!")
    return None
    
def processBodBook(bookName, color):
    book = setupBooks(bookName)
    if not book:
        return

    # Scan for matching BODs ONCE
    FindTypeEx(bodType, color, Backpack())
    bod_list = GetFoundList()

    # If no BODs of that color → nothing to do
    if not bod_list:
        return

    for bod in bod_list:
        tooltip = GetTooltip(book)
        if any(x in tooltip for x in closeToFull):
            print(f"{CharName()}: WARNING: {bookName} book nearly full!")

        MoveItem(bod, 1, book, 0, 0, 0)
        Wait(min_pause)

    
    
def bodToBook():
    # Tailor BODs
    processBodBook(bookTName, bodTCol)
    # Blacksmith BODs
    processBodBook(bookBName, bodBCol)
 
 
 
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
        start = datetime.datetime.now() 
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
        if InJournalBetweenTimes('You can get an order now.', start, datetime.datetime.now()) != -1:
            return
        else:
            Wait(min_pause) 
            newMoveXY( 988 , 523 , False , 1 , True )
            Wait(med_pause)
            #os.system('shutdown -s')
            Wait(90000)
  
             
 
def login(pgProfile):
    ChangeProfile(pgProfile)
    Wait(long_pause)
    Connect()     
    Wait(long_pause)
 
                     
 
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