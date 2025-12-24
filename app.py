from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json
import random
import os

app = Flask(__name__)

# Configuration
DATA_FILE = "players.json"
PLAYERS_PER_TEAM = 6

# Initialize data structure
def init_data():
    """Initialize default data structure"""
    return {
        "admins": [],  # List of admin phone numbers
        "players": {},  # {phone: {name}}
        "session": {
            "active": False,
            "participants": []  # List of phones who said "in"
        }
    }

def load_data():
    """Load data with error handling"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        else:
            return init_data()
    except Exception as e:
        print(f"Error loading data: {e}")
        return init_data()

def save_data(data):
    """Save data with error handling"""
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

def is_admin(phone, data):
    """Check if user is admin"""
    return phone in data.get("admins", [])

def create_teams(players):
    """
    Create teams of exactly 6 players each
    Remainder players go into a new team
    Examples:
      8 players  -> Team 1: 6, Team 2: 2
      13 players -> Team 1: 6, Team 2: 6, Team 3: 1
      18 players -> Team 1: 6, Team 2: 6, Team 3: 6
    """
    num_players = len(players)
    if num_players == 0:
        return []
    
    # Random shuffle
    shuffled = players.copy()
    random.shuffle(shuffled)
    
    # Create teams of exactly 6, remainder goes to last team
    teams = []
    for i in range(0, num_players, PLAYERS_PER_TEAM):
        team = shuffled[i:i+PLAYERS_PER_TEAM]
        teams.append(team)
    
    return teams

def format_teams(teams):
    """Format teams for WhatsApp message"""
    team_emojis = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "⚫", "⚪"]
    team_names = ["Red", "Blue", "Green", "Yellow", "Purple", "Orange", "Black", "White"]
    
    text = "⚽ *THIS WEEK'S TEAMS* ⚽\n"
    text += "=" * 30 + "\n\n"
    
    for i, team in enumerate(teams):
        if not team:  # Skip empty teams
            continue
            
        emoji = team_emojis[i % len(team_emojis)]
        name = team_names[i % len(team_names)]
        
        text += f"{emoji} *{name} Team* ({len(team)} players)\n"
        
        for p in team:
            text += f"  • {p['name']}\n"
        text += "\n"
    
    return text

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    """Main webhook handler"""
    msg_body = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    profile_name = request.values.get("ProfileName", "Player")
    
    # Load data
    data = load_data()
    
    # Initialize response
    response = MessagingResponse()
    reply = response.message()
    
    # Normalize command
    msg = msg_body.lower()
    
    # === ADMIN COMMANDS ===
    
    if msg.startswith("/addadmin"):
        if not is_admin(sender, data) and len(data["admins"]) == 0:
            # First user becomes admin
            data["admins"].append(sender)
            save_data(data)
            reply.body("👑 You are now an admin!")
        elif is_admin(sender, data):
            reply.body("✅ You're already an admin!\n\nAdmin commands:\n"
                      "/start - Start selection\n"
                      "/end - Create random teams\n"
                      "/status - View current status\n"
                      "/reset - Reset session")
        else:
            reply.body("❌ Only existing admins can add new admins")
    
    elif msg == "/start":
        if not is_admin(sender, data):
            reply.body("❌ Only admins can start selection")
        else:
            data["session"]["active"] = True
            data["session"]["participants"] = []
            save_data(data)
            reply.body("🎮 *TEAM SELECTION STARTED!*\n\n"
                      "Reply with:\n"
                      "• *in* - Join this week\n"
                      "• *out* - Skip this week\n\n"
                      "Admin will announce teams later!")
    
    elif msg == "/end":
        if not is_admin(sender, data):
            reply.body("❌ Only admins can end selection")
        elif not data["session"]["active"]:
            reply.body("❌ No active session. Use /start first")
        else:
            # Get participating players
            participants = data["session"]["participants"]
            if not participants:
                reply.body("❌ No players have joined yet!")
            else:
                # Build player list with names
                player_list = []
                for phone in participants:
                    player_info = data["players"].get(phone, {
                        "name": "Unknown"
                    })
                    player_list.append(player_info)
                
                # Create teams
                teams = create_teams(player_list)
                
                # Format and send
                result = f"🎲 *RANDOM TEAM SELECTION*\n\n{format_teams(teams)}"
                result += f"Total Players: {len(player_list)}\n"
                result += f"Teams Created: {len(teams)}"
                
                reply.body(result)
                
                # End session
                data["session"]["active"] = False
                save_data(data)
    
    elif msg == "/status":
        if not is_admin(sender, data):
            reply.body("❌ Admin only command")
        else:
            session = data["session"]
            status = "🟢 ACTIVE" if session["active"] else "🔴 INACTIVE"
            participant_count = len(session["participants"])
            
            status_msg = f"📊 *SESSION STATUS*\n\n"
            status_msg += f"Status: {status}\n"
            status_msg += f"Players In: {participant_count}\n\n"
            
            if participant_count > 0:
                status_msg += "Participants:\n"
                for phone in session["participants"]:
                    player = data["players"].get(phone, {"name": "Unknown"})
                    status_msg += f"  • {player['name']}\n"
            
            reply.body(status_msg)
    
    elif msg == "/reset":
        if not is_admin(sender, data):
            reply.body("❌ Only admins can reset")
        else:
            data["session"]["active"] = False
            data["session"]["participants"] = []
            save_data(data)
            reply.body("🔄 Session reset. Use /start to begin new selection")
    
    # === PLAYER COMMANDS ===
    
    elif msg == "in":
        if not data["session"]["active"]:
            reply.body("❌ No active selection. Wait for admin to /start")
        else:
            # Add to players if new
            if sender not in data["players"]:
                data["players"][sender] = {
                    "name": profile_name
                }
            
            # Add to participants
            if sender not in data["session"]["participants"]:
                data["session"]["participants"].append(sender)
                save_data(data)
                reply.body(f"✅ {data['players'][sender]['name']} is IN!\n"
                          f"Current count: {len(data['session']['participants'])} players")
            else:
                reply.body(f"ℹ️ You're already in, {data['players'][sender]['name']}!")
    
    elif msg == "out":
        if not data["session"]["active"]:
            reply.body("❌ No active selection")
        else:
            if sender in data["session"]["participants"]:
                data["session"]["participants"].remove(sender)
                save_data(data)
                player_name = data["players"].get(sender, {}).get("name", profile_name)
                reply.body(f"❌ {player_name} is OUT\n"
                          f"Current count: {len(data['session']['participants'])} players")
            else:
                reply.body("ℹ️ You weren't in the list")
    
    elif msg == "/help":
        help_text = "⚽ *FOOTBALL BOT COMMANDS*\n\n"
        help_text += "*Everyone:*\n"
        help_text += "• in - Join this week\n"
        help_text += "• out - Skip this week\n\n"
        
        if is_admin(sender, data):
            help_text += "*Admin Only:*\n"
            help_text += "• /start - Start selection\n"
            help_text += "• /end - Create random teams\n"
            help_text += "• /status - View status\n"
            help_text += "• /reset - Reset session"
        
        reply.body(help_text)
    
    else:
        # Unknown command
        if msg.startswith("/"):
            reply.body("❓ Unknown command. Send /help for commands")
    
    return str(response)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
