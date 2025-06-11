import aiosqlite
import discord
import pytz
from datetime import datetime, timedelta
from config import DB_PATH

# ------------------------- GAME SCHEDULING FUNCTIONS -------------------------
async def schedule_game(team1_id: int, team2_id: int, scheduled_time: str):
    """Schedule a game between two teams."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO scheduled_games (team1_id, team2_id, scheduled_time) VALUES (?, ?, ?)",
            (team1_id, team2_id, scheduled_time)
        )
        await db.commit()

async def schedule_game_and_post(team1_id: int, team2_id: int, scheduled_time: str, guild, schedule_channel, scheduled_by_user=None):
    """Schedule a game and post it to the channel, returning the game_id and message_id"""
    from database.teams import get_team_by_role
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Insert the game first
        cursor = await db.execute(
            "INSERT INTO scheduled_games (team1_id, team2_id, scheduled_time) VALUES (?, ?, ?)",
            (team1_id, team2_id, scheduled_time)
        )
        game_id = cursor.lastrowid
        await db.commit()
        
        # Get team data for the embed
        team1_data = await get_team_by_role(team1_id)
        team2_data = await get_team_by_role(team2_id)
        
        team1_emoji = team1_data[2] if team1_data and team1_data[2] else "🔥"
        team2_emoji = team2_data[2] if team2_data and team2_data[2] else "⚡"
        
        team1_role = guild.get_role(team1_id)
        team2_role = guild.get_role(team2_id)
        
        # Parse time for Discord timestamp
        match_datetime = datetime.fromisoformat(scheduled_time)
        if match_datetime.tzinfo is None:
            match_datetime = pytz.utc.localize(match_datetime)
        unix_timestamp = int(match_datetime.timestamp())
        
        # Use the actual user who scheduled the game if provided, otherwise fallback to bot
        scheduler_mention = scheduled_by_user.mention if scheduled_by_user else guild.me.mention
        
        embed = discord.Embed(
            title="📅 Game Scheduled",
            description=(
                f"{team1_emoji} {team1_role.mention} vs {team2_role.mention} {team2_emoji}\n"
                f"🕒 <t:{unix_timestamp}:F> (full date & time)\n"
                f"⏰ <t:{unix_timestamp}:R> (relative time)\n"
                f"🌍 <t:{unix_timestamp}:t> (local time)\n\n"
                f"**Scheduled by:** {scheduler_mention}"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Game ID: {game_id}")
        
        # Post message
        message = await schedule_channel.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")
        
        # Update database with message ID
        await db.execute(
            "UPDATE scheduled_games SET message_id = ? WHERE game_id = ?",
            (message.id, game_id)
        )
        await db.commit()
        
        return game_id, message.id

async def get_game_id_by_details(team1_id: int, team2_id: int, scheduled_time: str):
    """Get game ID by team IDs and scheduled time."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT game_id FROM scheduled_games WHERE ((team1_id = ? AND team2_id = ?) OR (team1_id = ? AND team2_id = ?)) AND scheduled_time = ?",
            (team1_id, team2_id, team2_id, team1_id, scheduled_time)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else None

async def add_referee_signup(game_id: int, user_id: int, username: str, discord_user: str):
    """Add a referee signup for a game."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO referee_signups (game_id, user_id, username, discord_user) VALUES (?, ?, ?, ?)",
            (game_id, user_id, username, discord_user)
        )
        await db.commit()

async def get_referee_signups(game_id: int):
    """Get all referee signups for a game."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, username, discord_user, signup_time FROM referee_signups WHERE game_id = ? ORDER BY signup_time",
            (game_id,)
        ) as cursor:
            return await cursor.fetchall()

async def check_existing_referee_signup(game_id: int, user_id: int):
    """Check if user already signed up as referee for this game."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM referee_signups WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] > 0

async def mark_reminder_sent(game_id: int):
    """Mark that a reminder has been sent for a game."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE scheduled_games SET reminder_sent = 1 WHERE game_id = ?", (game_id,))
        await db.commit()

async def get_all_scheduled_games():
    """Get all scheduled games ordered by time."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT team1_id, team2_id, scheduled_time FROM scheduled_games WHERE datetime(scheduled_time) > datetime('now') ORDER BY scheduled_time"
        ) as cursor:
            return await cursor.fetchall()

async def get_upcoming_games_needing_reminders():
    """Get games that need reminders sent (including older games that haven't been reminded yet)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Get current time
        now = datetime.utcnow()
        reminder_time = now + timedelta(minutes=5)
        
        async with db.execute(
            """
            SELECT game_id, team1_id, team2_id, scheduled_time 
            FROM scheduled_games 
            WHERE reminder_sent = 0 
            AND (
                -- Games starting in the next 5 minutes
                (datetime(scheduled_time) <= datetime(?) AND datetime(scheduled_time) > datetime(?))
                OR
                -- Past games that haven't been reminded yet (up to 24 hours old)
                (datetime(scheduled_time) <= datetime(?) AND datetime(scheduled_time) >= datetime(?))
            )
            AND message_id IS NOT NULL
            ORDER BY scheduled_time
            """,
            (
                reminder_time.isoformat(),  # For games in next 5 mins
                now.isoformat(),           # Must be in the future
                now.isoformat(),           # For past games
                (now - timedelta(hours=24)).isoformat()  # No older than 24 hours
            )
        ) as cursor:
            return await cursor.fetchall()

# Dashboard functions
