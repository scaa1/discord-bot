import aiosqlite
from config import DB_PATH

# ------------------------- TEAM FUNCTIONS -------------------------
async def add_team(role_id: int, emoji: str, name: str):
    """Add a new team to the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO teams (role_id, emoji, name) VALUES (?, ?, ?)", (role_id, emoji, name))
        await db.commit()

async def get_team_by_id(team_id: int):
    """Get team information by team ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,)) as cursor:
            return await cursor.fetchone()

async def get_team_by_role(role_id: int):
    """Get team information by Discord role ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM teams WHERE role_id = ?", (role_id,)) as cursor:
            return await cursor.fetchone()

async def get_team_by_owner(user_id: int):
    """Get team information by owner's user ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT team_id, role_id, emoji, name, owner_id FROM teams WHERE owner_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def get_all_teams_with_counts():
    """Get all teams with their member counts."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT teams.name, teams.emoji, COUNT(players.user_id) FROM teams LEFT JOIN players ON players.team_id = teams.team_id GROUP BY teams.team_id"
        ) as cursor:
            return await cursor.fetchall()

async def update_team_emoji(role_id: int, new_emoji: str):
    """Update a team's emoji."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE teams SET emoji = ? WHERE role_id = ?", (new_emoji, role_id))
        await db.commit()

async def set_team_owner(team_id: int, user_id: int):
    """Set the owner of a team."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE teams SET owner_id = ? WHERE team_id = ?", (user_id, team_id))
        await db.execute("INSERT OR IGNORE INTO players (user_id, username) VALUES (?, ?)", (user_id, "Unknown"))
        await db.execute("UPDATE players SET role = 'owner' WHERE user_id = ?", (user_id,))
        await db.commit()

async def remove_team_and_players(team_id: int):
    """Remove a team and all its players from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM players WHERE team_id = ?", (team_id,))
        await db.execute("DELETE FROM teams WHERE team_id = ?", (team_id,))