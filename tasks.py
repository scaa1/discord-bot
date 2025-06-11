import discord
from discord.ext import tasks
from datetime import datetime, timedelta
import pytz
import aiosqlite
from config import DB_PATH
from database.players import expire_blacklists
from database.games import (
    get_upcoming_games_needing_reminders, mark_reminder_sent, 
    get_referee_signups
)
from database.settings import (
    get_active_dashboard, deactivate_dashboard, 
    update_dashboard_timestamp, set_dashboard_message
)
from database.teams import get_team_by_role
from database.settings import (
    get_game_reminder_channel_id, get_referee_role_id, 
    get_official_ping_role_id, get_team_owner_dashboard_channel_id
)
from ui.views import RefereeSignupView, TeamOwnerDashboardView

# ========================= GAME REMINDER FUNCTIONS =========================

async def send_game_reminder(bot, game_id: int, team1_id: int, team2_id: int, scheduled_time: str):
    """Send a reminder for a game (handles both upcoming and past games)."""
    try:
        # Get the reminder channel
        reminder_channel = None
        reminder_channel_id = await get_game_reminder_channel_id()
        for guild in bot.guilds:
            channel = guild.get_channel(reminder_channel_id)
            if channel:
                reminder_channel = channel
                break
        
        if not reminder_channel:
            print(f"Reminder channel {reminder_channel_id} not found")
            return

        guild = reminder_channel.guild
        
        # Get team roles and data
        team1_role = guild.get_role(team1_id)
        team2_role = guild.get_role(team2_id)
        
        if not team1_role or not team2_role:
            print(f"Could not find team roles: {team1_id}, {team2_id}")
            return

        # Get team emojis
        team1_data = await get_team_by_role(team1_id)
        team2_data = await get_team_by_role(team2_id)
        
        team1_emoji = team1_data[2] if team1_data and team1_data[2] else "🔥"
        team2_emoji = team2_data[2] if team2_data and team2_data[2] else "⚡"

        # Get referee and official game ping roles
        referee_role_id = await get_referee_role_id()
        official_ping_role_id = await get_official_ping_role_id()
        
        referee_role = guild.get_role(referee_role_id)
        official_ping_role = guild.get_role(official_ping_role_id)
        
        referee_mention = referee_role.mention if referee_role else "@Referee"
        official_ping_mention = official_ping_role.mention if official_ping_role else "@Official game ping"

        # Parse the scheduled time and check if it's past or future
        try:
            match_time = datetime.fromisoformat(scheduled_time)
            if match_time.tzinfo is None:
                match_time = pytz.utc.localize(match_time)
            
            unix_timestamp = int(match_time.timestamp())
            now = datetime.now(pytz.utc)
            
            # Determine if this is a past game or upcoming
            is_past_game = match_time < now
            
            if is_past_game:
                time_display = f"<t:{unix_timestamp}:F> (STARTED)"
                prefix = "⚠️ **LATE REMINDER** - Game has already started!\n\n"
            else:
                time_display = f"<t:{unix_timestamp}:t>"  # Time format (e.g., "9:00 PM")
                prefix = ""
                
        except:
            time_display = "Game Time"
            prefix = ""
            is_past_game = False

        # Create the reminder message with referee signup
        reminder_text = (
            f"{prefix}"
            f"{team1_emoji} {team1_role.mention} (home) vs {team2_emoji} {team2_role.mention} (away)\n"
            f"{time_display} | ref: {referee_mention} **NEED ONE**\n"
            f"This match will be streamed! {official_ping_mention}"
        )

        # Create referee signup view
        view = RefereeSignupView(game_id, team1_role.name, team2_role.name)
        
        # Send the reminder
        message = await reminder_channel.send(reminder_text, view=view)
        
        # Store message reference for the view to update later
        view.original_message = message
        view.original_embed = None  # No embed initially
        
        await mark_reminder_sent(game_id)
        
        status = "late reminder" if is_past_game else "reminder"
        print(f"Sent {status} for game {game_id}: {team1_role.name} vs {team2_role.name}")

    except Exception as e:
        print(f"Error sending game reminder: {e}")

async def check_game_reminders(bot_instance):
    """Background task to check for games needing reminders."""
    try:
        # Expire old blacklists first
        await expire_blacklists()
        
        upcoming_games = await get_upcoming_games_needing_reminders()
        
        for game_id, team1_id, team2_id, scheduled_time in upcoming_games:
            await send_game_reminder(bot_instance, game_id, team1_id, team2_id, scheduled_time)
            
    except Exception as e:
        print(f"Error in check_game_reminders: {e}")

# ========================= DASHBOARD FUNCTIONS =========================

async def create_team_owner_dashboard_embeds(bot_instance=None):
    """Create the team owner dashboard embeds with current data."""
    try:
        # Get all teams with their owners
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT team_id, role_id, emoji, name, owner_id FROM teams ORDER BY name"
            ) as cursor:
                teams_data = await cursor.fetchall()
        
        if not teams_data:
            embed = discord.Embed(
                title="👑 Team Owner Dashboard",
                description="No teams found in the database.",
                color=0x2F3136
            )
            embed.set_footer(text="🔄 Auto-updates every hour")
            return [embed]

        # Organize teams by owner status
        teams_with_owners = []
        teams_without_owners = []
        
        for team_id, role_id, emoji, name, owner_id in teams_data:
            team_emoji = emoji or "🔥"
            
            # Get member count if bot instance is available
            member_count = "Unknown"
            if bot_instance:
                for guild in bot_instance.guilds:
                    role = guild.get_role(role_id)
                    if role:
                        member_count = len(role.members)
                        break
            
            team_info = {
                'emoji': team_emoji,
                'name': name,
                'role_id': role_id,
                'owner_id': owner_id,
                'member_count': member_count
            }
            
            if owner_id:
                # Check if owner exists in any guild
                owner_found = False
                if bot_instance:
                    for guild in bot_instance.guilds:
                        owner = guild.get_member(owner_id)
                        if owner:
                            team_info['owner_name'] = owner.display_name
                            team_info['owner_mention'] = owner.mention
                            owner_found = True
                            break
                
                if owner_found:
                    teams_with_owners.append(team_info)
                else:
                    teams_without_owners.append(team_info)
            else:
                teams_without_owners.append(team_info)
        
        # Create embeds
        embeds = []
        teams_per_page = 8
        
        # Teams with owners
        if teams_with_owners:
            total_pages = (len(teams_with_owners) + teams_per_page - 1) // teams_per_page
            
            for page in range(total_pages):
                start_idx = page * teams_per_page
                end_idx = start_idx + teams_per_page
                page_teams = teams_with_owners[start_idx:end_idx]
                
                embed = discord.Embed(
                    title="👑 Team Owner Dashboard",
                    description="Teams with active owners",
                    color=0x00FF7F
                )
                
                for team in page_teams:
                    field_name = f"{team['emoji']} {team['name']}"
                    field_value = (
                        f"**Owner:** {team.get('owner_name', 'Unknown')}\n"
                        f"**Members:** {team['member_count']}"
                    )
                    embed.add_field(name=field_name, value=field_value, inline=True)
                
                embed.set_footer(text=f"🔄 Auto-updates every hour • Page {page + 1}/{total_pages}")
                embeds.append(embed)
        
        # Teams without owners
        if teams_without_owners:
            embed = discord.Embed(
                title="⚠️ Teams Without Owners",
                description="These teams need owner assignment",
                color=0xFF6B47
            )
            
            for team in teams_without_owners[:10]:  # Limit to 10 to avoid embed limits
                field_name = f"{team['emoji']} {team['name']}"
                field_value = f"**Members:** {team['member_count']}\n*No owner assigned*"
                embed.add_field(name=field_name, value=field_value, inline=True)
            
            embed.set_footer(text="🔄 Auto-updates every hour")
            embeds.append(embed)
        
        # Summary embed if no teams
        if not embeds:
            embed = discord.Embed(
                title="👑 Team Owner Dashboard",
                description="All teams processed successfully!",
                color=0x00FF7F
            )
            embed.set_footer(text="🔄 Auto-updates every hour")
            embeds.append(embed)
        
        return embeds
        
    except Exception as e:
        print(f"Error creating team owner dashboard embeds: {e}")
        error_embed = discord.Embed(
            title="👑 Team Owner Dashboard",
            description=f"❌ Error loading dashboard: {str(e)}",
            color=0xFF0000
        )
        error_embed.set_footer(text="🔄 Auto-updates every hour")
        return [error_embed]

async def setup_dashboard_in_channel(channel: discord.TextChannel, bot_instance=None):
    """Set up the dashboard in the specified channel."""
    try:
        # Check if there's already an active dashboard
        existing_dashboard = await get_active_dashboard()
        if existing_dashboard:
            existing_message_id, existing_channel_id = existing_dashboard
            existing_channel = channel.guild.get_channel(existing_channel_id)
            
            if existing_channel and existing_channel.id != channel.id:
                # Delete old dashboard message if in different channel
                try:
                    old_message = await existing_channel.fetch_message(existing_message_id)
                    await old_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass  # Message already gone or no permission
            
            # Deactivate old dashboard
            await deactivate_dashboard()
        
        # Create the dashboard embeds with bot instance
        embeds = await create_team_owner_dashboard_embeds(bot_instance)
        
        # Create view if multiple pages
        view = TeamOwnerDashboardView(embeds) if len(embeds) > 1 else None
        
        # Post the dashboard message (always start with first page)
        dashboard_message = await channel.send(embed=embeds[0], view=view)
        
        # Store in database
        await set_dashboard_message(dashboard_message.id, channel.id)
        
        return True, None
        
    except discord.Forbidden:
        return False, f"I don't have permission to send messages in {channel.mention}."
    except Exception as e:
        return False, f"Error creating dashboard: {str(e)}"
# ========================= TASK DEFINITIONS =========================

@tasks.loop(minutes=1)  # Check every minute
async def game_reminder_task(bot):
    """Background task that runs every minute to check for upcoming games."""
    await check_game_reminders(bot)

@tasks.loop(hours=1)  # Update every hour
async def update_team_owner_dashboard(bot):
    """Background task to update the team owner dashboard."""
    try:
        dashboard_info = await get_active_dashboard()
        if not dashboard_info:
            return  # No active dashboard
        
        message_id, channel_id = dashboard_info
        
        # Find the channel across all guilds
        channel = None
        for guild in bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                break
        
        if not channel:
            print(f"Dashboard channel {channel_id} not found, deactivating dashboard")
            await deactivate_dashboard()
            return
        
        try:
            # Get the message
            message = await channel.fetch_message(message_id)
            
            # Create updated embeds with bot instance
            updated_embeds = await create_team_owner_dashboard_embeds(bot)
            
            # Create new view with updated embeds
            view = TeamOwnerDashboardView(updated_embeds) if len(updated_embeds) > 1 else None
            
            # Update the message (always show first page)
            await message.edit(embed=updated_embeds[0], view=view)
            
            # Update timestamp in database
            await update_dashboard_timestamp()
            
            print(f"Updated team owner dashboard in {channel.name} ({len(updated_embeds)} pages)")
            
        except discord.NotFound:
            print(f"Dashboard message {message_id} not found, deactivating dashboard")
            await deactivate_dashboard()
        except discord.Forbidden:
            print(f"No permission to edit dashboard message in {channel.name}")
        except Exception as e:
            print(f"Error updating dashboard message: {e}")
            
    except Exception as e:
        print(f"Error in update_team_owner_dashboard task: {e}")