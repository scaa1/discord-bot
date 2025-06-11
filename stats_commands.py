# Create this file as: stats_commands.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal, Optional
from database.stats import (
    add_stat_to_player, get_player_stats, get_stat_leaderboard,
    get_all_stats_categories, set_player_stat, remove_player_stat,
    get_player_rank_in_stat, subtract_stat_from_player, reset_all_stats,
    get_total_stats_count, get_players_with_stats
)
from database.teams import get_team_by_role
from utils.permissions import has_any_role
from config import ALLOWED_MANAGEMENT_ROLES
from utils.emoji_helpers import get_emoji_thumbnail_url, add_team_emoji_thumbnail
from database.settings import get_referee_role_id

# Define valid stat categories - Added spikehits
VALID_STATS = ['spikescores', 'spikehits', 'receives', 'illpoints', 'blocks', 'assists']

async def user_has_referee_or_management_permission(user: discord.Member) -> bool:
    """Check if user has referee role or management permissions."""
    # Check management roles first
    if await has_any_role(user, ALLOWED_MANAGEMENT_ROLES):
        return True
    
    # Check referee role
    try:
        referee_role_id = await get_referee_role_id()
        if referee_role_id and referee_role_id != 0:
            referee_role = user.guild.get_role(referee_role_id)
            if referee_role and referee_role in user.roles:
                return True
    except Exception as e:
        print(f"Error checking referee role: {e}")
    
    return False

def calculate_spike_percentage(spikescores: int, spikehits: int) -> str:
    """Calculate spike score percentage."""
    if spikehits == 0:
        return "N/A"
    percentage = (spikescores / spikehits) * 100
    return f"{percentage:.1f}%"

class StatsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Add or remove stats for players (always 1 point)")
    @app_commands.describe(
        action="Choose to add or remove stats",
        player="The player to modify stats for",
        category="The stat category to modify"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove")
    ])
    async def stats_command(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        player: discord.Member,
        category: Literal['spikescores', 'spikehits', 'receives', 'illpoints', 'blocks', 'assists']
    ):
        """Add or remove stats for a player (always 1 point)."""
        try:
            # Check if user has management permissions OR referee role
            if not await user_has_referee_or_management_permission(interaction.user):
                # Get referee role for display
                referee_role_id = await get_referee_role_id()
                referee_role = interaction.guild.get_role(referee_role_id) if referee_role_id else None
                
                allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
                if referee_role:
                    allowed_roles_text += f", {referee_role.name}"
                
                await interaction.response.send_message(
                    f"❌ You need one of these roles to manage stats: {allowed_roles_text}",
                    ephemeral=True
                )
                return

            # Fixed amount is always 1
            amount = 1

            await interaction.response.defer()

            # Get player's team info by checking their roles
            team_emoji = "⚡"
            team_color = discord.Color.green() if action.value == "add" else discord.Color.orange()
            
            # Get all teams from database
            import aiosqlite
            from config import DB_PATH
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT role_id, emoji FROM teams"
                ) as cursor:
                    teams_data = await cursor.fetchall()
            
            # Check which team role the player has
            player_roles = {role.id for role in player.roles}
            for role_id, emoji in teams_data:
                if role_id in player_roles:
                    if emoji:
                        team_emoji = emoji
                    break

            # Get stat emojis
            stat_emojis = {
                'spikescores': '🔥',
                'spikehits': '🏐',
                'receives': '🛡️',
                'illpoints': '💀',
                'blocks': '🚫',
                'assists': '🤝'
            }
            
            stat_emoji = stat_emojis.get(category, '📊')

            # Perform the action
            if action.value == "add":
                await add_stat_to_player(player.id, category, amount)
                
                embed = discord.Embed(
                    title="📊 Stat Added Successfully",
                    description=f"Added {amount} point to {player.mention}",
                    color=team_color
                )
                
                embed.add_field(
                    name="Added Stat",
                    value=f"{stat_emoji} **{category.title()}:** +{amount}",
                    inline=False
                )
                
            else:  # remove
                new_value = await subtract_stat_from_player(player.id, category, amount)
                
                embed = discord.Embed(
                    title="📉 Stat Removed Successfully",
                    description=f"Removed {amount} point from {player.mention}",
                    color=team_color
                )
                
                embed.add_field(
                    name="Removed Stat",
                    value=f"{stat_emoji} **{category.title()}:** -{amount} (now {new_value})",
                    inline=False
                )
            
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            embed.add_field(
                name="Player",
                value=f"{team_emoji} {player.display_name}",
                inline=True
            )
            
            embed.set_footer(text=f"{action.name}d by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in stats command: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while modifying stats.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while modifying stats.",
                    ephemeral=True
                )

    @app_commands.command(name="setstats", description="Set exact stat values for a player (Management only)")
    @app_commands.describe(
        player="Player to set stats for",
        spikescores="Set spike scores to this value",
        spikehits="Set spike hits to this value",
        receives="Set receives to this value", 
        illpoints="Set ill points to this value",
        blocks="Set blocks to this value",
        assists="Set assists to this value"
    )
    async def set_stats(
        self,
        interaction: discord.Interaction,
        player: discord.Member,
        spikescores: Optional[int] = None,
        spikehits: Optional[int] = None,
        receives: Optional[int] = None,
        illpoints: Optional[int] = None,
        blocks: Optional[int] = None,
        assists: Optional[int] = None
    ):
        """Set exact stat values for a player (overwrite, don't add) - Management only."""
        try:
            # Check if user has management permissions (NOT allowing referees for this command)
            if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
                await interaction.response.send_message(
                    f"❌ You need one of these roles to set stats: {allowed_roles_text}",
                    ephemeral=True
                )
                return

            # Check if any stats were provided
            stats_to_set = {
                'spikescores': spikescores,
                'spikehits': spikehits,
                'receives': receives,
                'illpoints': illpoints,
                'blocks': blocks,
                'assists': assists
            }
            
            # Filter out None values
            valid_stats = {k: v for k, v in stats_to_set.items() if v is not None}
            
            if not valid_stats:
                await interaction.response.send_message(
                    "❌ Please provide at least one stat value to set.",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Set stats in database
            set_stats_list = []
            for stat_name, value in valid_stats.items():
                if value < 0:
                    await interaction.followup.send(
                        f"❌ Stat values cannot be negative. {stat_name} was set to {value}.",
                        ephemeral=True
                    )
                    return
                
                await set_player_stat(player.id, stat_name, value)
                set_stats_list.append(f"{stat_name.title()}: {value}")

            # Get player's team info by checking their roles
            team_emoji = "⚡"
            team_color = discord.Color.purple()
            
            # Get all teams from database
            import aiosqlite
            from config import DB_PATH
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT role_id, emoji FROM teams"
                ) as cursor:
                    teams_data = await cursor.fetchall()
            
            # Check which team role the player has
            player_roles = {role.id for role in player.roles}
            for role_id, emoji in teams_data:
                if role_id in player_roles:
                    if emoji:
                        team_emoji = emoji
                    break

            # Create confirmation embed
            embed = discord.Embed(
                title="📝 Stats Set",
                description=f"Stats have been set for {player.mention}",
                color=team_color
            )
            
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            embed.add_field(
                name="Set Stats",
                value="\n".join(set_stats_list),
                inline=False
            )
            
            embed.add_field(
                name="Player",
                value=f"{team_emoji} {player.display_name}",
                inline=True
            )
            
            embed.add_field(
                name="💡 Note",
                value="These values **replace** existing stats, they don't add to them.",
                inline=False
            )
            
            embed.set_footer(text=f"Set by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in set_stats command: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while setting stats.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while setting stats.",
                    ephemeral=True
                )

    @app_commands.command(name="resetstats", description="Reset player stats (Management only)")
    @app_commands.describe(
        target="Choose what to reset",
        player="Specific player to reset (only for 'player' target)",
        category="Specific stat category to reset (leave empty to reset all stats)"
    )
    @app_commands.choices(target=[
        app_commands.Choice(name="Single Player", value="player"),
        app_commands.Choice(name="Everyone", value="everyone")
    ])
    async def reset_stats(
        self,
        interaction: discord.Interaction,
        target: app_commands.Choice[str],
        player: Optional[discord.Member] = None,
        category: Optional[Literal['spikescores', 'spikehits', 'receives', 'illpoints', 'blocks', 'assists']] = None
    ):
        """Reset stats for a player or everyone (Management only)."""
        try:
            # Check if user has management permissions (NOT allowing referees for this command)
            if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
                await interaction.response.send_message(
                    f"❌ You need one of these roles to reset stats: {allowed_roles_text}",
                    ephemeral=True
                )
                return

            # Validate input
            if target.value == 'player' and not player:
                await interaction.response.send_message(
                    "❌ You must specify a player when using target 'Single Player'.",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            if target.value == 'everyone':
                # Reset all stats for everyone - requires confirmation
                if category:
                    # Reset specific category for everyone
                    players_with_stats = await get_players_with_stats()
                    affected_count = 0
                    
                    for user_id in players_with_stats:
                        await remove_player_stat(user_id, category)
                        affected_count += 1
                    
                    embed = discord.Embed(
                        title="🗑️ Global Stats Reset",
                        description=f"Reset **{category.title()}** stats for **{affected_count}** players",
                        color=discord.Color.red()
                    )
                else:
                    # Reset ALL stats for everyone
                    total_removed = await reset_all_stats()
                    
                    embed = discord.Embed(
                        title="🗑️ Complete Stats Reset",
                        description=f"**ALL STATS HAVE BEEN RESET**\n\nRemoved **{total_removed}** stat entries from the database",
                        color=discord.Color.red()
                    )
                    
                    embed.add_field(
                        name="⚠️ Warning",
                        value="This action cannot be undone!",
                        inline=False
                    )

            else:  # target == 'player'
                # Reset stats for specific player
                await remove_player_stat(player.id, category)

                embed = discord.Embed(
                    title="🗑️ Player Stats Reset",
                    color=discord.Color.orange()
                )

                if category:
                    embed.description = f"Reset **{category.title()}** stats for {player.mention}"
                else:
                    embed.description = f"Reset **all stats** for {player.mention}"

            embed.set_footer(text=f"Reset by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()

            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in reset_stats command: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while resetting stats.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while resetting stats.",
                    ephemeral=True
                )

    @app_commands.command(name="statleaderboard", description="View stat leaderboards")
    @app_commands.describe(
        category="Specific stat category to view (leave empty for all categories)"
    )
    async def stat_leaderboard(
        self,
        interaction: discord.Interaction,
        category: Optional[Literal['spikescores', 'spikehits', 'receives', 'illpoints', 'blocks', 'assists']] = None
    ):
        """View stat leaderboards."""
        try:
            await interaction.response.defer()

            if category:
                # Show specific category leaderboard
                leaderboard_data = await get_stat_leaderboard(category, limit=10)
                
                if not leaderboard_data:
                    await interaction.followup.send(
                        f"📊 No stats found for **{category.title()}**.",
                        ephemeral=True
                    )
                    return

                embed = discord.Embed(
                    title=f"🏆 {category.title()} Leaderboard",
                    color=discord.Color.gold()
                )

                # Get all teams data for emoji lookup
                import aiosqlite
                from config import DB_PATH
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        "SELECT role_id, emoji FROM teams"
                    ) as cursor:
                        teams_data = await cursor.fetchall()

                leaderboard_text = ""
                for i, (user_id, stat_value) in enumerate(leaderboard_data, 1):
                    user = interaction.guild.get_member(user_id)
                    if user:
                        # Get player's team emoji by checking their roles
                        player_emoji = "⚡"
                        
                        # Check which team role the player has
                        player_roles = {role.id for role in user.roles}
                        for role_id, emoji in teams_data:
                            if role_id in player_roles:
                                if emoji:
                                    player_emoji = emoji
                                break

                        # Add medal emojis for top 3
                        medal = ""
                        if i == 1:
                            medal = "🥇 "
                        elif i == 2:
                            medal = "🥈 "
                        elif i == 3:
                            medal = "🥉 "
                        else:
                            medal = f"**{i}.** "

                        leaderboard_text += f"{medal}{player_emoji} {user.display_name}: **{stat_value}**\n"
                    else:
                        leaderboard_text += f"**{i}.** Unknown User: **{stat_value}**\n"

                embed.add_field(
                    name=f"Top {len(leaderboard_data)} Players",
                    value=leaderboard_text,
                    inline=False
                )

            else:
                # Show all categories (top 5 each)
                all_leaderboards = await get_stat_leaderboard(limit=5)
                
                if not any(all_leaderboards.values()):
                    await interaction.followup.send(
                        "📊 No stats found in any category.",
                        ephemeral=True
                    )
                    return

                embed = discord.Embed(
                    title="🏆 Stats Leaderboards",
                    description="Top 5 players in each category",
                    color=discord.Color.gold()
                )

                # Get all teams data for emoji lookup
                import aiosqlite
                from config import DB_PATH
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        "SELECT role_id, emoji FROM teams"
                    ) as cursor:
                        teams_data = await cursor.fetchall()

                for stat_name in VALID_STATS:
                    if stat_name in all_leaderboards and all_leaderboards[stat_name]:
                        leaderboard_text = ""
                        for i, (user_id, stat_value) in enumerate(all_leaderboards[stat_name], 1):
                            user = interaction.guild.get_member(user_id)
                            if user:
                                # Get player's team emoji by checking their roles
                                player_emoji = "⚡"
                                
                                # Check which team role the player has
                                player_roles = {role.id for role in user.roles}
                                for role_id, emoji in teams_data:
                                    if role_id in player_roles:
                                        if emoji:
                                            player_emoji = emoji
                                        break

                                if i == 1:
                                    leaderboard_text += f"🥇 {player_emoji} {user.display_name}: **{stat_value}**\n"
                                else:
                                    leaderboard_text += f"**{i}.** {player_emoji} {user.display_name}: {stat_value}\n"
                            else:
                                leaderboard_text += f"**{i}.** Unknown User: {stat_value}\n"
                        
                        embed.add_field(
                            name=f"🏐 {stat_name.title()}",
                            value=leaderboard_text or "No data",
                            inline=True
                        )

            embed.set_footer(text="📊 ORL Player Statistics")
            embed.timestamp = discord.utils.utcnow()
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in stat_leaderboard command: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while fetching leaderboards.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while fetching leaderboards.",
                    ephemeral=True
                )

    @app_commands.command(name="statboard", description="View your personal stats")
    @app_commands.describe(
        player="Player to view stats for (leave empty to view your own stats)"
    )
    async def stat_board(
        self,
        interaction: discord.Interaction,
        player: Optional[discord.Member] = None
    ):
        """View personal stats for a player."""
        try:
            target_player = player or interaction.user
            await interaction.response.defer()

            # Get player stats
            player_stats = await get_player_stats(target_player.id)
            
            if not player_stats:
                pronoun = "You have" if target_player == interaction.user else f"{target_player.display_name} has"
                await interaction.followup.send(
                    f"📊 {pronoun} no recorded stats yet.",
                    ephemeral=True
                )
                return

            # Get player's team info by checking their roles
            team_emoji = "⚡"
            team_color = discord.Color.blue()
            team_name = "No Team"
            
            # Get all teams from database
            import aiosqlite
            from config import DB_PATH
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT team_id, role_id, emoji, name FROM teams"
                ) as cursor:
                    teams_data = await cursor.fetchall()
            
            # Check which team role the player has
            player_roles = {role.id for role in target_player.roles}
            for team_id, role_id, emoji, name in teams_data:
                if role_id in player_roles:
                    # Player has this team role
                    team_emoji = emoji or "⚡"
                    team_name = name or "Unknown Team"
                    team_color = discord.Color.green()
                    break

            # Create stats embed
            embed = discord.Embed(
                title=f"📊 {target_player.display_name}'s Stats",
                description=f"Team: {team_emoji} {team_name}",
                color=team_color
            )
            
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            # Get stats values for percentage calculation
            stats_dict = {stat_name: stat_value for stat_name, stat_value in player_stats}
            
            # Add stats fields
            stats_text = ""
            total_stats = 0
            
            # Organize stats with emojis
            stat_emojis = {
                'spikescores': '🔥',
                'spikehits': '🏐',
                'receives': '🛡️',
                'illpoints': '💀',
                'blocks': '🚫',
                'assists': '🤝'
            }
            
            # Display stats in order
            for stat_name in VALID_STATS:
                if stat_name in stats_dict:
                    stat_value = stats_dict[stat_name]
                    emoji = stat_emojis.get(stat_name, '📊')
                    
                    # Get player's rank in this stat
                    rank = await get_player_rank_in_stat(target_player.id, stat_name)
                    rank_text = f" (#{rank})" if rank else ""
                    
                    stats_text += f"{emoji} **{stat_name.title()}:** {stat_value}{rank_text}\n"
                    total_stats += stat_value

            # Add spike percentage if both scores and hits exist
            if 'spikescores' in stats_dict and 'spikehits' in stats_dict:
                percentage = calculate_spike_percentage(stats_dict['spikescores'], stats_dict['spikehits'])
                stats_text += f"\n📈 **Spike Success Rate:** {percentage}\n"

            embed.add_field(
                name="Player Statistics",
                value=stats_text,
                inline=False
            )
            
            embed.add_field(
                name="📈 Total Stats",
                value=f"**{total_stats}** total stat points",
                inline=True
            )

            # Add some additional info
            if target_player == interaction.user:
                embed.add_field(
                    name="💡 Tip",
                    value="Use `/statleaderboard` to see how you rank against others!",
                    inline=False
                )

            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()
            
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in stat_board command: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while fetching stats.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while fetching stats.",
                    ephemeral=True
                )

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(StatsCommands(bot))
    print("📊 StatsCommands cog setup completed!")