# Complete enhanced standings_commands.py - Shows all teams and syncs with Discord
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
from datetime import datetime
import aiosqlite
import math

# Import configuration
from config import GUILD_ID, ALLOWED_MANAGEMENT_ROLES, DB_PATH

# Import database functions
from database.standings import (
    get_team_standings, get_team_standing, reset_all_standings,
    sync_teams_from_main_table, get_standings_summary, remove_team_from_standings,
    get_all_team_ids_from_standings, cleanup_orphaned_teams, get_recent_games,
    get_head_to_head, get_team_streak, get_team_performance_stats, initialize_database,
    # Game query functions
    get_games_by_team, get_games_by_teams, validate_standings_integrity, fix_standings_integrity,
    # Sync functions
    sync_teams_with_guild_roles
)
from database.settings import (
    get_standings_channel_id, set_standings_channel_id,
    get_active_standings_message, set_standings_message,
    deactivate_standings_message
)

# Import utility functions
from utils.permissions import has_any_role
from utils.emoji_helpers import get_emoji_thumbnail_url

class StandingsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        for command in self.__cog_app_commands__:
            command.guild_ids = [GUILD_ID]

    async def sync_standings_with_teams(self, guild):
        """Sync standings table with teams from main database and Discord roles."""
        try:
            # First sync with main teams table
            await sync_teams_from_main_table()
            
            # Then sync with actual guild roles
            synced, added, removed = await sync_teams_with_guild_roles(guild)
            
            print(f"✅ Standings sync complete: {synced} teams synced, {added} added, {removed} removed")
            return synced, added, removed
            
        except Exception as e:
            print(f"Error syncing standings: {e}")
            return 0, 0, 0

    async def cleanup_invalid_teams(self, guild):
        """Remove teams from standings whose Discord roles no longer exist."""
        try:
            # Get all current Discord role IDs
            valid_role_ids = {role.id for role in guild.roles}
            
            async with aiosqlite.connect(DB_PATH) as db:
                # Get all teams in standings
                async with db.execute("SELECT role_id, name FROM team_standings") as cursor:
                    standings_teams = await cursor.fetchall()
                
                removed_count = 0
                for role_id, team_name in standings_teams:
                    if role_id not in valid_role_ids:
                        # Remove this team from standings
                        await db.execute("DELETE FROM team_standings WHERE role_id = ?", (role_id,))
                        await db.execute("DELETE FROM game_results WHERE team1_role_id = ? OR team2_role_id = ?", (role_id, role_id))
                        removed_count += 1
                        print(f"Removed invalid team: {team_name} (role_id: {role_id})")
                
                await db.commit()
                print(f"Cleanup removed {removed_count} invalid teams")
                return removed_count
                
        except Exception as e:
            print(f"Error in cleanup_invalid_teams: {e}")
            return 0

    @app_commands.command(name="standings", description="View current team standings with enhanced options")
    @app_commands.describe(
        team="Optional: View a specific team's standing",
        sort="How to sort the standings",
        limit="Number of teams to show (default: all)"
    )
    @app_commands.choices(sort=[
        app_commands.Choice(name="Standard (Wins → Set Diff)", value="standard"),
        app_commands.Choice(name="Win Percentage", value="win_percentage"),
        app_commands.Choice(name="Set Differential", value="sets"),
        app_commands.Choice(name="Most Recent Activity", value="recent")
    ])
    async def standings(
        self,
        interaction: discord.Interaction,
        team: Optional[discord.Role] = None,
        sort: Optional[app_commands.Choice[str]] = None,
        limit: Optional[int] = None
    ):
        """Display enhanced team standings with multiple view options."""
        try:
            await interaction.response.defer()

            # Sync standings with current teams before showing
            await self.sync_standings_with_teams(interaction.guild)

            if team:
                # Show detailed individual team standing
                await self._show_individual_team_standing(interaction, team)
            else:
                # Show full standings table
                sort_method = sort.value if sort else "standard"
                await self._show_full_standings(interaction, sort_method, limit)

        except Exception as e:
            print(f"Error in standings command: {e}")
            await self._send_error_response(interaction, "retrieving standings")

    async def _show_individual_team_standing(self, interaction: discord.Interaction, team_role: discord.Role):
        """Show detailed standing for a specific team."""
        # Get team performance data
        performance_data = await get_team_performance_stats(team_role.id)
        
        if not performance_data or not performance_data.get('standing'):
            await interaction.followup.send(
                f"❌ No standings data found for {team_role.mention}.",
                ephemeral=True
            )
            return

        standing = performance_data['standing']
        recent_form = performance_data.get('recent_form', [])
        streak_info = performance_data.get('streak', {})
        
        # Unpack standing data (enhanced schema)
        (role_id, team_id, name, emoji, wins, losses, sets_won, sets_lost, 
         points_for, points_against, games_played, win_percentage, 
         set_differential, last_game_date, last_updated) = standing
        
        team_emoji = emoji or "🏐"
        
        # Create comprehensive embed
        embed = discord.Embed(
            title=f"{team_emoji} {name} - Detailed Statistics",
            color=self._get_team_color(wins, losses)
        )
        
        # Add team emoji thumbnail
        thumbnail_url = get_emoji_thumbnail_url(team_emoji)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        
        # Main record and ranking
        all_standings = await get_team_standings()
        position = next((i + 1 for i, s in enumerate(all_standings) if s[0] == team_role.id), "N/A")
        
        embed.add_field(
            name="🏆 Record & Ranking",
            value=(
                f"**Record:** {wins}-{losses} ({win_percentage:.1f}%)\n"
                f"**Position:** #{position} of {len(all_standings)} teams\n"
                f"**Games Played:** {games_played}"
            ),
            inline=True
        )
        
        # Set statistics
        embed.add_field(
            name="🔥 Set Performance",
            value=(
                f"**Sets:** {sets_won}-{sets_lost}\n"
                f"**Differential:** {set_differential:+d}\n"
                f"**Set Win %:** {(sets_won/(sets_won+sets_lost)*100):.1f}%" if (sets_won+sets_lost) > 0 else "**Set Win %:** 0.0%"
            ),
            inline=True
        )
        
        # Recent form and streak
        form_display = " ".join(recent_form) if recent_form else "No recent games"
        streak_display = f"{streak_info['count']}{streak_info['type']}" if streak_info.get('count', 0) > 0 else "No streak"
        
        embed.add_field(
            name="📈 Recent Form & Streak",
            value=(
                f"**Last 5:** {form_display}\n"
                f"**Current Streak:** {streak_display}\n"
                f"**Form Record:** {performance_data.get('form_record', '0-0')}"
            ),
            inline=True
        )
        
        # Points (if tracked)
        if points_for > 0 or points_against > 0:
            points_differential = points_for - points_against
            embed.add_field(
                name="🎯 Points",
                value=(
                    f"**For:** {points_for}\n"
                    f"**Against:** {points_against}\n"
                    f"**Differential:** {points_differential:+d}"
                ),
                inline=True
            )
        
        # Activity info
        if last_game_date:
            try:
                game_time = datetime.fromisoformat(last_game_date.replace('Z', '+00:00'))
                embed.add_field(
                    name="🕒 Activity",
                    value=f"**Last Game:** <t:{int(game_time.timestamp())}:R>",
                    inline=True
                )
            except:
                pass
        
        embed.add_field(
            name="💡 Quick Actions",
            value="• Use `/teamgames` to see all games for this team\n• Use `/standings` without a team to see full rankings",
            inline=False
        )
        
        embed.set_footer(text="Use /standings without a team to see full standings")
        
        await interaction.followup.send(embed=embed)

    async def _show_full_standings(self, interaction: discord.Interaction, sort_method: str, limit: Optional[int]):
        """Show full standings table with sorting options."""
        standings = await get_team_standings(limit=limit, sort_by=sort_method)
        
        # Don't filter out 0-0 teams anymore!
        # Just filter for valid Discord roles
        current_role_ids = {role.id for role in interaction.guild.roles}
        valid_standings = [s for s in standings if s[0] in current_role_ids]
        
        # Remove invalid teams from database
        invalid_teams = [s for s in standings if s[0] not in current_role_ids]
        if invalid_teams:
            print(f"Found {len(invalid_teams)} invalid teams, cleaning up...")
            for invalid_team in invalid_teams:
                await remove_team_from_standings(invalid_team[0])
            print(f"Cleaned up {len(invalid_teams)} invalid teams")
        
        if not valid_standings:
            embed = discord.Embed(
                title="🏆 Team Standings",
                description="No teams found. Make sure teams are registered first.",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="💡 How to Get Started",
                value=(
                    "• Register teams using `/createteam`\n"
                    "• Report game results using `/gamescore`\n"
                    "• Use `/setupstandings` to create a live standings display"
                ),
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            return

        # Create enhanced standings embed with pagination
        embed = await self._create_enhanced_standings_embed_paginated(valid_standings, interaction.guild, sort_method)
        await interaction.followup.send(embed=embed)

    async def _create_enhanced_standings_embed_paginated(self, standings, guild, sort_method: str):
        """Create a comprehensive standings embed with proper pagination for large lists."""
        # Get summary stats
        summary = await get_standings_summary()
        
        # Sort method descriptions
        sort_descriptions = {
            "standard": "Wins → Set Differential → Sets Won",
            "win_percentage": "Win Percentage → Games Played",
            "sets": "Set Differential → Wins",
            "recent": "Recent Activity → Wins"
        }
        
        embed = discord.Embed(
            title="🏆 Team Standings",
            description=f"**{len(standings)} teams • {summary['total_games']} games played**\n*Sorted by: {sort_descriptions.get(sort_method, 'Standard')}*",
            color=discord.Color.gold()
        )
        
        # Limit display to prevent embed field size issues
        display_limit = 15  # Show max 15 teams to stay under 1024 char limit
        standings_to_show = standings[:display_limit]
        
        # Add standings table
        standings_text = ""
        char_count = 0
        
        for i, standing in enumerate(standings_to_show, 1):
            # Unpack enhanced standing data
            (role_id, team_id, name, emoji, wins, losses, sets_won, sets_lost, 
             points_for, points_against, games_played, win_percentage, 
             set_differential, last_game_date, last_updated) = standing
            
            # Check if emoji is actually an emoji or if it's the team name
            # If emoji field contains text that matches the team name, use default emoji
            if emoji and (emoji == name or not emoji.strip() or len(emoji) > 2):
                team_emoji = "🏐"
            else:
                team_emoji = emoji or "🏐"
            
            # Position emoji
            position_emoji = self._get_position_emoji(i)
            
            # Build display line - FIXED to not duplicate name
            line = f"{position_emoji} {team_emoji} **{name}**"
            
            if sort_method == "win_percentage":
                line += f" - {win_percentage:.1f}%"
                if games_played > 0:
                    line += f" ({wins}-{losses})"
            elif sort_method == "sets":
                line += f" - {set_differential:+d} sets"
                if games_played > 0:
                    line += f" ({sets_won}-{sets_lost})"
            else:  # standard or recent
                line += f" - {wins}-{losses}"
                if games_played > 0:
                    line += f" ({win_percentage:.0f}%)"
            
            line += "\n"
            
            # Check if adding this line would exceed character limit
            if char_count + len(line) > 900:  # Leave some buffer
                standings_text += f"*... and {len(standings) - i + 1} more teams*\n"
                break
            
            standings_text += line
            char_count += len(line)
        
        # If we have more teams than displayed, add a note
        if len(standings) > display_limit:
            if not standings_text.endswith("*... and"):  # If we didn't already add the note
                standings_text += f"\n*... and {len(standings) - display_limit} more teams*"
        
        embed.add_field(
            name="📊 Current Standings",
            value=standings_text,
            inline=False
        )
        
        # Add summary statistics
        if standings:
            # Find the leader among teams that have played games
            leader = None
            for s in standings:
                if s[10] > 0:  # games_played > 0
                    leader = s
                    break
            
            if leader:
                # Check if leader emoji is valid
                leader_emoji = leader[3]
                if leader_emoji and (leader_emoji == leader[2] or not leader_emoji.strip() or len(leader_emoji) > 2):
                    leader_emoji = "🏐"
                else:
                    leader_emoji = leader_emoji or "🏐"
                    
                leader_name = leader[2]
                leader_record = f"{leader[4]}-{leader[5]}"
                
                embed.add_field(
                    name="👑 Current Leader",
                    value=f"{leader_emoji} **{leader_name}** ({leader_record})",
                    inline=True
                )
            
            embed.add_field(
                name="📈 League Stats",
                value=(
                    f"**Total Games:** {summary['total_games']}\n"
                    f"**Avg per Team:** {summary['avg_games_per_team']}\n"
                    f"**Active Teams:** {len(standings)}"
                ),
                inline=True
            )
        
        # Add recent activity
        recent_games = await get_recent_games(3)
        if recent_games:
            recent_text = ""
            for game in recent_games:
                team1_name, team2_name, team1_sets, team2_sets, _, _, match_date, reported_by = game
                try:
                    game_time = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                    time_str = f"<t:{int(game_time.timestamp())}:R>"
                except:
                    time_str = "Recently"
                recent_text += f"• {team1_name} {team1_sets}-{team2_sets} {team2_name} {time_str}\n"
            
            embed.add_field(
                name="🎮 Recent Games",
                value=recent_text,
                inline=False
            )
        
        # Add helpful tips if we have many teams
        if len(standings) > display_limit:
            embed.add_field(
                name="💡 View More",
                value=f"• Use `/standings [team]` for detailed team stats\n• Use `/standings sort:win_percentage limit:25` to see more teams\n• Full list available in live standings display",
                inline=False
            )
        else:
            embed.add_field(
                name="💡 Quick Tips",
                value="• Use `/standings [team]` for detailed team stats\n• Use `/teamgames [team]` to see all games for a team\n• Use `/removegame` to remove incorrect games",
                inline=False
            )
        
        embed.set_footer(text="🔄 Last updated")
        embed.timestamp = discord.utils.utcnow()
        
        return embed

    @app_commands.command(name="teamgames", description="View all games for a specific team")
    @app_commands.describe(
        team="Team to view games for",
        limit="Number of games to show (default: 10, max: 25)"
    )
    async def team_games(
        self,
        interaction: discord.Interaction,
        team: discord.Role,
        limit: Optional[int] = 10
    ):
        """Show all games for a specific team with game IDs."""
        try:
            await interaction.response.defer()
            
            limit = min(limit or 10, 25)  # Cap at 25
            
            # Get team games
            games = await get_games_by_team(team.id, limit)
            
            if not games:
                await interaction.followup.send(
                    f"📊 No games found for {team.mention}. They haven't played any recorded games yet!",
                    ephemeral=True
                )
                return
            
            # Get team standing info
            team_standing = await get_team_standing(team.id)
            team_emoji = team_standing[3] if team_standing else "🏐"
            team_name = team_standing[2] if team_standing else team.name
            
            # Check if emoji is valid
            if team_emoji and (team_emoji == team_name or not team_emoji.strip() or len(team_emoji) > 2):
                team_emoji = "🏐"
            
            embed = discord.Embed(
                title=f"🎮 {team_emoji} {team_name} - Game History",
                description=f"Last {len(games)} games • Use game ID with `/removegame` to remove",
                color=discord.Color.blue()
            )
            
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            games_text = ""
            wins = 0
            losses = 0
            
            for game in games:
                game_id = game['id']
                team1_name = game['team1_name']
                team2_name = game['team2_name']
                team1_sets = game['team1_sets']
                team2_sets = game['team2_sets']
                winner_role_id = game['winner_role_id']
                match_date = game['match_date']
                reported_by = game['reported_by_name']
                
                # Determine if this team won
                team_won = (winner_role_id == team.id)
                if team_won:
                    wins += 1
                    result_emoji = "🏆"
                else:
                    losses += 1
                    result_emoji = "❌"
                
                # Format the game line
                if game['team1_role_id'] == team.id:
                    # This team was team1
                    opponent = team2_name
                    score = f"{team1_sets}-{team2_sets}"
                else:
                    # This team was team2
                    opponent = team1_name
                    score = f"{team2_sets}-{team1_sets}"
                
                games_text += f"**#{game_id}** {result_emoji} vs {opponent} **{score}**\n"
                
                # Add timestamp
                try:
                    game_time = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                    games_text += f"   *<t:{int(game_time.timestamp())}:d>*"
                except:
                    games_text += f"   *Recently*"
                
                if reported_by:
                    games_text += f" • by {reported_by}"
                
                games_text += "\n\n"
            
            embed.add_field(
                name=f"📋 Game History ({wins}W-{losses}L)",
                value=games_text,
                inline=False
            )
            
            # Add current standing info
            if team_standing:
                total_wins = team_standing[4]
                total_losses = team_standing[5]
                win_percentage = team_standing[11]
                set_differential = team_standing[12]
                
                embed.add_field(
                    name="📊 Current Standing",
                    value=(
                        f"**Record:** {total_wins}-{total_losses} ({win_percentage:.1f}%)\n"
                        f"**Set Diff:** {set_differential:+d}"
                    ),
                    inline=True
                )
            
            embed.add_field(
                name="🗑️ Game Management",
                value=(
                    "Use `/removegame game_id:[ID]` to remove a game\n"
                    "Only team owners, vice captains, or admins can remove games"
                ),
                inline=True
            )
            
            embed.set_footer(text="🔄 Game history updates automatically")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in team_games command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while retrieving team games: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="h2h", description="Head-to-head comparison between two teams")
    @app_commands.describe(
        team1="First team to compare",
        team2="Second team to compare"
    )
    async def head_to_head(
        self,
        interaction: discord.Interaction,
        team1: discord.Role,
        team2: discord.Role
    ):
        """Show head-to-head record between two teams."""
        try:
            await interaction.response.defer()
            
            # Get head-to-head data
            h2h_data = await get_head_to_head(team1.id, team2.id)
            team1_standing = await get_team_standing(team1.id)
            team2_standing = await get_team_standing(team2.id)
            
            if not team1_standing or not team2_standing:
                await interaction.followup.send(
                    "❌ One or both teams not found in standings database.",
                    ephemeral=True
                )
                return
            
            # Get team info
            team1_emoji = team1_standing[3] or "🏐"
            team2_emoji = team2_standing[3] or "🏐"
            team1_name = team1_standing[2]
            team2_name = team2_standing[2]
            
            # Validate emojis
            if team1_emoji and (team1_emoji == team1_name or not team1_emoji.strip() or len(team1_emoji) > 2):
                team1_emoji = "🏐"
            if team2_emoji and (team2_emoji == team2_name or not team2_emoji.strip() or len(team2_emoji) > 2):
                team2_emoji = "🏐"
            
            embed = discord.Embed(
                title=f"⚔️ Head-to-Head Comparison",
                description=f"{team1_emoji} **{team1_name}** vs **{team2_name}** {team2_emoji}",
                color=discord.Color.purple()
            )
            
            # Overall record comparison
            team1_record = f"{team1_standing[4]}-{team1_standing[5]}"
            team2_record = f"{team2_standing[4]}-{team2_standing[5]}"
            
            embed.add_field(
                name="📊 Overall Records",
                value=(
                    f"{team1_emoji} **{team1_name}:** {team1_record} ({team1_standing[11]:.1f}%)\n"
                    f"{team2_emoji} **{team2_name}:** {team2_record} ({team2_standing[11]:.1f}%)"
                ),
                inline=False
            )
            
            # Head-to-head record
            total_h2h = h2h_data['total_games']
            if total_h2h > 0:
                embed.add_field(
                    name="⚔️ Head-to-Head Record",
                    value=(
                        f"{team1_emoji} **{team1_name}:** {h2h_data['team1_wins']} wins\n"
                        f"{team2_emoji} **{team2_name}:** {h2h_data['team2_wins']} wins\n"
                        f"**Total Games:** {total_h2h}"
                    ),
                    inline=True
                )
                
                # Recent matchups
                if h2h_data['recent_games']:
                    recent_text = ""
                    for game in h2h_data['recent_games'][:3]:
                        winner_id, team1_sets, team2_sets, match_date = game
                        if winner_id == team1.id:
                            recent_text += f"🏆 {team1_emoji} {team1_sets}-{team2_sets}\n"
                        else:
                            recent_text += f"🏆 {team2_emoji} {team2_sets}-{team1_sets}\n"
                    
                    embed.add_field(
                        name="🎮 Recent Matchups",
                        value=recent_text,
                        inline=True
                    )
            else:
                embed.add_field(
                    name="⚔️ Head-to-Head Record",
                    value="No games played between these teams yet!",
                    inline=False
                )
            
            # Set differential comparison
            embed.add_field(
                name="🔥 Set Differentials",
                value=(
                    f"{team1_emoji} **{team1_name}:** {team1_standing[12]:+d}\n"
                    f"{team2_emoji} **{team2_name}:** {team2_standing[12]:+d}"
                ),
                inline=True
            )
            
            embed.set_footer(text="Use /teamgames [team] for detailed individual game histories")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in head_to_head command: {e}")
            await self._send_error_response(interaction, "retrieving head-to-head data")

    @app_commands.command(name="validatestandings", description="Check standings integrity and accuracy")
    async def validate_standings(
        self,
        interaction: discord.Interaction
    ):
        """Validate that standings match actual game results AND Discord roles."""
        try:
            # Check permissions
            if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
                await interaction.response.send_message(
                    f"❌ You need one of these roles to validate standings: {allowed_roles_text}",
                    ephemeral=True
                )
                return

            await interaction.response.defer()
            
            # Run integrity check WITH GUILD to check Discord roles
            integrity_report = await validate_standings_integrity(interaction.guild)
            
            if 'error' in integrity_report:
                await interaction.followup.send(
                    f"❌ Error during validation: {integrity_report['error']}",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🔍 Standings Integrity Validation",
                description="Checking standings against game results AND Discord roles...",
                color=discord.Color.blue()
            )
            
            # Validation summary
            teams_checked = integrity_report['teams_checked']
            discrepancies_found = integrity_report['discrepancies_found']
            missing_from_standings = integrity_report.get('missing_from_standings', [])
            orphaned_in_standings = integrity_report.get('orphaned_in_standings', [])
            
            total_issues = discrepancies_found + len(missing_from_standings) + len(orphaned_in_standings)
            
            if total_issues == 0:
                embed.color = discord.Color.green()
                embed.add_field(
                    name="✅ Validation Results",
                    value=(
                        f"**Teams Checked:** {teams_checked}\n"
                        f"**Issues Found:** 0\n"
                        f"**Status:** All standings are accurate and synced!"
                    ),
                    inline=False
                )
            else:
                embed.color = discord.Color.orange()
                embed.add_field(
                    name="⚠️ Validation Results",
                    value=(
                        f"**Teams Checked:** {teams_checked}\n"
                        f"**Game Discrepancies:** {discrepancies_found}\n"
                        f"**Missing from Standings:** {len(missing_from_standings)}\n"
                        f"**Orphaned Teams:** {len(orphaned_in_standings)}\n"
                        f"**Total Issues:** {total_issues}"
                    ),
                    inline=False
                )
                
                # Show missing teams
                if missing_from_standings:
                    missing_text = ""
                    for team in missing_from_standings[:5]:
                        missing_text += f"• {team['emoji']} {team['team_name']} (Role ID: {team['role_id']})\n"
                    
                    if len(missing_from_standings) > 5:
                        missing_text += f"*... and {len(missing_from_standings) - 5} more teams*"
                    
                    embed.add_field(
                        name="🆕 Teams Missing from Standings",
                        value=missing_text,
                        inline=False
                    )
                
                # Show orphaned teams
                if orphaned_in_standings:
                    orphaned_text = ""
                    for team in orphaned_in_standings[:5]:
                        orphaned_text += f"• {team['team_name']} (Role deleted - ID: {team['role_id']})\n"
                    
                    if len(orphaned_in_standings) > 5:
                        orphaned_text += f"*... and {len(orphaned_in_standings) - 5} more teams*"
                    
                    embed.add_field(
                        name="🗑️ Teams with Deleted Roles",
                        value=orphaned_text,
                        inline=False
                    )
                
                # Show game discrepancies
                if integrity_report['issues']:
                    issues_text = ""
                    for issue in integrity_report['issues'][:3]:
                        team_name = issue['team_name']
                        recorded = issue['recorded']
                        actual = issue['actual']
                        
                        issues_text += f"**{team_name}:**\n"
                        issues_text += f"  Recorded: {recorded['wins']}-{recorded['losses']} ({recorded['sets_won']}-{recorded['sets_lost']} sets)\n"
                        issues_text += f"  Actual: {actual['wins']}-{actual['losses']} ({actual['sets_won']}-{actual['sets_lost']} sets)\n\n"
                    
                    if len(integrity_report['issues']) > 3:
                        issues_text += f"*... and {len(integrity_report['issues']) - 3} more issues*"
                    
                    embed.add_field(
                        name="🚨 Game Result Discrepancies",
                        value=issues_text,
                        inline=False
                    )
                
                embed.add_field(
                    name="🔧 Fix Options",
                    value="Use `/fixstandings` to automatically correct ALL these issues",
                    inline=False
                )
            
            embed.set_footer(text="💡 Run this validation regularly to ensure data accuracy")
            embed.timestamp = discord.utils.utcnow()
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in validate_standings command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred during validation: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="fixstandings", description="Fix standings discrepancies and sync with Discord roles")
    async def fix_standings(
        self,
        interaction: discord.Interaction
    ):
        """Fix standings discrepancies by recalculating from game results AND syncing with Discord."""
        try:
            # Check permissions
            if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
                await interaction.response.send_message(
                    f"❌ You need one of these roles to fix standings: {allowed_roles_text}",
                    ephemeral=True
                )
                return

            await interaction.response.defer()
            
            # First validate to show what needs fixing
            integrity_report = await validate_standings_integrity(interaction.guild)
            
            total_issues = (integrity_report.get('discrepancies_found', 0) + 
                          len(integrity_report.get('missing_from_standings', [])) + 
                          len(integrity_report.get('orphaned_in_standings', [])))
            
            if total_issues == 0:
                await interaction.followup.send(
                    "✅ No issues found! Standings are already accurate and synced.",
                    ephemeral=True
                )
                return
            
            # Apply fixes WITH GUILD to sync roles
            fix_report = await fix_standings_integrity(interaction.guild)
            
            if 'error' in fix_report:
                await interaction.followup.send(
                    f"❌ Error during fix: {fix_report['error']}",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🔧 Standings Integrity Fix",
                description="Fixed standings discrepancies and synced with Discord roles",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="✅ Fix Results",
                value=(
                    f"**Teams Checked:** {fix_report['teams_checked']}\n"
                    f"**Teams Fixed:** {fix_report['teams_fixed']}\n"
                    f"**Teams Added:** {fix_report.get('teams_added', 0)}\n"
                    f"**Teams Removed:** {fix_report.get('teams_removed', 0)}\n"
                    f"**Status:** All standings corrected and synced!"
                ),
                inline=False
            )
            
            # Show some examples of fixes applied
            if fix_report['fixes_applied']:
                fixes_text = ""
                for fix in fix_report['fixes_applied'][:3]:
                    team_name = fix['team_name']
                    stats = fix['corrected_stats']
                    
                    fixes_text += f"**{team_name}:**\n"
                    fixes_text += f"  Record: {stats['wins']}-{stats['losses']} ({stats['win_percentage']}%)\n"
                    fixes_text += f"  Sets: {stats['sets_won']}-{stats['sets_lost']}\n\n"
                
                if len(fix_report['fixes_applied']) > 3:
                    fixes_text += f"*... and {len(fix_report['fixes_applied']) - 3} more teams fixed*"
                
                embed.add_field(
                    name="📊 Example Corrections",
                    value=fixes_text,
                    inline=False
                )
            
            # Update live standings if active
            try:
                await self._update_live_standings(interaction.guild)
                embed.add_field(
                    name="🔄 Live Updates",
                    value="Live standings display has been updated with corrected data",
                    inline=False
                )
            except Exception as update_error:
                print(f"Error updating live standings after fix: {update_error}")
            
            embed.set_footer(text=f"Fixed by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in fix_standings command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred during fix: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="setupstandings", description="Setup live standings display in a channel")
    @app_commands.describe(
        channel="Channel where the live standings will be displayed"
    )
    async def setup_standings(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Setup a live standings display in the specified channel."""
        try:
            # Check permissions
            if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
                await interaction.response.send_message(
                    f"❌ You need one of these roles to setup standings: {allowed_roles_text}",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Check bot permissions
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.send_messages or not permissions.embed_links:
                await interaction.followup.send(
                    f"❌ I don't have permission to send messages or embed links in {channel.mention}.",
                    ephemeral=True
                )
                return

            # Initialize database and sync teams
            await initialize_database()
            
            # Sync all teams with Discord roles
            synced, added, removed = await self.sync_standings_with_teams(interaction.guild)
            
            # Clean up invalid teams
            cleanup_count = await self.cleanup_invalid_teams(interaction.guild)

            # Handle existing standings message
            existing_message_info = await get_active_standings_message()
            if existing_message_info:
                message_id, existing_channel_id = existing_message_info
                existing_channel = interaction.guild.get_channel(existing_channel_id)
                
                if existing_channel:
                    try:
                        old_message = await existing_channel.fetch_message(message_id)
                        await old_message.delete()
                    except:
                        pass
                
                await deactivate_standings_message()

            # Get current standings (ALL teams including 0-0)
            standings = await get_team_standings()
            
            # Filter for valid teams only
            current_role_ids = {role.id for role in interaction.guild.roles}
            valid_standings = [s for s in standings if s[0] in current_role_ids]
            
            # Create and send the standings embed
            embed = await self._create_enhanced_standings_embed_paginated(valid_standings, interaction.guild, "standard")
            
            # Post the standings message
            standings_message = await channel.send(embed=embed)
            
            # Store the message info
            await set_standings_message(standings_message.id, channel.id)
            await set_standings_channel_id(channel.id)
            
            # Success message
            success_embed = discord.Embed(
                title="✅ Enhanced Live Standings Setup Complete",
                description=f"Live team standings have been set up in {channel.mention}!",
                color=discord.Color.green()
            )
            
            success_embed.add_field(
                name="🎯 Enhanced Features",
                value=(
                    "• **All Teams Shown** - Including 0-0 records\n"
                    "• **Automatic Updates** - Updates when games are reported/removed\n"
                    "• **Role Sync** - Automatically syncs with Discord team roles\n"
                    "• **Win-Loss Records** - Full game history tracking\n"
                    "• **Set Differentials** - Detailed set statistics\n"
                    "• **Smart Filtering** - Only shows teams with valid Discord roles"
                ),
                inline=False
            )
            
            success_embed.add_field(
                name="🔄 Sync Status",
                value=(
                    f"**Teams Synced:** {synced}\n"
                    f"**Teams Added:** {added}\n"
                    f"**Invalid Removed:** {removed + cleanup_count}"
                ),
                inline=True
            )

            success_embed.add_field(
                name="📊 Current Status",
                value=f"Displaying {len(valid_standings)} active teams",
                inline=True
            )
            
            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except Exception as e:
            print(f"Error in setup_standings command: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ An error occurred while setting up standings: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="resetstandings", description="Reset all team standings (Management only)")
    async def reset_standings(
        self,
        interaction: discord.Interaction
    ):
        """Reset all team standings."""
        try:
            # Check permissions
            if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
                await interaction.response.send_message(
                    f"❌ You need one of these roles to reset standings: {allowed_roles_text}",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Reset standings
            await reset_all_standings()
            
            # Reinitialize for existing teams
            await sync_teams_from_main_table()
            
            # Sync with guild roles
            await self.sync_standings_with_teams(interaction.guild)
            
            # Update live standings if active
            await self._update_live_standings(interaction.guild)
            
            embed = discord.Embed(
                title="🔄 Complete Standings Reset",
                description="All team standings have been reset to 0-0.",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name="✅ Reset Complete",
                value=(
                    "• All wins and losses cleared\n"
                    "• Set records reset to 0-0\n"
                    "• Points and percentages cleared\n"
                    "• Game history archived\n"
                    "• All teams synced with Discord roles"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🎮 Next Steps",
                value="Report new game results with `/gamescore` to start building new standings",
                inline=False
            )
            
            embed.set_footer(text=f"Reset by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()
            
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in reset_standings command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while resetting standings: {str(e)}",
                ephemeral=True
            )

    # Helper methods
    def _get_team_color(self, wins: int, losses: int) -> discord.Color:
        """Get color based on team performance."""
        if wins == 0 and losses == 0:
            return discord.Color.light_grey()
        elif wins > losses:
            return discord.Color.green()
        elif losses > wins:
            return discord.Color.red()
        else:
            return discord.Color.orange()

    def _get_position_emoji(self, position: int) -> str:
        """Get appropriate emoji for position."""
        if position == 1:
            return "🥇"
        elif position == 2:
            return "🥈"
        elif position == 3:
            return "🥉"
        elif position <= 5:
            return "🏅"
        else:
            return f"**{position}.**"

    async def _update_live_standings(self, guild):
        """Update the live standings message if it exists."""
        try:
            message_info = await get_active_standings_message()
            if not message_info:
                return
            
            message_id, channel_id = message_info
            channel = guild.get_channel(channel_id)
            
            if not channel:
                await deactivate_standings_message()
                return
            
            try:
                message = await channel.fetch_message(message_id)
                
                # Sync standings before updating
                await self.sync_standings_with_teams(guild)
                
                standings = await get_team_standings()
                # Filter for valid teams only
                current_role_ids = {role.id for role in guild.roles}
                valid_standings = [s for s in standings if s[0] in current_role_ids]
                
                embed = await self._create_enhanced_standings_embed_paginated(valid_standings, guild, "standard")
                await message.edit(embed=embed)
                
            except discord.NotFound:
                await deactivate_standings_message()
            except discord.Forbidden:
                print(f"No permission to update standings message in {channel.name}")
            except Exception as e:
                print(f"Error updating live standings: {e}")
                
        except Exception as e:
            print(f"Error in _update_live_standings: {e}")

    async def _send_error_response(self, interaction: discord.Interaction, action: str):
        """Send a standardized error response."""
        error_message = f"❌ An error occurred while {action}."
        
        if not interaction.response.is_done():
            await interaction.response.send_message(error_message, ephemeral=True)
        else:
            await interaction.followup.send(error_message, ephemeral=True)

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(StandingsCommands(bot))
    print("🏆 Enhanced StandingsCommands cog setup completed!")