import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
MODEL = os.getenv("MODEL_ANALYSIS", "@cf/meta/llama-3.1-8b-instruct")

def call_cloudflare_ai(prompt, system_instruction="You are a helpful assistant for an Ultima Online bot developer."):
    """Calls Cloudflare Workers AI with exponential backoff."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{MODEL}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {
        "contents": [{ "parts": [{ "text": prompt }] }],
        "systemInstruction": { "parts": [{ "text": system_instruction }] }
    }
    
    # Actually, Cloudflare's standard AI API uses a slightly different payload format than Gemini
    # Correct Cloudflare format:
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
                return result.get("result", {}).get("response", "No response from AI.")
            elif response.status_code == 429: # Rate limit
                time.sleep(2**i)
            else:
                return f"Error: {response.status_code} - {response.text}"
        except Exception as e:
            time.sleep(2**i)
    
    return "AI request failed after 5 retries."

def send_discord_alert(item_name, old_id, new_id, ai_analysis):
    """Sends a formatted embed to Discord."""
    if not DISCORD_WEBHOOK:
        return
        
    data = {
        "username": "BOD Cycler Intelligence",
        "embeds": [{
            "title": "🚨 Circuit Breaker: ID Mismatch Detected",
            "color": 15158332, # Red
            "fields": [
                {"name": "Item", "value": f"`{item_name}`", "inline": True},
                {"name": "Expected ID", "value": f"`{old_id}`", "inline": True},
                {"name": "Actual ID", "value": f"`{new_id}`", "inline": True},
                {"name": "AI Recommendation", "value": ai_analysis}
            ],
            "footer": {"text": "Stealth Client AI Debugger • Hot-Reload ready"}
        }]
    }
    
    try:
        requests.post(DISCORD_WEBHOOK, json=data)
    except Exception as e:
        print(f"Discord failed: {e}")

def analyze_and_report_mismatch(item_name, expected_id, actual_id, category):
    """
    Called by the Circuit Breaker. 
    Uses AI to confirm if the change looks legitimate and alerts Discord.
    """
    prompt = (
        f"In my Ultima Online script, the item '{item_name}' (Category: {category}) "
        f"was expected to have Type ID {expected_id}, but the bot found {actual_id}. "
        f"Format a one-sentence explanation and a code snippet to update the python dictionary: "
        f"'{item_name}': ('{category}', '{item_name}', {actual_id}, cost)"
    )
    
    system_msg = "You are an expert in Ultima Online scripting and Python data structures."
    
    analysis = call_cloudflare_ai(prompt, system_msg)
    send_discord_alert(item_name, expected_id, actual_id, analysis)
    
    # Save a local pending fix file for the GUI to potentially auto-apply
    pending_file = "pending_fixes.json"
    fixes = {}
    if os.path.exists(pending_file):
        with open(pending_file, "r") as f: fixes = json.load(f)
        
    fixes[item_name] = {"old": expected_id, "new": actual_id, "cat": category, "time": str(time.ctime())}
    
    with open(pending_file, "w") as f:
        json.dump(fixes, f, indent=4)

if __name__ == "__main__":
    # Test call
    analyze_and_report_mismatch("bandana", "0x1540", "0x1541", "Hats")