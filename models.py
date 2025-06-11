import aiosqlite
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            team_id INTEGER,
            role TEXT DEFAULT 'player',
            blacklisted BOOLEAN DEFAULT 0,
            leaves INTEGER DEFAULT 0,
            demands_used INTEGER DEFAULT 0
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER UNIQUE,
            emoji TEXT,
            name TEXT,
            owner_id INTEGER
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team1_id INTEGER,
            team2_id INTEGER,
            scheduled_time TIMESTAMP,
            status TEXT DEFAULT 'pending',
            reminder_sent BOOLEAN DEFAULT 0,
            message_id INTEGER DEFAULT NULL,
            FOREIGN KEY (team1_id) REFERENCES teams(team_id),
            FOREIGN KEY (team2_id) REFERENCES teams(team_id)
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS referee_signups (
            signup_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            user_id INTEGER,
            username TEXT,
            discord_user TEXT,
            signup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES scheduled_games(game_id)
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS blacklists (
            blacklist_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            blacklisted_by INTEGER,
            blacklist_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            active BOOLEAN DEFAULT 1
        );
        """)
        
        # ADD THIS NEW TABLE FOR DASHBOARD:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_messages (
            dashboard_id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            channel_id INTEGER,
            dashboard_type TEXT,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        await db.commit()
        
        # Add the message_id column if it doesn't exist (for existing databases)
        try:
            await db.execute("ALTER TABLE scheduled_games ADD COLUMN message_id INTEGER DEFAULT NULL")
            await db.commit()
        except:
            pass  # Column already exists
        
        # Initialize default settings if they don't exist
        default_settings = {
            'signing_open': 'true',
            'team_member_cap': '10',
            'sign_log_channel_id': '0',
            'schedule_log_channel_id': '0',
            'game_results_channel_id': '0',
            'game_reminder_channel_id': '0',
            'demand_log_channel_id': '0',  # Channel for demand notifications
            'blacklist_log_channel_id': '0',  # Channel for blacklist notifications
            'team_owner_alert_channel_id': '0',  # Channel for team owner alerts
            'referee_role_id': '0',
            'lft_channel_id': '0',
            'official_ping_role_id': '0',
            'required_roles': '',  # Comma-separated role IDs required for signing
            'free_agent_role_id': '0',  # Role that gets removed when signed, added when unsigned
            'max_demands_allowed': '1',  # Maximum demands allowed per player
            'vice_captain_role_id': '0',  # Single Vice Captain role
            'team_announcements_channel_id': '0',
            'team_owner_dashboard_channel_id': '0',
        }
        
        for key, value in default_settings.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))