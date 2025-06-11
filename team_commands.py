# Fixed team_commands.py - Added automatic standings integration
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

# Import configuration
from config import DB_PATH, GUILD_ID, ALLOWED_MANAGEMENT_ROLES, TEAM_OWNER_ROLE_NAME

# Import database functions
from database.teams import (
    get_team_by_owner, get_team_by_role, add_team, get_team_by_id,
    update_team_emoji, set_team_owner, remove_team_and_players
)
from database.players import sign_player_to_team, remove_player_from_team
from database.settings import (
    get_sign_log_channel_id, get_required_roles, is_signing_open,
    get_team_member_cap, get_vice_captain_role_id, get_free_agent_role_id,
    get_one_of_required_roles
)
# FIXED: Import standings functions
from database.standings import add_team_to_standings, remove_team_from_standings

# Import utility functions
from utils.permissions import has_any_role, user_is_team_owner, user_has_coach_role_async
from utils.alerts import send_team_owner_alert
from utils.emoji_helpers import get_emoji_thumbnail_url, add_team_emoji_thumbnail

# Import UI components
from ui.views import LeaveTeamView

class TeamCommands(commands.Cog):
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

    # ... [sign and release methods remain the same] ...

    # Fixed sign and unsign methods for team_commands.py

    @app_commands.command(name="sign", description="Sign a user to your team")
    async def sign(self, interaction: discord.Interaction, user: discord.Member):
        try:
            # Defer the interaction immediately with ephemeral=True for invisibility
            await interaction.response.defer(ephemeral=True)
            
            print(f"Sign command called by {interaction.user} for {user}")
            
            # Check if the user is a team owner by role
            if not user_is_team_owner(interaction.user):
                # Check if they're a vice captain
                has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                if not has_coach_role:
                    await interaction.followup.send(
                        "❌ You are not authorized to sign players. Only team owners or vice captains can.",
                        ephemeral=True
                    )
                    return

            # Get team by checking user's actual roles
            team = await self.get_user_team_by_role(interaction.user)
            if not team:
                await interaction.followup.send(
                    "❌ You are not on any team or your team is not registered.",
                    ephemeral=True
                )
                return

            # Ensure signings are open
            signing_open = await is_signing_open()
            if not signing_open:
                await interaction.followup.send(
                    "❌ Signing period is currently closed.",
                    ephemeral=True
                )
                return

            # Check for required roles (configurable)
            required_role_ids = await get_required_roles()
            one_of_required_role_ids = await get_one_of_required_roles()
            
            # Check ALL required roles
            if required_role_ids:
                user_role_ids = [role.id for role in user.roles]
                missing_roles = []
                
                for required_role_id in required_role_ids:
                    if required_role_id not in user_role_ids:
                        required_role = interaction.guild.get_role(required_role_id)
                        if required_role:
                            missing_roles.append(required_role.name)
                        else:
                            missing_roles.append(f"Role ID {required_role_id}")
                
                if missing_roles:
                    roles_text = ", ".join(missing_roles)
                    await interaction.followup.send(
                        f"❌ {user.mention} must have the following required role(s) to be signed: {roles_text}",
                        ephemeral=True
                    )
                    return

            # Check ONE-OF required roles
            if one_of_required_role_ids:
                user_role_ids = [role.id for role in user.roles]
                has_one_of_required = any(role_id in user_role_ids for role_id in one_of_required_role_ids)
                
                if not has_one_of_required:
                    one_of_roles = []
                    for role_id in one_of_required_role_ids:
                        role_obj = interaction.guild.get_role(role_id)
                        if role_obj:
                            one_of_roles.append(role_obj.name)
                        else:
                            one_of_roles.append(f"Role ID {role_id}")
                    
                    roles_text = ", ".join(one_of_roles)
                    await interaction.followup.send(
                        f"❌ {user.mention} must have at least one of the following roles to be signed: {roles_text}",
                        ephemeral=True
                    )
                    return

            # Cannot be blacklisted
            blacklisted_role = discord.utils.get(interaction.guild.roles, name="Blacklisted")
            if blacklisted_role and blacklisted_role in user.roles:
                await interaction.followup.send(
                    f"❌ {user.mention} is blacklisted and cannot be signed.",
                    ephemeral=True
                )
                return

            # Get the team role and check existence
            team_id, role_id, team_emoji, team_name = team
            
            team_role = interaction.guild.get_role(role_id)
            if not team_role:
                await interaction.followup.send(
                    f"❌ Your team's role (ID: {role_id}) could not be found on this server.",
                    ephemeral=True
                )
                return

            # Check if user is already on this team
            if team_role in user.roles:
                await interaction.followup.send(
                    f"❌ {user.mention} is already on your team.",
                    ephemeral=True
                )
                return

            # Check if user is already on ANY team by checking their roles
            user_team = await self.get_user_team_by_role(user)
            if user_team:
                existing_team_role = interaction.guild.get_role(user_team[1])
                if existing_team_role:
                    await interaction.followup.send(
                        f"❌ {user.mention} is already on {existing_team_role.mention}. "
                        "Players must be released before signing to a new team.",
                        ephemeral=True
                    )
                    return

            # Enforce roster cap
            current_members = team_role.members
            cap = await get_team_member_cap()

            if len(current_members) >= cap:
                await interaction.followup.send(
                    f"❌ Cannot sign {user.mention}. Team has reached the cap of {cap} members (including owner).",
                    ephemeral=True
                )
                return

            # FIXED: Sign player in database with proper error handling
            try:
                await sign_player_to_team(user.id, str(user), team_id)
                print(f"✅ Successfully added {user} to database for team {team_id}")
            except Exception as db_error:
                print(f"❌ Database error when signing player: {db_error}")
                await interaction.followup.send(
                    f"❌ Database error occurred while signing {user.mention}. Please try again.",
                    ephemeral=True
                )
                return
            
            # FIXED: Add Discord role with proper error handling
            try:
                await user.add_roles(team_role, reason=f"Signed by {interaction.user}")
                print(f"✅ Successfully added team role {team_role.name} to {user}")
            except discord.Forbidden:
                await interaction.followup.send(
                    f"❌ I don't have permission to add the team role to {user.mention}.",
                    ephemeral=True
                )
                # Rollback database change
                await remove_player_from_team(user.id)
                return
            except discord.HTTPException as e:
                print(f"❌ Discord error when adding role: {e}")
                await interaction.followup.send(
                    f"❌ Discord error occurred while adding role to {user.mention}: {str(e)}",
                    ephemeral=True
                )
                # Rollback database change
                await remove_player_from_team(user.id)
                return

            # Remove free agent role if configured and user has it
            free_agent_role_id = await get_free_agent_role_id()
            if free_agent_role_id:
                free_agent_role = interaction.guild.get_role(free_agent_role_id)
                if free_agent_role and free_agent_role in user.roles:
                    try:
                        await user.remove_roles(free_agent_role, reason="Signed to team - removed free agent status")
                        print(f"✅ Removed free agent role from {user}")
                    except Exception as fa_error:
                        print(f"⚠️ Could not remove free agent role: {fa_error}")
                        # Don't fail the command for this

            # Wait a moment for Discord to update
            await asyncio.sleep(0.5)
            updated_count = len(team_role.members)

            # Get current roster for display
            roster_members = []
            team_owner_id = None
            
            # Get team owner from database
            team_data = await get_team_by_id(team_id)
            if team_data and len(team_data) > 4:
                team_owner_id = team_data[4]
            
            # Separate owner and other members
            for member in team_role.members:
                if member.id == team_owner_id:
                    roster_members.insert(0, f"👑 {member.display_name} (Owner)")
                else:
                    roster_members.append(f"• {member.display_name}")
            
            # Limit roster display to prevent embed overflow
            if len(roster_members) > 10:
                display_roster = roster_members[:10]
                display_roster.append(f"... and {len(roster_members) - 10} more")
            else:
                display_roster = roster_members

            # Create ephemeral response embed for the command user
            response_embed = discord.Embed(
                title="✅ Player Signed Successfully",
                description=(
                    f"{team_emoji or ''} You have successfully signed **{user.display_name}** to {team_role.mention}!\n\n"
                    f"**Player:** {user.mention}\n"
                    f"**Team:** {team_emoji} {team_name}\n"
                    f"**Roster Size:** {updated_count}/{cap}"
                ),
                color=discord.Color.green()
            )
            # Add team emoji thumbnail to response embed
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                response_embed.set_thumbnail(url=thumbnail_url)

            # Send ephemeral response to command user
            await interaction.followup.send(embed=response_embed, ephemeral=True)

            # Create Forced Signing Reversal button for the signed user
            view = LeaveTeamView(team_id, role_id, user.id)

            # Send to log channel with button (this remains public)
            try:
                log_channel_id = await get_sign_log_channel_id()
                if log_channel_id:
                    log_channel = interaction.guild.get_channel(log_channel_id)
                    if log_channel:
                        log_embed = discord.Embed(
                            title="✅ Player Signed",
                            description=(
                                f"{team_emoji or ''} {user.mention} has been signed to {team_role.mention}.\n"
                                f"👤 Signed by: {interaction.user.mention}"
                            ),
                            color=discord.Color.green()
                        )
                        # Add team emoji thumbnail to log embed
                        if thumbnail_url:
                            log_embed.set_thumbnail(url=thumbnail_url)
                        log_embed.set_footer(text=f"Current roster: {updated_count}/{cap}")
                        await log_channel.send(embed=log_embed, view=view)
            except Exception as log_error:
                print(f"Failed to send to log channel: {log_error}")

            # Send DM to signed user with button
            try:
                dm_embed = discord.Embed(
                    title="⚠️ You've been force signed!",
                    description=(
                        f"You have been **force signed** to **{team_name}** {team_emoji or ''} by {interaction.user.mention}.\n\n"
                        f"If this was done without your consent, you can reverse this forced signing within 12 hours using the button below."
                    ),
                    color=discord.Color.orange()
                )
                # Add team emoji thumbnail to DM embed
                if thumbnail_url:
                    dm_embed.set_thumbnail(url=thumbnail_url)
                dm_view = LeaveTeamView(team_id, role_id, user.id)
                await user.send(embed=dm_embed, view=dm_view)
            except discord.Forbidden:
                print(f"Could not send DM to {user} - DMs disabled")
            except Exception as dm_error:
                print(f"Error sending DM: {dm_error}")
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in sign command: {error_details}")
            
            try:
                await interaction.followup.send(
                    f"❌ An error occurred while signing {user.mention}: {str(e)}",
                    ephemeral=True
                )
            except Exception as response_error:
                print(f"Failed to send error response: {response_error}")

    @app_commands.command(name="release", description="Remove a user from your team")
    async def unsign(self, interaction: discord.Interaction, user: discord.Member):
        try:
            # Defer the interaction immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            print(f"Release command called by {interaction.user} for {user}")
            
            # Check if the caller is an owner or vice captain by role
            if not user_is_team_owner(interaction.user):
                has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                if not has_coach_role:
                    await interaction.followup.send(
                        "❌ You are not authorized to release players. Only team owners or vice captains can.",
                        ephemeral=True
                    )
                    return

            # Get team by checking user's actual roles
            team = await self.get_user_team_by_role(interaction.user)
            if not team:
                await interaction.followup.send(
                    "❌ You are not on any team or your team is not registered.",
                    ephemeral=True
                )
                return

            team_id, role_id, team_emoji, team_name = team
            team_role = interaction.guild.get_role(role_id)
            
            if not team_role:
                await interaction.followup.send(
                    "❌ Your team's role could not be found.",
                    ephemeral=True
                )
                return

            # Check if user is actually on this team (by role, not database)
            if team_role not in user.roles:
                await interaction.followup.send(
                    f"❌ {user.mention} is not on your team.",
                    ephemeral=True
                )
                return

            print(f"Releasing {user} from {team_role.name}")

            # FIXED: Remove player from database first with proper error handling
            try:
                await remove_player_from_team(user.id)
                print(f"✅ Removed {user} from database")
            except Exception as db_error:
                print(f"❌ Database error when removing player: {db_error}")
                await interaction.followup.send(
                    f"❌ Database error occurred while releasing {user.mention}. Please try again.",
                    ephemeral=True
                )
                return

            # Collect ALL roles to remove
            roles_to_remove = []
            
            # Always add the team role
            if team_role in user.roles:
                roles_to_remove.append(team_role)
                print(f"Added team role to removal list: {team_role.name}")
            
            # Check for and add vice captain role
            vice_captain_role_id = await get_vice_captain_role_id()
            if vice_captain_role_id and vice_captain_role_id != 0:
                vice_captain_role = interaction.guild.get_role(vice_captain_role_id)
                if vice_captain_role and vice_captain_role in user.roles:
                    roles_to_remove.append(vice_captain_role)
                    print(f"Added vice captain role to removal list: {vice_captain_role.name}")

            # FIXED: Remove all collected roles with proper error handling
            if roles_to_remove:
                try:
                    await user.remove_roles(*roles_to_remove, reason=f"Released by {interaction.user}")
                    print(f"✅ Successfully removed {len(roles_to_remove)} roles from {user}")
                    
                    # Verify roles were actually removed
                    still_has_roles = []
                    for role in roles_to_remove:
                        if role in user.roles:
                            still_has_roles.append(role.name)
                    
                    if still_has_roles:
                        print(f"⚠️ WARNING: User still has roles after removal: {still_has_roles}")
                        # Try to remove them individually
                        for role in roles_to_remove:
                            if role in user.roles:
                                try:
                                    await user.remove_roles(role, reason=f"Retry removal - Released by {interaction.user}")
                                    print(f"✅ Retry successful for role: {role.name}")
                                except Exception as retry_error:
                                    print(f"❌ Retry failed for role {role.name}: {retry_error}")
                            
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"❌ I don't have permission to remove roles from {user.mention}.",
                        ephemeral=True
                    )
                    # Rollback database change
                    try:
                        await sign_player_to_team(user.id, str(user), team_id)
                    except:
                        pass  # If rollback fails, log it but don't error again
                    return
                except discord.HTTPException as e:
                    print(f"❌ Discord error when removing roles: {e}")
                    await interaction.followup.send(
                        f"❌ Discord error while removing roles from {user.mention}: {str(e)}",
                        ephemeral=True
                    )
                    # Rollback database change
                    try:
                        await sign_player_to_team(user.id, str(user), team_id)
                    except:
                        pass
                    return
            else:
                print("⚠️ No roles found to remove")

            # Add free agent role back if configured
            free_agent_role_id = await get_free_agent_role_id()
            if free_agent_role_id and free_agent_role_id != 0:
                free_agent_role = interaction.guild.get_role(free_agent_role_id)
                if free_agent_role:
                    if free_agent_role not in user.roles:
                        try:
                            await user.add_roles(free_agent_role, reason="Released from team - restored free agent status")
                            print(f"✅ Added free agent role back to {user}")
                        except discord.Forbidden:
                            print(f"⚠️ No permission to add free agent role to {user}")
                        except discord.HTTPException as e:
                            print(f"⚠️ Error adding free agent role: {e}")
                    else:
                        print(f"ℹ️ User {user} already has free agent role")
                else:
                    print(f"⚠️ Free agent role (ID: {free_agent_role_id}) not found in guild")

            # Wait for Discord to update
            await asyncio.sleep(0.5)
            
            # Get updated member count
            updated_count = len(team_role.members)
            cap = await get_team_member_cap()

            # Create log embed
            removed_role_names = [role.name for role in roles_to_remove]
            embed = discord.Embed(
                title="🚫 Player Released",
                description=(
                    f"{team_emoji} {user.mention} has been released from {team_role.mention}.\n"
                    f"👤 Released by: {interaction.user.mention}"
                ),
                color=discord.Color.red()
            )
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            if removed_role_names:
                embed.add_field(name="Roles Removed", value=", ".join(removed_role_names), inline=False)
            
            embed.set_footer(text=f"Current roster: {updated_count}/{cap}")

            # Send to log channel
            try:
                log_channel_id = await get_sign_log_channel_id()
                if log_channel_id:
                    log_channel = interaction.guild.get_channel(log_channel_id)
                    if log_channel:
                        await log_channel.send(embed=embed)
            except Exception as log_error:
                print(f"Failed to send to log channel: {log_error}")

            # Send confirmation
            confirmation_text = f"✅ {team_emoji} {user.mention} has been successfully released from {team_role.mention}."
            if removed_role_names:
                confirmation_text += f"\n**Roles removed:** {', '.join(removed_role_names)}"
            
            await interaction.followup.send(confirmation_text, ephemeral=True)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in release command: {error_details}")
            
            try:
                await interaction.followup.send(
                    f"❌ An error occurred while releasing {user.mention}: {str(e)}",
                    ephemeral=True
                )
            except Exception as response_error:
                print(f"Failed to send error response: {response_error}")

    @app_commands.command(name="addteam", description="Add a team to the list")
    async def addteam(self, interaction: discord.Interaction, role: discord.Role, emoji: str):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer()
        
        try:
            # Add to main teams table
            await add_team(role.id, emoji, role.name)
            
            # FIXED: Also add to standings automatically
            async with aiosqlite.connect(DB_PATH) as db:
                # Get the team_id that was just created
                async with db.execute(
                    "SELECT team_id FROM teams WHERE role_id = ?", (role.id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    team_id = result[0] if result else None
            
            # Add to standings with proper alignment
            await add_team_to_standings(role.id, team_id, role.name, emoji)
            
            embed = discord.Embed(
                title="✅ Team Added Successfully",
                description=f"Team {emoji} {role.name} has been added to both the main database and standings system.",
                color=discord.Color.green()
            )
            
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            embed.add_field(
                name="🏆 Standings Integration",
                value="Team has been automatically added to the standings system and is ready for game reporting!",
                inline=False
            )
            
            embed.add_field(
                name="💡 Next Steps",
                value="• Use `/appoint @user @role` to assign a team owner\n• Team is ready for `/gamescore` reporting\n• Use `/standings` to view current rankings",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in addteam command: {e}")
            await interaction.followup.send(
                f"❌ Error adding team: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="disband", description="Remove a team and clean up related roles")
    @app_commands.describe(role="The team role to remove")
    async def removeteam(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)

        try:
            if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
                await interaction.followup.send("❌ You don't have permission to use this command.", ephemeral=True)
                return

            # Get team from DB
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute("SELECT team_id, role_id, name, owner_id FROM teams WHERE role_id = ?", (role.id,))
                team = await cursor.fetchone()

            if not team:
                await interaction.followup.send("❌ Team not found in the database.", ephemeral=True)
                return

            team_id, team_role_id, team_name, team_owner_id = team

            guild = interaction.guild
            team_role = guild.get_role(team_role_id)
            owner_role = discord.utils.get(guild.roles, name=TEAM_OWNER_ROLE_NAME)

            # Get vice captain role from config
            vice_captain_role_id = await get_vice_captain_role_id()
            vice_captain_role = guild.get_role(vice_captain_role_id) if vice_captain_role_id != 0 else None

            # Get free agent role for adding back to members
            free_agent_role_id = await get_free_agent_role_id()
            free_agent_role = guild.get_role(free_agent_role_id) if free_agent_role_id else None

            # Remove roles from team members
            if team_role:
                for member in team_role.members:
                    roles_to_remove = [team_role]

                    if member.id == team_owner_id and owner_role and owner_role in member.roles:
                        roles_to_remove.append(owner_role)

                    # Check for vice captain role
                    async with aiosqlite.connect(DB_PATH) as db:
                        cursor = await db.execute(
                            "SELECT role FROM players WHERE user_id = ? AND team_id = ?",
                            (member.id, team_id)
                        )
                        row = await cursor.fetchone()

                        if row and row[0] == 'vice captain':
                            if vice_captain_role and vice_captain_role in member.roles:
                                roles_to_remove.append(vice_captain_role)

                    try:
                        await member.remove_roles(*roles_to_remove, reason="Team disbanded")
                        
                        # Add free agent role back if configured and member doesn't have it
                        if free_agent_role and free_agent_role not in member.roles:
                            await member.add_roles(free_agent_role, reason="Team disbanded - restored free agent status")
                            
                    except Exception as e:
                        print(f"Error removing roles from {member}: {e}")

            # FIXED: Remove from standings first
            try:
                await remove_team_from_standings(role.id)
                print(f"Removed team {team_name} from standings")
            except Exception as e:
                print(f"Error removing team from standings: {e}")

            # Delete team and all its players from main database
            await remove_team_and_players(team_id)

            # Confirmation embed
            embed = discord.Embed(
                title="🗑️ Team Completely Removed",
                description=f"Team {role.mention} has been completely disbanded and removed from all systems.",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="✅ Cleanup Complete",
                value=(
                    "• Removed from main teams database\n"
                    "• Removed from standings system\n"
                    "• All game history cleared\n"
                    "• Player roles removed\n"
                    "• Free agent status restored"
                ),
                inline=False
            )
            
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: `{e}`", ephemeral=True)
            print(f"Error in removeteam: {e}")

    @app_commands.command(name="editteam", description="Edit a team's emoji")
    async def editteam(self, interaction: discord.Interaction, role: discord.Role, new_emoji: str):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer()
        
        try:
            # Update main teams table
            await update_team_emoji(role.id, new_emoji)
            
            # FIXED: Also update in standings
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE team_standings SET emoji = ? WHERE role_id = ?",
                    (new_emoji, role.id)
                )
                await db.commit()
            
            embed = discord.Embed(
                title="✅ Team Updated Successfully",
                description=f"Team {role.name} emoji updated to {new_emoji} in both main database and standings.",
                color=discord.Color.blue()
            )
            
            # Add new emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(new_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            embed.add_field(
                name="🔄 Systems Updated",
                value="• Main teams database\n• Standings system\n• Live displays will refresh automatically",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in editteam command: {e}")
            await interaction.followup.send(
                f"❌ Error updating team: {str(e)}",
                ephemeral=True
            )

    # ... [rest of the methods remain the same - sign, release, appoint, unappoint] ...

async def setup(bot):
    await bot.add_cog(TeamCommands(bot))