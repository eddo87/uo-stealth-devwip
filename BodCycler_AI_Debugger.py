import os
import re
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# Import PyStealth to dynamically grab Character Name and Script Path
from stealth import CharName, StealthPath

load_dotenv()

# Configuration
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
MODEL = os.getenv("MODEL_ANALYSIS", "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b")

# Dynamically set the file paths to match the main scripts (e.g. LA FABBRICA_bodcycler_stats.json)
try:
    PREFIX = f"{StealthPath()}Scripts\\{CharName()}_"
except Exception:
    PREFIX = "" # Fallback if somehow run entirely outside of Stealth

STATS_FILE = f"{PREFIX}bodcycler_stats.json"
SUPPLY_FILE = f"{PREFIX}bodcycler_supplies.json"
LEARNING_DB = f"{PREFIX}learning_engine.json"

def call_cloudflare_ai(prompt, system_instruction="You are a helpful assistant for an Ultima Online bot developer."):
    """Calls Cloudflare Workers AI with exponential backoff."""
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        return "AI API credentials not configured."
        
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{MODEL}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    cf_payload = {
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]
    }

    for i in range(5): # 5 retries
        try:
            response = requests.post(url, headers=headers, json=cf_payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("result", {}).get("response", "No response from AI.")
                response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()
                return response_text
            elif response.status_code == 429: # Rate limit
                time.sleep(2**i)
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            time.sleep(2**i)
    
    return "AI request failed after 5 retries."

def log_failure(item_name, reason, material):
    """Logs a failure to the learning engine to track efficiency."""
    db = {}
    if os.path.exists(LEARNING_DB):
        try:
            with open(LEARNING_DB, "r") as f:
                db = json.load(f)
        except: pass
    
    entry = db.get(item_name, {"failures": 0, "reasons": [], "last_material": material})
    entry["failures"] += 1
    if reason not in entry["reasons"]:
        entry["reasons"].append(reason)
    
    db[item_name] = entry
    
    with open(LEARNING_DB, "w") as f:
        json.dump(db, f, indent=4)

def should_trash(item_name):
    """Checks if the Learning Engine suggests trashing this item."""
    if not os.path.exists(LEARNING_DB):
        return False
        
    try:
        with open(LEARNING_DB, "r") as f:
            db = json.load(f)
        entry = db.get(item_name)
        if entry and entry["failures"] >= 3:
            return True
    except: pass
    return False

def evaluate_riprova_queue(riprova_list):
    """AI evaluation to see which BODs in Riprova are worth retrying based on current supplies."""
    if not os.path.exists(SUPPLY_FILE): return []
    
    try:
        with open(SUPPLY_FILE, "r") as f:
            supplies = json.load(f).get("resources", {})
    except:
        supplies = {}
        
    retry_list = []
    for bod in riprova_list:
        mat = bod.get("material", "Iron").title()
        if supplies.get(mat, 0) > 100:
            retry_list.append(bod)
            
    return retry_list

def send_prize_notification(prize_name: str):
    """Sends an instant Discord alert when a prize is secured into the Reward Crate."""
    if not DISCORD_WEBHOOK:
        return
    payload = {
        "username": "BOD Cycler Intelligence",
        "embeds": [{
            "title": "🏆 Prize Secured!",
            "description": f"**{prize_name}** dropped into the Reward Crate.",
            "color": 16766720,  # Gold
            "footer": {"text": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except Exception as e:
        print(f"Discord prize notification failed: {e}")


def send_discord_session_report():
    """Sends a detailed Discord report tracking specific materials used, speed, and rewards."""
    if not DISCORD_WEBHOOK: return

    stats = {}
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f: stats = json.load(f)
        except: pass
        
    supplies = {}
    if os.path.exists(SUPPLY_FILE):
        try:
            with open(SUPPLY_FILE, "r") as f: supplies = json.load(f)
        except: pass
        
    db = {}
    if os.path.exists(LEARNING_DB):
        try:
            with open(LEARNING_DB, "r") as f: db = json.load(f)
        except: pass

    # 1. Calculate Production and Speed
    crafted = stats.get("crafted", 0)
    session_start = stats.get("session_start", time.time())
    hours_elapsed = (time.time() - session_start) / 3600.0
    if hours_elapsed < 0.01: hours_elapsed = 0.01 # Prevent divide by zero error on instant stops
    bods_per_hour = round(crafted / hours_elapsed, 1)

    # 2. Extract Rewards
    cbds = stats.get("cbd_count", 0)
    barbed_kits = stats.get("barbed_kit_count", 0)
    prizes_small = stats.get("prized_small", 0)
    prizes_large = stats.get("prized_large", 0)
    total_prizes = cbds + barbed_kits + prizes_small + prizes_large
    
    yield_eff = round((total_prizes / crafted) * 100 if crafted > 0 else 0, 1)
    recovery_hits = stats.get("recovery_success", 0)

    # 3. Extract Materials Consumed
    mats_used = stats.get("mats_used", {})
    used_cloth = mats_used.get("cloth", 0)
    used_leather = mats_used.get("leather", 0)
    used_spined = mats_used.get("spined", 0)
    used_horned = mats_used.get("horned", 0)
    used_barbed = mats_used.get("barbed", 0)

    # Aggregate current Supplies
    res = supplies.get("resources", {})
    cloth = res.get("Cloth", 0)
    iron = res.get("Ingots", 0)
    leather = res.get("Leather", 0)
    spined = res.get("Spined", 0)
    horned = res.get("Horned", 0)
    barbed = res.get("Barbed", 0)

    # Identify most failed items from the learning engine
    top_failures = sorted(db.items(), key=lambda x: x[1].get('failures', 0), reverse=True)[:3]
    fail_str = ", ".join([f"{k} ({v['failures']}x)" for k, v in top_failures]) if top_failures else "None"

    # Call Cloudflare AI for a brief, intelligent summary of the run
    ai_prompt = (
        f"Analyze this Ultima Online bot session data briefly (2 sentences max). "
        f"Crafted: {crafted} at {bods_per_hour}/hr, High-Tier Loot: {cbds} CBDs, {barbed_kits} Barbed Kits. "
        f"Mats used: Cloth {used_cloth}, Leather {used_leather}, Barbed {used_barbed}. "
        f"Most failed items: {fail_str}."
    )
    ai_analysis = call_cloudflare_ai(ai_prompt)

    payload = {
        "username": "BOD Cycler Intelligence",
        "embeds": [{
            "title": "📊 BOD Cycler: End of Session Report",
            "color": 3447003, # Blue
            "fields": [
                {"name": "⚙️ Production", "value": f"**Total Crafted:** {crafted}\n**Speed:** {bods_per_hour} BODs/hr\n**Yield Eff:** {yield_eff}%", "inline": True},
                {"name": "🎯 Saved for Prizes", "value": f"**Small BODs:** {prizes_small}\n**Large BODs:** {prizes_large}\n**Total Saved:** {prizes_small + prizes_large}", "inline": True},
                {"name": "🏆 High-Tier Loot", "value": f"**CBDs:** {cbds}\n**Barbed Kits:** {barbed_kits}", "inline": True},
                {"name": "🔥 Materials Consumed", "value": f"**Cloth:** {used_cloth} | **Leather:** {used_leather}\n**Spined:** {used_spined} | **Horned:** {used_horned} | **Barbed:** {used_barbed}", "inline": False},
                {"name": "📦 Current Reserves", "value": f"**Cloth:** {cloth}  |  **Iron:** {iron}\n**Leather:** {leather} (N) / {spined} (S) / {horned} (H) / {barbed} (B)", "inline": False},
                {"name": "🔄 Riprova Recovery", "value": f"**Recovered BODs:** {recovery_hits}\n**Top Failures:** {fail_str}", "inline": False},
                {"name": "🧠 AI Session Insights", "value": ai_analysis, "inline": False}
            ],
            "footer": {"text": f"Session End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Hot-Reload Active"}
        }]
    }

    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except Exception as e:
        print(f"Discord report failed: {e}")