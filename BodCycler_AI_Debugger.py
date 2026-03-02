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
MODEL_FAST = os.getenv("MODEL_FAST", "@cf/meta/llama-3.1-8b-instruct-fast")

# Dynamically set the file paths to match the main scripts (e.g. LA FABBRICA_bodcycler_stats.json)
try:
    PREFIX = f"{StealthPath()}Scripts\\{CharName()}_"
except Exception:
    PREFIX = "" # Fallback if somehow run entirely outside of Stealth

STATS_FILE = f"{PREFIX}bodcycler_stats.json"
SUPPLY_FILE = f"{PREFIX}bodcycler_supplies.json"
LEARNING_DB = f"{PREFIX}learning_engine.json"

def _call_cf(model, prompt, system_instruction, max_tokens=256, timeout=10):
    """Private helper: calls Cloudflare Workers AI with exponential backoff and <think> stripping."""
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        return "AI API credentials not configured."

    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    cf_payload = {
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens
    }

    for i in range(5):
        try:
            response = requests.post(url, headers=headers, json=cf_payload, timeout=timeout)
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("result", {}).get("response", "No response from AI.")
                response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
                response_text = re.sub(r'<think>.*', '', response_text, flags=re.DOTALL)
                response_text = response_text.strip()
                if not response_text:
                    response_text = "No response."
                return response_text
            elif response.status_code == 429:
                time.sleep(2**i)
            else:
                return f"Error: {response.status_code}"
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
        except Exception: pass
    
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
    except Exception: pass
    return False

def evaluate_riprova_queue(riprova_list):
    """AI evaluation to see which BODs in Riprova are worth retrying based on current supplies."""
    if not os.path.exists(SUPPLY_FILE): return []
    
    try:
        with open(SUPPLY_FILE, "r") as f:
            supplies = json.load(f).get("resources", {})
    except Exception:
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


def report_mismatch(item_name, expected_id, actual_id, category):
    """Reports a graphic ID mismatch to Discord when a crafted item is rejected by a BOD."""
    detail = f"expected graphic 0x{expected_id:04X}, got 0x{actual_id:04X}, category '{category}'"
    send_error_alert("graphic_mismatch", item_name, detail, True)


def send_error_alert(event_type, bod_name, detail, had_resources):
    """Sends a Discord alert for error-handling events (retry, riprova, origine refill)."""
    if not DISCORD_WEBHOOK:
        return

    # Use fast model to generate a 1-sentence explanation
    prompt = (
        f"UO bot event '{event_type}': BOD '{bod_name}', detail '{detail}', "
        f"resources {'available' if had_resources else 'missing'}. "
        f"In one sentence, explain what happened and why."
    )
    msg = _call_cf(MODEL_FAST, prompt,
                   "You are a concise UO bot assistant. Reply with exactly one sentence only.",
                   max_tokens=80, timeout=10)

    # Choose color: orange=lag/recoverable, red=shortage
    color = 0xFFA500 if had_resources else 0xFF4444

    payload = {
        "username": "BOD Cycler Intelligence",
        "embeds": [{
            "title": f"⚠️ {event_type.replace('_', ' ').title()}",
            "description": msg,
            "color": color,
            "footer": {"text": datetime.now().strftime('%H:%M:%S')}
        }]
    }

    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except Exception as e:
        print(f"Discord error alert failed: {e}")


