import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import re
import math  # ADD THIS MISSING IMPORT
from datetime import datetime, timedelta
# Import configuration
from config import DB_PATH, GUILD_ID, TEAM_OWNER_ROLE_NAME

# Import database functions
from database.teams import get_team_by_role, get_team_by_id
from database.settings import (
    get_team_member_cap, get_vice_captain_role_id, get_free_agent_role_id,
    get_required_roles, get_one_of_required_roles
)

# Import utility functions
from utils.emoji_helpers import get_emoji_thumbnail_url

# Import UI components
from ui.views import PaginatorView

class RosterCommands(commands.Cog):
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
            'is_referee': False,
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
                elif role_key == 'referee':
                    status['is_referee'] = True
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

    @app_commands.command(name="viewroster", description="View a team's roster with comprehensive role information")
    @app_commands.describe(team_role="The role representing the team (leave blank to view your own team)")
    async def viewroster(self, interaction: discord.Interaction, team_role: discord.Role = None):
        try:
            await interaction.response.defer()
            user = interaction.user
            guild = interaction.guild

            # If team_role not provided, try to detect user's team
            if team_role is None:
                user_team = await self.get_user_team_by_role(user)
                if not user_team:
                    await interaction.followup.send("You are not on any team. Please specify a team role to view.", ephemeral=True)
                    return
                
                team_id, role_id, team_emoji, team_name = user_team
                team_role = guild.get_role(role_id)
                
                if not team_role:
                    await interaction.followup.send("Your team role could not be found.", ephemeral=True)
                    return
            else:
                team = await get_team_by_role(team_role.id)
                if not team:
                    await interaction.followup.send("Team not found in database.", ephemeral=True)
                    return
                team_id, role_id, team_emoji, team_name, owner_id = team

            # Get team data
            team_data = await get_team_by_role(team_role.id)
            if not team_data:
                await interaction.followup.send("Team not found in database.", ephemeral=True)
                return
            
            team_id, role_id, team_emoji, team_name, owner_id = team_data

            # Get config roles
            config_roles = await self.get_all_config_roles(guild)
            
            role_members = team_role.members
            owner_member = guild.get_member(owner_id) if owner_id else None
            
            embed = discord.Embed(
                title=f"{team_emoji} {team_name} Roster",
                color=discord.Color.blue()
            )
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            # Owner section with role verification
            if owner_member:
                owner_status = await self.get_member_role_status(owner_member, config_roles)
                owner_display = f"{owner_member.mention} ({owner_member.display_name})"
                
                # Check if owner has team owner role
                if not owner_status['is_team_owner']:
                    owner_display += " ⚠️ *Missing Team Owner role*"
                
                embed.add_field(name="👑 Owner", value=owner_display, inline=False)
            else:
                embed.add_field(name="👑 Owner", value="No owner assigned", inline=False)

            # Categorize members by roles (using Discord roles as source of truth)
            vice_captains = []
            normal_players = []
            members_with_issues = []

            for member in role_members:
                if member.id == owner_id:
                    continue

                member_status = await self.get_member_role_status(member, config_roles)
                
                # Basic member info
                member_info = {
                    'member': member,
                    'status': member_status,
                    'display_roles': []
                }
                
                # Add role indicators
                if member_status['is_vice_captain']:
                    member_info['display_roles'].append("⚔️")
                    vice_captains.append(member_info)
                else:
                    normal_players.append(member_info)
                
                # Add other role indicators
                if member_status['is_referee']:
                    member_info['display_roles'].append("🏁")
                if member_status['is_blacklisted']:
                    member_info['display_roles'].append("🚫")
                    members_with_issues.append(member)
                if not member_status['has_required_roles']:
                    member_info['display_roles'].append("❌")
                    members_with_issues.append(member)

            def format_members_with_roles(members_list):
                formatted = []
                for i, member_info in enumerate(members_list):
                    member = member_info['member']
                    roles_str = "".join(member_info['display_roles'])
                    roles_suffix = f" {roles_str}" if roles_str else ""
                    formatted.append(f"{i+1}. {member.mention} ({member.display_name}){roles_suffix}")
                return "\n".join(formatted)

            # Vice captains section
            if vice_captains:
                embed.add_field(
                    name="⚔️ Vice Captains", 
                    value=format_members_with_roles(vice_captains), 
                    inline=False
                )
            
            # Players section
            if normal_players:
                embed.add_field(
                    name="👤 Players", 
                    value=format_members_with_roles(normal_players), 
                    inline=False
                )
            else:
                embed.add_field(name="👤 Players", value="*None*", inline=False)

            # Statistics and sync info
            cap = await get_team_member_cap()
            used_slots = len(role_members)
            remaining_slots = cap - used_slots
            stats = f"Total Members: {used_slots}/{cap} (including owner)\n"
            stats += f"{remaining_slots} slots remaining" if remaining_slots > 0 else "FULL"
            
            if members_with_issues:
                stats += f"\n🚨 {len(set(members_with_issues))} member(s) with role issues"
            
            embed.add_field(name="📊 Statistics", value=stats, inline=False)
            
            # Sync recommendations
            if members_with_issues:
                sync_text = [f"🔄 `/sync_all_roles team_role:{team_role.name}` to fix role sync"]
                embed.add_field(
                    name="🛠️ Recommendations", 
                    value="\n".join(sync_text), 
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"⚠️ Error occurred: `{e}`", ephemeral=True)
            print(f"Error in viewroster: {e}")

    @app_commands.command(name="viewteams", description="View all teams and actual member counts by role")
    async def viewteams(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT role_id, emoji, name FROM teams") as cursor:
                teams_data = await cursor.fetchall()
        
        if not teams_data:
            await interaction.followup.send("No teams found.")
            return

        cap = await get_team_member_cap()
        teams_per_page = 5
        pages = []

        all_fields = []
        for role_id, emoji, name in teams_data:
            role = interaction.guild.get_role(role_id)
            # SKIP TEAMS WITH DELETED/MISSING ROLES
            if role:
                count = len(role.members)
                all_fields.append((f"{emoji or '🔥'} {name}", f"{count}/{cap} members (including owner)"))

        # Handle case where all teams have deleted roles
        if not all_fields:
            await interaction.followup.send("No teams with valid roles found.", ephemeral=True)
            return

        # Split into pages
        total_pages = math.ceil(len(all_fields) / teams_per_page)
        for i in range(total_pages):
            embed = discord.Embed(
                title=f"Teams and Member Counts (Page {i+1}/{total_pages})",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Team Member Cap: {cap} members per team (including owner)")

            for name, value in all_fields[i*teams_per_page:(i+1)*teams_per_page]:
                embed.add_field(name=name, value=value, inline=False)

            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            view = PaginatorView(pages)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

    @app_commands.command(name="member", description="List all users with a given role")
    @app_commands.describe(role="The role to list members from")
    async def member(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        
        members_with_role = [member.mention for member in role.members]

        if not members_with_role:
            await interaction.followup.send(f"No members have the role {role.mention}.", ephemeral=True)
            return

        # Split members into pages (25 members per page for readability)
        members_per_page = 25
        pages = []
        
        for i in range(0, len(members_with_role), members_per_page):
            page_members = members_with_role[i:i + members_per_page]
            member_list = "\n".join([f"{idx + 1 + i}. {member}" for idx, member in enumerate(page_members)])
            
            embed = discord.Embed(
                title=f"👥 Members with {role.name}",
                description=member_list,
                color=role.color if role.color != discord.Color.default() else discord.Color.blurple()
            )
            
            # Add page info and total count
            page_num = i // members_per_page + 1
            total_pages = (len(members_with_role) + members_per_page - 1) // members_per_page
            
            embed.set_footer(text=f"Page {page_num}/{total_pages} • Total: {len(members_with_role)} members")
            
            # Add role info in thumbnail if role has an icon
            if hasattr(role, 'display_icon') and role.display_icon:
                embed.set_thumbnail(url=role.display_icon.url)
            
            pages.append(embed)

        # If only one page, send directly
        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            # Use pagination for multiple pages
            view = PaginatorView(pages)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RosterCommands(bot))