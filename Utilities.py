"""
Script written by JDuff

Script is designed to be imported into other scripts,
providing portability/reusablility of generic methods,
variables, and classes
"""
from stealth import *
from datetime import *
import re
import threading
import datetime

try:
    from discord_webhook import *
except:
    pass

##################
# Global variables
##################
AFK_CHECK_GUMPS = [0xb3601a01, 0xc37345f3, 0xc8485931]
GMS = ["dysis", "eos", "selene", "marshall", "larson"]
TONG_ID = 0xfbb
TINKER_ID = 0x1eb8
INGOT_ID = 0x1bf2
BOD_BOOK_ID = 0x2259
BOD_ID = 8792
BOD_BOOK_GUMP = 1425364447
#CRAFT_GUMP = 949095101
CRAFT_GUMP = 0x38920abd
RB_GUMP = 0x554B87F3
BOD_GUMP = 1526454082
SMALL_BOD_GUMP = 2611865322
LARGE_BOD_GUMP = 3188567326
HAMMER_IDS = [0x13E4, 0x13E3]
leathertypes = [0, 0x0851, 0x0845, 0x08AC]


#SHARD
RECALL_CHIVALRY_OFFSET = 7  # Adjusted to start from 7
RUNE_INCREMENT = 6  # The difference between consecutive rune indices

RESET_BOD_ITEMS = [
	"bascinet",
	"bronze shield",
	"buckler",
	"close helmet",
	"female plate",
	"heater shield",
	"helmet",
	"metal kite shield",
	"metal shield",
	"norse helm",
	"tear kite shield"
]
ARMOR_ITEM_LAYERS  = [
    TorsoHLayer(),
    EggsLayer(),
    NeckLayer(),
    RobeLayer(),
    WaistLayer(),
    TalismanLayer(),
    HatLayer(),
    ArmsLayer(),
    TorsoLayer(),
    PantsLayer(),
    GlovesLayer(),
    LhandLayer(),
    RingLayer(),
    BraceLayer(),
    CloakLayer(),
    EarLayer(),
    RhandLayer(),
    ShoesLayer(),
    ShirtLayer()
]
ARMOR_ITEM_LIST = []
RES_GUMP = 2304780453
RES_GUMP2 = 2957810225
VAMP_HUE = 33918
WRAITH_HUE = 0x4001
NOTORIETIES = {
	"Blue": 1,
	"Green": 2,
	"Gray": 3,
	"Criminal": 4,
	"Orange": 5,
	"Red": 6,
	"Yellow": 7
}

##################
# Definitions
##################
# Demise AFK check
def afkCheck():
    rtrn = False
    gumpList = GetGumpsCount()

    for i in range(gumpList):
        if GetGumpID(i) in AFK_CHECK_GUMPS:
            rtrn = True
            break

    FindType(-1, Ground())
    for x in GetFoundList():
        if GetName(x).lower() in GMS:
            rtrn = True
            break

    return rtrn

# Attempt to send a Discord message
def sendMessage(URL: str, Message: str):
	try:
		if URL:
			webhook = DiscordWebhook(url=URL, content=Message)
			webhook.execute()
		else:
			AddToSystemJournal("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
			AddToSystemJournal(Message)
			AddToSystemJournal("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
	except:
		AddToSystemJournal("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
		AddToSystemJournal(Message)
		AddToSystemJournal("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

# Send a Discordd embedded message
def sendReport(URL: str, title: str, *data):
	try:
		webhook = DiscordWebhook(url=URL)
		embed = DiscordEmbed(title=title)

		for arg in data:
			for key in arg.keys():
				if key == list(arg.keys())[-1]:
					embed.add_embed_field(getResourceName(key), arg[key], False)
				else:
					embed.add_embed_field(getResourceName(key), arg[key])

		webhook.add_embed(embed)
		webhook.execute()
	except:
		AddToSystemJournal("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
		AddToSystemJournal("Failed to send report data")
		AddToSystemJournal("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

# Get resource name from hue
def getResourceName(hue: int):
	resource = str(hue).title()

	match hue:
		case 0:
			resource = "Iron"
		case 2419:
			resource = "Dull Copper"
		case 2406:
			resource = "Shadow Iron"
		case 2413:
			resource = "Copper"
		case 2418:
			resource = "Bronze"
		case 2213:
			resource = "Gold"
		case 2425:
			resource = "Agapite"
		case 2207:
			resource = "Verite"
		case 2219:
			resource = "Valorite"
		case 0x3195:
			resource = "Ecru Citrine"
		case 0x3193:
			resource = "Turquoise"
		case 0x3192:
			resource = "Dark Sapphire"
		case 0x3194:
			resource = "Perfect Emerald"
		case 0x3198:
			resource = "Blue Diamond"
		case 0x3197:
			resource = "Fire Ruby"
		case 0x5732:
			resource = "Crystalline Blackrock"
		case 0x0F28:
			resource = "Small Blackrock"

	return resource

# Determine if a GUMP exists
def getGumpIndex(GUMP_ID: int):
    rtrn = -1

    for i in range(GetGumpsCount()):
        if GetGumpID(i) == GUMP_ID:
            rtrn = i
            break

    return rtrn

# Wait for a gump for a set amount of time
def waitForGump(GUMP_ID: int, Timeout = 15000):
    start = datetime.datetime.now()

    while getGumpIndex(GUMP_ID) == -1:
        Wait(1)

        if (datetime.datetime.now() - start) >= timedelta(milliseconds = Timeout):
            break
     
# Find a string in a gump
def inGump(string: str, gumpID: int):
	gumpIndex = getGumpIndex(gumpID)
	isTrue = False
	
	for x in GetGumpFullLines(gumpIndex):
		if string in x:
			isTrue = True
			break
		
	return isTrue
	   
# Is item found in container?
def isItemInContainer(item: int, container = Backpack(), in_sub = False):
    itemType = GetType(item)
    itemColor = GetColor(item)
    FindTypeEx(itemType, itemColor, container, in_sub)

    if item in GetFoundList():
        return True
    else:
        return False

# Drop item on the ground
def dropToGround(item: int):
	X, Y, Z = GetX(Self()), GetY(Self()), GetZ(Self())
	success = True

	MoveItem(item, 1, Ground(), X, Y - 1, Z)
	Wait(800)
    
	if isItemInContainer(item):
		MoveItem(item, 1, Ground(), X, Y + 1, Z)
		Wait(800)
            
		if isItemInContainer(item):
			MoveItem(item, 1, Ground(), X - 1, Y, Z)
			Wait(800)
                    
			if isItemInContainer(item):
				MoveItem(item, 1, Ground(), X + 1, Y, Z)
				Wait(800)

				if isItemInContainer(item):
					AddToSystemJournal("Could not drop item")
					success = False

	return success

# Use Runebook
def useRB(rb: int, rune: int, spell = "recall"):
    X, Y = GetX(Self()), GetY(Self())

    if spell == "chiv":
        if rune == 1:
            rune_Btn = RECALL_CHIVALRY_OFFSET
        else:
            rune_Btn = RECALL_CHIVALRY_OFFSET + (rune - 1) * RUNE_INCREMENT

    elif spell == "gate":
        runes = list(range(0, 102, 6))
    else:
        runes = list((range(-1, 100, 6)))

    while GetX(Self()) == X and GetY(Self()) == Y:
        print(f'Use rb {rb} rune {rune} method: {spell}')
        start = datetime.datetime.now() 
        UseObject(rb)
        #print(rune_Btn)
        Wait(450)
        for gmp in range(GetGumpsCount()):
            if GetGumpID(gmp) == RB_GUMP: 
                Wait(150)
                NumGumpButton(gmp, rune_Btn)
                Wait(2000)
                if InJournalBetweenTimes('That location is blocked.', start, datetime.datetime.now()) != -1:
                    print('location blocked')
                    return
                elif InJournalBetweenTimes('Your concentration is disturbed', start, datetime.datetime.now()) != -1:
                    print('vai via puttana!')
                    Cast("Dispel Evil")
                    Wait(2000)
                    return

def deposit(rb, runacasa, lootboxcasa, spell = "recall"):
    useRB(rb, runacasa, spell)
    Wait(900)
    #UseObject(lootboxcasa)
    for col in leathertypes:
        FindTypeEx(0x1081, col, Backpack(), True)
        CheckLag()
        MoveItem(FindItem(),FindQuantity(),lootboxcasa,0,0,0)
        #CheckLag()
    return

# Find out where we are
def isInBounds(x1: int, y1: int, x2: int, y2: int):
    inBounds = False
    selfX = GetX(Self())
    selfY = GetY(Self())

    if selfX >= x1 and selfX <= x2 and selfY >= y1 and selfY <= y2:
        inBounds = True

    return inBounds

# Get the tooltip of an item
def getTooltip(item: int):
    start = datetime.datetime.now()
    tooltip = ""

    while tooltip == "":
        tooltip = GetTooltip(item).lower()

        if (datetime.datetime.now() - start) >= timedelta(seconds = 2):
            FindType(-1, Backpack())
            GetTooltip(FindItem())

    return tooltip

# Get crafting itemID and gump buttons
def getCraftingButtons(item: str):
	item_id = 0
	gump_button1 = 0
	gump_button2 = 0
	
	# Determine item_id and gump buttons, based on item we need to craft
	match item:
		# Axes
		case "axe":
			item_id = 0x0F49
			gump_button1 = 43
			gump_button2 = 2
		case "battle axe":
			item_id = 0x0F47
			gump_button1 = 43
			gump_button2 = 9
		case "double axe":
			item_id = 0x0F4B
			gump_button1 = 43
			gump_button2 = 16
		case "executioners axe":
			item_id = 0x0F45
			gump_button1 = 43
			gump_button2 = 23
		case "large battle axe":
			item_id = 0x13FB
			gump_button1 = 43
			gump_button2 = 30
		case "two handed axe":
			item_id = 0x1443
			gump_button1 = 43
			gump_button2 = 37
		case "war axe":
			item_id = 0x13B0
			gump_button1 = 43
			gump_button2 = 44
		# Bashing
		case "hammer pick":
			item_id = 0x143D
			gump_button1 = 57
			gump_button2 = 2
		case "mace":
			item_id = 0x0F5C
			gump_button1 = 57
			gump_button2 = 9
		case "maul":
			item_id = 0x143B
			gump_button1 = 57
			gump_button2 = 16
		case "war mace":
			item_id = 0x1407
			gump_button1 = 57
			gump_button2 = 30
		case "war hammer":
			item_id = 0x1439
			gump_button1 = 57
			gump_button2 = 37
		# Polearms
		case "bardiche":
			item_id = 0x0F4D
			gump_button1 = 50
			gump_button2 = 2
		case "halberd":
			item_id = 0x143E
			gump_button1 = 50
			gump_button2 = 23
		case "short spear":
			item_id = 0x1403
			gump_button1 = 50
			gump_button2 = 44
		case "spear":
			item_id = 0x0F62
			gump_button1 = 50
			gump_button2 = 58
		case "war fork":
			item_id = 0x1405
			gump_button1 = 50
			gump_button2 = 65
		# Bladed
		case "broadsword":
			item_id = 0x0F5E
			gump_button1 = 36
			gump_button2 = 9
		case "cutlass":
			item_id = 0x1441
			gump_button1 = 36
			gump_button2 = 23
		case "dagger":
			item_id = 0x0F52
			gump_button1 = 36
			gump_button2 = 30
		case "katana":
			item_id = 0x13FF
			gump_button1 = 36
			gump_button2 = 37
		case "kryss":
			item_id = 0x1401
			gump_button1 = 36
			gump_button2 = 44
		case "longsword":
			item_id = 0x0F61
			gump_button1 = 36
			gump_button2 = 51
		case "scimitar":
			item_id = 0x13B6
			gump_button1 = 36
			gump_button2 = 58
		case "viking sword":
			item_id = 0x13B9
			gump_button1 = 36
			gump_button2 = 65
		# Chainmail
		case "chainmail coif":
			item_id = 0x13BB
			gump_button1 = 8
			gump_button2 = 2
		case "chainmail leggings":
			item_id = 0x13BE
			gump_button1 = 8
			gump_button2 = 9
		case "chainmail tunic":
			item_id = 0x13BF
			gump_button1 = 8
			gump_button2 = 16
		# Helmets
		case "bascinet":
			item_id = 0x140C
			gump_button1 = 22
			gump_button2 = 2
		case "close helmet":
			item_id = 0x1408
			gump_button1 = 22
			gump_button2 = 9
		case "helmet":
			item_id = 0x140A
			gump_button1 = 22
			gump_button2 = 16
		case "norse helm":
			item_id = 0x140E
			gump_button1 = 22
			gump_button2 = 23
		case "plate helm":
			item_id = 0x1412
			gump_button1 = 22
			gump_button2 = 30
		# Platemail
		case "platemail arms":
			item_id = 0x1410
			gump_button1 = 15
			gump_button2 = 2
		case "platemail gloves":
			item_id = 0x1414
			gump_button1 = 15
			gump_button2 = 9
		case "platemail gorget":
			item_id = 0x1413
			gump_button1 = 15
			gump_button2 = 16
		case "platemail legs":
			item_id = 0x1411
			gump_button1 = 15
			gump_button2 = 23
		case "platemail tunic":
			item_id = 0x1415
			gump_button1 = 15
			gump_button2 = 30
		case "female plate":
			item_id = 0x1C04
			gump_button1 = 15
			gump_button2 = 37
		# Ringmail
		case "ringmail gloves":
			item_id = 0x13EB
			gump_button1 = 1
			gump_button2 = 2
		case "ringmail leggings":
			item_id = 0x13F0
			gump_button1 = 1
			gump_button2 = 9
		case "ringmail sleeves":
			item_id = 0x13EE
			gump_button1 = 1
			gump_button2 = 16
		case "ringmail tunic":
			item_id = 0x13EC
			gump_button1 = 1
			gump_button2 = 23
		# Shields
		case "buckler":
			item_id = 0x1B73
			gump_button1 = 29
			gump_button2 = 2
		case "bronze shield":
			item_id = 0x1B72
			gump_button1 = 29
			gump_button2 = 9
		case "heater shield":
			item_id = 0x1B76
			gump_button1 = 29
			gump_button2 = 16
		case "metal shield":
			item_id = 0x1B7B
			gump_button1 = 29
			gump_button2 = 23
		case "metal kite shield":
			item_id = 0x1B74
			gump_button1 = 29
			gump_button2 = 30
		case "tear kite shield":
			item_id = 0x1B79
			gump_button1 = 29
			gump_button2 = 37

	return item_id, gump_button1, gump_button2

# Get material hue and craft gump button to change material
def getMaterialColor(tooltip: str):
	color = 0
	gump_button = 6
	material = "iron"
	
	if "with dull copper" in tooltip:
		material = "dull copper"
		gump_button = 13
		color = 2419
	elif "with shadow iron" in tooltip:
		material = "shadow iron"
		gump_button = 20
		color = 2406
	elif "with copper" in tooltip:
		material = "copper"
		gump_button = 27
		color = 2413
	elif "with bronze" in tooltip:
		material = "bronze"
		gump_button = 34
		color = 2418
	elif "with gold" in tooltip:
		material = "gold"
		gump_button = 41
		color = 2213
	elif "with agapite" in tooltip:
		material = "agapite"
		gump_button = 48
		color = 2425
	elif "with verite" in tooltip:
		material = "verite"
		gump_button = 55
		color = 2207
	elif "with valorite" in tooltip:
		material = "valorite"
		gump_button = 62
		color = 2219

	return color, gump_button, material

# Returns a BOD object
def populateBOD(tooltip: str):
	bod = BOD()
	tip = 4
	tooltips = tooltip.split("|")

	bod.Exceptional = "exceptional" in tooltip
	bod.Color, bod.CraftChangeButton, bod.Material = getMaterialColor(tooltip)

	if "large" in tooltip:
		bod.Size = "large"

	if bod.Exceptional:
		tip += 1

	if bod.Color > 0:
		tip += 1

	bod.Item = re.sub("[^a-z ]", "", tooltips[tip + 1]).strip()
	bod.Quantity = int(re.sub("[^0-9]", "", tooltips[tip])) - int(re.sub("[^0-9]", "", tooltips[tip + 1]))
	bod.ItemID, bod.CraftButton1, bod.CraftButton2 = getCraftingButtons(bod.Item)

	return bod

# Equips a +smithing hammer
def equipHammer(restock_box: int):
	rhand = ObjAtLayer(RhandLayer())

	if rhand > 0 and GetType(rhand) not in HAMMER_IDS:
		MoveItem(ObjAtLayer(RhandLayer()), 1, Backpack(), 0, 0, 0)
		Wait(800)
		rhand = 0

	if rhand == 0:
		FindTypesArrayEx(HAMMER_IDS, [0x0482], [Backpack()], True)
		found = GetFoundList()

		if len(found) <= 0:
			FindTypesArrayEx(HAMMER_IDS, [0x0482], [restock_box], True)
			found = GetFoundList()

		rhand = found[0]
		Equip(RhandLayer(), rhand)
		Wait(800)

	return rhand

# Unequips hammer
def unequipHammer():
	hammer = ObjAtLayer(RhandLayer())

	if hammer > 0 and GetType(hammer) in HAMMER_IDS:
		MoveItem(hammer, 1, Backpack(), 0, 0, 0)
		Wait(800)

# Crafts item listed on BOD
def craftItem(restock_box: int, webhook_url: str, bod):
	if bod.ItemID == 0:
		sendMessage(webhook_url, "Unable to determine BOD item: " + bod.Item)
		return
	
	# Do we need to restock?
	if CountEx(INGOT_ID, bod.Color, Backpack()) < 1000:
		restockIngots(restock_box, bod.Color, 1000, webhook_url)

	FindTypeEx(bod.ItemID, bod.Color, Backpack(), False)
	i = len(GetFoundList())

	# Make the items
	while i < bod.Quantity:
		AddToSystemJournal("Crafting item {} of {}".format(str(i + 1).rjust(2), bod.Quantity))

		# Get a hammer if we are making plate items
		if "plate" in bod.Item and bod.Exceptional:
			tong = equipHammer(restock_box)
		else:
			FindTypeEx(TONG_ID, 0xFFFF, Backpack(), True)
			tong = FindItem()

		# Do we have any tongs?
		if tong == 0:
			# Do we need to restock?
			if CountEx(INGOT_ID, 0, Backpack()) < 100:
				restockIngots(restock_box, 0, 100, webhook_url)

			FindTypeEx(TINKER_ID, 0xFFFF, Backpack(), True)
			tinker_tools = GetFoundList()
			count = len(tinker_tools)

			# Do we have any tinker tools??
			while count < 3:
				UseObject(tinker_tools[0])
				waitForGump(CRAFT_GUMP)
				NumGumpButton(getGumpIndex(CRAFT_GUMP), 8)
				waitForGump(CRAFT_GUMP)
				NumGumpButton(getGumpIndex(CRAFT_GUMP), 23)
				waitForGump(CRAFT_GUMP, 2000)
				FindTypeEx(TINKER_ID, 0xFFFF, Backpack(), True)
				count = len(GetFoundList())
			
			# Craft 3 tongs
			for i in range(3):
				UseObject(tinker_tools[0])
				waitForGump(CRAFT_GUMP)
				NumGumpButton(getGumpIndex(CRAFT_GUMP), 8)
				waitForGump(CRAFT_GUMP)
				NumGumpButton(getGumpIndex(CRAFT_GUMP), 86)
				waitForGump(CRAFT_GUMP, 2000)

			# Tongs made, let's continue
			FindTypeEx(TONG_ID, 0xFFFF, Backpack(), True)
			tong = FindItem()

		UseObject(tong)
		waitForGump(CRAFT_GUMP)
		NumGumpButton(getGumpIndex(CRAFT_GUMP), bod.CraftButton1)
		waitForGump(CRAFT_GUMP)
		NumGumpButton(getGumpIndex(CRAFT_GUMP), bod.CraftButton2)
		waitForGump(CRAFT_GUMP, 2000)
		Wait(700)

		if bod.Exceptional:
			FindTypeEx(bod.ItemID, bod.Color, Backpack(), False)

			for item in GetFoundList():
				tooltip = getTooltip(item).lower()

				if "exceptional" not in tooltip:
					FindTypeEx(TONG_ID, 0xFFFF, Backpack(), True)
					UseObject(FindItem())
					waitForGump(CRAFT_GUMP)
					NumGumpButton(getGumpIndex(CRAFT_GUMP), 14)
					WaitForTarget(800)
					TargetToObject(item)
					waitForGump(CRAFT_GUMP)
					CloseSimpleGump(getGumpIndex(CRAFT_GUMP))
					Wait(800)

		FindTypeEx(bod.ItemID, bod.Color, Backpack(), False)
		foundlist = GetFoundList()
		i = len(foundlist)

		if i > bod.Quantity:
			FindTypeEx(TONG_ID, 0xFFFF, Backpack(), True)
			UseObject(FindItem())
			waitForGump(CRAFT_GUMP)
			NumGumpButton(getGumpIndex(CRAFT_GUMP), 14)
			WaitForTarget(800)
			TargetToObject(foundlist[0])
			waitForGump(CRAFT_GUMP)
			CloseSimpleGump(getGumpIndex(CRAFT_GUMP))
			Wait(800)

	CloseSimpleGump(getGumpIndex(CRAFT_GUMP))
	unequipHammer()

# Restock ingots
def restockIngots(restock_box: int, color: int, ingot_count: int, webhook_url: str):
	Wait(800)
	UseObject(restock_box)
	Wait(800)
	on_hand = CountEx(INGOT_ID, 0, Backpack())
	in_box = CountEx(INGOT_ID, 0, restock_box)

	if in_box < ingot_count:
		sendMessage(webhook_url, CharName() + " - Out of ingots!")
		Disconnect()
		exit()
	else:
		while on_hand < ingot_count:
			FindTypeEx(INGOT_ID, color, restock_box, True)
			ingots = FindItem()
			move_amt = ingot_count - on_hand
			MoveItem(ingots, move_amt, Backpack(), 0, 0, 0)
			Wait(800)
			on_hand = CountEx(INGOT_ID, color, Backpack())

# Find a trash can and drop the item in
def trashItem(item_id: int):
	current_find = GetFindDistance()
	SetFindDistance(3)
	FindTypeEx(0x0E77, 0xFFFF, Ground(), False)
	trash_can = FindItem()
	
	if trash_can > 0:
		newMoveXY(GetX(trash_can), GetY(trash_can), -1, 1, True)
		MoveItem(item_id, 1, trash_can, 0, 0, 0)
		Wait(1000)
		
	SetFindDistance(current_find)

# Set the current equipment list
def setDress():
    global ARMOR_ITEM_LIST

    for i in ARMOR_ITEM_LAYERS:
        ARMOR_ITEM_LIST.append(0)

    for i in range(len(ARMOR_ITEM_LAYERS)):
        if ObjAtLayer(ARMOR_ITEM_LAYERS[i]) > 0:
            ARMOR_ITEM_LIST[i] = ObjAtLayer(ARMOR_ITEM_LAYERS[i])
            


# Send gold to bank
def sendGold(WEBHOOK: str):
    success = False
    FindTypeEx(0xe76, 0xFFFF, Backpack(), False)
    bags = GetFoundList()

    if len(bags) > 0:
        for bag in bags:
            tooltip = getTooltip(bag)

            if tooltip.split("|")[0].lower() == "a bag of sending":
                charges = int(getCharges(tooltip))

                if charges < 1:
                    FindTypeEx(0x26b8, 0xFFFF, Backpack(), False)
                    pot = GetFoundList()

                    if len(pot) > 0:
                        UseObject(pot[0])
                        CheckLag()
                        TargetToObject(bag)
                        Wait(800)
                    else:
                        sendMessage(WEBHOOK, CharName() + " - Out of Powder of Translocation and has a full bag")

                FindTypeEx(0xeed, 0xFFFF, Backpack(), True)
                UseObject(bag)
                CheckLag()
                TargetToObject(FindItem())
                CheckLag()
                success = True
                break
    else:
        sendMessage(WEBHOOK, CharName() + " - No Bag of Sending found and has a full bag")

    return success
		
# Get charges left on bag
def getCharges(tooltip: str):
    tips = tooltip.split("|")
    return tips[2].split(":")[1].strip()

# Check durability on equipment
def checkEquip(WEBHOOK: str):
	AddToSystemJournal("Checking durability")
    
	for item in ARMOR_ITEM_LIST:
		if item > 0:
			tooltip = getTooltip(item)
        
			if getDur(tooltip) <= 10:
				sendMessage(WEBHOOK, CharName() + " - " + tooltip.split("|")[0] + " needs repaired!")

# Returns the durability of an item
def getDur(tooltip: str):
	dur = 255
	
	for x in tooltip.lower().split("|"):
		if "durability" in x:
			dur = int(re.sub("[^0-9]", "", x.split("/")[0]))
			break
		
	return dur

# Re-equip after res
def reEquip():
    robe = ObjAtLayer(RobeLayer())

    if robe > 0:
        MoveItem(robe, 1, Backpack(), 0, 0, 0)
        Wait(800)
        dropToGround(robe)

    for i in range(len(ARMOR_ITEM_LIST)):
        if ARMOR_ITEM_LIST[i] > 0:
            Equip(ARMOR_ITEM_LAYERS[i], ARMOR_ITEM_LIST[i])
            Wait(700)

# Check if a buff is activate
def buffActive(buff: str):
	active = False

	for icon in GetBuffBarInfo():
		if buff.lower() in GetClilocByID(icon["ClilocID1"]).lower().strip():
			active = True

	return active

# Try honoring target
def tryHonor(target: int):
	if GetHP(target) == GetMaxHP(target) and not buffActive("Honored"):
		UseVirtue("Honor")
		WaitForTarget(15000)
		TargetToObject(target)
		
	Attack(target)

# Check if Enemy of One is active
def checkEOO():
	if Mana() >= 10 and not buffActive("Enemy of One"):
		Cast("Enemy Of One")
		Wait(2000)

# Check if Consecrate Weapon is active
def checkCons():
	if Mana() >= 7 and not buffActive("Consecrate"):
		Cast("Consecrate Weapon")
		Wait(500)

# Check if Divine Fury is active
def checkDF():
	if Mana() >= 10 and not buffActive("Divine Fury"):
		Cast("Divine Fury")
		Wait(1300)

# Check if we NEED to cast Divine Fury
def checkDF2():
	if Mana() >= 10 and (Stam() <= (MaxStam() - 30) or not buffActive("Divine Fury")):
		Cast("Divine Fury")
		Wait(1300)

# Check if Counter Attack is active
def checkCA():
	if Mana() >= 4 and not buffActive("Counter Attack"):
		Cast("Counter Attack")
		Wait(300)

# Check if Curse Wepon is active
def checkCW():
	if Mana() >= 5 and not buffActive("Curse Weapon"):
		FindTypeEx(0x2263, 0xFFFF, Backpack(), True)
		scrolls = FindItem()

		if scrolls > 0:
			UseObject(scrolls)
		else:
			Cast("Curse Weapon")

		Wait(750)

# Move to target
def moveToBoss(target: int):
	targetX = GetX(target)
	targetY = GetY(target)
	targetZ = GetZ(target)

	if newMoveXYZ(targetX, targetY, targetZ, 0, 0, True, None):
		AddToSystemJournal("Moving to target @ ({}, {})".format(targetX, targetY))

	Attack(target)
	ClearBadLocationList()
		

##################
# Objects
##################
class BOD:
	Material: str
	Quantity: int
	Color: int
	Item: str
	Size = "small"
	Exceptional: bool
	ItemID: int
	CraftButton1: int
	CraftButton2: int
	CraftChangeButton: int
