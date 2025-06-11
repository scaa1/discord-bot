import aiosqlite
from config import DB_PATH

# ------------------------- SETTINGS FUNCTIONS -------------------------
async def get_config_value(key: str, default_value=None):
    """Get configuration value from database."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return int(result[0]) if result[0].isdigit() else result[0]
            return default_value

async def set_config_value(key: str, value):
    """Set configuration value in database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def get_lft_channel_id():
    """Get the current LFT (Looking for Team) channel ID."""
    return await get_config_value("lft_channel_id", 0)

async def set_lft_channel_id(channel_id: int):
    """Set the LFT (Looking for Team) channel ID."""
    await set_config_value("lft_channel_id", channel_id)

async def get_team_member_cap():
    """Get the maximum number of members allowed per team."""
    return await get_config_value("team_member_cap", 10)

async def set_team_member_cap(cap: int):
    """Set the maximum number of members allowed per team."""
    await set_config_value("team_member_cap", cap)

async def is_signing_open():
    """Check if player signing is currently open."""
    value = await get_config_value("signing_open", "true")
    return value == "true"

async def set_signing_state(state: bool):
    """Open or close player signing."""
    await set_config_value("signing_open", "true" if state else "false")

async def get_sign_log_channel_id():
    """Get the current sign log channel ID."""
    return await get_config_value("sign_log_channel_id", 0)

async def get_schedule_log_channel_id():
    """Get the current schedule log channel ID."""
    return await get_config_value("schedule_log_channel_id", 0)

async def get_game_results_channel_id():
    """Get the current game results channel ID."""
    return await get_config_value("game_results_channel_id", 0)

async def get_game_reminder_channel_id():
    """Get the current game reminder channel ID."""
    return await get_config_value("game_reminder_channel_id", 0)

async def get_demand_log_channel_id():
    """Get the current demand log channel ID."""
    return await get_config_value("demand_log_channel_id", 0)

async def get_blacklist_log_channel_id():
    """Get the current blacklist log channel ID."""
    return await get_config_value("blacklist_log_channel_id", 0)

async def get_team_owner_alert_channel_id():
    """Get the current team owner alert channel ID."""
    return await get_config_value("team_owner_alert_channel_id", 0)

async def get_referee_role_id():
    """Get the current referee role ID."""
    return await get_config_value("referee_role_id", 0)

async def get_official_ping_role_id():
    """Get the current official ping role ID."""
    return await get_config_value("official_ping_role_id", 0)

async def get_required_roles():
    """Get the list of required role IDs for signing."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", ("required_roles",)) as cursor:
            result = await cursor.fetchone()
            if result and result[0]:
                value_str = str(result[0])
                return [int(role_id.strip()) for role_id in value_str.split(',') if role_id.strip()]
            return []

async def set_required_roles(role_ids: list[int]):
    """Set the required role IDs for signing."""
    await set_config_value("required_roles", ','.join(map(str, role_ids)))

async def get_free_agent_role_id():
    """Get the free agent role ID."""
    return await get_config_value("free_agent_role_id", 0)

async def set_free_agent_role_id(role_id: int):
    """Set the free agent role ID."""
    await set_config_value("free_agent_role_id", role_id)

async def get_max_demands_allowed():
    """Get the maximum demands allowed per player."""
    return await get_config_value("max_demands_allowed", 1)

async def set_max_demands_allowed(max_demands: int):
    """Set the maximum demands allowed per player."""
    await set_config_value("max_demands_allowed", max_demands)

async def get_vice_captain_role_id():
    """Get the Vice Captain role ID."""
    return await get_config_value("vice_captain_role_id", 0)

async def set_vice_captain_role_id(role_id: int):
    """Set the Vice Captain role ID."""
    await set_config_value("vice_captain_role_id", role_id)

async def get_team_announcements_channel_id():
    """Get the current LFP/recruitment channel ID."""
    return await get_config_value("team_announcements_channel_id", 0)

async def set_team_announcements_channel_id(channel_id: int):
    """Set the LFP/recruitment channel ID."""
    await set_config_value("team_announcements_channel_id", channel_id)

async def get_team_owner_dashboard_channel_id():
    """Get the team owner dashboard channel ID."""
    return await get_config_value("team_owner_dashboard_channel_id", 0)

async def set_team_owner_dashboard_channel_id(channel_id: int):
    """Set the team owner dashboard channel ID."""
    await set_config_value("team_owner_dashboard_channel_id", channel_id)

async def get_active_dashboard():
    """Get the active team owner dashboard message info."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT message_id, channel_id FROM dashboard_messages WHERE dashboard_type = 'team_owners' AND active = 1 ORDER BY created_at DESC LIMIT 1"
        ) as cursor:
            return await cursor.fetchone()

async def set_dashboard_message(message_id: int, channel_id: int):
    """Store dashboard message info in database."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Deactivate any existing dashboards
        await db.execute(
            "UPDATE dashboard_messages SET active = 0 WHERE dashboard_type = 'team_owners'"
        )
        
        # Add new dashboard
        await db.execute(
            "INSERT INTO dashboard_messages (message_id, channel_id, dashboard_type) VALUES (?, ?, ?)",
            (message_id, channel_id, "team_owners")
        )
        await db.commit()

async def update_dashboard_timestamp():
    """Update the last_updated timestamp for the dashboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE dashboard_messages SET last_updated = CURRENT_TIMESTAMP WHERE dashboard_type = 'team_owners' AND active = 1"
        )
        await db.commit()

async def deactivate_dashboard():
    """Deactivate the current dashboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE dashboard_messages SET active = 0 WHERE dashboard_type = 'team_owners'"
        )
        await db.commit()

