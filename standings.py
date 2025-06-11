# Enhanced standings.py - Shows all teams including 0-0 records
import aiosqlite
from datetime import datetime
from typing import List, Tuple, Optional, Dict

# Import the correct database path
from config import DB_PATH

async def init_standings_table():
    """Initialize the standings database tables with proper schema - SAFE version."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if tables exist before creating
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='team_standings'") as cursor:
                standings_exists = await cursor.fetchone()
            
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='game_results'") as cursor:
                game_results_exists = await cursor.fetchone()
            
            # Create team_standings table if it doesn't exist
            if not standings_exists:
                await db.execute("""
                    CREATE TABLE team_standings (
                        role_id INTEGER PRIMARY KEY,
                        team_id INTEGER,
                        name TEXT NOT NULL DEFAULT 'Unknown Team',
                        emoji TEXT DEFAULT '🏐',
                        wins INTEGER DEFAULT 0,
                        losses INTEGER DEFAULT 0,
                        sets_won INTEGER DEFAULT 0,
                        sets_lost INTEGER DEFAULT 0,
                        points_for INTEGER DEFAULT 0,
                        points_against INTEGER DEFAULT 0,
                        games_played INTEGER DEFAULT 0,
                        win_percentage REAL DEFAULT 0.0,
                        set_differential INTEGER DEFAULT 0,
                        last_game_date TEXT,
                        last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (role_id) REFERENCES teams(role_id)
                    )
                """)
                print("✅ Created team_standings table")
            else:
                # Migrate existing table if needed
                await migrate_standings_table(db)
            
            # Create game_results table if it doesn't exist
            if not game_results_exists:
                await db.execute("""
                    CREATE TABLE game_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        team1_role_id INTEGER NOT NULL,
                        team2_role_id INTEGER NOT NULL,
                        team1_name TEXT,
                        team2_name TEXT,
                        team1_sets INTEGER NOT NULL,
                        team2_sets INTEGER NOT NULL,
                        team1_points INTEGER DEFAULT 0,
                        team2_points INTEGER DEFAULT 0,
                        winner_role_id INTEGER NOT NULL,
                        loser_role_id INTEGER NOT NULL,
                        reported_by INTEGER,
                        reported_by_name TEXT,
                        match_date TEXT DEFAULT CURRENT_TIMESTAMP,
                        season TEXT DEFAULT 'Current',
                        notes TEXT,
                        FOREIGN KEY (team1_role_id) REFERENCES team_standings(role_id),
                        FOREIGN KEY (team2_role_id) REFERENCES team_standings(role_id),
                        FOREIGN KEY (winner_role_id) REFERENCES team_standings(role_id),
                        FOREIGN KEY (loser_role_id) REFERENCES team_standings(role_id)
                    )
                """)
                print("✅ Created game_results table")
            
            # Create indexes for better performance
            await db.execute("CREATE INDEX IF NOT EXISTS idx_standings_wins ON team_standings(wins DESC)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_standings_set_diff ON team_standings(set_differential DESC)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_game_results_date ON game_results(match_date DESC)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_game_results_teams ON game_results(team1_role_id, team2_role_id)")
            
            await db.commit()
            print("✅ Enhanced standings database initialized successfully")
            
    except Exception as e:
        print(f"❌ Error initializing enhanced standings database: {e}")
        import traceback
        traceback.print_exc()

async def migrate_standings_table(db):
    """Migrate existing standings table to new schema if needed."""
    try:
        # Get current table schema
        async with db.execute("PRAGMA table_info(team_standings)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
        
        # Add missing columns if they don't exist
        columns_to_add = [
            ("team_id", "INTEGER"),
            ("emoji", "TEXT DEFAULT '🏐'"),
            ("sets_won", "INTEGER DEFAULT 0"),
            ("sets_lost", "INTEGER DEFAULT 0"),
            ("points_for", "INTEGER DEFAULT 0"),
            ("points_against", "INTEGER DEFAULT 0"),
            ("games_played", "INTEGER DEFAULT 0"),
            ("win_percentage", "REAL DEFAULT 0.0"),
            ("set_differential", "INTEGER DEFAULT 0"),
            ("last_game_date", "TEXT"),
            ("last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP"),
            ("created_at", "TEXT DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for col_name, col_type in columns_to_add:
            if col_name not in column_names:
                await db.execute(f"ALTER TABLE team_standings ADD COLUMN {col_name} {col_type}")
                print(f"✅ Added column {col_name} to team_standings")
        
        # Update any null values with defaults
        await db.execute("""
            UPDATE team_standings 
            SET name = COALESCE(name, 'Unknown Team'),
                emoji = COALESCE(emoji, '🏐'),
                wins = COALESCE(wins, 0),
                losses = COALESCE(losses, 0),
                sets_won = COALESCE(sets_won, 0),
                sets_lost = COALESCE(sets_lost, 0),
                points_for = COALESCE(points_for, 0),
                points_against = COALESCE(points_against, 0),
                games_played = COALESCE(games_played, wins + losses),
                win_percentage = CASE 
                    WHEN COALESCE(wins, 0) + COALESCE(losses, 0) = 0 THEN 0
                    ELSE ROUND(CAST(COALESCE(wins, 0) AS FLOAT) / 
                         (COALESCE(wins, 0) + COALESCE(losses, 0)) * 100, 1)
                END,
                set_differential = COALESCE(sets_won, 0) - COALESCE(sets_lost, 0),
                last_updated = COALESCE(last_updated, CURRENT_TIMESTAMP)
        """)
        
        await db.commit()
        print("✅ Successfully migrated standings table")
        
    except Exception as e:
        print(f"⚠️ Migration warning: {e}")

async def sync_teams_from_main_table():
    """Sync all teams from main teams table to standings table."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # First ensure the standings table exists
            await init_standings_table()
            
            # Get all teams from the main teams table
            async with db.execute("SELECT team_id, role_id, name, emoji FROM teams") as cursor:
                teams = await cursor.fetchall()
            
            if not teams:
                print("No teams found in main database")
                return 0
            
            print(f"Found {len(teams)} teams in main database, syncing to standings...")
            
            synced_count = 0
            
            for team_id, role_id, name, emoji in teams:
                # Check if team already exists in standings
                async with db.execute("SELECT role_id FROM team_standings WHERE role_id = ?", (role_id,)) as cursor:
                    exists = await cursor.fetchone()
                
                if exists:
                    # Update team info but preserve stats
                    await db.execute("""
                        UPDATE team_standings 
                        SET team_id = ?, name = ?, emoji = ?, last_updated = ?
                        WHERE role_id = ?
                    """, (team_id, name or f"Team {role_id}", emoji or "🏐", 
                          datetime.utcnow().isoformat(), role_id))
                else:
                    # Insert new team
                    await db.execute("""
                        INSERT INTO team_standings 
                        (role_id, team_id, name, emoji, wins, losses, sets_won, sets_lost,
                         points_for, points_against, games_played, win_percentage, set_differential, 
                         last_updated, created_at)
                        VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0.0, 0, ?, ?)
                    """, (role_id, team_id, name or f"Team {role_id}", emoji or "🏐",
                          datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
                
                synced_count += 1
                print(f"Synced team {name or f'Team {role_id}'} (role_id: {role_id})")
            
            await db.commit()
            print(f"✅ Successfully synced {synced_count} teams")
            return synced_count
            
    except Exception as e:
        print(f"Error syncing teams: {e}")
        import traceback
        traceback.print_exc()
        return 0

async def sync_teams_with_guild_roles(guild):
    """Sync teams based on actual Discord roles in the guild."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Get all teams from main teams table
            async with db.execute("SELECT team_id, role_id, name, emoji FROM teams") as cursor:
                teams_in_db = await cursor.fetchall()
            
            synced_count = 0
            added_count = 0
            removed_count = 0
            
            # Get all role IDs that exist in Discord
            guild_role_ids = {role.id for role in guild.roles}
            
            # First, add/update teams that exist in both DB and Discord
            for team_id, role_id, name, emoji in teams_in_db:
                if role_id in guild_role_ids:
                    # Role exists in Discord - ensure it's in standings
                    role = guild.get_role(role_id)
                    if role:
                        # Check if in standings
                        async with db.execute("SELECT role_id FROM team_standings WHERE role_id = ?", (role_id,)) as cursor:
                            exists = await cursor.fetchone()
                        
                        if not exists:
                            # Add to standings
                            await db.execute("""
                                INSERT INTO team_standings 
                                (role_id, team_id, name, emoji, wins, losses, sets_won, sets_lost,
                                 points_for, points_against, games_played, win_percentage, set_differential, 
                                 last_updated, created_at)
                                VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0.0, 0, ?, ?)
                            """, (role_id, team_id, name or role.name, emoji or "🏐",
                                  datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
                            added_count += 1
                            print(f"✅ Added team to standings: {name or role.name}")
                        else:
                            # Update name/emoji if changed
                            await db.execute("""
                                UPDATE team_standings 
                                SET team_id = ?, name = ?, emoji = ?, last_updated = ?
                                WHERE role_id = ?
                            """, (team_id, name or role.name, emoji or "🏐", 
                                  datetime.utcnow().isoformat(), role_id))
                        synced_count += 1
            
            # Remove teams from standings whose roles no longer exist
            async with db.execute("SELECT role_id, name FROM team_standings") as cursor:
                standings_teams = await cursor.fetchall()
            
            for role_id, team_name in standings_teams:
                if role_id not in guild_role_ids:
                    # Role doesn't exist in Discord - remove from standings
                    await db.execute("DELETE FROM team_standings WHERE role_id = ?", (role_id,))
                    await db.execute("DELETE FROM game_results WHERE team1_role_id = ? OR team2_role_id = ?", 
                                   (role_id, role_id))
                    removed_count += 1
                    print(f"🗑️ Removed team from standings: {team_name} (role no longer exists)")
            
            await db.commit()
            
            print(f"✅ Sync complete: {synced_count} synced, {added_count} added, {removed_count} removed")
            return synced_count, added_count, removed_count
            
    except Exception as e:
        print(f"Error syncing teams with guild roles: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0, 0

async def add_team_to_standings(role_id: int, team_id: int = None, name: str = None, emoji: str = None):
    """Add a new team to standings."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if team already exists
            async with db.execute("SELECT role_id FROM team_standings WHERE role_id = ?", (role_id,)) as cursor:
                exists = await cursor.fetchone()
            
            if not exists:
                await db.execute("""
                    INSERT INTO team_standings 
                    (role_id, team_id, name, emoji, wins, losses, sets_won, sets_lost,
                     points_for, points_against, games_played, win_percentage, set_differential, 
                     last_updated, created_at)
                    VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0.0, 0, ?, ?)
                """, (role_id, team_id, name or f"Team {role_id}", emoji or "🏐",
                      datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
                
                await db.commit()
                print(f"✅ Added team {name or role_id} to standings (role_id: {role_id})")
            else:
                print(f"Team {role_id} already exists in standings")
    except Exception as e:
        print(f"Error adding team {role_id} to standings: {e}")

async def update_team_standing(role_id: int, won: bool, sets_won: int, sets_lost: int,
                             points_for: int = 0, points_against: int = 0, opponent_role_id: int = None):
    """Update a team's standing after a game."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Ensure team exists in standings
            async with db.execute(
                "SELECT role_id, wins, losses, games_played FROM team_standings WHERE role_id = ?", (role_id,)
            ) as cursor:
                team_data = await cursor.fetchone()
                
            if not team_data:
                # Get team info from main teams table and add to standings
                async with db.execute(
                    "SELECT team_id, role_id, name, emoji FROM teams WHERE role_id = ?", (role_id,)
                ) as cursor:
                    team_info = await cursor.fetchone()
                    
                if team_info:
                    await add_team_to_standings(
                        team_info[1],  # role_id
                        team_info[0],  # team_id
                        team_info[2],  # name
                        team_info[3]   # emoji
                    )
                else:
                    # Fallback: add with minimal info
                    await add_team_to_standings(role_id, None, f"Team {role_id}", "🏐")
                
                # Re-fetch after adding
                async with db.execute(
                    "SELECT role_id, wins, losses, games_played FROM team_standings WHERE role_id = ?", (role_id,)
                ) as cursor:
                    team_data = await cursor.fetchone()

            # Calculate changes
            wins_change = 1 if won else 0
            losses_change = 1 if not won else 0
            
            # Calculate new values
            current_wins = team_data[1] if team_data else 0
            current_losses = team_data[2] if team_data else 0
            current_games = team_data[3] if team_data else 0
            
            new_wins = current_wins + wins_change
            new_losses = current_losses + losses_change
            new_games = current_games + 1
            new_win_percentage = (new_wins / new_games * 100) if new_games > 0 else 0.0
            
            # Update standings
            await db.execute("""
                UPDATE team_standings
                SET wins = wins + ?,
                    losses = losses + ?,
                    sets_won = sets_won + ?,
                    sets_lost = sets_lost + ?,
                    points_for = points_for + ?,
                    points_against = points_against + ?,
                    games_played = games_played + 1,
                    win_percentage = ?,
                    set_differential = (sets_won + ?) - (sets_lost + ?),
                    last_game_date = ?,
                    last_updated = ?
                WHERE role_id = ?
            """, (wins_change, losses_change, sets_won, sets_lost,
                  points_for, points_against, new_win_percentage,
                  sets_won, sets_lost, datetime.utcnow().isoformat(),
                  datetime.utcnow().isoformat(), role_id))
            
            await db.commit()
            print(f"✅ Updated standings for team {role_id}: {'W' if won else 'L'} ({sets_won}-{sets_lost})")
            
    except Exception as e:
        print(f"Error updating team standing for {role_id}: {e}")
        import traceback
        traceback.print_exc()

async def record_game_result(team1_role_id: int, team2_role_id: int, team1_sets: int, team2_sets: int,
                           team1_points: int = 0, team2_points: int = 0, reported_by: int = None,
                           reported_by_name: str = None, notes: str = None):
    """Record a complete game result."""
    try:
        # Determine winner and loser
        winner_role_id = team1_role_id if team1_sets > team2_sets else team2_role_id
        loser_role_id = team2_role_id if team1_sets > team2_sets else team1_role_id
        
        # Get team names for the record
        async with aiosqlite.connect(DB_PATH) as db:
            # Ensure both teams exist in standings first
            for rid in [team1_role_id, team2_role_id]:
                async with db.execute("SELECT role_id FROM team_standings WHERE role_id = ?", (rid,)) as cursor:
                    if not await cursor.fetchone():
                        # Try to add from main teams table
                        async with db.execute("SELECT team_id, name, emoji FROM teams WHERE role_id = ?", (rid,)) as cursor2:
                            team_info = await cursor2.fetchone()
                            if team_info:
                                await add_team_to_standings(rid, team_info[0], team_info[1], team_info[2])
            
            # Now get the names
            async with db.execute(
                "SELECT name FROM team_standings WHERE role_id = ?", (team1_role_id,)
            ) as cursor:
                team1_result = await cursor.fetchone()
                team1_name = team1_result[0] if team1_result else f"Team {team1_role_id}"
                
            async with db.execute(
                "SELECT name FROM team_standings WHERE role_id = ?", (team2_role_id,)
            ) as cursor:
                team2_result = await cursor.fetchone()
                team2_name = team2_result[0] if team2_result else f"Team {team2_role_id}"
            
            # Record the game result
            await db.execute("""
                INSERT INTO game_results 
                (team1_role_id, team2_role_id, team1_name, team2_name, team1_sets, team2_sets,
                 team1_points, team2_points, winner_role_id, loser_role_id, reported_by, 
                 reported_by_name, match_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (team1_role_id, team2_role_id, team1_name, team2_name, team1_sets, team2_sets,
                  team1_points, team2_points, winner_role_id, loser_role_id, reported_by, 
                  reported_by_name, datetime.utcnow().isoformat(), notes))
            
            await db.commit()
            print(f"✅ Recorded game: {team1_name} {team1_sets}-{team2_sets} {team2_name}")
            
    except Exception as e:
        print(f"Error recording game result: {e}")
        import traceback
        traceback.print_exc()

# ========================= CONTINUOUS SYNC FUNCTIONS =========================

async def sync_single_team(role_id: int, team_id: int, name: str, emoji: str):
    """Sync a single team to the standings table."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if team exists
            async with db.execute("SELECT role_id FROM team_standings WHERE role_id = ?", (role_id,)) as cursor:
                exists = await cursor.fetchone()
            
            if exists:
                # Update existing team
                await db.execute("""
                    UPDATE team_standings 
                    SET team_id = ?, name = ?, emoji = ?, last_updated = ?
                    WHERE role_id = ?
                """, (team_id, name, emoji, datetime.utcnow().isoformat(), role_id))
            else:
                # Insert new team
                await add_team_to_standings(role_id, team_id, name, emoji)
            
            await db.commit()
            print(f"✅ Synced single team: {name} (role_id: {role_id})")
            return True
            
    except Exception as e:
        print(f"Error syncing single team {role_id}: {e}")
        return False

async def remove_single_team_from_standings(role_id: int) -> bool:
    """Remove a single team from standings when its role is deleted."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if team exists in standings
            async with db.execute(
                "SELECT name FROM team_standings WHERE role_id = ?", (role_id,)
            ) as cursor:
                team_info = await cursor.fetchone()
            
            if team_info:
                team_name = team_info[0]
                
                # Remove from standings
                await db.execute("DELETE FROM team_standings WHERE role_id = ?", (role_id,))
                
                # Remove related game results
                await db.execute(
                    "DELETE FROM game_results WHERE team1_role_id = ? OR team2_role_id = ?",
                    (role_id, role_id)
                )
                
                await db.commit()
                print(f"🗑️ Removed team from standings: {team_name} (role_id: {role_id})")
                return True
            
            return False
            
    except Exception as e:
        print(f"Error removing team {role_id} from standings: {e}")
        return False

async def get_standings_sync_status() -> dict:
    """Get detailed sync status information."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Count teams in main table
            async with db.execute("SELECT COUNT(*) FROM teams") as cursor:
                result = await cursor.fetchone()
                main_table_count = result[0] if result else 0
            
            # Count teams in standings
            async with db.execute("SELECT COUNT(*) FROM team_standings") as cursor:
                result = await cursor.fetchone()
                standings_count = result[0] if result else 0
            
            # Find teams missing from standings
            async with db.execute("""
                SELECT COUNT(*)
                FROM teams t
                LEFT JOIN team_standings ts ON t.role_id = ts.role_id
                WHERE ts.role_id IS NULL
            """) as cursor:
                result = await cursor.fetchone()
                missing_count = result[0] if result else 0
            
            # Find teams with outdated info
            async with db.execute("""
                SELECT COUNT(*)
                FROM teams t
                INNER JOIN team_standings ts ON t.role_id = ts.role_id
                WHERE t.name != ts.name OR t.emoji != ts.emoji
            """) as cursor:
                result = await cursor.fetchone()
                outdated_count = result[0] if result else 0
            
            # Get last update time
            async with db.execute("""
                SELECT MAX(last_updated) FROM team_standings
            """) as cursor:
                last_update = await cursor.fetchone()
                last_update_time = last_update[0] if last_update and last_update[0] else None
            
            return {
                'main_table_count': main_table_count,
                'standings_count': standings_count,
                'missing_count': missing_count,
                'outdated_count': outdated_count,
                'last_update': last_update_time,
                'in_sync': missing_count == 0 and outdated_count == 0
            }
            
    except Exception as e:
        print(f"Error getting sync status: {e}")
        return {
            'main_table_count': 0,
            'standings_count': 0,
            'missing_count': 0,
            'outdated_count': 0,
            'last_update': None,
            'in_sync': False,
            'error': str(e)
        }

async def cleanup_orphaned_teams(guild_role_ids: set = None) -> int:
    """Clean up teams whose Discord roles no longer exist."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if guild_role_ids:
                # Get teams that will be removed for logging
                placeholders = ','.join('?' * len(guild_role_ids))
                async with db.execute(
                    f"SELECT role_id, name FROM team_standings WHERE role_id NOT IN ({placeholders})",
                    list(guild_role_ids)
                ) as cursor:
                    orphaned_teams = await cursor.fetchall()
                
                if orphaned_teams:
                    print(f"🧹 Cleaning up {len(orphaned_teams)} orphaned teams:")
                    for role_id, name in orphaned_teams:
                        print(f"   - {name} (role_id: {role_id})")
                
                # Remove teams that don't have corresponding Discord roles
                result = await db.execute(
                    f"DELETE FROM team_standings WHERE role_id NOT IN ({placeholders})",
                    list(guild_role_ids)
                )
                removed_count = result.rowcount if hasattr(result, 'rowcount') else 0
                
                # Also remove their game results
                await db.execute(
                    f"DELETE FROM game_results WHERE team1_role_id NOT IN ({placeholders}) OR team2_role_id NOT IN ({placeholders})",
                    list(guild_role_ids) * 2
                )
            else:
                # Remove invalid entries
                result = await db.execute(
                    "DELETE FROM team_standings WHERE role_id IS NULL OR role_id = 0"
                )
                removed_count = result.rowcount if hasattr(result, 'rowcount') else 0
                
            await db.commit()
            
            if removed_count > 0:
                print(f"✅ Cleanup complete: removed {removed_count} orphaned team entries")
            
            return removed_count
            
    except Exception as e:
        print(f"Error in cleanup_orphaned_teams: {e}")
        return 0

# ========================= GAME MANAGEMENT FUNCTIONS =========================

async def get_game_result_by_id(game_id: int) -> Optional[Dict]:
    """Get a specific game result by its ID."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT id, team1_role_id, team2_role_id, team1_name, team2_name,
                       team1_sets, team2_sets, team1_points, team2_points,
                       winner_role_id, loser_role_id, reported_by, reported_by_name,
                       match_date, season, notes
                FROM game_results
                WHERE id = ?
            """, (game_id,)) as cursor:
                result = await cursor.fetchone()
                
                if result:
                    return {
                        'id': result[0],
                        'team1_role_id': result[1],
                        'team2_role_id': result[2],
                        'team1_name': result[3],
                        'team2_name': result[4],
                        'team1_sets': result[5],
                        'team2_sets': result[6],
                        'team1_points': result[7],
                        'team2_points': result[8],
                        'winner_role_id': result[9],
                        'loser_role_id': result[10],
                        'reported_by': result[11],
                        'reported_by_name': result[12],
                        'match_date': result[13],
                        'season': result[14],
                        'notes': result[15]
                    }
                return None
    except Exception as e:
        print(f"Error getting game result by ID {game_id}: {e}")
        return None

async def remove_game_result(game_id: int) -> bool:
    """Remove a game result from the database."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if game exists first
            async with db.execute("SELECT COUNT(*) FROM game_results WHERE id = ?", (game_id,)) as cursor:
                exists = await cursor.fetchone()
                
            if not exists or exists[0] == 0:
                return False
            
            # Remove the game result
            await db.execute("DELETE FROM game_results WHERE id = ?", (game_id,))
            await db.commit()
            
            print(f"✅ Successfully removed game result ID {game_id}")
            return True
            
    except Exception as e:
        print(f"Error removing game result {game_id}: {e}")
        return False

async def reverse_team_standing_update(role_id: int, won: bool, sets_won: int, sets_lost: int,
                                     points_for: int = 0, points_against: int = 0):
    """Reverse a team's standing update (subtract what was previously added)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Ensure team exists in standings
            async with db.execute(
                "SELECT wins, losses, games_played, sets_won as current_sets_won, sets_lost as current_sets_lost FROM team_standings WHERE role_id = ?", 
                (role_id,)
            ) as cursor:
                team_data = await cursor.fetchone()
                
            if not team_data:
                print(f"⚠️ Warning: Team {role_id} not found in standings during reversal")
                return
            
            current_wins, current_losses, current_games, current_sets_won, current_sets_lost = team_data
            
            # Calculate what to subtract
            new_wins = max(0, current_wins - (1 if won else 0))
            new_losses = max(0, current_losses - (0 if won else 1))
            new_games = max(0, current_games - 1)
            new_sets_won = max(0, current_sets_won - sets_won)
            new_sets_lost = max(0, current_sets_lost - sets_lost)
            
            new_win_percentage = (new_wins / new_games * 100) if new_games > 0 else 0.0
            new_set_differential = new_sets_won - new_sets_lost
            
            # Update with new values
            await db.execute("""
                UPDATE team_standings
                SET wins = ?,
                    losses = ?,
                    sets_won = ?,
                    sets_lost = ?,
                    points_for = points_for - ?,
                    points_against = points_against - ?,
                    games_played = ?,
                    win_percentage = ?,
                    set_differential = ?,
                    last_updated = ?
                WHERE role_id = ?
            """, (new_wins, new_losses, new_sets_won, new_sets_lost,
                  points_for, points_against, new_games, new_win_percentage,
                  new_set_differential, datetime.utcnow().isoformat(), role_id))
            
            await db.commit()
            print(f"✅ Reversed standings for team {role_id}: {'W' if won else 'L'} removed ({sets_won}-{sets_lost})")
            
    except Exception as e:
        print(f"Error reversing team standing for {role_id}: {e}")
        import traceback
        traceback.print_exc()

async def get_games_by_team(role_id: int, limit: int = 20) -> List[Dict]:
    """Get all games for a specific team."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT id, team1_role_id, team2_role_id, team1_name, team2_name,
                       team1_sets, team2_sets, team1_points, team2_points,
                       winner_role_id, match_date, reported_by_name
                FROM game_results
                WHERE team1_role_id = ? OR team2_role_id = ?
                ORDER BY match_date DESC
                LIMIT ?
            """, (role_id, role_id, limit)) as cursor:
                results = await cursor.fetchall()
                
                games = []
                for result in results:
                    games.append({
                        'id': result[0],
                        'team1_role_id': result[1],
                        'team2_role_id': result[2],
                        'team1_name': result[3],
                        'team2_name': result[4],
                        'team1_sets': result[5],
                        'team2_sets': result[6],
                        'team1_points': result[7],
                        'team2_points': result[8],
                        'winner_role_id': result[9],
                        'match_date': result[10],
                        'reported_by_name': result[11]
                    })
                
                return games
    except Exception as e:
        print(f"Error getting games for team {role_id}: {e}")
        return []

async def get_games_by_teams(team1_role_id: int, team2_role_id: int, limit: int = 10) -> List[Dict]:
    """Get games between two specific teams."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT id, team1_role_id, team2_role_id, team1_name, team2_name,
                       team1_sets, team2_sets, team1_points, team2_points,
                       winner_role_id, match_date, reported_by_name
                FROM game_results
                WHERE (team1_role_id = ? AND team2_role_id = ?) OR (team1_role_id = ? AND team2_role_id = ?)
                ORDER BY match_date DESC
                LIMIT ?
            """, (team1_role_id, team2_role_id, team2_role_id, team1_role_id, limit)) as cursor:
                results = await cursor.fetchall()
                
                games = []
                for result in results:
                    games.append({
                        'id': result[0],
                        'team1_role_id': result[1],
                        'team2_role_id': result[2],
                        'team1_name': result[3],
                        'team2_name': result[4],
                        'team1_sets': result[5],
                        'team2_sets': result[6],
                        'team1_points': result[7],
                        'team2_points': result[8],
                        'winner_role_id': result[9],
                        'match_date': result[10],
                        'reported_by_name': result[11]
                    })
                
                return games
    except Exception as e:
        print(f"Error getting games between teams {team1_role_id} and {team2_role_id}: {e}")
        return []

async def validate_standings_integrity(guild=None) -> Dict:
    """Validate that standings match the actual game results and guild roles."""
    try:
        integrity_report = {
            'teams_checked': 0,
            'discrepancies_found': 0,
            'issues': [],
            'missing_from_standings': [],
            'orphaned_in_standings': []
        }
        
        async with aiosqlite.connect(DB_PATH) as db:
            # If guild provided, check against actual Discord roles
            if guild:
                # Get all team roles from main teams table
                async with db.execute("SELECT team_id, role_id, name, emoji FROM teams") as cursor:
                    teams_in_db = await cursor.fetchall()
                
                guild_role_ids = {role.id for role in guild.roles}
                
                # Check for teams that should be in standings but aren't
                for team_id, role_id, name, emoji in teams_in_db:
                    if role_id in guild_role_ids:
                        # Role exists, check if in standings
                        async with db.execute("SELECT role_id FROM team_standings WHERE role_id = ?", (role_id,)) as cursor:
                            if not await cursor.fetchone():
                                integrity_report['missing_from_standings'].append({
                                    'team_name': name,
                                    'role_id': role_id,
                                    'team_id': team_id,
                                    'emoji': emoji
                                })
                
                # Check for teams in standings whose roles no longer exist
                async with db.execute("SELECT role_id, name FROM team_standings") as cursor:
                    standings_teams = await cursor.fetchall()
                
                for role_id, name in standings_teams:
                    if role_id not in guild_role_ids:
                        integrity_report['orphaned_in_standings'].append({
                            'team_name': name,
                            'role_id': role_id
                        })
            
            # Get all teams in standings
            async with db.execute("SELECT role_id, name, wins, losses, sets_won, sets_lost FROM team_standings") as cursor:
                teams = await cursor.fetchall()
            
            for role_id, name, recorded_wins, recorded_losses, recorded_sets_won, recorded_sets_lost in teams:
                integrity_report['teams_checked'] += 1
                
                # Calculate actual stats from game results
                actual_wins = 0
                actual_losses = 0
                actual_sets_won = 0
                actual_sets_lost = 0
                
                async with db.execute("""
                    SELECT team1_role_id, team2_role_id, team1_sets, team2_sets, winner_role_id
                    FROM game_results
                    WHERE team1_role_id = ? OR team2_role_id = ?
                """, (role_id, role_id)) as cursor2:
                    games = await cursor2.fetchall()
                
                for team1_id, team2_id, team1_sets, team2_sets, winner_id in games:
                    if team1_id == role_id:
                        # This team was team1
                        actual_sets_won += team1_sets
                        actual_sets_lost += team2_sets
                        if winner_id == role_id:
                            actual_wins += 1
                        else:
                            actual_losses += 1
                    else:
                        # This team was team2
                        actual_sets_won += team2_sets
                        actual_sets_lost += team1_sets
                        if winner_id == role_id:
                            actual_wins += 1
                        else:
                            actual_losses += 1
                
                # Check for discrepancies
                if (actual_wins != recorded_wins or actual_losses != recorded_losses or
                    actual_sets_won != recorded_sets_won or actual_sets_lost != recorded_sets_lost):
                    
                    integrity_report['discrepancies_found'] += 1
                    integrity_report['issues'].append({
                        'team_name': name,
                        'role_id': role_id,
                        'recorded': {
                            'wins': recorded_wins,
                            'losses': recorded_losses,
                            'sets_won': recorded_sets_won,
                            'sets_lost': recorded_sets_lost
                        },
                        'actual': {
                            'wins': actual_wins,
                            'losses': actual_losses,
                            'sets_won': actual_sets_won,
                            'sets_lost': actual_sets_lost
                        }
                    })
        
        return integrity_report
        
    except Exception as e:
        print(f"Error validating standings integrity: {e}")
        return {'teams_checked': 0, 'discrepancies_found': 0, 'issues': [], 'error': str(e)}

async def fix_standings_integrity(guild=None) -> Dict:
    """Fix standings discrepancies by recalculating from game results and syncing with guild."""
    try:
        fix_report = {
            'teams_fixed': 0,
            'teams_checked': 0,
            'teams_added': 0,
            'teams_removed': 0,
            'fixes_applied': []
        }
        
        async with aiosqlite.connect(DB_PATH) as db:
            # First sync with guild if provided
            if guild:
                synced, added, removed = await sync_teams_with_guild_roles(guild)
                fix_report['teams_added'] = added
                fix_report['teams_removed'] = removed
            
            # Get all teams in standings
            async with db.execute("SELECT role_id, name FROM team_standings") as cursor:
                teams = await cursor.fetchall()
            
            for role_id, name in teams:
                fix_report['teams_checked'] += 1
                
                # Calculate correct stats from game results
                wins = 0
                losses = 0
                sets_won = 0
                sets_lost = 0
                points_for = 0
                points_against = 0
                
                async with db.execute("""
                    SELECT team1_role_id, team2_role_id, team1_sets, team2_sets,
                           team1_points, team2_points, winner_role_id
                    FROM game_results
                    WHERE team1_role_id = ? OR team2_role_id = ?
                """, (role_id, role_id)) as cursor2:
                    games = await cursor2.fetchall()
                
                games_played = len(games)
                
                for team1_id, team2_id, team1_sets, team2_sets, team1_points, team2_points, winner_id in games:
                    if team1_id == role_id:
                        # This team was team1
                        sets_won += team1_sets
                        sets_lost += team2_sets
                        points_for += team1_points
                        points_against += team2_points
                        if winner_id == role_id:
                            wins += 1
                        else:
                            losses += 1
                    else:
                        # This team was team2
                        sets_won += team2_sets
                        sets_lost += team1_sets
                        points_for += team2_points
                        points_against += team1_points
                        if winner_id == role_id:
                            wins += 1
                        else:
                            losses += 1
                
                win_percentage = (wins / games_played * 100) if games_played > 0 else 0.0
                set_differential = sets_won - sets_lost
                
                # Update the standings with correct values
                await db.execute("""
                    UPDATE team_standings
                    SET wins = ?, losses = ?, sets_won = ?, sets_lost = ?,
                        points_for = ?, points_against = ?, games_played = ?,
                        win_percentage = ?, set_differential = ?, last_updated = ?
                    WHERE role_id = ?
                """, (wins, losses, sets_won, sets_lost, points_for, points_against,
                      games_played, win_percentage, set_differential,
                      datetime.utcnow().isoformat(), role_id))
                
                fix_report['teams_fixed'] += 1
                fix_report['fixes_applied'].append({
                    'team_name': name,
                    'role_id': role_id,
                    'corrected_stats': {
                        'wins': wins,
                        'losses': losses,
                        'sets_won': sets_won,
                        'sets_lost': sets_lost,
                        'games_played': games_played,
                        'win_percentage': round(win_percentage, 1)
                    }
                })
            
            await db.commit()
        
        return fix_report
        
    except Exception as e:
        print(f"Error fixing standings integrity: {e}")
        return {'teams_fixed': 0, 'teams_checked': 0, 'fixes_applied': [], 'error': str(e)}

# ========================= RETRIEVAL FUNCTIONS =========================

async def get_team_standings(limit: int = None, sort_by: str = "standard") -> List[Tuple]:
    """Get team standings - INCLUDING ALL TEAMS (even 0-0 records)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Different sorting options
            if sort_by == "win_percentage":
                order_clause = "ORDER BY win_percentage DESC, games_played DESC, set_differential DESC"
            elif sort_by == "sets":
                order_clause = "ORDER BY set_differential DESC, wins DESC, win_percentage DESC"
            elif sort_by == "recent":
                order_clause = "ORDER BY last_game_date DESC NULLS LAST, wins DESC"
            else:  # standard
                order_clause = "ORDER BY wins DESC, set_differential DESC, sets_won DESC, win_percentage DESC"
            
            # REMOVED the WHERE clause that filtered out 0-0 teams
            query = f"""
                SELECT role_id, team_id, name, emoji, wins, losses, 
                       sets_won, sets_lost, points_for, points_against, 
                       games_played, win_percentage, set_differential, 
                       last_game_date, last_updated
                FROM team_standings
                {order_clause}
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            async with db.execute(query) as cursor:
                return await cursor.fetchall()
    except Exception as e:
        print(f"Error getting team standings: {e}")
        return []

async def get_team_standing(role_id: int) -> Optional[Tuple]:
    """Get a specific team's standing."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT role_id, team_id, name, emoji, wins, losses,
                       sets_won, sets_lost, points_for, points_against,
                       games_played, win_percentage, set_differential,
                       last_game_date, last_updated
                FROM team_standings
                WHERE role_id = ?
            """, (role_id,)) as cursor:
                return await cursor.fetchone()
    except Exception as e:
        print(f"Error getting team standing for {role_id}: {e}")
        return None

async def get_recent_games(limit: int = 10) -> List[Tuple]:
    """Get recent game results."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT team1_name, team2_name, team1_sets, team2_sets,
                       team1_points, team2_points, match_date, reported_by_name
                FROM game_results
                ORDER BY match_date DESC
                LIMIT ?
            """, (limit,)) as cursor:
                return await cursor.fetchall()
    except Exception as e:
        print(f"Error getting recent games: {e}")
        return []

async def get_head_to_head(team1_role_id: int, team2_role_id: int) -> Dict:
    """Get head-to-head record between two teams."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT winner_role_id, team1_sets, team2_sets, match_date
                FROM game_results
                WHERE (team1_role_id = ? AND team2_role_id = ?) OR (team1_role_id = ? AND team2_role_id = ?)
                ORDER BY match_date DESC
            """, (team1_role_id, team2_role_id, team2_role_id, team1_role_id)) as cursor:
                games = await cursor.fetchall()
                
                team1_wins = sum(1 for game in games if game[0] == team1_role_id)
                team2_wins = sum(1 for game in games if game[0] == team2_role_id)
                
                return {
                    'team1_wins': team1_wins,
                    'team2_wins': team2_wins,
                    'total_games': len(games),
                    'recent_games': games[:5]  # Last 5 games
                }
    except Exception as e:
        print(f"Error getting head-to-head: {e}")
        return {'team1_wins': 0, 'team2_wins': 0, 'total_games': 0, 'recent_games': []}

async def get_team_streak(role_id: int) -> Dict:
    """Get a team's current win/loss streak."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT (winner_role_id = ?) as won, match_date
                FROM game_results
                WHERE team1_role_id = ? OR team2_role_id = ?
                ORDER BY match_date DESC
                LIMIT 10
            """, (role_id, role_id, role_id)) as cursor:
                games = await cursor.fetchall()
                
                if not games:
                    return {'type': None, 'count': 0, 'last_result': None}
                
                current_streak = 0
                streak_type = 'W' if games[0][0] else 'L'
                
                for won, _ in games:
                    if (won and streak_type == 'W') or (not won and streak_type == 'L'):
                        current_streak += 1
                    else:
                        break
                
                return {
                    'type': streak_type,
                    'count': current_streak,
                    'last_result': 'W' if games[0][0] else 'L'
                }
    except Exception as e:
        print(f"Error getting team streak: {e}")
        return {'type': None, 'count': 0, 'last_result': None}

async def get_standings_summary() -> Dict:
    """Get comprehensive standings summary."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Basic stats - REMOVED the WHERE games_played > 0 filter
            async with db.execute("""
                SELECT COUNT(*) as total_teams,
                       SUM(games_played) / 2.0 as total_games,
                       AVG(games_played) as avg_games_per_team,
                       MAX(games_played) as max_games,
                       MIN(games_played) as min_games
                FROM team_standings
            """) as cursor:
                basic_stats = await cursor.fetchone()
                
            # Get leader info - only from teams that have played
            async with db.execute("""
                SELECT name, wins, losses, set_differential, emoji
                FROM team_standings
                WHERE games_played > 0
                ORDER BY wins DESC, set_differential DESC
                LIMIT 1
            """) as cursor:
                leader = await cursor.fetchone()
                
            # Get most recent game
            async with db.execute("""
                SELECT team1_name, team2_name, team1_sets, team2_sets, match_date
                FROM game_results
                ORDER BY match_date DESC
                LIMIT 1
            """) as cursor:
                recent_game = await cursor.fetchone()
                
            return {
                'total_teams': basic_stats[0] or 0,
                'total_games': int(basic_stats[1] or 0),
                'avg_games_per_team': round(basic_stats[2] or 0, 1),
                'max_games': basic_stats[3] or 0,
                'min_games': basic_stats[4] or 0,
                'leader_name': leader[0] if leader else "No games played",
                'leader_record': f"{leader[1]}-{leader[2]}" if leader else "0-0",
                'leader_emoji': leader[4] if leader else "🏐",
                'leader_set_diff': leader[3] if leader else 0,
                'recent_game': recent_game
            }
    except Exception as e:
        print(f"Error getting standings summary: {e}")
        return {
            'total_teams': 0, 'total_games': 0, 'avg_games_per_team': 0,
            'max_games': 0, 'min_games': 0, 'leader_name': 'Error', 
            'leader_record': '0-0', 'leader_emoji': '🏐', 'leader_set_diff': 0,
            'recent_game': None
        }

async def reset_all_standings():
    """Reset all team standings but preserve team info."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Reset standings while keeping team info
            await db.execute("""
                UPDATE team_standings
                SET wins = 0, losses = 0, sets_won = 0, sets_lost = 0,
                    points_for = 0, points_against = 0, games_played = 0,
                    win_percentage = 0.0, set_differential = 0,
                    last_game_date = NULL, last_updated = ?
            """, (datetime.utcnow().isoformat(),))
            
            # Clear game history
            await db.execute("DELETE FROM game_results")
            
            await db.commit()
            print("✅ All standings reset successfully")
    except Exception as e:
        print(f"Error resetting standings: {e}")

async def get_team_performance_stats(role_id: int) -> Dict:
    """Get detailed performance statistics for a team."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Get basic standing
            standing = await get_team_standing(role_id)
            if not standing:
                return {}
                
            # Get recent form (last 5 games)
            async with db.execute("""
                SELECT (winner_role_id = ?) as won
                FROM game_results
                WHERE team1_role_id = ? OR team2_role_id = ?
                ORDER BY match_date DESC
                LIMIT 5
            """, (role_id, role_id, role_id)) as cursor:
                results = await cursor.fetchall()
                recent_form = ['W' if won[0] else 'L' for won in results]
                
            # Get streak info
            streak_info = await get_team_streak(role_id)
            
            return {
                'standing': standing,
                'recent_form': recent_form,
                'streak': streak_info,
                'form_record': f"{recent_form.count('W')}-{recent_form.count('L')}" if recent_form else "0-0"
            }
    except Exception as e:
        print(f"Error getting team performance stats: {e}")
        return {}

# ========================= UTILITY FUNCTIONS =========================

async def initialize_database():
    """Initialize the database when the module is loaded."""
    await init_standings_table()
    print("✅ Database initialization complete")

async def get_all_team_ids_from_standings() -> List[int]:
    """Get all role IDs that exist in the standings database."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT DISTINCT role_id FROM team_standings"
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows] if rows else []
    except Exception as e:
        print(f"Error getting all role IDs from standings: {e}")
        return []

async def remove_team_from_standings(role_id: int) -> bool:
    """Remove a specific team from the standings database."""
    return await remove_single_team_from_standings(role_id)

# This function seems to be for a different table structure - let's fix it
async def get_all_standings():
    """Get standings for all teams - legacy compatibility."""
    standings = await get_team_standings()
    # Convert to expected format
    formatted_standings = []
    for standing in standings:
        # standing is: (role_id, team_id, name, emoji, wins, losses, ...)
        formatted_standings.append((
            standing[0],  # role_id
            standing[2],  # name
            standing[3],  # emoji
            standing[4],  # wins
            standing[5],  # losses
            standing[11], # win_percentage
            standing[10]  # games_played
        ))
    return formatted_standings