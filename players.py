import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH

# ------------------------- PLAYER FUNCTIONS -------------------------
async def get_player(user_id: int):
    """Get player information by user ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def sign_player_to_team(user_id: int, username: str, team_id: int):
    """Sign a player to a team."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO players (user_id, username, team_id) VALUES (?, ?, ?)",
            (user_id, username, team_id)
        )
        await db.execute(
            "UPDATE players SET team_id = ? WHERE user_id = ?",
            (team_id, user_id)
        )
        await db.commit()

async def remove_player_from_team(user_id: int):
    """Remove a player from their current team."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE players SET team_id = NULL WHERE user_id = ?", (user_id,))
        await db.commit()

async def blacklist_user(user_id: int):
    """Add a user to the blacklist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO players (user_id, blacklisted) VALUES (?, 1)", (user_id,))
        await db.execute("UPDATE players SET blacklisted = 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def demote_player(user_id: int):
    """Demote a player to regular 'player' role."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE players SET role = 'player' WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_team_roster(team_id: int):
    """Get all players (excluding owner) from a team."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username FROM players WHERE team_id = ? AND role != 'owner'", 
            (team_id,)
        ) as cursor:
            return await cursor.fetchall()

async def vice_captain_exists(team_id: int) -> bool:
    """Check if a team has a vice captain."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM players WHERE team_id = ? AND role = 'vice captain'",
            (team_id,)
        ) as cursor:
            (count,) = await cursor.fetchone()
            return count > 0

async def get_vice_captain_by_team(team_id: int) -> tuple[int, str] | None:
    """Get vice captain from a team."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, role FROM players WHERE team_id = ? AND role = 'vice captain'",
            (team_id,)
        ) as cursor:
            return await cursor.fetchone()

async def add_blacklist(user_id: int, reason: str, blacklisted_by: int, duration_hours: int = None):
    """Add a user to the blacklist with optional duration."""
    async with aiosqlite.connect(DB_PATH) as db:
        if duration_hours:
            expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
            await db.execute(
                "INSERT INTO blacklists (user_id, reason, blacklisted_by, expires_at) VALUES (?, ?, ?, ?)",
                (user_id, reason, blacklisted_by, expires_at.isoformat())
            )
        else:
            await db.execute(
                "INSERT INTO blacklists (user_id, reason, blacklisted_by) VALUES (?, ?, ?)",
                (user_id, reason, blacklisted_by)
            )
        await db.commit()

async def is_user_blacklisted(user_id: int) -> bool:
    """Check if user is currently blacklisted (considering expiration)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM blacklists 
            WHERE user_id = ? AND active = 1 
            AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
            """,
            (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] > 0

async def expire_blacklists():
    """Mark expired blacklists as inactive."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE blacklists SET active = 0 WHERE expires_at IS NOT NULL AND datetime(expires_at) <= datetime('now')"
        )