# Complete game_commands.py - Enhanced with game removal functionality
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import aiosqlite

# Import configuration
from config import DB_PATH, GUILD_ID, ALLOWED_MANAGEMENT_ROLES

# Import database functions
from database.teams import get_team_by_role
from database.settings import get_game_results_channel_id
from database.standings import (
    update_team_standing, record_game_result, 
    get_game_result_by_id, remove_game_result, reverse_team_standing_update
)

# Import utility functions
from utils.permissions import has_any_role, user_is_team_owner, user_has_coach_role_async
from utils.emoji_helpers import get_emoji_thumbnail_url

class GameCommands(commands.Cog):
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

    @app_commands.command(name="gamescore", description="Report match results with detailed set scores or forfeits")
    @app_commands.describe(
        team1="First team role",
        team2="Second team role", 
        set1_score="Set 1 score (format: 25-23) or forfeit (ffw/ffl)",
        set2_score="Set 2 score (format: 25-20) or leave empty for forfeit",
        set3_score="Set 3 score (optional, format: 25-22)",
        set4_score="Set 4 score (optional, format: 25-18)",
        set5_score="Set 5 score (optional, format: 15-10)",
        attachment1="Optional: Attach first file (screenshot, score sheet, etc.)",
        attachment2="Optional: Attach second file",
        attachment3="Optional: Attach third file",
        attachment4="Optional: Attach fourth file",
        attachment5="Optional: Attach fifth file"
    )
    async def gamescore(
        self,
        interaction: discord.Interaction,
        team1: discord.Role,
        team2: discord.Role,
        set1_score: str,
        set2_score: str = None,
        set3_score: str = None,
        set4_score: str = None,
        set5_score: str = None,
        attachment1: discord.Attachment = None,
        attachment2: discord.Attachment = None,
        attachment3: discord.Attachment = None,
        attachment4: discord.Attachment = None,
        attachment5: discord.Attachment = None
    ):
        try:
            # Check if user is authorized (team owner, vice captain, or admin)
            is_authorized = False
            
            # Check if admin
            if await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                is_authorized = True
            else:
                # Check if team owner
                if user_is_team_owner(interaction.user):
                    user_team = await self.get_user_team_by_role(interaction.user)
                    if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                        is_authorized = True
                
                # Check if vice captain of either team
                if not is_authorized:
                    has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                    if has_coach_role:
                        user_team = await self.get_user_team_by_role(interaction.user)
                        if user_team and (user_team[1] == team1.id or user_team[1] == team2.id):
                            is_authorized = True
            
            if not is_authorized:
                await interaction.response.send_message(
                    "You are not authorized to report scores. Only team owners, vice captains, or admins can report match results.",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Get team info from database
            team1_data = await get_team_by_role(team1.id)
            team2_data = await get_team_by_role(team2.id)
            
            if not team1_data or not team2_data:
                await interaction.followup.send("One or both teams not found in database.", ephemeral=True)
                return

            team1_emoji = team1_data[2] or "🔥"
            team2_emoji = team2_data[2] or "⚡"

            # Check for forfeit first
            is_forfeit = False
            forfeit_winner = None
            forfeit_type = None
            
            if set1_score.lower() in ['ffw', 'ffl']:
                is_forfeit = True
                forfeit_type = set1_score.lower()
                
                # Determine which team forfeited based on who reported it
                user_team = await self.get_user_team_by_role(interaction.user)
                if user_team:
                    reporting_team_id = user_team[1]
                    
                    if forfeit_type == 'ffw':
                        # Forfeit win - the reporting team wins
                        forfeit_winner = team1.id if reporting_team_id == team1.id else team2.id
                    else:  # ffl
                        # Forfeit loss - the reporting team loses
                        forfeit_winner = team2.id if reporting_team_id == team1.id else team1.id
                else:
                    # If we can't determine the reporting team, default based on team1/team2 order
                    forfeit_winner = team1.id if forfeit_type == 'ffw' else team2.id

            # Initialize variables for standings update
            team1_sets_won = 0
            team2_sets_won = 0
            team1_points = 0
            team2_points = 0
            
            if is_forfeit:
                # Handle forfeit case
                if forfeit_winner == team1.id:
                    team1_sets_won = 3
                    team2_sets_won = 0
                    winner_text = f"{team1_emoji} **{team1.name}** wins by forfeit"
                else:
                    team1_sets_won = 0
                    team2_sets_won = 3
                    winner_text = f"{team2_emoji} **{team2.name}** wins by forfeit"
                
                # Create forfeit embed
                embed = discord.Embed(
                    title="🏐 Match Results - FORFEIT",
                    color=discord.Color.orange()
                )
                # Add winning team's emoji as thumbnail
                winning_emoji = team1_emoji if forfeit_winner == team1.id else team2_emoji
                thumbnail_url = get_emoji_thumbnail_url(winning_emoji)
                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)

                match_header = f"**{team1_emoji} {team1.mention}** vs **{team2.mention} {team2_emoji}**"
                embed.add_field(name="Teams", value=match_header, inline=False)
                embed.add_field(name="Result", value="**FORFEIT**", inline=False)
                embed.add_field(name="Winner", value=winner_text, inline=False)
                
            else:
                # Handle normal scoring
                sets = []
                set_scores = [set1_score, set2_score, set3_score, set4_score, set5_score]
                
                for i, score in enumerate(set_scores):
                    if score is None:
                        continue
                        
                    try:
                        # Parse score format "25-23"
                        parts = score.split('-')
                        if len(parts) != 2:
                            raise ValueError("Invalid format")
                        
                        score1 = int(parts[0])
                        score2 = int(parts[1])
                        
                        # Add to total points
                        team1_points += score1
                        team2_points += score2
                        
                        # Determine set winner
                        if score1 > score2:
                            winner_emoji = team1_emoji
                            team1_sets_won += 1
                        else:
                            winner_emoji = team2_emoji
                            team2_sets_won += 1
                        
                        sets.append({
                            'number': i + 1,
                            'score': f"{score1}-{score2}",
                            'winner_emoji': winner_emoji
                        })
                        
                    except ValueError:
                        await interaction.followup.send(
                            f"Invalid score format for Set {i+1}. Use format like '25-23' or 'ffw'/'ffl' for forfeit.",
                            ephemeral=True
                        )
                        return

                if len(sets) < 2:
                    await interaction.followup.send("At least 2 sets are required for non-forfeit games.", ephemeral=True)
                    return

                # Create normal game embed
                embed = discord.Embed(
                    title="🏐 Match Results",
                    color=discord.Color.gold()
                )

                # Add winning team's emoji as thumbnail
                winning_emoji = team1_emoji if team1_sets_won > team2_sets_won else team2_emoji
                thumbnail_url = get_emoji_thumbnail_url(winning_emoji)
                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)

                # Match header
                match_header = f"**{team1_emoji} {team1.mention}** vs **{team2.mention} {team2_emoji}**"
                embed.add_field(name="Teams", value=match_header, inline=False)

                # Set scores
                set_results = ""
                for set_data in sets:
                    set_results += f"Set {set_data['number']} | {set_data['score']} | {set_data['winner_emoji']}\n"
                
                embed.add_field(name="Set Scores", value=set_results, inline=False)

                # Final score
                final_score = f"**{team1_sets_won}-{team2_sets_won}**"
                if team1_sets_won > team2_sets_won:
                    winner_text = f"{team1_emoji} **{team1.name}** wins {final_score}"
                else:
                    winner_text = f"{team2_emoji} **{team2.name}** wins {final_score}"
                
                embed.add_field(name="Final Score", value=winner_text, inline=False)

            # UPDATE STANDINGS - Use role_id consistently
            try:
                # Determine who won
                team1_won = team1_sets_won > team2_sets_won
                team2_won = team2_sets_won > team1_sets_won
                
                # Update standings for both teams using role_id
                await update_team_standing(
                    team1.id,  # Use role_id directly
                    team1_won, 
                    team1_sets_won, 
                    team2_sets_won,  # team1's sets lost = team2's sets won
                    team1_points,
                    team2_points     # team1's points against = team2's points for
                )
                
                await update_team_standing(
                    team2.id,  # Use role_id directly
                    team2_won, 
                    team2_sets_won, 
                    team1_sets_won,  # team2's sets lost = team1's sets won
                    team2_points,
                    team1_points     # team2's points against = team1's points for
                )
                
                # Record the game result with proper role_ids
                await record_game_result(
                    team1.id, team2.id,  # Use role_ids
                    team1_sets_won, team2_sets_won,
                    team1_points, team2_points,
                    interaction.user.id,
                    interaction.user.display_name,
                    "Reported via /gamescore command"
                )
                
                # Update live standings display if it exists
                try:
                    from cog.standings_commands import StandingsCommands
                    standings_cog = self.bot.get_cog("StandingsCommands")
                    if standings_cog and hasattr(standings_cog, '_update_live_standings'):
                        await standings_cog._update_live_standings(interaction.guild)
                except Exception as standings_update_error:
                    print(f"Error updating live standings display: {standings_update_error}")
                
                print(f"✅ Updated standings: {team1.name} vs {team2.name} - {team1_sets_won}-{team2_sets_won}")
                
            except Exception as e:
                print(f"❌ Error updating standings: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail the entire command if standings update fails
                embed.add_field(
                    name="⚠️ Standings Update Issue",
                    value="Game recorded but there was an issue updating standings. Please notify an administrator.",
                    inline=False
                )

            # Process multiple attachments
            attachments = [attachment1, attachment2, attachment3, attachment4, attachment5]
            valid_attachments = [att for att in attachments if att is not None]
            
            processed_files = []
            attachment_info = []
            
            if valid_attachments:
                max_size = 25 * 1024 * 1024  # 25MB in bytes per file
                allowed_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.txt', '.csv', '.xlsx']
                total_size = 0
                
                for i, attachment in enumerate(valid_attachments):
                    # Check individual file size
                    if attachment.size > max_size:
                        await interaction.followup.send(
                            f"❌ File '{attachment.filename}' is too large. Maximum file size is 25MB per file.",
                            ephemeral=True
                        )
                        return
                    
                    # Check total size (Discord has a total limit of 25MB for all files combined)
                    total_size += attachment.size
                    if total_size > max_size:
                        await interaction.followup.send(
                            f"❌ Total file size exceeds 25MB limit. Please reduce the number or size of files.",
                            ephemeral=True
                        )
                        return
                    
                    # Check file extension
                    file_extension = attachment.filename.lower()
                    if not any(file_extension.endswith(ext) for ext in allowed_extensions):
                        await interaction.followup.send(
                            f"❌ File type not allowed for '{attachment.filename}'. Supported formats: {', '.join(allowed_extensions)}",
                            ephemeral=True
                        )
                        return
                    
                    # Process attachment
                    try:
                        attachment_file = await attachment.to_file()
                        processed_files.append(attachment_file)
                        attachment_info.append(f"📄 {attachment.filename}")
                    except Exception as e:
                        await interaction.followup.send(
                            f"❌ Failed to process attachment '{attachment.filename}': {str(e)}",
                            ephemeral=True
                        )
                        return

            # Add attachment info to embed if any attachments were provided
            if attachment_info:
                if len(attachment_info) == 1:
                    embed.add_field(name="📎 Attachment", value=attachment_info[0], inline=False)
                else:
                    attachments_text = "\n".join(attachment_info)
                    embed.add_field(name=f"📎 Attachments ({len(attachment_info)})", value=attachments_text, inline=False)
            
            # Add standings update notification to embed (only if no error occurred)
            if "Standings Update Issue" not in [field.name for field in embed.fields]:
                embed.add_field(
                    name="🏆 Standings Updated",
                    value="Team standings have been automatically updated with this result!",
                    inline=False
                )
            
            embed.set_footer(text=f"Reported by {interaction.user.display_name}")
            embed.timestamp = datetime.utcnow()

            # Send to game results channel
            results_channel_id = await get_game_results_channel_id()
            if results_channel_id:
                results_channel = interaction.guild.get_channel(results_channel_id)
                if results_channel:
                    try:
                        if processed_files:
                            await results_channel.send(embed=embed, files=processed_files)
                        else:
                            await results_channel.send(embed=embed)
                            
                        file_count_text = f" and {len(processed_files)} file(s)" if processed_files else ""
                        standings_text = "\n🏆 Team standings have been updated automatically!" if "Standings Update Issue" not in [field.name for field in embed.fields] else "\n⚠️ Game recorded but standings update had issues."
                        
                        await interaction.followup.send(
                            f"✅ Match results{file_count_text} posted to {results_channel.mention}!{standings_text}",
                            ephemeral=True
                        )
                    except Exception as e:
                        await interaction.followup.send(
                            f"❌ Failed to post to results channel: {str(e)}",
                            ephemeral=True
                        )
                else:
                    await interaction.followup.send(
                        "❌ Game results channel not found. Please check configuration with /config.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "❌ Game results channel not configured. Use /config to set it up.",
                    ephemeral=True
                )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in gamescore command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while reporting the score: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"An error occurred while reporting the score: {str(e)}",
                    ephemeral=True
                )

    @app_commands.command(name="removegame", description="Remove a previously scored game from standings")
    @app_commands.describe(
        game_id="Game ID from the /recentgames list or game results channel",
        reason="Reason for removing the game (optional)"
    )
    async def removegame(
        self,
        interaction: discord.Interaction,
        game_id: int,
        reason: str = "Game removal requested"
    ):
        """Remove a scored game and reverse its impact on standings."""
        try:
            # Check authorization - only admins and team owners/vice captains involved in the game
            is_authorized = False
            
            # Check if admin
            if await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                is_authorized = True
            else:
                # Get game details to check if user is involved
                game_result = await get_game_result_by_id(game_id)
                if game_result:
                    team1_role_id, team2_role_id = game_result['team1_role_id'], game_result['team2_role_id']
                    
                    # Check if team owner
                    if user_is_team_owner(interaction.user):
                        user_team = await self.get_user_team_by_role(interaction.user)
                        if user_team and (user_team[1] == team1_role_id or user_team[1] == team2_role_id):
                            is_authorized = True
                    
                    # Check if vice captain of either team
                    if not is_authorized:
                        has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                        if has_coach_role:
                            user_team = await self.get_user_team_by_role(interaction.user)
                            if user_team and (user_team[1] == team1_role_id or user_team[1] == team2_role_id):
                                is_authorized = True
            
            if not is_authorized:
                await interaction.response.send_message(
                    "❌ You are not authorized to remove games. Only admins or team owners/vice captains involved in the game can remove it.",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            # Get the game result details
            game_result = await get_game_result_by_id(game_id)
            if not game_result:
                await interaction.followup.send(
                    f"❌ Game with ID {game_id} not found. Use `/recentgames` to see available game IDs.",
                    ephemeral=True
                )
                return

            # Extract game data
            team1_role_id = game_result['team1_role_id']
            team2_role_id = game_result['team2_role_id']
            team1_name = game_result['team1_name']
            team2_name = game_result['team2_name']
            team1_sets = game_result['team1_sets']
            team2_sets = game_result['team2_sets']
            team1_points = game_result['team1_points']
            team2_points = game_result['team2_points']
            match_date = game_result['match_date']
            reported_by_name = game_result['reported_by_name']

            # Get team data for emojis
            team1_data = await get_team_by_role(team1_role_id)
            team2_data = await get_team_by_role(team2_role_id)
            team1_emoji = team1_data[2] if team1_data else "🔥"
            team2_emoji = team2_data[2] if team2_data else "⚡"

            # Reverse the standings impact
            try:
                # Determine who won originally
                team1_won = team1_sets > team2_sets
                team2_won = team2_sets > team1_sets
                
                # Reverse standings for both teams
                await reverse_team_standing_update(
                    team1_role_id,
                    team1_won,
                    team1_sets,
                    team2_sets,
                    team1_points,
                    team2_points
                )
                
                await reverse_team_standing_update(
                    team2_role_id,
                    team2_won,
                    team2_sets,
                    team1_sets,
                    team2_points,
                    team1_points
                )
                
                # Remove the game result from database
                await remove_game_result(game_id)
                
                print(f"✅ Removed game {game_id}: {team1_name} vs {team2_name}")
                
                # Update live standings display if it exists
                try:
                    from cog.standings_commands import StandingsCommands
                    standings_cog = self.bot.get_cog("StandingsCommands")
                    if standings_cog and hasattr(standings_cog, '_update_live_standings'):
                        await standings_cog._update_live_standings(interaction.guild)
                except Exception as standings_update_error:
                    print(f"Error updating live standings display: {standings_update_error}")
                
            except Exception as e:
                print(f"❌ Error reversing standings: {e}")
                await interaction.followup.send(
                    f"❌ Error occurred while reversing standings for game {game_id}: {str(e)}",
                    ephemeral=True
                )
                return

            # Create removal confirmation embed
            embed = discord.Embed(
                title="🗑️ Game Removed from Standings",
                description=f"Game **#{game_id}** has been successfully removed and standings have been updated.",
                color=discord.Color.red()
            )
            
            # Add team emoji thumbnail (winning team)
            winning_emoji = team1_emoji if team1_sets > team2_sets else team2_emoji
            thumbnail_url = get_emoji_thumbnail_url(winning_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            # Game details
            match_header = f"**{team1_emoji} {team1_name}** vs **{team2_name} {team2_emoji}**"
            embed.add_field(name="Teams", value=match_header, inline=False)
            
            # Original result
            original_result = f"**{team1_sets}-{team2_sets}**"
            if team1_sets > team2_sets:
                winner_text = f"{team1_emoji} **{team1_name}** won {original_result}"
            else:
                winner_text = f"{team2_emoji} **{team2_name}** won {original_result}"
            
            embed.add_field(name="Original Result", value=winner_text, inline=False)
            
            # Removal details
            embed.add_field(
                name="🗑️ Removal Details",
                value=(
                    f"**Removed by:** {interaction.user.mention}\n"
                    f"**Reason:** {reason}\n"
                    f"**Original Date:** {match_date[:10] if match_date else 'Unknown'}\n"
                    f"**Originally Reported by:** {reported_by_name or 'Unknown'}"
                ),
                inline=False
            )
            
            embed.add_field(
                name="📊 Standings Impact",
                value="Team standings have been automatically reversed to remove this game's impact.",
                inline=False
            )
            
            embed.set_footer(text=f"Game ID: {game_id} • Removed at")
            embed.timestamp = datetime.utcnow()

            # Send to game results channel
            results_channel_id = await get_game_results_channel_id()
            if results_channel_id:
                results_channel = interaction.guild.get_channel(results_channel_id)
                if results_channel:
                    try:
                        await results_channel.send(embed=embed)
                        await interaction.followup.send(
                            f"✅ Game **#{game_id}** successfully removed from standings!\n"
                            f"📊 Team standings have been automatically updated.\n"
                            f"📋 Removal logged in {results_channel.mention}",
                            ephemeral=True
                        )
                    except Exception as e:
                        await interaction.followup.send(
                            f"✅ Game **#{game_id}** removed from standings, but failed to log to results channel: {str(e)}",
                            ephemeral=True
                        )
                else:
                    await interaction.followup.send(
                        f"✅ Game **#{game_id}** removed from standings!\n"
                        f"⚠️ Results channel not found - removal not logged.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    f"✅ Game **#{game_id}** removed from standings!\n"
                    f"⚠️ No results channel configured - use `/config` to set one up.",
                    ephemeral=True
                )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in removegame command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ An error occurred while removing the game: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ An error occurred while removing the game: {str(e)}",
                    ephemeral=True
                )

    @app_commands.command(name="recentgames", description="View recent game results with game IDs for removal")
    @app_commands.describe(
        limit="Number of recent games to show (max 20)"
    )
    async def recent_games_with_ids(
        self,
        interaction: discord.Interaction,
        limit: int = 10
    ):
        """Show recent game results with their IDs for potential removal."""
        try:
            await interaction.response.defer()
            
            limit = min(limit or 10, 20)  # Cap at 20
            
            # Get recent games with IDs
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("""
                    SELECT id, team1_name, team2_name, team1_sets, team2_sets, 
                           team1_points, team2_points, match_date, reported_by_name
                    FROM game_results
                    ORDER BY match_date DESC
                    LIMIT ?
                """, (limit,)) as cursor:
                    recent_games = await cursor.fetchall()
            
            if not recent_games:
                await interaction.followup.send(
                    "📊 No recent games found. Report some game results with `/gamescore`!",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🎮 Recent Game Results (With IDs)",
                description=f"Last {len(recent_games)} reported games • Use game ID with `/removegame` to remove",
                color=discord.Color.blue()
            )
            
            games_text = ""
            for game in recent_games:
                game_id, team1_name, team2_name, team1_sets, team2_sets, team1_points, team2_points, match_date, reported_by = game
                
                # Determine winner
                if team1_sets > team2_sets:
                    games_text += f"**#{game_id}** • 🏆 **{team1_name}** {team1_sets}-{team2_sets} {team2_name}\n"
                else:
                    games_text += f"**#{game_id}** • 🏆 **{team2_name}** {team2_sets}-{team1_sets} {team1_name}\n"
                
                # Add timestamp if available
                try:
                    game_time = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                    games_text += f"   *<t:{int(game_time.timestamp())}:R>*"
                except:
                    games_text += f"   *Recently*"
                
                if reported_by:
                    games_text += f" • Reported by {reported_by}"
                
                games_text += "\n\n"
            
            embed.add_field(
                name="📋 Match Results",
                value=games_text,
                inline=False
            )
            
            embed.add_field(
                name="🗑️ Game Removal",
                value=(
                    "Use `/removegame game_id:[ID]` to remove a game\n"
                    "Example: `/removegame game_id:15 reason:Incorrect score`\n"
                    "Only team owners, vice captains involved, or admins can remove games"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💡 Tip",
                value="Use `/standings` to see how these games affect team rankings",
                inline=False
            )
            
            embed.set_footer(text="🔄 Results update automatically when games are reported or removed")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in recent_games_with_ids command: {e}")
            await interaction.followup.send(
                f"❌ An error occurred while retrieving recent games: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(GameCommands(bot))