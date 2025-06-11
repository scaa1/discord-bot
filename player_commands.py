import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import re
from datetime import datetime, timedelta

# Import configuration
from config import DB_PATH, GUILD_ID, ALLOWED_MANAGEMENT_ROLES, ALLOWED_RESET_ROLES, TEAM_OWNER_ROLE_NAME

# Import database functions
from database.teams import get_team_by_role, get_team_by_owner
from database.players import (
    get_player, remove_player_from_team, add_blacklist, is_user_blacklisted
)
from database.settings import (
    get_sign_log_channel_id, get_demand_log_channel_id, get_blacklist_log_channel_id,
    get_team_member_cap, get_vice_captain_role_id, get_free_agent_role_id,
    get_max_demands_allowed, get_required_roles, get_one_of_required_roles
)

# Import utility functions
from utils.permissions import has_any_role, user_is_team_owner, user_has_coach_role_async
from utils.emoji_helpers import get_emoji_thumbnail_url

class PlayerCommands(commands.Cog):
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

    async def get_all_config_roles(self, guild: discord.Guild):
        """Get all configured roles from settings."""
        roles_info = {}
        
        try:
            # Team owner role
            owner_role = discord.utils.get(guild.roles, name=TEAM_OWNER_ROLE_NAME)
            if owner_role:
                roles_info['team_owner'] = {
                    'role': owner_role,
                    'name': 'Team Owner',
                    'emoji': '👑'
                }
            
            # Vice captain role
            vice_captain_role_id = await get_vice_captain_role_id()
            if vice_captain_role_id and vice_captain_role_id != 0:
                vice_captain_role = guild.get_role(vice_captain_role_id)
                if vice_captain_role:
                    roles_info['vice_captain'] = {
                        'role': vice_captain_role,
                        'name': 'Vice Captain',
                        'emoji': '⚔️'
                    }
            
            # Free agent role
            free_agent_role_id = await get_free_agent_role_id()
            if free_agent_role_id and free_agent_role_id != 0:
                free_agent_role = guild.get_role(free_agent_role_id)
                if free_agent_role:
                    roles_info['free_agent'] = {
                        'role': free_agent_role,
                        'name': 'Free Agent',
                        'emoji': '🆓'
                    }
            
            # Required roles
            required_role_ids = await get_required_roles()
            for i, role_id in enumerate(required_role_ids):
                required_role = guild.get_role(role_id)
                if required_role:
                    roles_info[f'required_{i}'] = {
                        'role': required_role,
                        'name': f'Required: {required_role.name}',
                        'emoji': '🔒'
                    }
            
            # Blacklisted role
            blacklisted_role = discord.utils.get(guild.roles, name="Blacklisted")
            if blacklisted_role:
                roles_info['blacklisted'] = {
                    'role': blacklisted_role,
                    'name': 'Blacklisted',
                    'emoji': '🚫'
                }
            
        except Exception as e:
            print(f"Error getting config roles: {e}")
        
        return roles_info

    async def get_member_role_status(self, member: discord.Member, config_roles: dict):
        """Get comprehensive role status for a member."""
        status = {
            'team_roles': [],
            'config_roles': [],
            'is_team_owner': False,
            'is_vice_captain': False,
            'is_free_agent': False,
            'is_blacklisted': False,
            'has_required_roles': True,
            'missing_required_roles': []
        }
        
        # Check team membership
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT team_id, role_id, emoji, name FROM teams") as cursor:
                teams = await cursor.fetchall()
        
        for team_id, role_id, emoji, name in teams:
            team_role = member.guild.get_role(role_id)
            if team_role and team_role in member.roles:
                status['team_roles'].append({
                    'team_id': team_id,
                    'role': team_role,
                    'emoji': emoji,
                    'name': name
                })
        
        # Check config roles
        for role_key, role_info in config_roles.items():
            if role_info['role'] in member.roles:
                status['config_roles'].append({
                    'key': role_key,
                    'info': role_info
                })
                
                # Set specific flags
                if role_key == 'team_owner':
                    status['is_team_owner'] = True
                elif role_key == 'vice_captain':
                    status['is_vice_captain'] = True
                elif role_key == 'free_agent':
                    status['is_free_agent'] = True
                elif role_key == 'blacklisted':
                    status['is_blacklisted'] = True
        
        # Check required roles
        required_role_ids = await get_required_roles()
        if required_role_ids:
            user_role_ids = [role.id for role in member.roles]
            for role_id in required_role_ids:
                if role_id not in user_role_ids:
                    required_role = member.guild.get_role(role_id)
                    if required_role:
                        status['missing_required_roles'].append(required_role)
                        status['has_required_roles'] = False
        
        return status

    async def auto_sync_member_role(self, member: discord.Member, team_id: int):
        """Automatically sync a single member's role with the database."""
        try:
            # Get vice captain role from config
            vice_captain_role_id = await get_vice_captain_role_id()
            if not vice_captain_role_id or vice_captain_role_id == 0:
                return  # No vice captain role configured
            
            vice_captain_role = member.guild.get_role(vice_captain_role_id)
            if not vice_captain_role:
                return  # Vice captain role not found
            
            # Determine what their role should be based on Discord roles
            target_role = "player"  # Default
            if vice_captain_role in member.roles:
                target_role = "vice captain"
            
            # Update database
            async with aiosqlite.connect(DB_PATH) as db:
                # Ensure player exists in database
                await db.execute(
                    "INSERT OR IGNORE INTO players (user_id, username, team_id, role) VALUES (?, ?, ?, ?)",
                    (member.id, str(member), team_id, target_role)
                )
                # Update their role
                await db.execute(
                    "UPDATE players SET role = ? WHERE user_id = ? AND team_id = ?",
                    (target_role, member.id, team_id)
                )
                await db.commit()
            
            print(f"Auto-synced {member.display_name} to role '{target_role}' in team {team_id}")
            
        except Exception as e:
            print(f"Error in auto_sync_member_role: {e}")

    async def comprehensive_role_removal(self, user: discord.Member, reason: str = "Role cleanup"):
        """Comprehensively remove all team-related roles from a user."""
        try:
            print(f"Starting comprehensive role removal for user: {user.display_name}")
            
            # Collect all roles to remove
            roles_to_remove = []
            removed_count = 0
            
            # 1. Remove team roles and track which team they were on
            user_team_info = None
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT team_id, role_id, emoji, name FROM teams") as cursor:
                    teams = await cursor.fetchall()
                    
                    for team_id, role_id, emoji, name in teams:
                        team_role = user.guild.get_role(role_id)
                        if team_role and team_role in user.roles:
                            roles_to_remove.append(team_role)
                            user_team_info = (team_id, role_id, emoji, name)
                            removed_count += 1
                            print(f"Will remove team role: {team_role.name}")
                            
                            # Remove from database too
                            await remove_player_from_team(user.id)
                            print(f"Removed {user.display_name} from team database")
                            break
            
            # 2. Remove team owner role
            owner_role = discord.utils.get(user.guild.roles, name=TEAM_OWNER_ROLE_NAME)
            if owner_role and owner_role in user.roles:
                roles_to_remove.append(owner_role)
                removed_count += 1
                print(f"Will remove team owner role: {owner_role.name}")
                
                # Handle team ownership transfer if they were a team owner
                if user_team_info:
                    team_id, role_id, emoji, name = user_team_info
                    async with aiosqlite.connect(DB_PATH) as db:
                        # Check if they were the owner of the team they were on
                        async with db.execute(
                            "SELECT owner_id FROM teams WHERE team_id = ?", (team_id,)
                        ) as cursor:
                            result = await cursor.fetchone()
                            if result and result[0] == user.id:
                                # Remove ownership from database
                                await db.execute("UPDATE teams SET owner_id = NULL WHERE team_id = ?", (team_id,))
                                await db.commit()
                                print(f"Removed team ownership of {name} from {user.display_name}")
            
            # 3. Remove vice captain role
            vice_captain_role_id = await get_vice_captain_role_id()
            if vice_captain_role_id and vice_captain_role_id != 0:
                vice_captain_role = user.guild.get_role(vice_captain_role_id)
                if vice_captain_role and vice_captain_role in user.roles:
                    roles_to_remove.append(vice_captain_role)
                    removed_count += 1
                    print(f"Will remove vice captain role: {vice_captain_role.name}")
            
            # 4. Remove all required signing roles
            required_role_ids = await get_required_roles()
            for role_id in required_role_ids:
                required_role = user.guild.get_role(role_id)
                if required_role and required_role in user.roles:
                    roles_to_remove.append(required_role)
                    removed_count += 1
                    print(f"Will remove required role: {required_role.name}")
            
            # 5. Remove free agent role (they shouldn't be available for signing)
            free_agent_role_id = await get_free_agent_role_id()
            if free_agent_role_id and free_agent_role_id != 0:
                free_agent_role = user.guild.get_role(free_agent_role_id)
                if free_agent_role and free_agent_role in user.roles:
                    roles_to_remove.append(free_agent_role)
                    removed_count += 1
                    print(f"Will remove free agent role: {free_agent_role.name}")
            
            # Remove all collected roles
            if roles_to_remove:
                try:
                    await user.remove_roles(*roles_to_remove, reason=reason)
                    print(f"Successfully removed {len(roles_to_remove)} roles from {user.display_name}")
                    return True
                except discord.Forbidden:
                    print(f"No permission to remove roles from {user.display_name}")
                    return False
                except Exception as role_error:
                    print(f"Error removing roles: {role_error}")
                    return False
            else:
                print(f"No team-related roles to remove from {user.display_name}")
                return True
                
        except Exception as e:
            print(f"Error in comprehensive_role_removal: {e}")
            return False

    @app_commands.command(name="appoint", description="Appoint a user as team owner")
    @app_commands.describe(
        user="User to appoint as team owner",
        team_role="The team role to assign ownership of"
    )
    async def appoint(self, interaction: discord.Interaction, user: discord.Member, team_role: discord.Role):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=False)

            # Check if the role is actually a team role
            team_data = await get_team_by_role(team_role.id)
            if not team_data:
                await interaction.followup.send(
                    f"❌ {team_role.mention} is not a registered team role.",
                    ephemeral=False
                )
                return

            team_id, role_id, emoji, name, current_owner_id = team_data

            # Check if user is blacklisted
            if await is_user_blacklisted(user.id):
                await interaction.followup.send(
                    f"❌ {user.mention} is blacklisted and cannot be appointed as team owner.",
                    ephemeral=False
                )
                return

            # Check if team already has an owner
            if current_owner_id:
                current_owner = interaction.guild.get_member(current_owner_id)
                if current_owner:
                    await interaction.followup.send(
                        f"❌ {emoji} **{name}** already has an owner: {current_owner.mention}\n"
                        f"Use `/unappoint` first to remove the current owner.",
                        ephemeral=False
                    )
                    return

            # Get the team owner role
            owner_role = discord.utils.get(interaction.guild.roles, name=TEAM_OWNER_ROLE_NAME)
            if not owner_role:
                await interaction.followup.send(
                    f"❌ Team Owner role '{TEAM_OWNER_ROLE_NAME}' not found. Please create it first.",
                    ephemeral=False
                )
                return

            # Check if user is already a team owner by checking their Discord roles
            if owner_role and owner_role in user.roles:
                # Find which team they own by checking their team roles
                user_current_team = await self.get_user_team_by_role(user)
                if user_current_team:
                    existing_team_emoji = user_current_team[2] or "🔥"
                    existing_team_name = user_current_team[3] or "Unknown Team"
                    await interaction.followup.send(
                        f"❌ {user.mention} is already a team owner of {existing_team_emoji} **{existing_team_name}**.\n"
                        f"A user can only own one team at a time. Use `/unappoint` first to remove their current ownership.",
                        ephemeral=False
                    )
                    return
                else:
                    # They have owner role but no team role - probably a leftover role
                    await interaction.followup.send(
                        f"❌ {user.mention} has the Team Owner role but is not on any team. Please contact an admin to fix their roles.",
                        ephemeral=False
                    )
                    return

            roles_to_add = []
            role_changes = []

            # Add team owner role if they don't have it
            if owner_role not in user.roles:
                roles_to_add.append(owner_role)
                role_changes.append(f"Added {owner_role.name}")

            # Add team role if they don't have it
            if team_role not in user.roles:
                roles_to_add.append(team_role)
                role_changes.append(f"Added {team_role.name}")

            # Remove free agent role if they have it
            free_agent_role_id = await get_free_agent_role_id()
            if free_agent_role_id and free_agent_role_id != 0:
                free_agent_role = interaction.guild.get_role(free_agent_role_id)
                if free_agent_role and free_agent_role in user.roles:
                    await user.remove_roles(free_agent_role, reason=f"Appointed as team owner by {interaction.user}")
                    role_changes.append(f"Removed {free_agent_role.name}")

            # Remove vice captain role if they have it
            vice_captain_role_id = await get_vice_captain_role_id()
            if vice_captain_role_id and vice_captain_role_id != 0:
                vice_captain_role = interaction.guild.get_role(vice_captain_role_id)
                if vice_captain_role and vice_captain_role in user.roles:
                    await user.remove_roles(vice_captain_role, reason=f"Appointed as team owner by {interaction.user}")
                    role_changes.append(f"Removed {vice_captain_role.name}")

            # Add all roles at once
            if roles_to_add:
                try:
                    await user.add_roles(*roles_to_add, reason=f"Appointed as team owner by {interaction.user}")
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ I don't have permission to assign roles to this user.",
                        ephemeral=False
                    )
                    return
                except Exception as role_error:
                    await interaction.followup.send(
                        f"❌ Error assigning roles: {role_error}",
                        ephemeral=False
                    )
                    return

            # Update database - set team owner and add/update player record
            async with aiosqlite.connect(DB_PATH) as db:
                # Set team owner
                await db.execute(
                    "UPDATE teams SET owner_id = ? WHERE team_id = ?",
                    (user.id, team_id)
                )
                
                # Add or update player record
                await db.execute(
                    "INSERT OR IGNORE INTO players (user_id, username, team_id, role) VALUES (?, ?, ?, ?)",
                    (user.id, str(user), team_id, "owner")
                )
                await db.execute(
                    "UPDATE players SET team_id = ?, role = ? WHERE user_id = ?",
                    (team_id, "owner", user.id)
                )
                
                await db.commit()

            # Create success embed
            embed = discord.Embed(
                title="👑 Team Owner Appointed",
                description=f"{user.mention} has been appointed as the owner of {emoji} **{name}**!",
                color=discord.Color.gold()
            )

            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            embed.add_field(name="👤 New Owner", value=user.mention, inline=True)
            embed.add_field(name="🏐 Team", value=f"{emoji} {name}", inline=True)
            embed.add_field(name="⚖️ Appointed By", value=interaction.user.mention, inline=True)

            if role_changes:
                embed.add_field(
                    name="🔄 Role Changes",
                    value="\n".join([f"• {change}" for change in role_changes]),
                    inline=False
                )

            embed.set_footer(text=f"Team ID: {team_id}")
            embed.timestamp = discord.utils.utcnow()

            await interaction.followup.send(embed=embed)

            # Send DM to new owner
            try:
                dm_embed = discord.Embed(
                    title="👑 You've been appointed as Team Owner!",
                    description=f"You have been appointed as the owner of **{emoji} {name}** in {interaction.guild.name}.",
                    color=discord.Color.gold()
                )
                
                dm_embed.add_field(name="🏐 Team", value=f"{emoji} {name}", inline=True)
                dm_embed.add_field(name="⚖️ Appointed By", value=str(interaction.user), inline=True)
                
                if role_changes:
                    dm_embed.add_field(
                        name="🔄 Role Changes",
                        value="\n".join([f"• {change}" for change in role_changes]),
                        inline=False
                    )
                
                dm_embed.add_field(
                    name="🎯 Your Responsibilities",
                    value="• Manage your team roster\n• Promote/demote team members\n• Represent your team in league activities",
                    inline=False
                )
                
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                print(f"Could not send appointment DM to {user} - DMs disabled")
            except Exception as dm_error:
                print(f"Error sending appointment DM: {dm_error}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in appoint command: {error_details}")
            await interaction.followup.send(f"❌ Error appointing team owner: {e}", ephemeral=False)

    @app_commands.command(name="unappoint", description="Remove a user as team owner")
    @app_commands.describe(
        user="User to remove as team owner (optional - can specify team instead)",
        team_role="Team role to remove ownership from (optional - can specify user instead)"
    )
    async def unappoint(self, interaction: discord.Interaction, user: discord.Member = None, team_role: discord.Role = None):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Must specify either user or team_role
            if not user and not team_role:
                await interaction.followup.send(
                    "❌ You must specify either a user or a team role to unappoint.",
                    ephemeral=True
                )
                return

            target_team = None
            target_user = user

            # If team_role specified, find the owner
            if team_role:
                team_data = await get_team_by_role(team_role.id)
                if not team_data:
                    await interaction.followup.send(
                        f"❌ {team_role.mention} is not a registered team role.",
                        ephemeral=True
                    )
                    return
                
                target_team = team_data
                team_id, role_id, emoji, name, owner_id = team_data
                
                if not owner_id:
                    await interaction.followup.send(
                        f"❌ {emoji} **{name}** doesn't have an owner to remove.",
                        ephemeral=True
                    )
                    return
                
                target_user = interaction.guild.get_member(owner_id)
                if not target_user:
                    # Owner left server, just clean up database
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE teams SET owner_id = NULL WHERE team_id = ?", (team_id,))
                        await db.commit()
                    
                    await interaction.followup.send(
                        f"✅ Cleaned up ownership of {emoji} **{name}** (former owner left server).",
                        ephemeral=True
                    )
                    return

            # If user specified, find their team by checking their roles
            if user and not target_team:
                # Check if user has team owner role
                owner_role = discord.utils.get(interaction.guild.roles, name=TEAM_OWNER_ROLE_NAME)
                if not owner_role or owner_role not in user.roles:
                    await interaction.followup.send(
                        f"❌ {user.mention} is not a team owner (does not have Team Owner role).",
                        ephemeral=True
                    )
                    return
                
                # Find their team by checking their team roles
                user_current_team = await self.get_user_team_by_role(user)
                if not user_current_team:
                    await interaction.followup.send(
                        f"❌ {user.mention} has the Team Owner role but is not on any team. Please contact an admin to fix their roles.",
                        ephemeral=True
                    )
                    return
                
                # Get full team data from database for the team they're on
                target_team = await get_team_by_role(user_current_team[1])  # Use role_id
                if not target_team:
                    await interaction.followup.send(
                        f"❌ Could not find team data for {user.mention}'s team.",
                        ephemeral=True
                    )
                    return

            team_id, role_id, emoji, name, owner_id = target_team
            team_role_obj = interaction.guild.get_role(role_id)

            # Get team owner role
            owner_role = discord.utils.get(interaction.guild.roles, name=TEAM_OWNER_ROLE_NAME)

            roles_to_remove = []
            role_changes = []

            # Remove team owner role
            if owner_role and owner_role in target_user.roles:
                roles_to_remove.append(owner_role)
                role_changes.append(f"Removed {owner_role.name}")

            # Remove vice captain role if they have it
            vice_captain_role_id = await get_vice_captain_role_id()
            if vice_captain_role_id and vice_captain_role_id != 0:
                vice_captain_role = interaction.guild.get_role(vice_captain_role_id)
                if vice_captain_role and vice_captain_role in target_user.roles:
                    roles_to_remove.append(vice_captain_role)
                    role_changes.append(f"Removed {vice_captain_role.name}")

            # Note: We don't remove the team role - they can stay on the team as a regular player

            # Remove roles
            if roles_to_remove:
                try:
                    await target_user.remove_roles(*roles_to_remove, reason=f"Unappointed as team owner by {interaction.user}")
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ I don't have permission to remove roles from this user.",
                        ephemeral=True
                    )
                    return
                except Exception as role_error:
                    print(f"Error removing roles during unappoint: {role_error}")

            # Update database
            async with aiosqlite.connect(DB_PATH) as db:
                # Remove team ownership
                await db.execute("UPDATE teams SET owner_id = NULL WHERE team_id = ?", (team_id,))
                
                # Update player role to regular player (don't remove from team)
                await db.execute(
                    "UPDATE players SET role = 'player' WHERE user_id = ? AND team_id = ?",
                    (target_user.id, team_id)
                )
                
                await db.commit()

            # Create success embed
            embed = discord.Embed(
                title="📉 Team Owner Unappointed",
                description=f"{target_user.mention} is no longer the owner of {emoji} **{name}**.",
                color=discord.Color.orange()
            )

            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            embed.add_field(name="👤 Former Owner", value=target_user.mention, inline=True)
            embed.add_field(name="🏐 Team", value=f"{emoji} {name}", inline=True)
            embed.add_field(name="⚖️ Unappointed By", value=interaction.user.mention, inline=True)

            if role_changes:
                embed.add_field(
                    name="🔄 Role Changes",
                    value="\n".join([f"• {change}" for change in role_changes]),
                    inline=False
                )

            embed.add_field(
                name="📋 Status",
                value=f"Team {emoji} **{name}** now needs a new owner. Use `/appoint` to assign a new owner.",
                inline=False
            )

            embed.set_footer(text=f"Team ID: {team_id}")
            embed.timestamp = discord.utils.utcnow()

            await interaction.followup.send(embed=embed)

            # Send team owner alert
            from utils.alerts import send_team_owner_alert
            await send_team_owner_alert(
                interaction.client,
                target_team,
                "Unappointed",
                f"Unappointed by {interaction.user.display_name}"
            )

            # Send DM to former owner
            try:
                dm_embed = discord.Embed(
                    title="📉 You are no longer a Team Owner",
                    description=f"You have been removed as owner of **{emoji} {name}** in {interaction.guild.name}.",
                    color=discord.Color.orange()
                )
                
                dm_embed.add_field(name="🏐 Former Team", value=f"{emoji} {name}", inline=True)
                dm_embed.add_field(name="⚖️ Unappointed By", value=str(interaction.user), inline=True)
                
                if role_changes:
                    dm_embed.add_field(
                        name="🔄 Role Changes",
                        value="\n".join([f"• {change}" for change in role_changes]),
                        inline=False
                    )
                
                dm_embed.add_field(
                    name="ℹ️ What this means",
                    value="You remain on the team as a regular player, but no longer have owner privileges.",
                    inline=False
                )
                
                await target_user.send(embed=dm_embed)
            except discord.Forbidden:
                print(f"Could not send unappoint DM to {target_user} - DMs disabled")
            except Exception as dm_error:
                print(f"Error sending unappoint DM: {dm_error}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in unappoint command: {error_details}")
            await interaction.followup.send(f"❌ Error unappointing team owner: {e}", ephemeral=True)

    @app_commands.command(name="promote", description="Promote a player on your team to Assistant")
    @app_commands.describe(user="User to promote to vice captain")
    async def promote(self, interaction: discord.Interaction, user: discord.Member):
        try:
            if not user_is_team_owner(interaction.user):
                await interaction.response.send_message("You are not a team owner.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            team = await self.get_user_team_by_role(interaction.user)
            if not team:
                await interaction.followup.send("You are not on any registered team.", ephemeral=True)
                return

            team_id, role_id, team_emoji, team_name = team
            team_role = interaction.guild.get_role(role_id)
            
            if not team_role:
                await interaction.followup.send("Your team role could not be found.", ephemeral=True)
                return

            # Check if user is on your team (by Discord role, not database)
            if team_role not in user.roles:
                await interaction.followup.send(f"{user.mention} is not on your team.", ephemeral=True)
                return

            # Get the vice captain role ID from config
            vice_captain_role_id = await get_vice_captain_role_id()
            
            if not vice_captain_role_id or vice_captain_role_id == 0:
                await interaction.followup.send(
                    f"The Vice Captain role is not configured. Please ask an admin to set it up using `/config`.",
                    ephemeral=True
                )
                return

            role_to_assign = interaction.guild.get_role(vice_captain_role_id)
            if not role_to_assign:
                await interaction.followup.send(
                    f"The Vice Captain role (ID: {vice_captain_role_id}) does not exist on this server.",
                    ephemeral=True
                )
                return

            # Check if user already has the vice captain role
            if role_to_assign in user.roles:
                await interaction.followup.send(f"{user.mention} already has the **{role_to_assign.name}** role.", ephemeral=True)
                return

            # Check if team already has someone with the vice captain role
            team_members_with_vc_role = []
            for member in team_role.members:
                if role_to_assign in member.roles:
                    team_members_with_vc_role.append(member)

            if team_members_with_vc_role:
                existing_vcs = ", ".join([member.display_name for member in team_members_with_vc_role])
                await interaction.followup.send(
                    f"Your team already has a **{role_to_assign.name}**: {existing_vcs}.\n"
                    f"You must demote them first before promoting someone else to this role.",
                    ephemeral=True
                )
                return

            # Assign the Discord role first
            await user.add_roles(role_to_assign, reason=f"Promoted by {interaction.user}")

            # Auto-sync will handle database update
            await self.auto_sync_member_role(user, team_id)

            await interaction.followup.send(
                embed=discord.Embed(
                    title="📈 Player Promoted",
                    description=f"{user.mention} has been promoted to **{role_to_assign.name}**.",
                    color=discord.Color.gold()
                )
            )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in promote command: {error_details}")
            
            await interaction.followup.send(
                f"An error occurred while promoting {user.mention}: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="demote", description="Demote a vice captain on your team to a player")
    @app_commands.describe(user="The user to demote")
    async def demote(self, interaction: discord.Interaction, user: discord.Member):
        if not user_is_team_owner(interaction.user):
            await interaction.response.send_message("You are not a team owner.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        team = await self.get_user_team_by_role(interaction.user)
        if not team:
            await interaction.followup.send("You are not on any registered team.", ephemeral=True)
            return

        team_id, role_id, team_emoji, team_name = team
        team_role = interaction.guild.get_role(role_id)
        
        if not team_role:
            await interaction.followup.send("Your team role could not be found.", ephemeral=True)
            return

        if team_role not in user.roles:
            await interaction.followup.send(f"{user.mention} is not on your team.", ephemeral=True)
            return

        removed_roles = []
        vice_captain_role_id = await get_vice_captain_role_id()
        if vice_captain_role_id and vice_captain_role_id != 0:
            role = interaction.guild.get_role(vice_captain_role_id)
            if role and role in user.roles:
                await user.remove_roles(role, reason=f"Demoted by {interaction.user}")
                removed_roles.append(role.name)

        # Auto-sync will handle database update
        await self.auto_sync_member_role(user, team_id)

        if removed_roles:
            role_list = ", ".join(removed_roles)
            desc = f"{user.mention} has been demoted to `player` and removed from: **{role_list}**."
        else:
            desc = f"{user.mention} has been demoted to `player`."

        embed = discord.Embed(
            title="📉 Player Demoted",
            description=desc,
            color=discord.Color.red()
        )
        # Add team emoji thumbnail
        thumbnail_url = get_emoji_thumbnail_url(team_emoji)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="sync_all_roles", description="Comprehensive role sync for all config roles (admin only)")
    @app_commands.describe(
        team_role="Optional: Sync only this team's roles",
        member="Optional: Sync only this member's roles"
    )
    async def sync_all_roles(self, interaction: discord.Interaction, team_role: discord.Role = None, member: discord.Member = None):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            config_roles = await self.get_all_config_roles(interaction.guild)
            
            if not config_roles:
                await interaction.followup.send("❌ No config roles found to sync.", ephemeral=True)
                return
            
            teams_to_sync = []
            
            if team_role:
                # Sync specific team
                team_data = await get_team_by_role(team_role.id)
                if not team_data:
                    await interaction.followup.send("❌ Team not found in database.", ephemeral=True)
                    return
                teams_to_sync.append((team_data, team_role))
            else:
                # Sync all teams
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute("SELECT team_id, role_id, emoji, name, owner_id FROM teams") as cursor:
                        all_teams = await cursor.fetchall()
                
                for team_data in all_teams:
                    team_role_obj = interaction.guild.get_role(team_data[1])
                    if team_role_obj:
                        teams_to_sync.append((team_data, team_role_obj))
            
            synced_teams = 0
            total_updates = 0
            
            for team_data, team_role_obj in teams_to_sync:
                team_id, role_id, emoji, name, owner_id = team_data
                
                # Get all team members
                team_members = team_role_obj.members
                
                # If specific member provided, only sync that member
                if member and member not in team_members:
                    continue
                
                members_to_sync = [member] if member else team_members
                
                for team_member in members_to_sync:
                    member_status = await self.get_member_role_status(team_member, config_roles)
                    
                    # Determine database role
                    target_role = "player"  # Default
                    
                    # Check if they should be owner (Discord role + team ownership)
                    if member_status['is_team_owner'] and team_member.id == owner_id:
                        target_role = "owner"
                    elif member_status['is_vice_captain']:
                        target_role = "vice captain"
                    
                    # Get current role from database
                    async with aiosqlite.connect(DB_PATH) as db:
                        async with db.execute(
                            "SELECT role FROM players WHERE user_id = ? AND team_id = ?",
                            (team_member.id, team_id)
                        ) as cursor:
                            db_result = await cursor.fetchone()
                    
                    current_db_role = db_result[0] if db_result else "player"
                    
                    # Update if different
                    if current_db_role != target_role:
                        async with aiosqlite.connect(DB_PATH) as db:
                            # Ensure player exists in database
                            await db.execute(
                                "INSERT OR IGNORE INTO players (user_id, username, team_id, role) VALUES (?, ?, ?, ?)",
                                (team_member.id, str(team_member), team_id, target_role)
                            )
                            # Update their role
                            await db.execute(
                                "UPDATE players SET role = ? WHERE user_id = ? AND team_id = ?",
                                (target_role, team_member.id, team_id)
                            )
                            await db.commit()
                        
                        total_updates += 1
                        print(f"Updated {team_member.display_name} from '{current_db_role}' to '{target_role}' in {name}")
                
                synced_teams += 1
            
            embed = discord.Embed(
                title="✅ Comprehensive Role Sync Complete",
                description=f"Synced {synced_teams} team(s) with {total_updates} role updates.",
                color=discord.Color.green()
            )
            
            if total_updates > 0:
                embed.add_field(
                    name="Changes Made",
                    value=f"Updated {total_updates} player roles to match Discord roles.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Result",
                    value="All roles were already in sync!",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error syncing roles: {e}", ephemeral=True)

    @app_commands.command(name="check_member_roles", description="Check a member's comprehensive role status")
    @app_commands.describe(member="Member to check (leave empty to check yourself)")
    async def check_member_roles(self, interaction: discord.Interaction, member: discord.Member = None):
        try:
            await interaction.response.defer(ephemeral=True)
            
            target_member = member if member else interaction.user
            config_roles = await self.get_all_config_roles(interaction.guild)
            member_status = await self.get_member_role_status(target_member, config_roles)
            
            embed = discord.Embed(
                title=f"🔍 Role Status: {target_member.display_name}",
                color=discord.Color.blue()
            )
            
            embed.set_thumbnail(url=target_member.display_avatar.url if target_member.display_avatar else None)
            
            # Team roles
            if member_status['team_roles']:
                team_info = []
                for team_info_dict in member_status['team_roles']:
                    team_info.append(f"{team_info_dict['emoji']} {team_info_dict['name']}")
                embed.add_field(
                    name="🏐 Team Membership",
                    value="\n".join(team_info),
                    inline=False
                )
            else:
                embed.add_field(
                    name="🏐 Team Membership",
                    value="*Not on any team*",
                    inline=False
                )
            
            # Config roles
            if member_status['config_roles']:
                config_info = []
                for config_role in member_status['config_roles']:
                    role_info = config_role['info']
                    config_info.append(f"{role_info['emoji']} {role_info['name']}")
                embed.add_field(
                    name="⚙️ Config Roles",
                    value="\n".join(config_info),
                    inline=True
                )
            else:
                embed.add_field(
                    name="⚙️ Config Roles",
                    value="*None*",
                    inline=True
                )
            
            # Status flags
            status_flags = []
            if member_status['is_team_owner']:
                status_flags.append("👑 Team Owner")
            if member_status['is_vice_captain']:
                status_flags.append("⚔️ Vice Captain")
            if member_status['is_free_agent']:
                status_flags.append("🆓 Free Agent")
            if member_status['is_blacklisted']:
                status_flags.append("🚫 Blacklisted")
            
            embed.add_field(
                name="🏷️ Status",
                value="\n".join(status_flags) if status_flags else "*No special status*",
                inline=True
            )
            
            # Required roles check
            if member_status['has_required_roles']:
                embed.add_field(
                    name="✅ Required Roles",
                    value="Has all required roles",
                    inline=False
                )
            else:
                missing_roles = [role.name for role in member_status['missing_required_roles']]
                embed.add_field(
                    name="❌ Missing Required Roles",
                    value=", ".join(missing_roles),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error checking member roles: {e}", ephemeral=True)

    @app_commands.command(name="demand", description="Leave your current team using a demand.")
    async def demand(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        user = interaction.user
        
        # Check if user has any team role
        user_team = await self.get_user_team_by_role(user)
        if not user_team:
            await interaction.followup.send("You are not on any team.", ephemeral=True)
            return

        # Get player from database to check demands used
        player = await get_player(user.id)
        demands_used = 0
        
        # Get demands_used directly from database to ensure accuracy
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT demands_used FROM players WHERE user_id = ?", (user.id,))
            result = await cursor.fetchone()
            if result:
                demands_used = result[0] if result[0] is not None else 0
            else:
                # If player doesn't exist in DB, create entry
                await db.execute("INSERT INTO players (user_id, demands_used) VALUES (?, 0)", (user.id,))
                await db.commit()
                demands_used = 0

        max_demands = await get_max_demands_allowed()

        if demands_used >= max_demands:
            await interaction.followup.send(f"You have already used your maximum allowed demands ({demands_used}/{max_demands}).", ephemeral=True)
            return

        team_id, role_id, team_emoji, team_name = user_team
        team_role = interaction.guild.get_role(role_id)

        # Remove from DB and increment demand count
        await remove_player_from_team(user.id)
        
        # Ensure player exists and increment demand count
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if player exists
            cursor = await db.execute("SELECT user_id FROM players WHERE user_id = ?", (user.id,))
            exists = await cursor.fetchone()
            
            if exists:
                await db.execute("UPDATE players SET demands_used = COALESCE(demands_used, 0) + 1 WHERE user_id = ?", (user.id,))
            else:
                await db.execute("INSERT INTO players (user_id, demands_used) VALUES (?, 1)", (user.id,))
            
            await db.commit()

        # Get the updated demand count after increment
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT demands_used FROM players WHERE user_id = ?", (user.id,))
            result = await cursor.fetchone()
            new_demands_used = result[0] if result and result[0] is not None else 1

        # Get vice captain role ID
        vice_captain_role_id = await get_vice_captain_role_id()
        roles_to_remove = []
        
        # Add team role to removal list
        if team_role and team_role in user.roles:
            roles_to_remove.append(team_role)
        
        # Add vice captain role to removal list if user has it
        if vice_captain_role_id and vice_captain_role_id != 0:
            vice_captain_role = interaction.guild.get_role(vice_captain_role_id)
            if vice_captain_role and vice_captain_role in user.roles:
                roles_to_remove.append(vice_captain_role)
        
        # Remove team and vice captain roles
        if roles_to_remove:
            try:
                await user.remove_roles(*roles_to_remove, reason="Used demand to leave team")
                removed_names = [r.name for r in roles_to_remove]
                print(f"Successfully removed roles {removed_names} from {user}")
            except Exception as e:
                print(f"Error removing roles during demand: {e}")
                await interaction.followup.send(
                    "❌ There was an issue processing your demand. Please contact an admin.",
                    ephemeral=True
                )
                return

        # Add free agent role
        free_agent_role_id = await get_free_agent_role_id()
        if free_agent_role_id and free_agent_role_id != 0:
            free_agent_role = interaction.guild.get_role(free_agent_role_id)
            if free_agent_role:
                try:
                    await user.add_roles(free_agent_role, reason="Used demand to leave team - restored free agent status")
                    print(f"Successfully added free agent role to {user}")
                except Exception as fa_error:
                    print(f"Error adding free agent role: {fa_error}")
                    # Continue even if free agent role fails
        else:
            print("Free agent role not configured")

        embed = discord.Embed(
            title=f"📤 Demand Processed {team_emoji}",
            description=f"{team_emoji} {user.mention} has left {team_role.mention if team_role else team_name} via demand.",
            color=discord.Color.orange()
        )
        # Add team emoji thumbnail
        thumbnail_url = get_emoji_thumbnail_url(team_emoji)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        embed.add_field(name="Team", value=f"{team_emoji} {team_name}", inline=True)
        embed.add_field(name="Player", value=user.mention, inline=True)
        embed.add_field(name="Demands Used", value=f"{new_demands_used}/{max_demands}", inline=True)
        embed.set_footer(text=f"Player can use {max_demands - new_demands_used} more demands" if new_demands_used < max_demands else "Player has used all available demands")

        # Send to demand log channel if configured, otherwise fallback to sign log channel
        log_channel_id = await get_demand_log_channel_id()
        if not log_channel_id or log_channel_id == 0:
            log_channel_id = await get_sign_log_channel_id()
        
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)

        await interaction.followup.send(f"You have successfully used your demand to leave your team. ({new_demands_used}/{max_demands} demands used)")

    @app_commands.command(name="reset_demands", description="Reset all player demands (admin only)")
    async def reset_demands(self, interaction: discord.Interaction):
        if not await has_any_role(interaction.user, ALLOWED_RESET_ROLES):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE players SET demands_used = 0")
            await db.commit()

        await interaction.followup.send("All player demand counts have been reset.", ephemeral=True)

    @app_commands.command(name="reset_player_demands", description="Reset a specific player's demands (admin only)")
    @app_commands.describe(user="The player whose demands should be reset")
    async def reset_player_demands(self, interaction: discord.Interaction, user: discord.Member):
        if not await has_any_role(interaction.user, ALLOWED_RESET_ROLES):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get current demand count
            player = await get_player(user.id)
            current_demands = 0
            if player and len(player) > 6:
                current_demands = player[6]

            # Reset demands for this player
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE players SET demands_used = 0 WHERE user_id = ?", (user.id,))
                await db.commit()

            max_demands = await get_max_demands_allowed()

            embed = discord.Embed(
                title="✅ Player Demands Reset",
                description=f"{user.mention}'s demand count has been reset.",
                color=discord.Color.green()
            )
            embed.add_field(name="Previous Demands", value=f"{current_demands}/{max_demands}", inline=True)
            embed.add_field(name="Current Demands", value=f"0/{max_demands}", inline=True)
            embed.set_footer(text=f"Reset by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Error resetting player demands: {e}", ephemeral=True)

    @app_commands.command(name="check_demands", description="Check a player's current demand usage")
    @app_commands.describe(user="The player to check (leave empty to check yourself)")
    async def check_demands(self, interaction: discord.Interaction, user: discord.Member = None):
        try:
            await interaction.response.defer(ephemeral=True)
            
            target_user = user if user else interaction.user
            
            # Get player data
            player = await get_player(target_user.id)
            demands_used = 0
            if player and len(player) > 6:
                demands_used = player[6]

            max_demands = await get_max_demands_allowed()
            remaining_demands = max_demands - demands_used

            embed = discord.Embed(
                title="📊 Demand Usage",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Player", value=target_user.mention, inline=False)
            embed.add_field(name="Demands Used", value=f"{demands_used}/{max_demands}", inline=True)
            embed.add_field(name="Remaining", value=f"{remaining_demands}", inline=True)
            
            if remaining_demands <= 0:
                embed.add_field(name="Status", value="❌ No demands remaining", inline=False)
                embed.color = discord.Color.red()
            elif remaining_demands == 1:
                embed.add_field(name="Status", value="⚠️ Last demand available", inline=False)
                embed.color = discord.Color.orange()
            else:
                embed.add_field(name="Status", value="✅ Demands available", inline=False)
                embed.color = discord.Color.green()

            # Only show to command user if checking someone else (privacy)
            ephemeral = user is not None and user != interaction.user
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)

        except Exception as e:
            await interaction.followup.send(f"❌ Error checking demands: {e}", ephemeral=True)

    @app_commands.command(name="blacklist", description="Blacklist a user from being signed")
    @app_commands.describe(
        user="User to blacklist",
        reason="Reason for blacklist",
        duration="Duration (e.g., '2 hours', '3 days', '1 week') - leave empty for permanent"
    )
    async def blacklist(self, interaction: discord.Interaction, user: discord.Member, reason: str, duration: str = None):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        try:
            await interaction.response.defer()
            
            # Parse duration if provided
            duration_hours = None
            duration_text = "Permanent"
            expires_timestamp = None
            
            if duration:
                try:
                    # Parse flexible duration formats
                    duration_lower = duration.lower().strip()
                    
                    # Extract number and unit
                    match = re.match(r'(\d+)\s*(hour|hours|h|day|days|d|week|weeks|w|month|months|m)', duration_lower)
                    
                    if match:
                        amount = int(match.group(1))
                        unit = match.group(2)
                        
                        if unit in ['hour', 'hours', 'h']:
                            duration_hours = amount
                            duration_text = f"{amount} hour{'s' if amount != 1 else ''}"
                        elif unit in ['day', 'days', 'd']:
                            duration_hours = amount * 24
                            duration_text = f"{amount} day{'s' if amount != 1 else ''}"
                        elif unit in ['week', 'weeks', 'w']:
                            duration_hours = amount * 24 * 7
                            duration_text = f"{amount} week{'s' if amount != 1 else ''}"
                        elif unit in ['month', 'months', 'm']:
                            duration_hours = amount * 24 * 30  # Approximate month
                            duration_text = f"{amount} month{'s' if amount != 1 else ''}"
                        
                        if duration_hours:
                            expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
                            expires_timestamp = int(expires_at.timestamp())
                    else:
                        await interaction.followup.send(
                            "❌ Invalid duration format. Use formats like:\n"
                            "• `2 hours` or `2h`\n"
                            "• `3 days` or `3d`\n"
                            "• `1 week` or `1w`\n"
                            "• `2 months` or `2m`\n"
                            "Or leave empty for permanent blacklist.",
                            ephemeral=True
                        )
                        return
                        
                except Exception as parse_error:
                    print(f"Error parsing duration: {parse_error}")
                    await interaction.followup.send(
                        "❌ Error parsing duration. Use formats like '2 hours', '3 days', '1 week'.",
                        ephemeral=True
                    )
                    return

            # Comprehensive role removal (but don't announce what was removed)
            print(f"Starting blacklist process for user: {user.display_name}")
            
            # Use comprehensive role removal function
            removal_success = await self.comprehensive_role_removal(user, f"Blacklisted by {interaction.user}: {reason}")
            
            if not removal_success:
                await interaction.followup.send(
                    "❌ I don't have permission to remove some roles from this user.",
                    ephemeral=True
                )
                return

            # Add to blacklist database
            await add_blacklist(user.id, reason, interaction.user.id, duration_hours)

            # Add Discord blacklist role
            blacklisted_role = discord.utils.get(interaction.guild.roles, name="Blacklisted")
            if not blacklisted_role:
                blacklisted_role = await interaction.guild.create_role(
                    name="Blacklisted", 
                    reason="For sign ban enforcement",
                    color=discord.Color.dark_red()
                )

            if blacklisted_role not in user.roles:
                await user.add_roles(blacklisted_role, reason=f"Blacklisted: {reason}")

            # Create simplified embed (no role removal details)
            embed = discord.Embed(
                title="🚫 User Blacklisted",
                color=discord.Color.red()
            )
            
            embed.add_field(name="👤 User", value=user.mention, inline=True)
            embed.add_field(name="⚖️ Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="⏱️ Duration", value=duration_text, inline=True)
            
            embed.add_field(name="📝 Reason", value=reason, inline=False)
            
            if expires_timestamp:
                embed.add_field(
                    name="📅 Expires",
                    value=f"<t:{expires_timestamp}:F>\n<t:{expires_timestamp}:R>",
                    inline=False
                )
                embed.add_field(
                    name="📋 Status",
                    value="**User is permanently blacklisted** from being signed to teams until manually removed.",
                    inline=False
                )
            
            embed.set_footer(text=f"Blacklist ID: {user.id} • Applied at")
            embed.timestamp = discord.utils.utcnow()

            # Send to blacklist log channel if configured, otherwise use main channel
            blacklist_channel_id = await get_blacklist_log_channel_id()
            if blacklist_channel_id and blacklist_channel_id != 0:
                blacklist_channel = interaction.guild.get_channel(blacklist_channel_id)
                if blacklist_channel:
                    await blacklist_channel.send(embed=embed)
                    
                    # Send confirmation to command channel
                    confirm_embed = discord.Embed(
                        title="✅ Blacklist Applied",
                        description=f"{user.mention} has been blacklisted for **{duration_text.lower()}**.\nDetails logged to {blacklist_channel.mention}.",
                        color=discord.Color.orange()
                    )
                    await interaction.followup.send(embed=confirm_embed)
                else:
                    # Fallback to current channel if blacklist channel not found
                    await interaction.followup.send(embed=embed)
            else:
                # No blacklist channel configured, send to current channel
                await interaction.followup.send(embed=embed)

            # Send simplified DM to blacklisted user
            try:
                dm_embed = discord.Embed(
                    title="⚠️ You have been blacklisted",
                    description=f"You have been blacklisted from signing to teams in **{interaction.guild.name}**.",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="📝 Reason", value=reason, inline=False)
                dm_embed.add_field(name="⏱️ Duration", value=duration_text, inline=True)
                dm_embed.add_field(name="⚖️ Moderator", value=str(interaction.user), inline=True)
                
                if expires_timestamp:
                    dm_embed.add_field(
                        name="📅 Expires",
                        value=f"<t:{expires_timestamp}:F>",
                        inline=False
                    )
                    dm_embed.add_field(
                        name="ℹ️ What this means",
                        value="You cannot be signed to any team until this blacklist expires.",
                        inline=False
                    )
                else:
                    dm_embed.add_field(
                        name="ℹ️ What this means",
                        value="You are **permanently blacklisted** and cannot be signed to any team until a moderator removes this blacklist.",
                        inline=False
                    )
                
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                print(f"Could not send DM to {user} - DMs disabled")
            except Exception as dm_error:
                print(f"Error sending DM: {dm_error}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in blacklist command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error applying blacklist: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error applying blacklist: {e}", ephemeral=True)

    @app_commands.command(name="unblacklist", description="Remove a user from the blacklist and restore required signing roles")
    @app_commands.describe(
        user="The user to unblacklist",
        restore_free_agent="Whether to restore the Free Agent role (default: True)"
    )
    async def unblacklist(self, interaction: discord.Interaction, user: discord.Member, restore_free_agent: bool = True):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        try:
            await interaction.response.defer()

            # Check if user is actually blacklisted
            is_blacklisted = await is_user_blacklisted(user.id)
            if not is_blacklisted:
                await interaction.followup.send(
                    f"❌ {user.mention} is not currently blacklisted.",
                    ephemeral=True
                )
                return

            # Remove the "Blacklisted" role if it exists
            blacklisted_role = discord.utils.get(interaction.guild.roles, name="Blacklisted")
            roles_restored = []
            
            if blacklisted_role and blacklisted_role in user.roles:
                try:
                    await user.remove_roles(blacklisted_role, reason=f"Unblacklisted by {interaction.user}")
                    roles_restored.append("Removed Blacklisted role")
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ I don't have permission to remove the Blacklisted role from this user.",
                        ephemeral=True
                    )
                    return
                except Exception as role_error:
                    print(f"Error removing blacklisted role: {role_error}")

            # Restore required roles for signing
            required_role_ids = await get_required_roles()
            restored_required_roles = []
            failed_required_roles = []
            
            for role_id in required_role_ids:
                required_role = interaction.guild.get_role(role_id)
                if required_role:
                    if required_role not in user.roles:
                        try:
                            await user.add_roles(required_role, reason=f"Unblacklisted by {interaction.user} - restored required signing role")
                            restored_required_roles.append(required_role.name)
                            print(f"Restored required role: {required_role.name}")
                        except discord.Forbidden:
                            failed_required_roles.append(f"{required_role.name} (no permission)")
                            print(f"Failed to restore required role {required_role.name} - no permission")
                        except Exception as req_error:
                            failed_required_roles.append(f"{required_role.name} (error)")
                            print(f"Error restoring required role {required_role.name}: {req_error}")
                    else:
                        print(f"User already has required role: {required_role.name}")
                else:
                    failed_required_roles.append(f"Role ID {role_id} (not found)")
                    print(f"Required role ID {role_id} not found in guild")
            
            # Add summary of required roles restoration
            if restored_required_roles:
                roles_restored.append(f"Restored required roles: {', '.join(restored_required_roles)}")
            
            if failed_required_roles:
                roles_restored.append(f"⚠️ Failed to restore: {', '.join(failed_required_roles)}")

            # Optionally restore Free Agent role
            if restore_free_agent:
                free_agent_role_id = await get_free_agent_role_id()
                if free_agent_role_id and free_agent_role_id != 0:
                    free_agent_role = interaction.guild.get_role(free_agent_role_id)
                    if free_agent_role and free_agent_role not in user.roles:
                        try:
                            await user.add_roles(free_agent_role, reason=f"Unblacklisted by {interaction.user} - restored free agent status")
                            roles_restored.append("Added Free Agent role")
                        except Exception as fa_error:
                            print(f"Error adding free agent role: {fa_error}")
                            roles_restored.append("⚠️ Failed to add Free Agent role")

            # Update the blacklist in database
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE blacklists SET active = 0 WHERE user_id = ? AND active = 1", (user.id,)
                )
                await db.commit()

            # Create comprehensive embed
            embed = discord.Embed(
                title="✅ User Unblacklisted",
                description=f"{user.mention} has been removed from the blacklist.",
                color=discord.Color.green()
            )
            
            embed.add_field(name="👤 User", value=user.mention, inline=True)
            embed.add_field(name="⚖️ Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="📅 Unblacklisted", value=f"<t:{int(datetime.utcnow().timestamp())}:F>", inline=True)
            
            embed.add_field(
                name="📋 Status", 
                value="User can now be signed to teams again.",
                inline=False
            )
            
            embed.set_footer(text=f"Unblacklisted by {interaction.user.display_name}")
            embed.timestamp = discord.utils.utcnow()

            # Send to blacklist log channel if configured
            blacklist_channel_id = await get_blacklist_log_channel_id()
            if blacklist_channel_id and blacklist_channel_id != 0:
                blacklist_channel = interaction.guild.get_channel(blacklist_channel_id)
                if blacklist_channel:
                    await blacklist_channel.send(embed=embed)
                    
                    # Send confirmation to command channel
                    confirm_embed = discord.Embed(
                        title="✅ User Unblacklisted",
                        description=f"{user.mention} has been removed from the blacklist.\nDetails logged to {blacklist_channel.mention}.",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=confirm_embed)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(embed=embed)

            # Send DM to unblacklisted user
            try:
                dm_embed = discord.Embed(
                    title="✅ You have been unblacklisted",
                    description=f"Your blacklist has been removed in **{interaction.guild.name}**.",
                    color=discord.Color.green()
                )
                dm_embed.add_field(name="⚖️ Moderator", value=str(interaction.user), inline=True)
                dm_embed.add_field(name="📅 Unblacklisted", value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
                
                dm_embed.add_field(
                    name="ℹ️ What this means",
                    value="You can now be signed to teams again!",
                    inline=False
                )
                
                await user.send(embed=dm_embed)
            except discord.Forbidden:
                print(f"Could not send DM to {user} - DMs disabled")
            except Exception as dm_error:
                print(f"Error sending unblacklist DM: {dm_error}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in unblacklist command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error removing blacklist: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error removing blacklist: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PlayerCommands(bot))