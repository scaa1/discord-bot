# Create this file as: database/stats.py
import aiosqlite
from config import DB_PATH

# ------------------------- STATS FUNCTIONS -------------------------

async def init_stats_table():
    """Initialize the player stats table."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS player_stats (
            user_id INTEGER,
            stat_name TEXT,
            stat_value INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, stat_name)
        );
        """)
        await db.commit()

async def add_stat_to_player(user_id: int, stat_name: str, value: int):
    """Add or update a stat for a player."""
    await init_stats_table()  # Ensure table exists
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Insert or update the stat
        await db.execute(
            """
            INSERT INTO player_stats (user_id, stat_name, stat_value, last_updated) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, stat_name) 
            DO UPDATE SET 
                stat_value = stat_value + ?, 
                last_updated = CURRENT_TIMESTAMP
            """,
            (user_id, stat_name, value, value)
        )
        await db.commit()

async def get_player_stats(user_id: int):
    """Get all stats for a specific player."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT stat_name, stat_value FROM player_stats WHERE user_id = ? ORDER BY stat_name",
            (user_id,)
        ) as cursor:
            return await cursor.fetchall()

async def get_stat_leaderboard(stat_name: str = None, limit: int = 5):
    """Get leaderboard for a specific stat or all stats."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        if stat_name:
            # Get leaderboard for specific stat
            async with db.execute(
                """
                SELECT user_id, stat_value 
                FROM player_stats 
                WHERE stat_name = ? AND stat_value > 0
                ORDER BY stat_value DESC 
                LIMIT ?
                """,
                (stat_name, limit)
            ) as cursor:
                return await cursor.fetchall()
        else:
            # Get top players for each stat category - Updated to include spikehits
            stat_categories = ['spikescores', 'spikehits', 'receives', 'illpoints', 'blocks', 'assists']
            leaderboards = {}
            
            for category in stat_categories:
                async with db.execute(
                    """
                    SELECT user_id, stat_value 
                    FROM player_stats 
                    WHERE stat_name = ? AND stat_value > 0
                    ORDER BY stat_value DESC 
                    LIMIT ?
                    """,
                    (category, limit)
                ) as cursor:
                    leaderboards[category] = await cursor.fetchall()
            
            return leaderboards

async def get_all_stats_categories():
    """Get all unique stat categories that exist in the database."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT stat_name FROM player_stats ORDER BY stat_name"
        ) as cursor:
            results = await cursor.fetchall()
            return [row[0] for row in results]

async def set_player_stat(user_id: int, stat_name: str, value: int):
    """Set a specific stat value for a player (overwrite, don't add)."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO player_stats (user_id, stat_name, stat_value, last_updated) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, stat_name) 
            DO UPDATE SET 
                stat_value = ?, 
                last_updated = CURRENT_TIMESTAMP
            """,
            (user_id, stat_name, value, value)
        )
        await db.commit()

async def remove_player_stat(user_id: int, stat_name: str = None):
    """Remove a specific stat or all stats for a player."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        if stat_name:
            await db.execute(
                "DELETE FROM player_stats WHERE user_id = ? AND stat_name = ?",
                (user_id, stat_name)
            )
        else:
            await db.execute(
                "DELETE FROM player_stats WHERE user_id = ?",
                (user_id,)
            )
        await db.commit()

async def subtract_stat_from_player(user_id: int, stat_name: str, value: int):
    """Subtract a value from a player's stat (won't go below 0)."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Get current value
        async with db.execute(
            "SELECT stat_value FROM player_stats WHERE user_id = ? AND stat_name = ?",
            (user_id, stat_name)
        ) as cursor:
            result = await cursor.fetchone()
            current_value = result[0] if result else 0
        
        # Calculate new value (don't go below 0)
        new_value = max(0, current_value - value)
        
        if new_value == 0:
            # Remove the stat if it becomes 0
            await db.execute(
                "DELETE FROM player_stats WHERE user_id = ? AND stat_name = ?",
                (user_id, stat_name)
            )
        else:
            # Update with new value
            await db.execute(
                """
                INSERT INTO player_stats (user_id, stat_name, stat_value, last_updated) 
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, stat_name) 
                DO UPDATE SET 
                    stat_value = ?, 
                    last_updated = CURRENT_TIMESTAMP
                """,
                (user_id, stat_name, new_value, new_value)
            )
        await db.commit()
        return new_value

async def reset_all_stats():
    """Reset all stats for all players."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Get count before deletion
        async with db.execute("SELECT COUNT(*) FROM player_stats") as cursor:
            result = await cursor.fetchone()
            count = result[0] if result else 0
        
        # Delete all stats
        await db.execute("DELETE FROM player_stats")
        await db.commit()
        return count

async def get_total_stats_count():
    """Get total number of stat entries in the database."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM player_stats") as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

async def get_players_with_stats():
    """Get all players who have any stats recorded."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT user_id FROM player_stats ORDER BY user_id"
        ) as cursor:
            results = await cursor.fetchall()
            return [row[0] for row in results]

async def get_player_rank_in_stat(user_id: int, stat_name: str):
    """Get a player's rank in a specific stat category."""
    await init_stats_table()
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) + 1 as rank
            FROM player_stats 
            WHERE stat_name = ? 
            AND stat_value > (
                SELECT COALESCE(stat_value, 0) 
                FROM player_stats 
                WHERE user_id = ? AND stat_name = ?
            )
            """,
            (stat_name, user_id, stat_name)
        ) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else None