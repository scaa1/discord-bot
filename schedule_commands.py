import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import math
from datetime import datetime, timedelta
import pytz

# Import configuration
from config import DB_PATH, GUILD_ID, ALLOWED_MANAGEMENT_ROLES

# Import database functions
from database.teams import get_team_by_role, get_team_by_id
from database.games import (
    schedule_game_and_post, get_upcoming_games_needing_reminders,
    mark_reminder_sent
)
from database.settings import get_schedule_log_channel_id

# Import utility functions
from utils.permissions import has_any_role, user_is_team_owner, user_has_coach_role_async
from utils.time_parsing import parse_flexible_datetime, parse_flexible_datetime_allow_past
from utils.emoji_helpers import get_emoji_thumbnail_url

# Import UI components
from ui.views import PaginatorView

# Import tasks
from tasks import send_game_reminder

class ScheduleCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        for command in self.__cog_app_commands__:
            command.guild_ids = [GUILD_ID]

    async def get_user_team_by_role(self, user: discord.Member):
        """Get user's team by checking their actual Discord roles."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT team_id, role_id, emoji, name FROM teams") as cursor:
                teams = await cursor.fetchall()
                
                for team_id, role_id, emoji, name in teams:
                    team_role = user.guild.get_role(role_id)
                    if team_role and team_role in user.roles:
                        return (team_id, role_id, emoji, name)
                return None

    @app_commands.command(name="send_old_reminders", description="Send reminders for old games that haven't been reminded yet")
    async def send_old_reminders(self, interaction: discord.Interaction):
        """Manually trigger reminders for past games."""
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get games needing reminders
            games = await get_upcoming_games_needing_reminders()
            
            if not games:
                await interaction.followup.send("No games found that need reminders.", ephemeral=True)
                return
            
            sent_count = 0
            for game_id, team1_id, team2_id, scheduled_time in games:
                await send_game_reminder(self.bot, game_id, team1_id, team2_id, scheduled_time)
                sent_count += 1
                await asyncio.sleep(1)  # Small delay between messages
            
            await interaction.followup.send(
                f"✅ Sent reminders for {sent_count} games!",
                ephemeral=True
            )
        
        except Exception as e:
            await interaction.followup.send(f"❌ Error sending reminders: {e}", ephemeral=True)

    @app_commands.command(name="schedulegame", description="Schedule a game between two teams. You must be a team owner, vice captain, or admin.")
    @app_commands.describe(
        team1="The first team (home team)",
        team2="The second team (away team)",
        when="When to play (e.g., 'tomorrow 7pm', 'Friday 3:30pm', 'in 2 days 8pm')",
        timezone="Timezone (default: EST). Use EST, PST, CST, etc."
    )
    async def schedulegame(
        self,
        interaction: discord.Interaction,
        team1: discord.Role,
        team2: discord.Role,
        when: str,
        timezone: str = "EST"
    ):
        try:
            # Check if user is authorized (admin, or team owner/vice captain of either team)
            is_authorized = False
            
            # Check if admin
            if await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                is_authorized = True
            else:
                # Check if user is team owner
                if user_is_team_owner(interaction.user):
                    user_team = await self.get_user_team_by_role(interaction.user)
                    if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                        is_authorized = True
                
                # Check if user is vice captain of either team
                if not is_authorized:
                    has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                    if has_coach_role:
                        user_team = await self.get_user_team_by_role(interaction.user)
                        if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                            is_authorized = True
            
            if not is_authorized:
                await interaction.response.send_message(
                    "You are not authorized to schedule games. Only admins or team owners/vice captains of the participating teams can schedule games.", 
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Validate that both teams are different
            if team1.id == team2.id:
                await interaction.followup.send("You can't schedule a game between the same team.", ephemeral=True)
                return

            # Validate that both teams are registered
            team1_data = await get_team_by_role(team1.id)
            team2_data = await get_team_by_role(team2.id)
            
            if not team1_data:
                await interaction.followup.send(
                    f"❌ {team1.mention} is not a registered team. Only registered teams can be scheduled.",
                    ephemeral=True
                )
                return
                
            if not team2_data:
                await interaction.followup.send(
                    f"❌ {team2.mention} is not a registered team. Only registered teams can be scheduled.",
                    ephemeral=True
                )
                return

            # Parse the flexible datetime input
            try:
                match_datetime_utc = parse_flexible_datetime(when, timezone)
            except ValueError as e:
                await interaction.followup.send(
                    f"❌ **Invalid date/time format.**\n"
                    f"Error: {str(e)}\n\n"
                    f"**Try these formats:**\n"
                    f"• `tomorrow 7pm`\n"
                    f"• `Friday 3:30pm`\n"
                    f"• `in 2 days 8pm`\n"
                    f"• `Dec 25 14:00`\n"
                    f"• `next week 8pm`\n"
                    f"• `Jan 15 7:30pm`",
                    ephemeral=True
                )
                return

            try:
                # Schedule the game and post to channel
                log_channel_id = await get_schedule_log_channel_id()
                if log_channel_id:
                    log_channel = interaction.guild.get_channel(log_channel_id)
                    if log_channel:
                        game_id, message_id = await schedule_game_and_post(
                            team1.id, team2.id, match_datetime_utc.isoformat(), 
                            interaction.guild, log_channel, interaction.user
                        )
                        await interaction.followup.send("✅ Game scheduled and posted in the schedule channel!")
                    else:
                        await interaction.followup.send(f"Game scheduled, but schedule log channel {log_channel_id} not found.", ephemeral=True)
                else:
                    await interaction.followup.send("Game scheduled, but schedule log channel not configured. Use /config to set it up.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Error scheduling game: {e}", ephemeral=True)
                return

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in schedulegame command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while scheduling the game: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"An error occurred while scheduling the game: {str(e)}",
                    ephemeral=True
                )

    @app_commands.command(name="reschedule", description="Reschedule an existing game to a new date and time")
    @app_commands.describe(
        team1="The first team",
        team2="The second team",
        old_when="Current scheduled time (e.g., 'yesterday 7pm', 'last Friday 3:30pm', '2 days ago 8pm')",
        new_when="New time (e.g., 'next week 8pm', 'Saturday 2pm')",
        timezone="Timezone (default: EST). Use EST, PST, CST, etc."
    )
    async def reschedule(
        self,
        interaction: discord.Interaction,
        team1: discord.Role,
        team2: discord.Role,
        old_when: str,
        new_when: str,
        timezone: str = "EST"
    ):
        try:
            # Check if user is authorized (admin, or team owner/vice captain of either team)
            is_authorized = False
            
            # Check if admin
            if await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                is_authorized = True
            else:
                # Check if user is team owner
                if user_is_team_owner(interaction.user):
                    user_team = await self.get_user_team_by_role(interaction.user)
                    if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                        is_authorized = True
                
                # Check if user is vice captain of either team
                if not is_authorized:
                    has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                    if has_coach_role:
                        user_team = await self.get_user_team_by_role(interaction.user)
                        if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                            is_authorized = True
            
            if not is_authorized:
                await interaction.response.send_message(
                    "You are not authorized to reschedule games. Only admins or team owners/vice captains of the participating teams can reschedule games.", 
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Validate that both teams are different
            if team1.id == team2.id:
                await interaction.followup.send("You can't reschedule a game between the same team.", ephemeral=True)
                return

            # Parse old datetime
            try:
                old_match_datetime_utc = parse_flexible_datetime_allow_past(old_when, timezone)
            except ValueError as e:
                await interaction.followup.send(
                    f"❌ **Invalid OLD date/time format.**\n"
                    f"Error: {str(e)}\n\n"
                    f"**Try formats like:** `yesterday 7pm`, `last Friday 3:30pm`, `2 days ago 8pm`",
                    ephemeral=True
                )
                return

            # Parse new datetime
            try:
                new_match_datetime_utc = parse_flexible_datetime(new_when, timezone)
            except ValueError as e:
                await interaction.followup.send(
                    f"❌ **Invalid NEW date/time format.**\n"
                    f"Error: {str(e)}\n\n"
                    f"**Try formats like:** `next week 8pm`, `Saturday 2pm`, `Jan 15 7:30pm`",
                    ephemeral=True
                )
                return

            # Find game and get message info for deletion
            async with aiosqlite.connect(DB_PATH) as db:
                # Check if the game exists (with some tolerance for time differences)
                old_time_range_start = (old_match_datetime_utc - timedelta(minutes=30)).isoformat()
                old_time_range_end = (old_match_datetime_utc + timedelta(minutes=30)).isoformat()
                
                cursor = await db.execute(
                    """
                    SELECT game_id, scheduled_time, message_id FROM scheduled_games 
                    WHERE 
                        ((team1_id = ? AND team2_id = ?) OR (team1_id = ? AND team2_id = ?))
                        AND scheduled_time BETWEEN ? AND ?
                    """,
                    (team1.id, team2.id, team2.id, team1.id, old_time_range_start, old_time_range_end)
                )
                game = await cursor.fetchone()
                
                if not game:
                    await interaction.followup.send(
                        f"❌ No game found between {team1.mention} and {team2.mention} around the specified time.\n"
                        f"**Looking for game around:** <t:{int(old_match_datetime_utc.timestamp())}:f>\n"
                        f"Use `/viewgames team:{team1.name}` or `/viewgames team:{team2.name}` to see all scheduled games.",
                        ephemeral=True
                    )
                    return

                game_id, actual_scheduled_time, old_message_id = game

                # Update the game time and reset reminder
                await db.execute(
                    """
                    UPDATE scheduled_games 
                    SET scheduled_time = ?, reminder_sent = 0, message_id = NULL
                    WHERE game_id = ?
                    """,
                    (new_match_datetime_utc.isoformat(), game_id)
                )
                await db.commit()

            # Delete the old message if it exists
            if old_message_id:
                try:
                    log_channel_id = await get_schedule_log_channel_id()
                    if log_channel_id:
                        log_channel = interaction.guild.get_channel(log_channel_id)
                        if log_channel:
                            try:
                                old_message = await log_channel.fetch_message(old_message_id)
                                await old_message.delete()
                                print(f"Deleted old schedule message {old_message_id}")
                            except discord.NotFound:
                                print(f"Old schedule message {old_message_id} not found (already deleted)")
                            except Exception as e:
                                print(f"Error deleting old schedule message: {e}")
                except Exception as e:
                    print(f"Error accessing schedule channel for message deletion: {e}")

            # Create new schedule message
            new_unix_timestamp = int(new_match_datetime_utc.timestamp())
            old_unix_timestamp = int(old_match_datetime_utc.timestamp())
            
            # Get team emojis
            team1_data = await get_team_by_role(team1.id)
            team2_data = await get_team_by_role(team2.id)
            
            team1_emoji = team1_data[2] if team1_data and team1_data[2] else "🔥"
            team2_emoji = team2_data[2] if team2_data and team2_data[2] else "⚡"
            
            new_embed = discord.Embed(
                title="📅 Game Rescheduled",
                description=(
                    f"{team1_emoji} {team1.mention} vs {team2.mention} {team2_emoji}\n"
                    f"🕒 <t:{new_unix_timestamp}:F> (full date & time)\n"
                    f"⏰ <t:{new_unix_timestamp}:R> (relative time)\n\n"
                    f"**Rescheduled from:** <t:{old_unix_timestamp}:f>\n"
                    f"**Rescheduled by:** {interaction.user.mention}"
                ),
                color=discord.Color.orange()
            )
            new_embed.set_footer(text=f"Game ID: {game_id}")

            # Send new schedule message and update database with new message ID
            log_channel_id = await get_schedule_log_channel_id()
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    try:
                        message = await log_channel.send(embed=new_embed)
                        await message.add_reaction("✅")
                        await message.add_reaction("❌")
                        
                        # Update database with new message ID
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "UPDATE scheduled_games SET message_id = ? WHERE game_id = ?",
                                (message.id, game_id)
                            )
                            await db.commit()
                        
                        await interaction.followup.send("✅ Game successfully rescheduled and posted in the schedule channel.")
                    except Exception as e:
                        await interaction.followup.send(f"Game rescheduled in database, but failed to post to schedule channel: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send("Game rescheduled in database, but schedule log channel not found.", ephemeral=True)
            else:
                await interaction.followup.send("Game rescheduled in database, but schedule log channel not configured.", ephemeral=True)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in reschedule command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while rescheduling the game: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"An error occurred while rescheduling the game: {str(e)}",
                    ephemeral=True
                )

    @app_commands.command(name="removeschedule", description="Remove a scheduled game between two teams.")
    @app_commands.describe(
        team1="The first team",
        team2="The second team", 
        when="When the game is scheduled (e.g., 'tomorrow 7pm', 'Friday 3:30pm')",
        timezone="Timezone (default: EST). Use EST, PST, CST, etc."
    )
    async def removescheduledgame(
        self,
        interaction: discord.Interaction,
        team1: discord.Role,
        team2: discord.Role,
        when: str,
        timezone: str = "EST"
    ):
        try:
            # Check if user is authorized (admin, or team owner/vice captain of either team)
            is_authorized = False
            
            # Check if admin
            if await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                is_authorized = True
            else:
                # Check if user is team owner
                if user_is_team_owner(interaction.user):
                    user_team = await self.get_user_team_by_role(interaction.user)
                    if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                        is_authorized = True
                
                # Check if user is vice captain of either team
                if not is_authorized:
                    has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                    if has_coach_role:
                        user_team = await self.get_user_team_by_role(interaction.user)
                        if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                            is_authorized = True
            
            if not is_authorized:
                await interaction.response.send_message(
                    "You are not authorized to remove games. Only admins or team owners/vice captains of the participating teams can remove games.", 
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Validate that both teams are different
            if team1.id == team2.id:
                await interaction.followup.send("You can't remove a game between the same team.", ephemeral=True)
                return

            # Parse datetime
            try:
                match_datetime_utc = parse_flexible_datetime(when, timezone)
            except ValueError as e:
                await interaction.followup.send(
                    f"❌ **Invalid date/time format.**\n"
                    f"Error: {str(e)}\n\n"
                    f"**Try formats like:** `tomorrow 7pm`, `Friday 3:30pm`, `in 2 days 8pm`",
                    ephemeral=True
                )
                return

            # Remove from database and get message info for deletion
            time_range_start = (match_datetime_utc - timedelta(minutes=30)).isoformat()
            time_range_end = (match_datetime_utc + timedelta(minutes=30)).isoformat()
            
            async with aiosqlite.connect(DB_PATH) as db:
                # First find the game
                cursor = await db.execute(
                    """
                    SELECT game_id, scheduled_time, message_id FROM scheduled_games 
                    WHERE 
                        ((team1_id = ? AND team2_id = ?) OR (team1_id = ? AND team2_id = ?))
                        AND scheduled_time BETWEEN ? AND ?
                    """,
                    (team1.id, team2.id, team2.id, team1.id, time_range_start, time_range_end)
                )
                game = await cursor.fetchone()
                
                if not game:
                    await interaction.followup.send(
                        f"❌ No matching scheduled game found around the specified time.\n"
                        f"**Looking for game around:** <t:{int(match_datetime_utc.timestamp())}:f>\n"
                        f"Use `/viewgames team:{team1.name}` or `/viewgames team:{team2.name}` to see all scheduled games.",
                        ephemeral=True
                    )
                    return
                
                game_id, actual_scheduled_time, message_id = game
                
                # Delete the game and related referee signups
                await db.execute("DELETE FROM referee_signups WHERE game_id = ?", (game_id,))
                await db.execute("DELETE FROM scheduled_games WHERE game_id = ?", (game_id,))
                await db.commit()

            # Delete the message if it exists
            if message_id:
                try:
                    log_channel_id = await get_schedule_log_channel_id()
                    if log_channel_id:
                        log_channel = interaction.guild.get_channel(log_channel_id)
                        if log_channel:
                            try:
                                message = await log_channel.fetch_message(message_id)
                                await message.delete()
                                print(f"Deleted schedule message {message_id}")
                            except discord.NotFound:
                                print(f"Schedule message {message_id} not found (already deleted)")
                            except Exception as e:
                                print(f"Error deleting schedule message: {e}")
                except Exception as e:
                    print(f"Error accessing schedule channel for message deletion: {e}")

            # Create confirmation embed
            actual_datetime = datetime.fromisoformat(actual_scheduled_time)
            if actual_datetime.tzinfo is None:
                actual_datetime = pytz.utc.localize(actual_datetime)
            
            embed = discord.Embed(
                title="🗑️ Game Removed",
                description=f"❌ Game between {team1.mention} and {team2.mention} on <t:{int(actual_datetime.timestamp())}:f> has been removed.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Removed by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in removescheduledgame command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while removing the game: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"An error occurred while removing the game: {str(e)}",
                    ephemeral=True
                )

    @app_commands.command(name="viewgames", description="View scheduled games (optionally filter by team)")
    @app_commands.describe(team="Optional: Select a team role to view only their games")
    async def viewgames(self, interaction: discord.Interaction, team: discord.Role = None):
        try:
            await interaction.response.defer()
            
            # Validate team if provided
            team_data = None
            if team:
                team_data = await get_team_by_role(team.id)
                if not team_data:
                    await interaction.followup.send(
                        f"❌ {team.mention} is not a registered team in the database."
                    )
                    return
            
            # Get scheduled games (filtered by team if provided)
            if team:
                # Filter games for specific team
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        """
                        SELECT game_id, team1_id, team2_id, scheduled_time, status 
                        FROM scheduled_games 
                        WHERE team1_id = ? OR team2_id = ?
                        ORDER BY scheduled_time
                        """,
                        (team.id, team.id)
                    ) as cursor:
                        games = await cursor.fetchall()
            else:
                # Get all games
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        """
                        SELECT game_id, team1_id, team2_id, scheduled_time, status 
                        FROM scheduled_games 
                        ORDER BY scheduled_time
                        """
                    ) as cursor:
                        games = await cursor.fetchall()
            
            if not games:
                if team:
                    team_emoji = team_data[2] or "🔥"
                    team_name = team_data[3]
                    await interaction.followup.send(
                        f"No games are currently scheduled for {team_emoji} **{team_name}**."
                    )
                else:
                    await interaction.followup.send("No games are currently scheduled.")
                return

            # Use timezone-aware UTC datetime for comparison
            now_utc = datetime.now(pytz.utc)
            
            # Separate upcoming and past games with proper timezone handling
            upcoming_games = []
            past_games = []
            
            for game in games:
                game_id, team1_id, team2_id, scheduled_time_str, status = game
                
                try:
                    # Parse the scheduled time
                    scheduled_time = datetime.fromisoformat(scheduled_time_str)
                    
                    # If the datetime is naive, assume it's UTC and make it timezone-aware
                    if scheduled_time.tzinfo is None:
                        scheduled_time = pytz.utc.localize(scheduled_time)
                    
                    # Now we can safely compare timezone-aware datetimes
                    if scheduled_time > now_utc:
                        upcoming_games.append((game_id, team1_id, team2_id, scheduled_time, status))
                    else:
                        past_games.append((game_id, team1_id, team2_id, scheduled_time, status))
                        
                except (ValueError, TypeError) as dt_error:
                    print(f"Error parsing datetime for game {game_id}: {scheduled_time_str} - {dt_error}")
                    # Skip games with invalid datetime formats
                    continue

            # Create embeds for display
            embeds = []
            
            # Determine title prefix based on whether we're filtering by team
            if team:
                team_emoji = team_data[2] or "🔥"
                team_name = team_data[3]
                title_prefix = f"{team_emoji} {team_name}"
            else:
                title_prefix = "All Teams"
            
            if upcoming_games:
                # Sort upcoming games by time
                upcoming_games.sort(key=lambda x: x[3])
                
                embed = discord.Embed(
                    title=f"📅 {title_prefix} - Upcoming Games ({len(upcoming_games)})",
                    color=discord.Color.green()
                )
                
                game_list = []
                for game_id, team1_id, team2_id, scheduled_time, status in upcoming_games[:15]:  # Limit to 15 games
                    # Get team data
                    team1_data = await get_team_by_role(team1_id)
                    team2_data = await get_team_by_role(team2_id)
                    
                    if team1_data and team2_data:
                        team1_emoji = team1_data[2] or "🔥"
                        team1_name = team1_data[3]
                        team2_emoji = team2_data[2] or "⚡"
                        team2_name = team2_data[3]
                        
                        # Create Discord timestamp
                        unix_timestamp = int(scheduled_time.timestamp())
                        
                        # Highlight the filtered team if applicable
                        if team:
                            if team1_id == team.id:
                                team1_display = f"**{team1_emoji} {team1_name}** ← **YOUR TEAM**"
                                team2_display = f"{team2_emoji} {team2_name}"
                            else:
                                team1_display = f"{team1_emoji} {team1_name}"
                                team2_display = f"**{team2_emoji} {team2_name}** ← **YOUR TEAM**"
                        else:
                            team1_display = f"**{team1_emoji} {team1_name}**"
                            team2_display = f"**{team2_name} {team2_emoji}**"
                        
                        game_info = (
                            f"{team1_display} vs {team2_display}\n"
                            f"🕒 <t:{unix_timestamp}:F>\n"
                            f"⏰ <t:{unix_timestamp}:R>"
                        )
                        game_list.append(game_info)
                
                if game_list:
                    embed.description = "\n\n".join(game_list)
                    
                    if len(upcoming_games) > 15:
                        embed.set_footer(text=f"Showing first 15 of {len(upcoming_games)} upcoming games")
                    
                    embeds.append(embed)
            
            if past_games:
                # Sort past games by time (most recent first)
                past_games.sort(key=lambda x: x[3], reverse=True)
                
                embed = discord.Embed(
                    title=f"📋 {title_prefix} - Recent Games ({len(past_games)})",
                    color=discord.Color.blue()
                )
                
                game_list = []
                for game_id, team1_id, team2_id, scheduled_time, status in past_games[:10]:  # Limit to 10 past games
                    # Get team data
                    team1_data = await get_team_by_role(team1_id)
                    team2_data = await get_team_by_role(team2_id)
                    
                    if team1_data and team2_data:
                        team1_emoji = team1_data[2] or "🔥"
                        team1_name = team1_data[3]
                        team2_emoji = team2_data[2] or "⚡"
                        team2_name = team2_data[3]
                        
                        # Create Discord timestamp
                        unix_timestamp = int(scheduled_time.timestamp())
                        
                        # Highlight the filtered team if applicable
                        if team:
                            if team1_id == team.id:
                                team1_display = f"**{team1_emoji} {team1_name}** ← **YOUR TEAM**"
                                team2_display = f"{team2_emoji} {team2_name}"
                            else:
                                team1_display = f"{team1_emoji} {team1_name}"
                                team2_display = f"**{team2_emoji} {team2_name}** ← **YOUR TEAM**"
                        else:
                            team1_display = f"**{team1_emoji} {team1_name}**"
                            team2_display = f"**{team2_name} {team2_emoji}**"
                        
                        game_info = (
                            f"{team1_display} vs {team2_display}\n"
                            f"🕒 <t:{unix_timestamp}:F>"
                        )
                        game_list.append(game_info)
                
                if game_list:
                    embed.description = "\n\n".join(game_list)
                    
                    if len(past_games) > 10:
                        embed.set_footer(text=f"Showing 10 most recent of {len(past_games)} past games")
                    
                    embeds.append(embed)
            
            # If no valid games found
            if not embeds:
                if team:
                    await interaction.followup.send(
                        f"No valid games found for {team_emoji} **{team_name}**."
                    )
                else:
                    await interaction.followup.send("No valid games found in the schedule.")
                return
            
            # Add helpful information to the first embed
            if embeds:
                if team:
                    embeds[0].add_field(
                        name="💡 Tip",
                        value=f"Use `/viewgames` without a team to see all scheduled games.",
                        inline=False
                    )
                else:
                    embeds[0].add_field(
                        name="💡 Tip",
                        value=f"Use `/viewgames team:@TeamRole` to filter games for a specific team.",
                        inline=False
                    )
            
            # Send the embeds
            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                # If we have both upcoming and past games, use pagination
                view = PaginatorView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in viewgames command: {error_details}")
            
            try:
                await interaction.followup.send(
                    f"An error occurred while retrieving games: {str(e)}"
                )
            except Exception as response_error:
                print(f"Failed to send error response: {response_error}")

    # Add autocomplete functions
    @schedulegame.autocomplete('when')
    async def schedulegame_when_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        suggestions = [
            "tomorrow 7pm", "tomorrow 8pm", "Friday 7pm", "Saturday 2pm", 
            "Sunday 3pm", "next week 7pm", "today 8pm", "Monday 6pm"
        ]
        
        if current:
            suggestions = [s for s in suggestions if current.lower() in s.lower()]
        
        return [app_commands.Choice(name=suggestion, value=suggestion) for suggestion in suggestions[:25]]

    @reschedule.autocomplete('old_when')
    async def reschedule_old_when_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        suggestions = [
            "yesterday 7pm", "2 days ago 8pm", "last Friday 7pm", 
            "last Saturday 2pm", "3 hours ago", "last week 7pm",
            "today 3pm", "yesterday 9pm", "2 hours ago"
        ]
        
        if current:
            suggestions = [s for s in suggestions if current.lower() in s.lower()]
        
        return [app_commands.Choice(name=suggestion, value=suggestion) for suggestion in suggestions[:25]]

    @reschedule.autocomplete('new_when')
    async def reschedule_new_when_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        suggestions = [
            "tomorrow 7pm", "Friday 7pm", "Saturday 2pm", "Sunday 3pm", 
            "next week 8pm", "Monday 6pm", "Tuesday 7pm"
        ]
        
        if current:
            suggestions = [s for s in suggestions if current.lower() in s.lower()]
        
        return [app_commands.Choice(name=suggestion, value=suggestion) for suggestion in suggestions[:25]]

    @removescheduledgame.autocomplete('when')
    async def removegame_when_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        suggestions = [
            "tomorrow 7pm", "Friday 7pm", "Saturday 2pm", "Sunday 3pm", 
            "today 8pm", "Monday 6pm"
        ]
        
        if current:
            suggestions = [s for s in suggestions if current.lower() in s.lower()]
        
        return [app_commands.Choice(name=suggestion, value=suggestion) for suggestion in suggestions[:25]]

async def setup(bot):
    await bot.add_cog(ScheduleCommands(bot))