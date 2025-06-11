import asyncio
import discord
from discord.ext import commands
from discord import app_commands, ui
import aiosqlite
import math
from typing import Optional, Union

# Import configuration
from config import DB_PATH, GUILD_ID, ALLOWED_MANAGEMENT_ROLES

# Import database functions  
from database.teams import get_team_by_id
from database.settings import (
    get_sign_log_channel_id, get_schedule_log_channel_id, get_game_results_channel_id,
    get_game_reminder_channel_id, get_demand_log_channel_id, get_blacklist_log_channel_id,
    get_team_owner_alert_channel_id, get_lft_channel_id, get_team_announcements_channel_id,
    get_team_owner_dashboard_channel_id, get_referee_role_id, get_official_ping_role_id,
    get_vice_captain_role_id, get_free_agent_role_id, get_required_roles, set_required_roles,
    get_team_member_cap, set_team_member_cap, is_signing_open, set_signing_state,
    get_max_demands_allowed, set_max_demands_allowed, set_config_value,
    set_vice_captain_role_id, set_free_agent_role_id, get_active_dashboard,
    deactivate_dashboard, set_team_owner_dashboard_channel_id,
    get_one_of_required_roles, set_one_of_required_roles
)

# Import utility functions
from utils.permissions import has_any_role
from utils.alerts import send_team_owner_alert

# Import UI components
from ui.views import PaginatorView

# Import tasks
from tasks import setup_dashboard_in_channel

# ========================= ENHANCED CONFIGURATION UI COMPONENTS =========================

class ConfigMainMenu(ui.Select):
    """Main navigation menu for configuration categories."""
    
    def __init__(self, config_view):
        self.config_view = config_view
        
        options = [
            discord.SelectOption(
                label="📊 Overview", 
                description="Configuration overview and quick stats", 
                emoji="📊",
                value="overview"
            ),
            discord.SelectOption(
                label="📺 Channels", 
                description="Configure bot logging and notification channels", 
                emoji="📺",
                value="channels"
            ),
            discord.SelectOption(
                label="👥 Roles", 
                description="Configure bot roles and permissions", 
                emoji="👥",
                value="roles"
            ),
            discord.SelectOption(
                label="⚙️ General Settings", 
                description="Team caps, signing status, and limits", 
                emoji="⚙️",
                value="settings"
            ),
            discord.SelectOption(
                label="🔒 Access Control", 
                description="Manage signing requirements and role permissions", 
                emoji="🔒",
                value="access_control"
            ),
            discord.SelectOption(
                label="📊 Dashboard", 
                description="Manage live team owner dashboard", 
                emoji="📊",
                value="dashboard"
            ),
            discord.SelectOption(
                label="🛠️ Advanced", 
                description="Advanced settings and maintenance tools", 
                emoji="🛠️",
                value="advanced"
            )
        ]
        
        super().__init__(
            placeholder="🔧 Select a configuration category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="config_main_menu"
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "overview":
            await self.config_view.show_overview_page(interaction)
        else:
            await self.config_view.show_category(interaction, self.values[0])

class ChannelConfigDropdown(ui.Select):
    """Enhanced dropdown for channel configuration with categories."""
    
    def __init__(self, config_view):
        self.config_view = config_view
        
        options = [
            # Logging Channels
            discord.SelectOption(
                label="📝 Sign Log Channel", 
                description="Where player signings are logged",
                value="sign_log_channel", 
                emoji="📝"
            ),
            discord.SelectOption(
                label="📅 Schedule Log Channel", 
                description="Where game scheduling is logged",
                value="schedule_log_channel", 
                emoji="📅"
            ),
            discord.SelectOption(
                label="🏆 Game Results Channel", 
                description="Where match results are posted",
                value="game_results_channel", 
                emoji="🏆"
            ),
            discord.SelectOption(
                label="📋 Demand Log Channel", 
                description="Where trade demands are logged",
                value="demand_log_channel", 
                emoji="📋"
            ),
            discord.SelectOption(
                label="🚫 Blacklist Log Channel", 
                description="Where blacklist actions are logged",
                value="blacklist_log_channel", 
                emoji="🚫"
            ),
            # Notification Channels
            discord.SelectOption(
                label="⏰ Game Reminder Channel", 
                description="Where game reminders are sent",
                value="game_reminder_channel", 
                emoji="⏰"
            ),
            discord.SelectOption(
                label="⚠️ Team Owner Alert Channel", 
                description="Where team owner alerts are sent",
                value="team_owner_alert_channel", 
                emoji="⚠️"
            ),
            # Community Channels
            discord.SelectOption(
                label="📢 Team Announcements Channel", 
                description="Where team recruitment posts go",
                value="team_announcements_channel", 
                emoji="📢"
            ),
            discord.SelectOption(
                label="🔍 LFT Channel", 
                description="Where looking-for-team posts go",
                value="lft_channel", 
                emoji="🔍"
            ),
            # Dashboard
            discord.SelectOption(
                label="📊 Dashboard Channel", 
                description="Where team owner dashboard is displayed",
                value="team_owner_dashboard_channel", 
                emoji="📊"
            )
        ]
        
        super().__init__(
            placeholder="📺 Select a channel to configure...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="channel_config_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await self.config_view.handle_channel_config(interaction, self.values[0])

class RoleConfigDropdown(ui.Select):
    """Enhanced dropdown for role configuration with descriptions."""
    
    def __init__(self, config_view):
        self.config_view = config_view
        
        options = [
            discord.SelectOption(
                label="🏁 Referee Role", 
                description="Users who can referee games",
                value="referee_role", 
                emoji="🏁"
            ),
            discord.SelectOption(
                label="📺 Official Game Ping Role", 
                description="Role pinged for official streamed games",
                value="official_ping_role", 
                emoji="📺"
            ),
            discord.SelectOption(
                label="👨‍✈️ Vice Captain Role", 
                description="Team vice captains with special permissions",
                value="vice_captain_role", 
                emoji="👨‍✈️"
            ),
            discord.SelectOption(
                label="🆓 Free Agent Role", 
                description="Role for unsigned players",
                value="free_agent_role", 
                emoji="🆓"
            )
        ]
        
        super().__init__(
            placeholder="👥 Select a role to configure...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="role_config_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await self.config_view.handle_role_config(interaction, self.values[0])

class SettingsConfigDropdown(ui.Select):
    """Enhanced dropdown for general settings configuration."""
    
    def __init__(self, config_view):
        self.config_view = config_view
        
        options = [
            discord.SelectOption(
                label="👥 Team Member Cap", 
                description="Maximum players per team",
                value="team_member_cap", 
                emoji="👥"
            ),
            discord.SelectOption(
                label="📊 Max Demands Allowed", 
                description="Maximum trade demands per player",
                value="max_demands_allowed", 
                emoji="📊"
            ),
            discord.SelectOption(
                label="🔄 Toggle Signing Status", 
                description="Open or close player signing period",
                value="toggle_signing", 
                emoji="🔄"
            )
        ]
        
        super().__init__(
            placeholder="⚙️ Select a setting to configure...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="settings_config_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await self.config_view.handle_general_setting(interaction, self.values[0])

class AccessControlDropdown(ui.Select):
    """Enhanced dropdown for access control management."""
    
    def __init__(self, config_view):
        self.config_view = config_view
        
        options = [
            discord.SelectOption(
                label="📋 View ALL Required Roles", 
                description="View roles ALL required for signing",
                value="view_all_required", 
                emoji="📋"
            ),
            discord.SelectOption(
                label="➕ Add ALL Required Role", 
                description="Add to roles ALL required for signing",
                value="add_all_required", 
                emoji="➕"
            ),
            discord.SelectOption(
                label="➖ Remove ALL Required Role", 
                description="Remove from ALL required roles",
                value="remove_all_required", 
                emoji="➖"
            ),
            discord.SelectOption(
                label="🧹 Clear ALL Required Roles", 
                description="Remove all required roles",
                value="clear_all_required", 
                emoji="🧹"
            ),
            discord.SelectOption(
                label="🔀 View One-Of Required Roles", 
                description="View roles where ONE is required",
                value="view_one_of_required", 
                emoji="🔀"
            ),
            discord.SelectOption(
                label="➕ Add One-Of Required Role", 
                description="Add to one-of required roles",
                value="add_one_of_required", 
                emoji="➕"
            ),
            discord.SelectOption(
                label="➖ Remove One-Of Required Role", 
                description="Remove from one-of required roles",
                value="remove_one_of_required", 
                emoji="➖"
            ),
            discord.SelectOption(
                label="🧹 Clear One-Of Required Roles", 
                description="Clear all one-of required roles",
                value="clear_one_of_required", 
                emoji="🧹"
            )
        ]
        
        super().__init__(
            placeholder="🔒 Select an access control action...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="access_control_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await self.config_view.handle_access_control(interaction, self.values[0])

class DashboardControlDropdown(ui.Select):
    """Enhanced dropdown for dashboard management."""
    
    def __init__(self, config_view):
        self.config_view = config_view
        
        options = [
            discord.SelectOption(
                label="🚀 Setup Dashboard", 
                description="Create dashboard in a channel",
                value="setup_dashboard", 
                emoji="🚀"
            ),
            discord.SelectOption(
                label="🛑 Stop Dashboard", 
                description="Stop and remove current dashboard",
                value="stop_dashboard", 
                emoji="🛑"
            ),
            discord.SelectOption(
                label="📊 Dashboard Status", 
                description="Check dashboard status and health",
                value="dashboard_status", 
                emoji="📊"
            ),
            discord.SelectOption(
                label="🔄 Refresh Dashboard", 
                description="Force refresh dashboard data",
                value="refresh_dashboard", 
                emoji="🔄"
            )
        ]
        
        super().__init__(
            placeholder="📊 Select a dashboard action...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="dashboard_control_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await self.config_view.handle_dashboard_action(interaction, self.values[0])

class AdvancedConfigDropdown(ui.Select):
    """Enhanced dropdown for advanced configuration options."""
    
    def __init__(self, config_view):
        self.config_view = config_view
        
        options = [
            discord.SelectOption(
                label="🔍 Configuration Audit", 
                description="Check for configuration issues",
                value="config_audit", 
                emoji="🔍"
            ),
            discord.SelectOption(
                label="📋 Export Configuration", 
                description="Export current config as text",
                value="export_config", 
                emoji="📋"
            ),
            discord.SelectOption(
                label="🔧 Validate Setup", 
                description="Validate all channels and roles exist",
                value="validate_setup", 
                emoji="🔧"
            ),
            discord.SelectOption(
                label="📊 Usage Statistics", 
                description="View configuration usage stats",
                value="usage_stats", 
                emoji="📊"
            )
        ]
        
        super().__init__(
            placeholder="🛠️ Select an advanced option...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="advanced_config_dropdown"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await self.config_view.handle_advanced_action(interaction, self.values[0])

# ========================= ENHANCED MODAL FORMS =========================

class EnhancedChannelModal(ui.Modal, title="Channel Configuration"):
    def __init__(self, setting_name: str, setting_key: str, config_view, current_value: str = ""):
        super().__init__()
        self.setting_name = setting_name
        self.setting_key = setting_key
        self.config_view = config_view
        
        # Get description for this setting
        descriptions = {
            "sign_log_channel": "Channel where player signings and team changes are logged",
            "schedule_log_channel": "Channel where game scheduling activities are logged", 
            "game_results_channel": "Channel where match results and outcomes are posted",
            "game_reminder_channel": "Channel where game reminders are automatically sent",
            "demand_log_channel": "Channel where trade demands are logged",
            "blacklist_log_channel": "Channel where blacklist actions are logged",
            "team_owner_alert_channel": "Channel where team owner alerts are sent",
            "team_announcements_channel": "Channel for team recruitment and LFP posts",
            "lft_channel": "Channel for looking-for-team posts",
            "team_owner_dashboard_channel": "Channel where live team owner dashboard is displayed"
        }
        
        description = descriptions.get(setting_key, "Configure this channel setting")
        
        self.channel_input = ui.TextInput(
            label=f"🔧 {setting_name}",
            placeholder="Channel ID, #channel mention, or channel name",
            default=current_value,
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        
        self.description_field = ui.TextInput(
            label="ℹ️ What this does",
            default=description,
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph
        )
        self.description_field.disabled = True
        
        self.add_item(self.channel_input)
        self.add_item(self.description_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_input = self.channel_input.value.strip()
            
            # Parse channel input (ID, mention, or name)
            channel = None
            
            # Try mention format first
            if channel_input.startswith('<#') and channel_input.endswith('>'):
                try:
                    channel_id = int(channel_input[2:-1])
                    channel = interaction.guild.get_channel(channel_id)
                except ValueError:
                    pass
            
            # Try direct ID
            if not channel:
                try:
                    channel_id = int(channel_input)
                    channel = interaction.guild.get_channel(channel_id)
                except ValueError:
                    pass
            
            # Try channel name
            if not channel:
                for guild_channel in interaction.guild.channels:
                    if guild_channel.name.lower() == channel_input.lower():
                        channel = guild_channel
                        break
            
            if not channel:
                await interaction.response.send_message(
                    f"❌ **Channel Not Found**\n"
                    f"Could not find a channel matching: `{channel_input}`\n\n"
                    f"**Try these formats:**\n"
                    f"• Channel mention: {interaction.guild.text_channels[0].mention if interaction.guild.text_channels else '#channel'}\n"
                    f"• Channel ID: `{interaction.guild.text_channels[0].id if interaction.guild.text_channels else '123456789'}`\n"
                    f"• Channel name: `{interaction.guild.text_channels[0].name if interaction.guild.text_channels else 'general'}`",
                    ephemeral=True
                )
                return
            
            # Update the setting
            await set_config_value(f"{self.setting_key}_id", channel.id)
            
            # Create success embed with more details
            embed = discord.Embed(
                title="✅ Channel Configuration Updated",
                description=f"**{self.setting_name}** has been successfully configured!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📺 Channel",
                value=f"{channel.mention}\n`{channel.name}` (ID: {channel.id})",
                inline=True
            )
            
            embed.add_field(
                name="🔧 Setting",
                value=self.setting_name,
                inline=True
            )
            
            # Check permissions
            permissions = channel.permissions_for(interaction.guild.me)
            permission_issues = []
            
            if not permissions.send_messages:
                permission_issues.append("Send Messages")
            if not permissions.embed_links:
                permission_issues.append("Embed Links")
            if not permissions.read_message_history:
                permission_issues.append("Read Message History")
            
            if permission_issues:
                embed.add_field(
                    name="⚠️ Permission Issues",
                    value=f"Missing: {', '.join(permission_issues)}",
                    inline=False
                )
                embed.color = discord.Color.orange()
            else:
                embed.add_field(
                    name="✅ Permissions",
                    value="All required permissions available",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Refresh the config view
            await self.config_view.refresh_current_page(interaction)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Configuration Error**\n{str(e)}", 
                ephemeral=True
            )

class EnhancedRoleModal(ui.Modal, title="Role Configuration"):
    def __init__(self, setting_name: str, setting_key: str, config_view, current_value: str = ""):
        super().__init__()
        self.setting_name = setting_name
        self.setting_key = setting_key
        self.config_view = config_view
        
        # Get description for this role
        descriptions = {
            "referee_role": "Users with this role can sign up to referee games",
            "official_ping_role": "Role that gets pinged for official streamed games",
            "vice_captain_role": "Team vice captains with special management permissions",
            "free_agent_role": "Automatically managed role for unsigned players"
        }
        
        description = descriptions.get(setting_key, "Configure this role setting")
        
        self.role_input = ui.TextInput(
            label=f"🔧 {setting_name}",
            placeholder="Role ID, @role mention, or role name",
            default=current_value,
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        
        self.description_field = ui.TextInput(
            label="ℹ️ What this does",
            default=description,
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph
        )
        self.description_field.disabled = True
        
        self.add_item(self.role_input)
        self.add_item(self.description_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_input = self.role_input.value.strip()
            
            # Parse role input (ID, mention, or name)
            role = None
            
            # Try mention format first
            if role_input.startswith('<@&') and role_input.endswith('>'):
                try:
                    role_id = int(role_input[3:-1])
                    role = interaction.guild.get_role(role_id)
                except ValueError:
                    pass
            
            # Try direct ID
            if not role:
                try:
                    role_id = int(role_input)
                    role = interaction.guild.get_role(role_id)
                except ValueError:
                    pass
            
            # Try role name
            if not role:
                for guild_role in interaction.guild.roles:
                    if guild_role.name.lower() == role_input.lower():
                        role = guild_role
                        break
            
            if not role:
                await interaction.response.send_message(
                    f"❌ **Role Not Found**\n"
                    f"Could not find a role matching: `{role_input}`\n\n"
                    f"**Try these formats:**\n"
                    f"• Role mention: @RoleName\n"
                    f"• Role ID: `123456789`\n"
                    f"• Role name: `RoleName`",
                    ephemeral=True
                )
                return
            
            # Update the setting based on type
            if self.setting_key == "vice_captain_role":
                await set_vice_captain_role_id(role.id)
            elif self.setting_key == "free_agent_role":
                await set_free_agent_role_id(role.id)
            else:
                await set_config_value(f"{self.setting_key}_id", role.id)
            
            # Create success embed with more details
            embed = discord.Embed(
                title="✅ Role Configuration Updated",
                description=f"**{self.setting_name}** has been successfully configured!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="👥 Role",
                value=f"{role.mention}\n`{role.name}` (ID: {role.id})",
                inline=True
            )
            
            embed.add_field(
                name="🔧 Setting",
                value=self.setting_name,
                inline=True
            )
            
            embed.add_field(
                name="👤 Members",
                value=f"{len(role.members)} users have this role",
                inline=True
            )
            
            # Check role hierarchy
            bot_top_role = interaction.guild.me.top_role
            if role.position >= bot_top_role.position and role != bot_top_role:
                embed.add_field(
                    name="⚠️ Role Hierarchy Warning",
                    value="This role is above my highest role. I may not be able to manage users with this role.",
                    inline=False
                )
                embed.color = discord.Color.orange()
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Refresh the config view
            await self.config_view.refresh_current_page(interaction)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Configuration Error**\n{str(e)}", 
                ephemeral=True
            )

class EnhancedNumberModal(ui.Modal, title="Numeric Setting Configuration"):
    def __init__(self, setting_name: str, setting_key: str, config_view, current_value: str = "", min_val: int = 0, max_val: int = 999):
        super().__init__()
        self.setting_name = setting_name
        self.setting_key = setting_key
        self.config_view = config_view
        self.min_val = min_val
        self.max_val = max_val
        
        # Get description and constraints for this setting
        descriptions = {
            "team_member_cap": f"Maximum number of players per team (recommended: 8-15)",
            "max_demands_allowed": f"Maximum trade demands per player (recommended: 1-3)"
        }
        
        description = descriptions.get(setting_key, "Configure this numeric setting")
        
        self.number_input = ui.TextInput(
            label=f"🔧 {setting_name}",
            placeholder=f"Enter a number between {min_val} and {max_val}",
            default=current_value,
            required=True,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.description_field = ui.TextInput(
            label="ℹ️ What this does",
            default=description,
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph
        )
        self.description_field.disabled = True
        
        self.add_item(self.number_input)
        self.add_item(self.description_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.number_input.value.strip())
            
            if value < self.min_val or value > self.max_val:
                await interaction.response.send_message(
                    f"❌ **Invalid Value**\n"
                    f"Value must be between {self.min_val} and {self.max_val}.\n"
                    f"You entered: {value}",
                    ephemeral=True
                )
                return
            
            # Special validation for specific settings
            if self.setting_key == "team_member_cap" and value < 1:
                await interaction.response.send_message(
                    "❌ **Invalid Team Cap**\nTeam member cap must be at least 1!", 
                    ephemeral=True
                )
                return
            
            # Update the setting
            if self.setting_key == "team_member_cap":
                await set_team_member_cap(value)
                impact_message = "This affects how many players can be on each team."
            else:  # max_demands_allowed
                await set_max_demands_allowed(value)
                impact_message = "This affects how many trade demands each player can make."
            
            # Create success embed
            embed = discord.Embed(
                title="✅ Setting Updated",
                description=f"**{self.setting_name}** has been successfully updated!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="🔢 New Value",
                value=f"`{value}`",
                inline=True
            )
            
            embed.add_field(
                name="📊 Previous Value", 
                value=f"`{self.number_input.default}`",
                inline=True
            )
            
            embed.add_field(
                name="💡 Impact",
                value=impact_message,
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Refresh the config view
            await self.config_view.refresh_current_page(interaction)
            
        except ValueError:
            await interaction.response.send_message(
                f"❌ **Invalid Input**\n`{self.number_input.value}` is not a valid number!", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Configuration Error**\n{str(e)}", 
                ephemeral=True
            )

class RoleManagementModal(ui.Modal, title="Role Management"):
    def __init__(self, action: str, role_type: str, config_view):
        super().__init__()
        self.action = action
        self.role_type = role_type
        self.config_view = config_view
        
        role_type_display = "ALL Required" if role_type == "all" else "One-Of Required"
        
        if action in ["add", "remove"]:
            self.role_input = ui.TextInput(
                label=f"🔧 {action.title()} {role_type_display} Role",
                placeholder="Role ID, @role mention, or role name",
                required=True,
                max_length=100,
                style=discord.TextStyle.short
            )
            
            description = (
                f"Add a role to {role_type_display.lower()} list" if action == "add" 
                else f"Remove a role from {role_type_display.lower()} list"
            )
            
            self.description_field = ui.TextInput(
                label="ℹ️ What this does",
                default=description,
                required=False,
                max_length=200,
                style=discord.TextStyle.paragraph
            )
            self.description_field.disabled = True
            
            self.add_item(self.role_input)
            self.add_item(self.description_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.action in ["add", "remove"]:
                role_input = self.role_input.value.strip()
                
                # Parse role input
                role = None
                
                if role_input.startswith('<@&') and role_input.endswith('>'):
                    try:
                        role_id = int(role_input[3:-1])
                        role = interaction.guild.get_role(role_id)
                    except ValueError:
                        pass
                
                if not role:
                    try:
                        role_id = int(role_input)
                        role = interaction.guild.get_role(role_id)
                    except ValueError:
                        pass
                
                if not role:
                    for guild_role in interaction.guild.roles:
                        if guild_role.name.lower() == role_input.lower():
                            role = guild_role
                            break
                
                if not role:
                    await interaction.response.send_message(
                        f"❌ **Role Not Found**\nCould not find role: `{role_input}`", 
                        ephemeral=True
                    )
                    return
                
                # Get current roles
                if self.role_type == "all":
                    current_roles = await get_required_roles()
                else:  # one_of
                    current_roles = await get_one_of_required_roles()
                
                if self.action == "add":
                    if role.id in current_roles:
                        await interaction.response.send_message(
                            f"❌ **Role Already Exists**\n{role.mention} is already in the list!", 
                            ephemeral=True
                        )
                        return
                    
                    new_roles = current_roles + [role.id]
                    if self.role_type == "all":
                        await set_required_roles(new_roles)
                        message = f"✅ Added {role.mention} to ALL required roles"
                        description = "Users must now have ALL listed roles to be signed"
                    else:
                        await set_one_of_required_roles(new_roles)
                        message = f"✅ Added {role.mention} to one-of required roles"
                        description = "Users must have AT LEAST ONE of the listed roles to be signed"
                
                else:  # remove
                    if role.id not in current_roles:
                        await interaction.response.send_message(
                            f"❌ **Role Not Found**\n{role.mention} is not in the list!", 
                            ephemeral=True
                        )
                        return
                    
                    new_roles = [r for r in current_roles if r != role.id]
                    if self.role_type == "all":
                        await set_required_roles(new_roles)
                        message = f"✅ Removed {role.mention} from ALL required roles"
                        description = "Role requirement updated for signing"
                    else:
                        await set_one_of_required_roles(new_roles)
                        message = f"✅ Removed {role.mention} from one-of required roles"
                        description = "Role requirement updated for signing"
                
                # Create success embed
                embed = discord.Embed(
                    title="✅ Role Requirements Updated",
                    description=message,
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="📊 Current Count",
                    value=f"{len(new_roles)} roles in list",
                    inline=True
                )
                
                embed.add_field(
                    name="💡 Impact",
                    value=description,
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            elif self.action == "clear":
                if self.role_type == "all":
                    current_roles = await get_required_roles()
                    if not current_roles:
                        await interaction.response.send_message(
                            "❌ **Nothing to Clear**\nNo ALL required roles are currently set!", 
                            ephemeral=True
                        )
                        return
                    await set_required_roles([])
                    message = "✅ Cleared all ALL required roles"
                    description = "Any player can now be signed (no role requirements)"
                else:
                    current_roles = await get_one_of_required_roles()
                    if not current_roles:
                        await interaction.response.send_message(
                            "❌ **Nothing to Clear**\nNo one-of required roles are currently set!", 
                            ephemeral=True
                        )
                        return
                    await set_one_of_required_roles([])
                    message = "✅ Cleared all one-of required roles"
                    description = "Removed one-of role requirements for signing"
                
                embed = discord.Embed(
                    title="✅ Role Requirements Cleared",
                    description=message,
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="📊 Cleared",
                    value=f"{len(current_roles)} roles removed",
                    inline=True
                )
                
                embed.add_field(
                    name="💡 Impact",
                    value=description,
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Refresh the config view
            await self.config_view.refresh_current_page(interaction)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Configuration Error**\n{str(e)}", 
                ephemeral=True
            )

# ========================= ENHANCED MAIN CONFIG VIEW =========================

class EnhancedConfigView(ui.View):
    """Enhanced main configuration view with better navigation and features."""
    
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=600)  # 10 minute timeout
        self.interaction = interaction
        self.guild = interaction.guild
        self.current_page = "overview"
        
        # Add main navigation menu
        self.add_item(ConfigMainMenu(self))
        
        # Add quick action buttons
        self.add_quick_action_buttons()
    
    def add_quick_action_buttons(self):
        """Add quick action buttons to the view."""
        # Refresh button
        refresh_button = ui.Button(
            label="🔄 Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id="refresh_config"
        )
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)
        
        # Help button
        help_button = ui.Button(
            label="❓ Help",
            style=discord.ButtonStyle.secondary,
            custom_id="config_help"
        )
        help_button.callback = self.help_callback
        self.add_item(help_button)
    
    async def refresh_callback(self, interaction: discord.Interaction):
        """Handle refresh button click."""
        await self.refresh_current_page(interaction)
    
    async def help_callback(self, interaction: discord.Interaction):
        """Handle help button click."""
        embed = discord.Embed(
            title="❓ Configuration Help",
            description="**How to use the Configuration Panel:**",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🧭 Navigation",
            value=(
                "• Use the **main dropdown** to switch categories\n"
                "• Use **category dropdowns** to configure specific settings\n"
                "• Click **🔄 Refresh** to update displays\n"
                "• This panel auto-expires after 10 minutes"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📺 Channels",
            value="Configure where the bot sends logs and notifications",
            inline=True
        )
        
        embed.add_field(
            name="👥 Roles",
            value="Set up roles for referees, officials, and permissions",
            inline=True
        )
        
        embed.add_field(
            name="⚙️ Settings",
            value="Adjust team caps, signing status, and limits",
            inline=True
        )
        
        embed.add_field(
            name="🔒 Access Control",
            value="Manage who can be signed to teams",
            inline=True
        )
        
        embed.add_field(
            name="📊 Dashboard",
            value="Control the live team owner dashboard",
            inline=True
        )
        
        embed.add_field(
            name="🛠️ Advanced",
            value="Configuration audits and maintenance tools",
            inline=True
        )
        
        embed.add_field(
            name="💡 Tips",
            value=(
                "• **Green** status = Working properly\n"
                "• **Orange** status = Needs attention\n"
                "• **Red** status = Critical issue\n"
                "• Use **Export Config** to backup settings"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def show_overview(self):
        """Show enhanced overview page with detailed statistics."""
        embed = discord.Embed(
            title="📊 Bot Configuration Overview",
            description="**Complete configuration status and quick statistics**",
            color=discord.Color.blue()
        )
        
        # Channel Configuration Status
        channel_configs = [
            ("📝 Sign Log", await get_sign_log_channel_id()),
            ("📅 Schedule Log", await get_schedule_log_channel_id()),
            ("🏆 Game Results", await get_game_results_channel_id()),
            ("⏰ Game Reminders", await get_game_reminder_channel_id()),
            ("📋 Demand Log", await get_demand_log_channel_id()),
            ("🚫 Blacklist Log", await get_blacklist_log_channel_id()),
            ("⚠️ Team Owner Alerts", await get_team_owner_alert_channel_id()),
            ("📢 Team Announcements", await get_team_announcements_channel_id()),
            ("🔍 LFT Posts", await get_lft_channel_id()),
            ("📊 Dashboard", await get_team_owner_dashboard_channel_id())
        ]
        
        configured_channels = 0
        missing_channels = []
        invalid_channels = []
        
        for name, channel_id in channel_configs:
            if channel_id and channel_id != 0:
                channel = self.guild.get_channel(channel_id)
                if channel:
                    configured_channels += 1
                else:
                    invalid_channels.append(name)
            else:
                missing_channels.append(name)
        
        # Role Configuration Status
        role_configs = [
            ("🏁 Referee", await get_referee_role_id()),
            ("📺 Official Ping", await get_official_ping_role_id()),
            ("👨‍✈️ Vice Captain", await get_vice_captain_role_id()),
            ("🆓 Free Agent", await get_free_agent_role_id())
        ]
        
        configured_roles = 0
        missing_roles = []
        invalid_roles = []
        
        for name, role_id in role_configs:
            if role_id and role_id != 0:
                role = self.guild.get_role(role_id)
                if role:
                    configured_roles += 1
                else:
                    invalid_roles.append(name)
            else:
                missing_roles.append(name)
        
        # Access Control Status
        required_roles_all = await get_required_roles()
        required_roles_one_of = await get_one_of_required_roles()
        
        # General Settings
        team_cap = await get_team_member_cap()
        signing_open = await is_signing_open()
        max_demands = await get_max_demands_allowed()
        
        # Dashboard Status
        dashboard_active = bool(await get_active_dashboard())
        
        # Create status summary
        total_channels = len(channel_configs)
        total_roles = len(role_configs)
        
        if configured_channels == total_channels:
            channel_status = f"✅ {configured_channels}/{total_channels} channels configured"
            channel_color = "🟢"
        elif configured_channels >= total_channels // 2:
            channel_status = f"⚠️ {configured_channels}/{total_channels} channels configured"
            channel_color = "🟡"
        else:
            channel_status = f"❌ {configured_channels}/{total_channels} channels configured"
            channel_color = "🔴"
        
        if configured_roles == total_roles:
            role_status = f"✅ {configured_roles}/{total_roles} roles configured"
            role_color = "🟢"
        elif configured_roles >= total_roles // 2:
            role_status = f"⚠️ {configured_roles}/{total_roles} roles configured"
            role_color = "🟡"
        else:
            role_status = f"❌ {configured_roles}/{total_roles} roles configured"
            role_color = "🔴"
        
        # Main status field
        embed.add_field(
            name="🔧 Configuration Status",
            value=(
                f"{channel_color} **Channels:** {channel_status}\n"
                f"{role_color} **Roles:** {role_status}\n"
                f"🔒 **Access Control:** {len(required_roles_all)} ALL + {len(required_roles_one_of)} One-Of roles\n"
                f"📊 **Dashboard:** {'🟢 Active' if dashboard_active else '🔴 Inactive'}"
            ),
            inline=False
        )
        
        # Settings summary
        embed.add_field(
            name="⚙️ Current Settings",
            value=(
                f"👥 **Team Cap:** {team_cap} members\n"
                f"🔄 **Signing:** {'🟢 Open' if signing_open else '🔴 Closed'}\n"
                f"📊 **Max Demands:** {max_demands} per player"
            ),
            inline=True
        )
        
        # Quick stats
        embed.add_field(
            name="📈 Quick Stats",
            value=(
                f"🏠 **Server:** {self.guild.name}\n"
                f"👤 **Members:** {self.guild.member_count:,}\n"
                f"📺 **Channels:** {len(self.guild.channels)}\n"
                f"👥 **Roles:** {len(self.guild.roles)}"
            ),
            inline=True
        )
        
        # Issues section (if any)
        issues = []
        if missing_channels:
            issues.append(f"📺 Missing channels: {', '.join(missing_channels[:3])}{'...' if len(missing_channels) > 3 else ''}")
        if invalid_channels:
            issues.append(f"❌ Invalid channels: {', '.join(invalid_channels[:3])}{'...' if len(invalid_channels) > 3 else ''}")
        if missing_roles:
            issues.append(f"👥 Missing roles: {', '.join(missing_roles[:3])}{'...' if len(missing_roles) > 3 else ''}")
        if invalid_roles:
            issues.append(f"❌ Invalid roles: {', '.join(invalid_roles[:3])}{'...' if len(invalid_roles) > 3 else ''}")
        
        if issues:
            embed.add_field(
                name="⚠️ Configuration Issues",
                value="\n".join(issues[:4]),  # Show max 4 issues
                inline=False
            )
            if configured_channels + configured_roles < (total_channels + total_roles) * 0.7:
                embed.color = discord.Color.orange()
        
        # Navigation help
        embed.add_field(
            name="🧭 Quick Start",
            value=(
                "**1.** Configure channels for logging and notifications\n"
                "**2.** Set up roles for permissions and management\n"
                "**3.** Adjust general settings (team caps, signing status)\n"
                "**4.** Configure access control for player signing\n"
                "**5.** Set up the team owner dashboard"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 Use the dropdown menu above to configure specific categories")
        embed.timestamp = discord.utils.utcnow()
        
        return embed
    
    async def show_overview_page(self, interaction: discord.Interaction):
        """Show the overview page and reset view to main menu."""
        self.current_page = "overview"
        
        # Reset view to main menu only
        self.clear_items()
        self.add_item(ConfigMainMenu(self))
        self.add_quick_action_buttons()
        
        embed = await self.show_overview()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def show_category(self, interaction: discord.Interaction, category: str):
        """Show a specific configuration category with enhanced display."""
        self.current_page = category
        
        # Clear and rebuild view for category
        self.clear_items()
        self.add_item(ConfigMainMenu(self))
        
        if category == "channels":
            embed = await self.create_enhanced_channels_embed()
            self.add_item(ChannelConfigDropdown(self))
        elif category == "roles":
            embed = await self.create_enhanced_roles_embed()
            self.add_item(RoleConfigDropdown(self))
        elif category == "settings":
            embed = await self.create_enhanced_settings_embed()
            self.add_item(SettingsConfigDropdown(self))
        elif category == "access_control":
            embed = await self.create_enhanced_access_control_embed()
            self.add_item(AccessControlDropdown(self))
        elif category == "dashboard":
            embed = await self.create_enhanced_dashboard_embed()
            self.add_item(DashboardControlDropdown(self))
        elif category == "advanced":
            embed = await self.create_enhanced_advanced_embed()
            self.add_item(AdvancedConfigDropdown(self))
        else:
            embed = await self.show_overview()
        
        self.add_quick_action_buttons()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def create_enhanced_channels_embed(self):
        """Create enhanced channels configuration display."""
        embed = discord.Embed(
            title="📺 Channel Configuration",
            description="**Configure bot channels for logging and notifications**",
            color=discord.Color.blue()
        )
        
        # Group channels by category
        logging_channels = [
            ("📝 Sign Log", "sign_log_channel", await get_sign_log_channel_id()),
            ("📅 Schedule Log", "schedule_log_channel", await get_schedule_log_channel_id()),
            ("🏆 Game Results", "game_results_channel", await get_game_results_channel_id()),
            ("📋 Demand Log", "demand_log_channel", await get_demand_log_channel_id()),
            ("🚫 Blacklist Log", "blacklist_log_channel", await get_blacklist_log_channel_id())
        ]
        
        notification_channels = [
            ("⏰ Game Reminders", "game_reminder_channel", await get_game_reminder_channel_id()),
            ("⚠️ Team Owner Alerts", "team_owner_alert_channel", await get_team_owner_alert_channel_id())
        ]
        
        community_channels = [
            ("📢 Team Announcements", "team_announcements_channel", await get_team_announcements_channel_id()),
            ("🔍 LFT Posts", "lft_channel", await get_lft_channel_id()),
            ("📊 Dashboard", "team_owner_dashboard_channel", await get_team_owner_dashboard_channel_id())
        ]
        
        # Build logging channels display
        logging_text = ""
        for name, key, channel_id in logging_channels:
            if channel_id and channel_id != 0:
                channel = self.guild.get_channel(channel_id)
                if channel:
                    logging_text += f"✅ {name}: {channel.mention}\n"
                else:
                    logging_text += f"❌ {name}: *Not found* (ID: {channel_id})\n"
            else:
                logging_text += f"⚪ {name}: *Not configured*\n"
        
        embed.add_field(
            name="📋 Logging Channels",
            value=logging_text or "*No logging channels configured*",
            inline=False
        )
        
        # Build notification channels display  
        notification_text = ""
        for name, key, channel_id in notification_channels:
            if channel_id and channel_id != 0:
                channel = self.guild.get_channel(channel_id)
                if channel:
                    notification_text += f"✅ {name}: {channel.mention}\n"
                else:
                    notification_text += f"❌ {name}: *Not found* (ID: {channel_id})\n"
            else:
                notification_text += f"⚪ {name}: *Not configured*\n"
        
        embed.add_field(
            name="🔔 Notification Channels",
            value=notification_text or "*No notification channels configured*",
            inline=False
        )
        
        # Build community channels display
        community_text = ""
        for name, key, channel_id in community_channels:
            if channel_id and channel_id != 0:
                channel = self.guild.get_channel(channel_id)
                if channel:
                    community_text += f"✅ {name}: {channel.mention}\n"
                else:
                    community_text += f"❌ {name}: *Not found* (ID: {channel_id})\n"
            else:
                community_text += f"⚪ {name}: *Not configured*\n"
        
        embed.add_field(
            name="🌐 Community Channels",
            value=community_text or "*No community channels configured*",
            inline=False
        )
        
        # Add usage tips
        embed.add_field(
            name="💡 Configuration Tips",
            value=(
                "• **Logging channels** record bot activities for audit trails\n"
                "• **Notification channels** send automated alerts and reminders\n"
                "• **Community channels** are where players interact with bot features\n"
                "• Ensure the bot has **Send Messages** and **Embed Links** permissions in all channels"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown menu to configure individual channels")
        
        return embed
    
    async def create_enhanced_roles_embed(self):
        """Create enhanced roles configuration display."""
        embed = discord.Embed(
            title="👥 Role Configuration", 
            description="**Configure bot roles for permissions and functionality**",
            color=discord.Color.blue()
        )
        
        roles = [
            ("🏁 Referee Role", "referee_role", await get_referee_role_id(), "Users who can referee games"),
            ("📺 Official Game Ping Role", "official_ping_role", await get_official_ping_role_id(), "Role pinged for streamed games"),
            ("👨‍✈️ Vice Captain Role", "vice_captain_role", await get_vice_captain_role_id(), "Team vice captains with special permissions"),
            ("🆓 Free Agent Role", "free_agent_role", await get_free_agent_role_id(), "Automatically managed for unsigned players")
        ]
        
        role_text = ""
        configured_count = 0
        
        for name, key, role_id, description in roles:
            if role_id and role_id != 0:
                role = self.guild.get_role(role_id)
                if role:
                    member_count = len(role.members)
                    role_text += f"✅ **{name}**\n"
                    role_text += f"   {role.mention} • {member_count} members\n"
                    role_text += f"   *{description}*\n\n"
                    configured_count += 1
                else:
                    role_text += f"❌ **{name}**\n"
                    role_text += f"   *Role not found (ID: {role_id})*\n"
                    role_text += f"   *{description}*\n\n"
            else:
                role_text += f"⚪ **{name}**\n"
                role_text += f"   *Not configured*\n"
                role_text += f"   *{description}*\n\n"
        
        embed.add_field(
            name=f"🔧 Role Configuration ({configured_count}/4 configured)",
            value=role_text.strip(),
            inline=False
        )
        
        # Add role hierarchy info
        bot_top_role = self.guild.me.top_role
        embed.add_field(
            name="📊 Bot Role Hierarchy",
            value=(
                f"🤖 **Bot's Highest Role:** {bot_top_role.mention}\n"
                f"📍 **Position:** {bot_top_role.position}/{len(self.guild.roles)}\n"
                f"💡 *Bot can only manage roles below its highest role*"
            ),
            inline=True
        )
        
        # Add permission info
        embed.add_field(
            name="🔒 Important Notes",
            value=(
                "• **Free Agent Role** is automatically managed\n"
                "• **Vice Captain Role** grants team management permissions\n"
                "• **Referee Role** allows game officiating signup\n"
                "• Ensure bot can manage these roles (hierarchy)"
            ),
            inline=True
        )
        
        embed.set_footer(text="Use the dropdown menu to configure individual roles")
        
        return embed
    
    async def create_enhanced_settings_embed(self):
        """Create enhanced general settings display."""
        embed = discord.Embed(
            title="⚙️ General Settings",
            description="**Configure team limits, signing status, and gameplay settings**",
            color=discord.Color.blue()
        )
        
        team_cap = await get_team_member_cap()
        signing_open = await is_signing_open()
        max_demands = await get_max_demands_allowed()
        
        # Settings display with detailed info
        embed.add_field(
            name="👥 Team Management",
            value=(
                f"**Team Member Cap:** `{team_cap}` members\n"
                f"💡 *Maximum players allowed per team*\n\n"
                f"**Signing Status:** {'🟢 **OPEN**' if signing_open else '🔴 **CLOSED**'}\n"
                f"💡 *Whether new player signings are allowed*"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 Trade Management", 
            value=(
                f"**Max Demands:** `{max_demands}` per player\n"
                f"💡 *Maximum trade demands each player can make*"
            ),
            inline=False
        )
        
        # Add recommendations
        embed.add_field(
            name="📝 Recommended Settings",
            value=(
                "• **Team Cap:** 8-15 members (allows for subs and availability)\n"
                "• **Max Demands:** 1-3 per player (prevents spam)\n"
                "• **Signing Status:** Open during active seasons, closed during breaks"
            ),
            inline=False
        )
        
        # Current impact
        embed.add_field(
            name="📈 Current Impact",
            value=(
                f"• Teams can have up to **{team_cap} members** each\n"
                f"• Player signing is currently **{'allowed' if signing_open else 'disabled'}**\n"
                f"• Players can make up to **{max_demands} trade demands** each"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown menu to modify these settings")
        
        return embed
    
    async def create_enhanced_access_control_embed(self):
        """Create enhanced access control display."""
        embed = discord.Embed(
            title="🔒 Access Control Configuration",
            description="**Manage role requirements for player signing**",
            color=discord.Color.blue()
        )
        
        # ALL Required Roles
        all_required_role_ids = await get_required_roles()
        if all_required_role_ids:
            all_roles_text = ""
            valid_roles = 0
            
            for role_id in all_required_role_ids:
                role = self.guild.get_role(role_id)
                if role:
                    all_roles_text += f"✅ {role.mention} ({len(role.members)} members)\n"
                    valid_roles += 1
                else:
                    all_roles_text += f"❌ *Missing role (ID: {role_id})*\n"
            
            all_status = f"({valid_roles}/{len(all_required_role_ids)} valid)"
            all_description = "\n*Users must have ALL of these roles to be signed*"
        else:
            all_roles_text = "*No ALL required roles configured*"
            all_status = "(0 roles)"
            all_description = "\n*Any user can be signed (no role requirements)*"
        
        embed.add_field(
            name=f"📋 ALL Required Roles {all_status}",
            value=all_roles_text + all_description,
            inline=False
        )
        
        # One-Of Required Roles
        one_of_required_role_ids = await get_one_of_required_roles()
        if one_of_required_role_ids:
            one_of_roles_text = ""
            valid_one_of_roles = 0
            
            for role_id in one_of_required_role_ids:
                role = self.guild.get_role(role_id)
                if role:
                    one_of_roles_text += f"✅ {role.mention} ({len(role.members)} members)\n"
                    valid_one_of_roles += 1
                else:
                    one_of_roles_text += f"❌ *Missing role (ID: {role_id})*\n"
            
            one_of_status = f"({valid_one_of_roles}/{len(one_of_required_role_ids)} valid)"
            one_of_description = "\n*Users need AT LEAST ONE of these roles to be signed*"
        else:
            one_of_roles_text = "*No one-of required roles configured*"
            one_of_status = "(0 roles)"
            one_of_description = "\n*No one-of role requirements*"
        
        embed.add_field(
            name=f"🔀 One-Of Required Roles {one_of_status}",
            value=one_of_roles_text + one_of_description,
            inline=False
        )
        
        # Access control explanation
        embed.add_field(
            name="💡 How Access Control Works",
            value=(
                "**ALL Required Roles:** User must have every single role in this list\n"
                "**One-Of Required Roles:** User must have at least one role from this list\n"
                "**Combined:** User must satisfy BOTH conditions if both are configured\n"
                "**None configured:** Anyone can be signed to teams"
            ),
            inline=False
        )
        
        # Calculate current access
        total_all = len(all_required_role_ids)
        total_one_of = len(one_of_required_role_ids)
        
        if total_all == 0 and total_one_of == 0:
            access_status = "🟢 **Open Access** - Anyone can be signed"
        elif total_all > 0 and total_one_of > 0:
            access_status = f"🔴 **Strict Access** - Must have ALL {total_all} roles AND one of {total_one_of} roles"
        elif total_all > 0:
            access_status = f"🟡 **Moderate Access** - Must have ALL {total_all} roles"
        else:
            access_status = f"🟡 **Selective Access** - Must have one of {total_one_of} roles"
        
        embed.add_field(
            name="🎯 Current Access Level",
            value=access_status,
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown menu to manage role requirements")
        
        return embed
    
    async def create_enhanced_dashboard_embed(self):
        """Create enhanced dashboard configuration display."""
        embed = discord.Embed(
            title="📊 Dashboard Configuration",
            description="**Manage the live team owner dashboard**",
            color=discord.Color.blue()
        )
        
        dashboard_info = await get_active_dashboard()
        
        if dashboard_info:
            message_id, channel_id = dashboard_info
            channel = self.guild.get_channel(channel_id)
            
            if channel:
                try:
                    # Try to fetch the message to verify it exists
                    await channel.fetch_message(message_id)
                    status_emoji = "🟢"
                    status_text = "**ACTIVE**"
                    status_description = f"Dashboard is running in {channel.mention}"
                    health_status = "✅ **Healthy** - Message exists and is accessible"
                except discord.NotFound:
                    status_emoji = "🟡"
                    status_text = "**MESSAGE DELETED**"
                    status_description = f"Dashboard channel exists ({channel.mention}) but message was deleted"
                    health_status = "⚠️ **Needs Recreation** - Dashboard message was deleted"
                except discord.Forbidden:
                    status_emoji = "🟡"
                    status_text = "**ACCESS DENIED**"
                    status_description = f"Dashboard in {channel.mention} but bot lacks permissions"
                    health_status = "⚠️ **Permission Issue** - Cannot access dashboard message"
                except Exception:
                    status_emoji = "🟡"
                    status_text = "**UNKNOWN ERROR**"
                    status_description = f"Dashboard in {channel.mention} but status unclear"
                    health_status = "⚠️ **Unknown Issue** - Cannot verify dashboard status"
            else:
                status_emoji = "🔴"
                status_text = "**CHANNEL MISSING**"
                status_description = f"Dashboard channel was deleted (ID: {channel_id})"
                health_status = "❌ **Critical Issue** - Dashboard channel no longer exists"
        else:
            status_emoji = "🔴"
            status_text = "**INACTIVE**"
            status_description = "No dashboard is currently running"
            health_status = "⚪ **Not Running** - Dashboard has not been set up"
        
        embed.add_field(
            name="📊 Dashboard Status",
            value=f"{status_emoji} {status_text}\n{status_description}",
            inline=False
        )
        
        embed.add_field(
            name="🔍 Health Check",
            value=health_status,
            inline=True
        )
        
        if dashboard_info:
            embed.add_field(
                name="📋 Dashboard Details",
                value=(
                    f"**Message ID:** `{message_id}`\n"
                    f"**Channel ID:** `{channel_id}`\n"
                    f"**Updates:** Every hour automatically"
                ),
                inline=True
            )
        
        # Dashboard features
        embed.add_field(
            name="✨ Dashboard Features",
            value=(
                "• **Live team roster tracking** with member counts\n"
                "• **Team owner monitoring** and alerts\n"
                "• **Automatic hourly updates** with fresh data\n"
                "• **Multi-page pagination** for large team lists\n"
                "• **Team capacity monitoring** with configurable limits"
            ),
            inline=False
        )
        
        # Management actions
        embed.add_field(
            name="🛠️ Available Actions",
            value=(
                "🚀 **Setup** - Create dashboard in a channel\n"
                "🛑 **Stop** - Remove current dashboard\n"
                "📊 **Status** - Detailed health and status check\n"
                "🔄 **Refresh** - Force immediate data update"
            ),
            inline=False
        )
        
        # Requirements and permissions
        embed.add_field(
            name="📋 Requirements",
            value=(
                "• Bot needs **Send Messages** permission\n"
                "• Bot needs **Embed Links** permission\n"
                "• Bot needs **Use External Emojis** permission\n"
                "• Channel should be accessible to team owners"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown menu to manage dashboard actions")
        
        return embed
    
    async def create_enhanced_advanced_embed(self):
        """Create enhanced advanced configuration display."""
        embed = discord.Embed(
            title="🛠️ Advanced Configuration",
            description="**Advanced settings, maintenance tools, and configuration management**",
            color=discord.Color.blue()
        )
        
        # System status
        embed.add_field(
            name="🔧 System Status",
            value=(
                f"**Server:** {self.guild.name}\n"
                f"**Members:** {self.guild.member_count:,}\n"
                f"**Channels:** {len(self.guild.channels)}\n"
                f"**Roles:** {len(self.guild.roles)}\n"
                f"**Bot Permissions:** {'✅ Administrator' if self.guild.me.guild_permissions.administrator else '⚠️ Limited'}"
            ),
            inline=True
        )
        
        # Configuration health
        total_configs = 14  # Total number of configurable items
        configured_items = 0
        
        # Count configured items
        channel_configs = [
            await get_sign_log_channel_id(), await get_schedule_log_channel_id(),
            await get_game_results_channel_id(), await get_game_reminder_channel_id(),
            await get_demand_log_channel_id(), await get_blacklist_log_channel_id(),
            await get_team_owner_alert_channel_id(), await get_team_announcements_channel_id(),
            await get_lft_channel_id(), await get_team_owner_dashboard_channel_id()
        ]
        
        role_configs = [
            await get_referee_role_id(), await get_official_ping_role_id(),
            await get_vice_captain_role_id(), await get_free_agent_role_id()
        ]
        
        for config in channel_configs + role_configs:
            if config and config != 0:
                configured_items += 1
        
        health_percentage = (configured_items / total_configs) * 100
        
        if health_percentage >= 90:
            health_status = "🟢 Excellent"
            health_color = "✅"
        elif health_percentage >= 70:
            health_status = "🟡 Good"
            health_color = "⚠️"
        elif health_percentage >= 50:
            health_status = "🟠 Fair"
            health_color = "⚠️"
        else:
            health_status = "🔴 Poor"
            health_color = "❌"
        
        embed.add_field(
            name="📊 Configuration Health",
            value=(
                f"**Overall Health:** {health_color} {health_status}\n"
                f"**Configured:** {configured_items}/{total_configs} ({health_percentage:.0f}%)\n"
                f"**Dashboard:** {'🟢 Active' if await get_active_dashboard() else '🔴 Inactive'}\n"
                f"**Signing:** {'🟢 Open' if await is_signing_open() else '🔴 Closed'}"
            ),
            inline=True
        )
        
        # Available tools
        embed.add_field(
            name="🔍 Maintenance Tools",
            value=(
                "🔍 **Configuration Audit** - Comprehensive health check\n"
                "📋 **Export Configuration** - Backup current settings\n"
                "🔧 **Validate Setup** - Check all channels and roles exist\n"
                "📊 **Usage Statistics** - View configuration metrics"
            ),
            inline=False
        )
        
        # Advanced tips
        embed.add_field(
            name="💡 Advanced Tips",
            value=(
                "• Run **Configuration Audit** weekly to catch issues early\n"
                "• **Export Configuration** before making major changes\n"
                "• Use **Validate Setup** after Discord server reorganization\n"
                "• Monitor **Usage Statistics** to optimize bot performance"
            ),
            inline=False
        )
        
        # Warning section
        embed.add_field(
            name="⚠️ Important Notes",
            value=(
                "• These tools are for advanced users and administrators\n"
                "• Always backup your configuration before major changes\n"
                "• Some operations may require bot restart to take effect\n"
                "• Contact support if you encounter critical issues"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use the dropdown menu to access advanced tools")
        
        return embed
    
    # ========================= CONFIGURATION HANDLERS =========================
    
    async def handle_channel_config(self, interaction: discord.Interaction, setting_key: str):
        """Handle channel configuration with enhanced modal."""
        setting_names = {
            "sign_log_channel": "Sign Log Channel",
            "schedule_log_channel": "Schedule Log Channel", 
            "game_results_channel": "Game Results Channel",
            "game_reminder_channel": "Game Reminder Channel",
            "demand_log_channel": "Demand Log Channel",
            "blacklist_log_channel": "Blacklist Log Channel",
            "team_owner_alert_channel": "Team Owner Alert Channel",
            "team_announcements_channel": "Team Announcements Channel",
            "lft_channel": "LFT Channel",
            "team_owner_dashboard_channel": "Team Owner Dashboard Channel"
        }
        
        setting_name = setting_names.get(setting_key, setting_key.replace('_', ' ').title())
        
        # Get current value to pre-fill
        current_value = ""
        if setting_key == "sign_log_channel":
            current_id = await get_sign_log_channel_id()
        elif setting_key == "schedule_log_channel":
            current_id = await get_schedule_log_channel_id()
        elif setting_key == "game_results_channel":
            current_id = await get_game_results_channel_id()
        elif setting_key == "game_reminder_channel":
            current_id = await get_game_reminder_channel_id()
        elif setting_key == "demand_log_channel":
            current_id = await get_demand_log_channel_id()
        elif setting_key == "blacklist_log_channel":
            current_id = await get_blacklist_log_channel_id()
        elif setting_key == "team_owner_alert_channel":
            current_id = await get_team_owner_alert_channel_id()
        elif setting_key == "team_announcements_channel":
            current_id = await get_team_announcements_channel_id()
        elif setting_key == "lft_channel":
            current_id = await get_lft_channel_id()
        elif setting_key == "team_owner_dashboard_channel":
            current_id = await get_team_owner_dashboard_channel_id()
        else:
            current_id = 0
        
        if current_id and current_id != 0:
            current_value = str(current_id)
        
        modal = EnhancedChannelModal(setting_name, setting_key, self, current_value)
        await interaction.response.send_modal(modal)
    
    async def handle_role_config(self, interaction: discord.Interaction, setting_key: str):
        """Handle role configuration with enhanced modal."""
        setting_names = {
            "referee_role": "Referee Role",
            "official_ping_role": "Official Game Ping Role",
            "vice_captain_role": "Vice Captain Role",
            "free_agent_role": "Free Agent Role"
        }
        
        setting_name = setting_names.get(setting_key, setting_key.replace('_', ' ').title())
        
        # Get current value to pre-fill
        current_value = ""
        if setting_key == "referee_role":
            current_id = await get_referee_role_id()
        elif setting_key == "official_ping_role":
            current_id = await get_official_ping_role_id()
        elif setting_key == "vice_captain_role":
            current_id = await get_vice_captain_role_id()
        elif setting_key == "free_agent_role":
            current_id = await get_free_agent_role_id()
        else:
            current_id = 0
        
        if current_id and current_id != 0:
            current_value = str(current_id)
        
        modal = EnhancedRoleModal(setting_name, setting_key, self, current_value)
        await interaction.response.send_modal(modal)
    
    async def handle_general_setting(self, interaction: discord.Interaction, setting_key: str):
        """Handle general setting configuration."""
        if setting_key == "toggle_signing":
            current_state = await is_signing_open()
            new_state = not current_state
            await set_signing_state(new_state)
            
            embed = discord.Embed(
                title="✅ Signing Status Updated",
                description=f"Player signing has been **{'opened' if new_state else 'closed'}**!",
                color=discord.Color.green() if new_state else discord.Color.red()
            )
            
            embed.add_field(
                name="🔄 New Status",
                value=f"{'🟢 **OPEN**' if new_state else '🔴 **CLOSED**'}",
                inline=True
            )
            
            embed.add_field(
                name="💡 Impact",
                value=f"Players can {'now' if new_state else 'no longer'} be signed to teams",
                inline=True
            )
            
            if new_state:
                embed.add_field(
                    name="📋 What's Next",
                    value="Team owners can now sign players using `/sign` command",
                    inline=False
                )
            else:
                embed.add_field(
                    name="📋 What's Next", 
                    value="All signing attempts will be blocked until reopened",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.refresh_current_page(interaction)
            
        else:
            setting_names = {
                "team_member_cap": "Team Member Cap",
                "max_demands_allowed": "Max Demands Allowed"
            }
            
            setting_name = setting_names.get(setting_key, setting_key.replace('_', ' ').title())
            
            # Get current value and constraints
            if setting_key == "team_member_cap":
                current_value = str(await get_team_member_cap())
                min_val, max_val = 1, 50
            else:  # max_demands_allowed
                current_value = str(await get_max_demands_allowed())
                min_val, max_val = 0, 10
            
            modal = EnhancedNumberModal(setting_name, setting_key, self, current_value, min_val, max_val)
            await interaction.response.send_modal(modal)
    
    async def handle_access_control(self, interaction: discord.Interaction, action: str):
        """Handle access control actions."""
        if action.startswith("view_"):
            role_type = "all" if "all_required" in action else "one_of"
            
            if role_type == "all":
                role_ids = await get_required_roles()
                title = "📋 ALL Required Roles for Signing"
                description = "**Users must have ALL of these roles to be signed to teams**"
            else:
                role_ids = await get_one_of_required_roles()
                title = "🔀 One-Of Required Roles for Signing"
                description = "**Users need AT LEAST ONE of these roles to be signed**"
            
            embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
            
            if role_ids:
                roles_text = ""
                valid_roles = 0
                total_members = 0
                
                for role_id in role_ids:
                    role = self.guild.get_role(role_id)
                    if role:
                        member_count = len(role.members)
                        roles_text += f"✅ {role.mention}\n"
                        roles_text += f"   **Members:** {member_count} • **Position:** #{role.position}\n\n"
                        valid_roles += 1
                        total_members += member_count
                    else:
                        roles_text += f"❌ **Missing Role** (ID: `{role_id}`)\n"
                        roles_text += f"   *This role has been deleted*\n\n"
                
                embed.add_field(
                    name=f"Current Roles ({valid_roles}/{len(role_ids)} valid)",
                    value=roles_text.strip(),
                    inline=False
                )
                
                if valid_roles > 0:
                    # Calculate potential signups
                    if role_type == "all":
                        # For ALL required, need intersection of all role members
                        eligible_members = set()
                        if valid_roles > 0:
                            first_role = next((self.guild.get_role(rid) for rid in role_ids if self.guild.get_role(rid)), None)
                            if first_role:
                                eligible_members = set(first_role.members)
                                for role_id in role_ids:
                                    role = self.guild.get_role(role_id)
                                    if role:
                                        eligible_members &= set(role.members)
                        
                        embed.add_field(
                            name="📊 Access Statistics",
                            value=(
                                f"**Total Members:** {total_members:,} (with duplicates)\n"
                                f"**Eligible Members:** {len(eligible_members):,} (have ALL roles)\n"
                                f"**Access Rate:** {(len(eligible_members)/self.guild.member_count*100):.1f}% of server"
                            ),
                            inline=True
                        )
                    else:
                        # For one-of, union of all role members
                        eligible_members = set()
                        for role_id in role_ids:
                            role = self.guild.get_role(role_id)
                            if role:
                                eligible_members |= set(role.members)
                        
                        embed.add_field(
                            name="📊 Access Statistics",
                            value=(
                                f"**Total Members:** {total_members:,} (with duplicates)\n"
                                f"**Eligible Members:** {len(eligible_members):,} (have any role)\n"
                                f"**Access Rate:** {(len(eligible_members)/self.guild.member_count*100):.1f}% of server"
                            ),
                            inline=True
                        )
            else:
                embed.add_field(
                    name="Current Roles (0)",
                    value="*No roles configured*",
                    inline=False
                )
                
                embed.add_field(
                    name="📊 Access Statistics",
                    value="**Access:** Open to all server members",
                    inline=True
                )
            
            embed.add_field(
                name="🛠️ Management",
                value="Use the dropdown menu to add, remove, or clear roles",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        else:
            # Handle add/remove/clear actions
            if action.startswith("add_"):
                role_type = "all" if "all_required" in action else "one_of"
                modal = RoleManagementModal("add", role_type, self)
                await interaction.response.send_modal(modal)
            elif action.startswith("remove_"):
                role_type = "all" if "all_required" in action else "one_of"
                modal = RoleManagementModal("remove", role_type, self)
                await interaction.response.send_modal(modal)
            elif action.startswith("clear_"):
                role_type = "all" if "all_required" in action else "one_of"
                modal = RoleManagementModal("clear", role_type, self)
                await interaction.response.send_modal(modal)
    
    async def handle_dashboard_action(self, interaction: discord.Interaction, action: str):
        """Handle dashboard management actions."""
        if action == "setup_dashboard":
            modal = ui.Modal(title="Setup Team Owner Dashboard")
            channel_input = ui.TextInput(
                label="Channel",
                placeholder="Channel ID, #channel mention, or channel name",
                required=True,
                max_length=100
            )
            modal.add_item(channel_input)
            
            async def setup_callback(modal_interaction):
                try:
                    channel_input_value = channel_input.value.strip()
                    
                    # Parse channel input
                    channel = None
                    
                    if channel_input_value.startswith('<#') and channel_input_value.endswith('>'):
                        try:
                            channel_id = int(channel_input_value[2:-1])
                            channel = self.guild.get_channel(channel_id)
                        except ValueError:
                            pass
                    
                    if not channel:
                        try:
                            channel_id = int(channel_input_value)
                            channel = self.guild.get_channel(channel_id)
                        except ValueError:
                            pass
                    
                    if not channel:
                        for guild_channel in self.guild.channels:
                            if guild_channel.name.lower() == channel_input_value.lower():
                                channel = guild_channel
                                break
                    
                    if not channel:
                        await modal_interaction.response.send_message(
                            f"❌ **Channel Not Found**\nCould not find channel: `{channel_input_value}`",
                            ephemeral=True
                        )
                        return
                    
                    await modal_interaction.response.defer(ephemeral=True)
                    
                    success, error_msg = await setup_dashboard_in_channel(channel, self.interaction.client)
                    
                    if success:
                        await set_team_owner_dashboard_channel_id(channel.id)
                        
                        embed = discord.Embed(
                            title="✅ Dashboard Setup Complete",
                            description=f"Team owner dashboard has been successfully created!",
                            color=discord.Color.green()
                        )
                        
                        embed.add_field(
                            name="📊 Dashboard Location",
                            value=f"{channel.mention} (`{channel.name}`)",
                            inline=True
                        )
                        
                        embed.add_field(
                            name="🔄 Update Schedule",
                            value="Automatically every hour",
                            inline=True
                        )
                        
                        embed.add_field(
                            name="✨ Features",
                            value=(
                                "• Live team roster tracking\n"
                                "• Team owner monitoring\n"
                                "• Multi-page pagination\n"
                                "• Automatic updates"
                            ),
                            inline=False
                        )
                        
                        await modal_interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        await modal_interaction.followup.send(
                            f"❌ **Dashboard Setup Failed**\n{error_msg}",
                            ephemeral=True
                        )
                    
                    await self.refresh_current_page(modal_interaction, edit_original=False)
                    
                except Exception as e:
                    await modal_interaction.followup.send(
                        f"❌ **Setup Error**\n{str(e)}",
                        ephemeral=True
                    )
            
            modal.on_submit = setup_callback
            await interaction.response.send_modal(modal)
            
        elif action == "stop_dashboard":
            dashboard_info = await get_active_dashboard()
            if not dashboard_info:
                await interaction.response.send_message(
                    "❌ **No Active Dashboard**\nNo dashboard is currently running!",
                    ephemeral=True
                )
                return
            
            message_id, channel_id = dashboard_info
            channel = self.guild.get_channel(channel_id)
            
            # Try to delete the dashboard message
            deleted_message = False
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                    deleted_message = True
                except:
                    pass  # Message already deleted or no permission
            
            await deactivate_dashboard()
            await set_team_owner_dashboard_channel_id(0)
            
            embed = discord.Embed(
                title="🛑 Dashboard Stopped",
                description="The team owner dashboard has been successfully stopped!",
                color=discord.Color.orange()
            )
            
            if channel:
                embed.add_field(
                    name="📊 Previous Location",
                    value=f"{channel.mention} (`{channel.name}`)",
                    inline=True
                )
            
            embed.add_field(
                name="🗑️ Cleanup",
                value=f"Dashboard message {'✅ deleted' if deleted_message else '⚠️ could not be deleted'}",
                inline=True
            )
            
            embed.add_field(
                name="💡 Next Steps",
                value="Use **Setup Dashboard** to create a new dashboard in any channel",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await self.refresh_current_page(interaction)
            
        elif action == "dashboard_status":
            embed = await self.create_enhanced_dashboard_embed()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        elif action == "refresh_dashboard":
            dashboard_info = await get_active_dashboard()
            if not dashboard_info:
                await interaction.response.send_message(
                    "❌ **No Active Dashboard**\nNo dashboard is currently running to refresh!",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # Force refresh the dashboard
            try:
                from tasks import update_team_owner_dashboard
                await update_team_owner_dashboard(self.interaction.client)
                
                embed = discord.Embed(
                    title="✅ Dashboard Refreshed",
                    description="Team owner dashboard has been manually refreshed!",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="🔄 Update Status",
                    value="✅ Dashboard data updated with latest information",
                    inline=True
                )
                
                embed.add_field(
                    name="⏰ Next Auto-Update",
                    value="Within the next hour",
                    inline=True
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
            except Exception as e:
                await interaction.followup.send(
                    f"❌ **Refresh Failed**\nError updating dashboard: {str(e)}",
                    ephemeral=True
                )
    
    async def handle_advanced_action(self, interaction: discord.Interaction, action: str):
        """Handle advanced configuration actions."""
        await interaction.response.defer(ephemeral=True)
        
        if action == "config_audit":
            embed = discord.Embed(
                title="🔍 Configuration Audit Report",
                description="**Comprehensive configuration health check**",
                color=discord.Color.blue()
            )
            
            issues = []
            warnings = []
            successes = []
            
            # Check channels
            channel_configs = [
                ("Sign Log", await get_sign_log_channel_id()),
                ("Schedule Log", await get_schedule_log_channel_id()),
                ("Game Results", await get_game_results_channel_id()),
                ("Game Reminder", await get_game_reminder_channel_id()),
                ("Demand Log", await get_demand_log_channel_id()),
                ("Blacklist Log", await get_blacklist_log_channel_id()),
                ("Team Owner Alert", await get_team_owner_alert_channel_id()),
                ("Team Announcements", await get_team_announcements_channel_id()),
                ("LFT", await get_lft_channel_id()),
                ("Dashboard", await get_team_owner_dashboard_channel_id())
            ]
            
            for name, channel_id in channel_configs:
                if not channel_id or channel_id == 0:
                    warnings.append(f"📺 {name} channel not configured")
                else:
                    channel = self.guild.get_channel(channel_id)
                    if not channel:
                        issues.append(f"📺 {name} channel deleted (ID: {channel_id})")
                    else:
                        # Check permissions
                        perms = channel.permissions_for(self.guild.me)
                        if not (perms.send_messages and perms.embed_links):
                            issues.append(f"📺 {name} channel lacks permissions")
                        else:
                            successes.append(f"📺 {name} channel configured correctly")
            
            # Check roles
            role_configs = [
                ("Referee", await get_referee_role_id()),
                ("Official Ping", await get_official_ping_role_id()),
                ("Vice Captain", await get_vice_captain_role_id()),
                ("Free Agent", await get_free_agent_role_id())
            ]
            
            for name, role_id in role_configs:
                if not role_id or role_id == 0:
                    warnings.append(f"👥 {name} role not configured")
                else:
                    role = self.guild.get_role(role_id)
                    if not role:
                        issues.append(f"👥 {name} role deleted (ID: {role_id})")
                    else:
                        # Check if bot can manage role
                        if role.position >= self.guild.me.top_role.position:
                            warnings.append(f"👥 {name} role above bot in hierarchy")
                        else:
                            successes.append(f"👥 {name} role configured correctly")
            
            # Check access control
            all_required = await get_required_roles()
            one_of_required = await get_one_of_required_roles()
            
            for role_id in all_required:
                if not self.guild.get_role(role_id):
                    issues.append(f"🔒 ALL required role deleted (ID: {role_id})")
            
            for role_id in one_of_required:
                if not self.guild.get_role(role_id):
                    issues.append(f"🔒 One-of required role deleted (ID: {role_id})")
            
            # Check dashboard
            dashboard_info = await get_active_dashboard()
            if dashboard_info:
                message_id, channel_id = dashboard_info
                channel = self.guild.get_channel(channel_id)
                if not channel:
                    issues.append("📊 Dashboard channel deleted")
                else:
                    try:
                        await channel.fetch_message(message_id)
                        successes.append("📊 Dashboard active and healthy")
                    except:
                        warnings.append("📊 Dashboard message deleted")
            
            # Build report
            if issues:
                embed.add_field(
                    name=f"❌ Critical Issues ({len(issues)})",
                    value="\n".join(issues[:10]) + ("..." if len(issues) > 10 else ""),
                    inline=False
                )
            
            if warnings:
                embed.add_field(
                    name=f"⚠️ Warnings ({len(warnings)})",
                    value="\n".join(warnings[:10]) + ("..." if len(warnings) > 10 else ""),
                    inline=False
                )
            
            if successes:
                embed.add_field(
                    name=f"✅ Working Correctly ({len(successes)})",
                    value="\n".join(successes[:5]) + ("..." if len(successes) > 5 else ""),
                    inline=False
                )
            
            # Overall health score
            total_items = len(channel_configs) + len(role_configs) + 1  # +1 for dashboard
            healthy_items = len(successes)
            health_score = (healthy_items / total_items) * 100
            
            if health_score >= 90:
                health_color = "🟢"
                health_text = "Excellent"
            elif health_score >= 70:
                health_color = "🟡"
                health_text = "Good"
            elif health_score >= 50:
                health_color = "🟠"
                health_text = "Fair"
            else:
                health_color = "🔴"
                health_text = "Poor"
            
            embed.add_field(
                name="📊 Overall Health Score",
                value=f"{health_color} **{health_text}** ({health_score:.0f}%)",
                inline=True
            )
            
            embed.add_field(
                name="📋 Summary",
                value=(
                    f"**Issues:** {len(issues)}\n"
                    f"**Warnings:** {len(warnings)}\n"
                    f"**Working:** {len(successes)}"
                ),
                inline=True
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        elif action == "export_config":
            # Create configuration export
            config_text = "# Bot Configuration Export\n"
            config_text += f"# Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
            config_text += f"# Server: {self.guild.name} (ID: {self.guild.id})\n\n"
            
            # Channels
            config_text += "## Channels\n"
            channel_configs = [
                ("sign_log_channel_id", await get_sign_log_channel_id()),
                ("schedule_log_channel_id", await get_schedule_log_channel_id()),
                ("game_results_channel_id", await get_game_results_channel_id()),
                ("game_reminder_channel_id", await get_game_reminder_channel_id()),
                ("demand_log_channel_id", await get_demand_log_channel_id()),
                ("blacklist_log_channel_id", await get_blacklist_log_channel_id()),
                ("team_owner_alert_channel_id", await get_team_owner_alert_channel_id()),
                ("team_announcements_channel_id", await get_team_announcements_channel_id()),
                ("lft_channel_id", await get_lft_channel_id()),
                ("team_owner_dashboard_channel_id", await get_team_owner_dashboard_channel_id())
            ]
            
            for key, value in channel_configs:
                if value and value != 0:
                    channel = self.guild.get_channel(value)
                    channel_name = channel.name if channel else "DELETED"
                    config_text += f"{key} = {value} # {channel_name}\n"
                else:
                    config_text += f"{key} = 0 # Not configured\n"
            
            # Roles
            config_text += "\n## Roles\n"
            role_configs = [
                ("referee_role_id", await get_referee_role_id()),
                ("official_ping_role_id", await get_official_ping_role_id()),
                ("vice_captain_role_id", await get_vice_captain_role_id()),
                ("free_agent_role_id", await get_free_agent_role_id())
            ]
            
            for key, value in role_configs:
                if value and value != 0:
                    role = self.guild.get_role(value)
                    role_name = role.name if role else "DELETED"
                    config_text += f"{key} = {value} # {role_name}\n"
                else:
                    config_text += f"{key} = 0 # Not configured\n"
            
            # Settings
            config_text += "\n## Settings\n"
            config_text += f"team_member_cap = {await get_team_member_cap()}\n"
            config_text += f"signing_open = {await is_signing_open()}\n"
            config_text += f"max_demands_allowed = {await get_max_demands_allowed()}\n"
            
            # Access Control
            config_text += "\n## Access Control\n"
            all_required = await get_required_roles()
            one_of_required = await get_one_of_required_roles()
            
            config_text += f"required_roles_all = {all_required}\n"
            config_text += f"required_roles_one_of = {one_of_required}\n"
            
            # Dashboard
            config_text += "\n## Dashboard\n"
            dashboard_info = await get_active_dashboard()
            if dashboard_info:
                message_id, channel_id = dashboard_info
                config_text += f"dashboard_message_id = {message_id}\n"
                config_text += f"dashboard_channel_id = {channel_id}\n"
            else:
                config_text += "dashboard_active = false\n"
            
            # Send as file
            import io
            config_file = io.StringIO(config_text)
            file = discord.File(config_file, filename=f"bot_config_{self.guild.id}_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt")
            
            embed = discord.Embed(
                title="📋 Configuration Exported",
                description="Your bot configuration has been exported to a text file.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📄 Export Details",
                value=(
                    f"**Server:** {self.guild.name}\n"
                    f"**Generated:** {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                    f"**Format:** Human-readable text file"
                ),
                inline=False
            )
            
            embed.add_field(
                name="💡 Usage",
                value=(
                    "• Keep this file as a backup of your settings\n"
                    "• Use it to document your configuration\n"
                    "• Share with support if you need assistance\n"
                    "• Reference when setting up similar servers"
                ),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            
        elif action == "validate_setup":
            embed = discord.Embed(
                title="🔧 Setup Validation Report",
                description="**Validating all configured channels and roles exist**",
                color=discord.Color.blue()
            )
            
            valid_items = []
            invalid_items = []
            missing_items = []
            
            # Validate channels
            channel_settings = [
                ("Sign Log Channel", await get_sign_log_channel_id()),
                ("Schedule Log Channel", await get_schedule_log_channel_id()),
                ("Game Results Channel", await get_game_results_channel_id()),
                ("Game Reminder Channel", await get_game_reminder_channel_id()),
                ("Demand Log Channel", await get_demand_log_channel_id()),
                ("Blacklist Log Channel", await get_blacklist_log_channel_id()),
                ("Team Owner Alert Channel", await get_team_owner_alert_channel_id()),
                ("Team Announcements Channel", await get_team_announcements_channel_id()),
                ("LFT Channel", await get_lft_channel_id()),
                ("Dashboard Channel", await get_team_owner_dashboard_channel_id())
            ]
            
            for name, channel_id in channel_settings:
                if not channel_id or channel_id == 0:
                    missing_items.append(f"📺 {name}")
                else:
                    channel = self.guild.get_channel(channel_id)
                    if channel:
                        valid_items.append(f"📺 {name} → {channel.mention}")
                    else:
                        invalid_items.append(f"📺 {name} (ID: {channel_id})")
            
            # Validate roles
            role_settings = [
                ("Referee Role", await get_referee_role_id()),
                ("Official Ping Role", await get_official_ping_role_id()),
                ("Vice Captain Role", await get_vice_captain_role_id()),
                ("Free Agent Role", await get_free_agent_role_id())
            ]
            
            for name, role_id in role_settings:
                if not role_id or role_id == 0:
                    missing_items.append(f"👥 {name}")
                else:
                    role = self.guild.get_role(role_id)
                    if role:
                        valid_items.append(f"👥 {name} → {role.mention}")
                    else:
                        invalid_items.append(f"👥 {name} (ID: {role_id})")
            
            # Display results
            if valid_items:
                embed.add_field(
                    name=f"✅ Valid Configuration ({len(valid_items)})",
                    value="\n".join(valid_items[:10]) + ("..." if len(valid_items) > 10 else ""),
                    inline=False
                )
            
            if invalid_items:
                embed.add_field(
                    name=f"❌ Invalid Configuration ({len(invalid_items)})",
                    value="\n".join(invalid_items),
                    inline=False
                )
            
            if missing_items:
                embed.add_field(
                    name=f"⚪ Not Configured ({len(missing_items)})",
                    value="\n".join(missing_items[:10]) + ("..." if len(missing_items) > 10 else ""),
                    inline=False
                )
            
            # Validation summary
            total_items = len(channel_settings) + len(role_settings)
            validation_score = (len(valid_items) / total_items) * 100
            
            embed.add_field(
                name="📊 Validation Score",
                value=f"**{validation_score:.0f}%** ({len(valid_items)}/{total_items} items valid)",
                inline=True
            )
            
            if invalid_items:
                embed.add_field(
                    name="🛠️ Recommended Actions",
                    value=(
                        "• Reconfigure invalid items using this panel\n"
                        "• Check if channels/roles were renamed or deleted\n"
                        "• Run configuration audit for detailed analysis"
                    ),
                    inline=True
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        elif action == "usage_stats":
            embed = discord.Embed(
                title="📊 Configuration Usage Statistics",
                description="**Bot configuration metrics and usage analysis**",
                color=discord.Color.blue()
            )
            
            # Configuration completeness
            total_configs = 14  # 10 channels + 4 roles
            configured_count = 0
            
            # Count configured items
            all_configs = [
                await get_sign_log_channel_id(), await get_schedule_log_channel_id(),
                await get_game_results_channel_id(), await get_game_reminder_channel_id(),
                await get_demand_log_channel_id(), await get_blacklist_log_channel_id(),
                await get_team_owner_alert_channel_id(), await get_team_announcements_channel_id(),
                await get_lft_channel_id(), await get_team_owner_dashboard_channel_id(),
                await get_referee_role_id(), await get_official_ping_role_id(),
                await get_vice_captain_role_id(), await get_free_agent_role_id()
            ]
            
            for config in all_configs:
                if config and config != 0:
                    configured_count += 1
            
            completeness = (configured_count / total_configs) * 100
            
            embed.add_field(
                name="🔧 Configuration Completeness",
                value=(
                    f"**Overall:** {completeness:.0f}% ({configured_count}/{total_configs})\n"
                    f"**Channels:** {len([c for c in all_configs[:10] if c and c != 0])}/10\n"
                    f"**Roles:** {len([c for c in all_configs[10:] if c and c != 0])}/4"
                ),
                inline=True
            )
            
            # Access control stats
            all_required = await get_required_roles()
            one_of_required = await get_one_of_required_roles()
            
            embed.add_field(
                name="🔒 Access Control",
                value=(
                    f"**ALL Required Roles:** {len(all_required)}\n"
                    f"**One-Of Required Roles:** {len(one_of_required)}\n"
                    f"**Signing Status:** {'🟢 Open' if await is_signing_open() else '🔴 Closed'}"
                ),
                inline=True
            )
            
            # Server stats
            embed.add_field(
                name="🏠 Server Statistics",
                value=(
                    f"**Members:** {self.guild.member_count:,}\n"
                    f"**Text Channels:** {len(self.guild.text_channels)}\n"
                    f"**Roles:** {len(self.guild.roles)}\n"
                    f"**Bot Joined:** {self.guild.me.joined_at.strftime('%Y-%m-%d')}"
                ),
                inline=True
            )
            
            # Dashboard stats
            dashboard_active = bool(await get_active_dashboard())
            embed.add_field(
                name="📊 Dashboard Status",
                value=(
                    f"**Status:** {'🟢 Active' if dashboard_active else '🔴 Inactive'}\n"
                    f"**Team Cap:** {await get_team_member_cap()} members\n"
                    f"**Max Demands:** {await get_max_demands_allowed()} per player"
                ),
                inline=True
            )
            
            # Configuration health
            if completeness >= 90:
                health_status = "🟢 Excellent - Fully configured"
            elif completeness >= 70:
                health_status = "🟡 Good - Mostly configured"
            elif completeness >= 50:
                health_status = "🟠 Fair - Partially configured"
            else:
                health_status = "🔴 Poor - Needs configuration"
            
            embed.add_field(
                name="💊 Configuration Health",
                value=health_status,
                inline=True
            )
            
            embed.add_field(
                name="📈 Recommendations",
                value=(
                    f"• Configure remaining {total_configs - configured_count} items for full functionality\n"
                    f"• {'✅' if dashboard_active else '❌'} Set up team owner dashboard\n"
                    f"• {'✅' if len(all_required + one_of_required) > 0 else '❌'} Configure access control\n"
                    f"• Run weekly configuration audits"
                ),
                inline=False
            )
            
            embed.set_footer(text="📊 Use Configuration Audit for detailed analysis")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def refresh_current_page(self, interaction: discord.Interaction, edit_original: bool = True):
        """Refresh the current page with updated data."""
        try:
            if self.current_page == "overview":
                embed = await self.show_overview()
            elif self.current_page == "channels":
                embed = await self.create_enhanced_channels_embed()
            elif self.current_page == "roles":
                embed = await self.create_enhanced_roles_embed()
            elif self.current_page == "settings":
                embed = await self.create_enhanced_settings_embed()
            elif self.current_page == "access_control":
                embed = await self.create_enhanced_access_control_embed()
            elif self.current_page == "dashboard":
                embed = await self.create_enhanced_dashboard_embed()
            elif self.current_page == "advanced":
                embed = await self.create_enhanced_advanced_embed()
            else:
                embed = await self.show_overview()
            
            if edit_original:
                try:
                    await interaction.edit_original_response(embed=embed, view=self)
                except:
                    # If we can't edit the original, send a new ephemeral message
                    await interaction.followup.send(embed=embed, view=self, ephemeral=True)
        except Exception as e:
            print(f"Error refreshing config page: {e}")
    
    async def on_timeout(self):
        """Handle view timeout after 10 minutes."""
        for item in self.children:
            item.disabled = True
        
        try:
            embed = discord.Embed(
                title="⏰ Configuration Panel Expired",
                description="This configuration panel has expired. Use `/config` to open a new one.",
                color=discord.Color.orange()
            )
            await self.interaction.edit_original_response(embed=embed, view=self)
        except:
            pass  # Interaction might be expired

# ========================= ENHANCED ADMIN COMMANDS COG =========================

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print(f"🔧 Enhanced AdminCommands cog initialized with {len(self.__cog_app_commands__)} commands")

    async def cog_load(self):
        """Called when the cog is loaded."""
        print("🔧 Enhanced AdminCommands cog loaded successfully!")
        for command in self.__cog_app_commands__:
            print(f"  📝 Registered command: /{command.name}")


    async def sync_team_owners_from_roles(self, guild: discord.Guild):
        """
        Sync the database team owners with the current Discord role state.
        Returns a dict with sync statistics.
        """
        from config import TEAM_OWNER_ROLE_NAME
        import aiosqlite
        from config import DB_PATH
        
        stats = {
            'teams_checked': 0,
            'owners_added': 0,
            'owners_removed': 0,
            'already_correct': 0,
            'teams_without_owners': 0
        }
        
        try:
            # Get the team owner role
            team_owner_role = discord.utils.get(guild.roles, name=TEAM_OWNER_ROLE_NAME)
            if not team_owner_role:
                raise ValueError("Team Owner role not found")
            
            # Get all teams from database
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT team_id, role_id, owner_id FROM teams"
                ) as cursor:
                    teams = await cursor.fetchall()
            
            for team_id, role_id, current_owner_id in teams:
                stats['teams_checked'] += 1
                
                # Get the team role
                team_role = guild.get_role(role_id)
                if not team_role:
                    continue  # Skip deleted roles
                
                # Find actual owner from Discord roles
                actual_owner = None
                for member in team_role.members:
                    if team_owner_role in member.roles:
                        actual_owner = member
                        break
                
                # Compare with database
                actual_owner_id = actual_owner.id if actual_owner else None
                
                if actual_owner_id == current_owner_id:
                    stats['already_correct'] += 1
                else:
                    # Need to update database
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute(
                            "UPDATE teams SET owner_id = ? WHERE team_id = ?",
                            (actual_owner_id, team_id)
                        )
                        await db.commit()
                    
                    if actual_owner_id and not current_owner_id:
                        stats['owners_added'] += 1
                    elif not actual_owner_id and current_owner_id:
                        stats['owners_removed'] += 1
                    else:
                        # Owner changed
                        stats['owners_removed'] += 1
                        stats['owners_added'] += 1
                
                if not actual_owner_id:
                    stats['teams_without_owners'] += 1
            
            return stats
            
        except Exception as e:
            print(f"Error syncing team owners: {e}")
            raise

    # ========================= ENHANCED INTERACTIVE CONFIG COMMAND =========================
    
    @app_commands.command(name="config", description="🔧 Interactive bot configuration panel with enhanced features")
    async def config(self, interaction: discord.Interaction):
        """Enhanced interactive configuration panel with full featured UI."""
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            embed = discord.Embed(
                title="❌ Access Denied",
                description="You don't have permission to use the configuration panel.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Required Roles",
                value=", ".join(f"`{role}`" for role in ALLOWED_MANAGEMENT_ROLES),
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Create the enhanced configuration view
        view = EnhancedConfigView(interaction)
        embed = await view.show_overview()
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


    # ========================= LEGACY CONFIG COMMAND (COMMENTED OUT) =========================
    
    # This is the old config command - keeping it commented for reference
    # You can uncomment and rename this if you want to keep both versions
    
    # @app_commands.command(name="config-old", description="Configure bot settings (legacy)")
    # @app_commands.describe(
    #     category="Configuration category",
    #     setting="Specific setting to configure",
    #     value="Value to set (required for most settings)",
    #     action="Action for special settings like dashboard"
    # )
    # @app_commands.choices(category=[
    #     app_commands.Choice(name="Channels", value="channels"),
    #     app_commands.Choice(name="Roles", value="roles"),
    #     app_commands.Choice(name="Settings", value="settings"),
    #     app_commands.Choice(name="Dashboard", value="dashboard"),
    #     app_commands.Choice(name="View Config", value="view")
    # ])
    # async def config_old(
    #     self, 
    #     interaction: discord.Interaction, 
    #     category: app_commands.Choice[str],
    #     setting: Optional[str] = None,
    #     value: Optional[str] = None,
    #     action: Optional[str] = None
    # ):
    #     # ... legacy config implementation ...
    #     pass

    # ========================= OTHER ADMIN COMMANDS =========================
    
    @app_commands.command(name="teamowners", description="View all team owners and their teams (from Discord roles)")
    async def teamowners(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get the team owner role
            from config import TEAM_OWNER_ROLE_NAME
            team_owner_role = discord.utils.get(interaction.guild.roles, name=TEAM_OWNER_ROLE_NAME)
            
            if not team_owner_role:
                await interaction.followup.send("❌ Team Owner role not found in this server.", ephemeral=True)
                return
            
            # Get all team data from database (for emoji and identification)
            team_db_data = {}
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT team_id, role_id, emoji, name FROM teams"
                ) as cursor:
                    teams_data = await cursor.fetchall()
                    for team_id, role_id, emoji, name in teams_data:
                        team_db_data[role_id] = {
                            'team_id': team_id,
                            'emoji': emoji or "🔥",
                            'db_name': name
                        }
            
            if not team_db_data:
                await interaction.followup.send("No teams found in the database.", ephemeral=True)
                return
            
            # Process teams by checking Discord roles
            team_info_list = []
            teams_without_owners = []
            
            # Check each team role
            for role_id, team_data in team_db_data.items():
                team_role = interaction.guild.get_role(role_id)
                
                # Skip if role was deleted
                if not team_role:
                    print(f"Skipping team {team_data['db_name']} - role {role_id} not found (deleted)")
                    continue
                
                team_emoji = team_data['emoji']
                
                # Find owner by checking who has both this team role AND team owner role
                team_owner = None
                for member in team_role.members:
                    if team_owner_role in member.roles:
                        team_owner = member
                        break
                
                member_count = len(team_role.members)
                
                if team_owner:
                    team_info_list.append({
                        'emoji': team_emoji,
                        'name': team_role.name,  # Use role name as source of truth
                        'role': team_role,
                        'owner': team_owner,
                        'member_count': member_count
                    })
                else:
                    teams_without_owners.append({
                        'emoji': team_emoji,
                        'name': team_role.name,
                        'role': team_role,
                        'member_count': member_count
                    })
            
            # Sort teams alphabetically
            team_info_list.sort(key=lambda x: x['name'].lower())
            teams_without_owners.sort(key=lambda x: x['name'].lower())
            
            # Check if we have any valid teams
            total_valid_teams = len(team_info_list) + len(teams_without_owners)
            if total_valid_teams == 0:
                await interaction.followup.send("No valid teams found (all team roles have been deleted).", ephemeral=True)
                return
            
            # Create embeds for pagination
            embeds = []
            teams_per_page = 8
            
            # Main teams with owners
            if team_info_list:
                total_pages = math.ceil(len(team_info_list) / teams_per_page)
                
                for page in range(total_pages):
                    start_idx = page * teams_per_page
                    end_idx = start_idx + teams_per_page
                    page_teams = team_info_list[start_idx:end_idx]
                    
                    embed = discord.Embed(
                        title="👑 Team Owners (Role-Based View)",
                        description=f"Teams with assigned owners",
                        color=discord.Color.gold()
                    )
                    
                    for team_info in page_teams:
                        team_field_name = f"{team_info['emoji']} {team_info['name']}"
                        
                        team_field_value = (
                            f"**Owner:** {team_info['owner'].mention} ({team_info['owner'].display_name})\n"
                            f"**Team:** {team_info['role'].mention}\n"
                            f"**Members:** {team_info['member_count']}"
                        )
                        
                        embed.add_field(
                            name=team_field_name,
                            value=team_field_value,
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Page {page + 1}/{total_pages} • {len(team_info_list)} teams with owners")
                    embeds.append(embed)
            
            # Teams without owners (if any)
            if teams_without_owners:
                embed = discord.Embed(
                    title="⚠️ Teams Without Owners",
                    description="Teams that need owner assignment",
                    color=discord.Color.orange()
                )
                
                for team_info in teams_without_owners[:10]:  # Limit to 10 to avoid embed size limit
                    team_field_name = f"{team_info['emoji']} {team_info['name']}"
                    
                    team_field_value = (
                        f"**Owner:** Not assigned\n"
                        f"**Team:** {team_info['role'].mention}\n"
                        f"**Members:** {team_info['member_count']}\n"
                        f"*Use `/appoint` to assign an owner*"
                    )
                    
                    embed.add_field(
                        name=team_field_name,
                        value=team_field_value,
                        inline=False
                    )
                
                if len(teams_without_owners) > 10:
                    embed.add_field(
                        name="...",
                        value=f"And {len(teams_without_owners) - 10} more teams without owners",
                        inline=False
                    )
                
                embed.set_footer(text=f"{len(teams_without_owners)} teams without owners")
                embeds.append(embed)
            
            # Summary embed (always first)
            if embeds:
                teams_with_owners = len(team_info_list)
                teams_without = len(teams_without_owners)
                total_owners = len(team_owner_role.members)
                
                summary_text = (
                    f"**Valid Teams:** {total_valid_teams}\n"
                    f"**With Owners:** {teams_with_owners}\n"
                    f"**Without Owners:** {teams_without}\n"
                    f"**Total Team Owners:** {total_owners} members with {team_owner_role.mention} role"
                )
                
                if teams_without > 0:
                    summary_text += f"\n\n⚠️ **{teams_without} teams need owner assignment**"
                
                embeds[0].insert_field_at(0, name="📊 Summary", value=summary_text, inline=False)
            
            # Send embeds
            if not embeds:
                await interaction.followup.send("No valid team data could be processed.", ephemeral=True)
                return
            elif len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0], ephemeral=True)
            else:
                # Use pagination for multiple pages
                view = PaginatorView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view, ephemeral=True)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in teamowners command: {error_details}")
            
            try:
                await interaction.followup.send(
                    f"An error occurred while retrieving team owners: {str(e)}",
                    ephemeral=True
                )
            except Exception as response_error:
                print(f"Failed to send error response: {response_error}")

    @app_commands.command(name="check-ownerless-teams", description="Check for teams without owners (from Discord roles) and send alerts")
    async def check_ownerless_teams(self, interaction: discord.Interaction):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # First sync the database with current role state
            sync_stats = await sync_team_owners_from_roles(interaction.guild)
            
            # Get the team owner role
            from config import TEAM_OWNER_ROLE_NAME
            team_owner_role = discord.utils.get(interaction.guild.roles, name=TEAM_OWNER_ROLE_NAME)
            
            if not team_owner_role:
                await interaction.followup.send("❌ Team Owner role not found!", ephemeral=True)
                return
            
            # Get all teams
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT team_id, role_id, emoji, name FROM teams"
                ) as cursor:
                    teams = await cursor.fetchall()
            
            ownerless_teams = []
            
            for team in teams:
                team_id, role_id, emoji, name = team
                
                # Get the team role
                team_role = interaction.guild.get_role(role_id)
                if not team_role:
                    continue  # Skip deleted roles
                
                # Check if anyone with this team role also has team owner role
                has_owner = False
                for member in team_role.members:
                    if team_owner_role in member.roles:
                        has_owner = True
                        break
                
                if not has_owner:
                    ownerless_teams.append((team_id, role_id, emoji, name, None))
            
            # Send alerts for ownerless teams
            alerts_sent = 0
            for team in ownerless_teams:
                await send_team_owner_alert(
                    self.bot, 
                    team, 
                    "No owner assigned", 
                    "Role-based check discovered ownerless team"
                )
                alerts_sent += 1
            
            # Create response embed
            embed = discord.Embed(
                title="🔍 Team Ownership Check Results",
                color=discord.Color.blue() if ownerless_teams else discord.Color.green()
            )
            
            # Sync statistics
            embed.add_field(
                name="🔄 Database Sync Results",
                value=(
                    f"**Teams Checked:** {sync_stats['teams_checked']}\n"
                    f"**Already Correct:** {sync_stats['already_correct']}\n"
                    f"**Owners Added:** {sync_stats['owners_added']}\n"
                    f"**Owners Removed:** {sync_stats['owners_removed']}"
                ),
                inline=True
            )
            
            # Ownership status
            if ownerless_teams:
                embed.add_field(
                    name="⚠️ Teams Without Owners",
                    value=f"**Found:** {len(ownerless_teams)} teams\n**Alerts Sent:** {alerts_sent}",
                    inline=True
                )
                
                # List first few teams
                team_list = []
                for team in ownerless_teams[:5]:
                    team_role = interaction.guild.get_role(team[1])
                    if team_role:
                        team_list.append(f"• {team[2]} {team_role.mention}")
                
                if team_list:
                    embed.add_field(
                        name="Teams Needing Owners",
                        value="\n".join(team_list) + (f"\n*...and {len(ownerless_teams) - 5} more*" if len(ownerless_teams) > 5 else ""),
                        inline=False
                    )
            else:
                embed.add_field(
                    name="✅ All Teams Have Owners",
                    value="Every team has an assigned owner!",
                    inline=True
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
                    
        except Exception as e:
            await interaction.followup.send(f"❌ Error checking ownerless teams: {e}", ephemeral=True)

    @app_commands.command(name="closesign", description="Closes the signing period")
    async def closesign(self, interaction: discord.Interaction):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer()
        await set_signing_state(False)
        embed = discord.Embed(
            title="Signings Closed",
            description="The signing period has been closed.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="opensign", description="Opens the signing period")
    async def opensign(self, interaction: discord.Interaction):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer()
        await set_signing_state(True)
        embed = discord.Embed(
            title="Signings Opened",
            description="The signing period is now open.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    # ========================= DEBUG COMMANDS =========================
    
    @app_commands.command(name="debug-commands", description="Debug slash command registration")
    async def debug_commands(self, interaction: discord.Interaction):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get guild commands
            guild = discord.Object(id=GUILD_ID)
            guild_commands = await self.bot.tree.fetch_commands(guild=guild)
            
            # Get global commands
            global_commands = await self.bot.tree.fetch_commands()
            
            embed = discord.Embed(
                title="🔍 Command Debug Information",
                color=discord.Color.blue()
            )
            
            if guild_commands:
                guild_cmd_list = [f"• `/{cmd.name}` - {cmd.description}" for cmd in guild_commands]
                embed.add_field(
                    name=f"Guild Commands ({len(guild_commands)})",
                    value="\n".join(guild_cmd_list[:10]) + ("\n..." if len(guild_cmd_list) > 10 else ""),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Guild Commands (0)",
                    value="No guild commands found",
                    inline=False
                )
            
            if global_commands:
                global_cmd_list = [f"• `/{cmd.name}` - {cmd.description}" for cmd in global_commands]
                embed.add_field(
                    name=f"Global Commands ({len(global_commands)})",
                    value="\n".join(global_cmd_list[:5]) + ("\n..." if len(global_cmd_list) > 5 else ""),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Global Commands (0)",
                    value="No global commands found",
                    inline=False
                )
            
            # Show cog information
            admin_cog = self.bot.get_cog("AdminCommands")
            if admin_cog:
                cog_commands = admin_cog.__cog_app_commands__
                embed.add_field(
                    name=f"AdminCommands Cog ({len(cog_commands)})",
                    value=f"Loaded with {len(cog_commands)} commands",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error debugging commands: {e}", ephemeral=True)

    # ========================= LEGACY CONFIG (IF NEEDED) =========================
    
    @app_commands.command(name="config-legacy", description="Legacy configuration command with text parameters")
    @app_commands.describe(
        category="Configuration category",
        setting="Specific setting to configure",
        value="Value to set (required for most settings)",
        action="Action for special settings like dashboard"
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="Channels", value="channels"),
        app_commands.Choice(name="Roles", value="roles"),
        app_commands.Choice(name="Settings", value="settings"),
        app_commands.Choice(name="Dashboard", value="dashboard"),
        app_commands.Choice(name="View Config", value="view")
    ])
    async def config_legacy(
        self, 
        interaction: discord.Interaction, 
        category: app_commands.Choice[str],
        setting: Optional[str] = None,
        value: Optional[str] = None,
        action: Optional[str] = None
    ):
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        try:
            if category.value == "view":
                # Show the view config functionality
                await interaction.response.defer(ephemeral=True)
                
                embed = discord.Embed(
                    title="⚙️ Bot Configuration (Legacy View)",
                    description="💡 **Tip:** Use `/config` for the new interactive configuration panel!",
                    color=discord.Color.blue()
                )

                # Channel configurations
                channels = [
                    ("Sign Log Channel", await get_sign_log_channel_id()),
                    ("Schedule Log Channel", await get_schedule_log_channel_id()),
                    ("Game Results Channel", await get_game_results_channel_id()),
                    ("Game Reminder Channel", await get_game_reminder_channel_id()),
                    ("Demand Log Channel", await get_demand_log_channel_id()),
                    ("Blacklist Log Channel", await get_blacklist_log_channel_id()),
                    ("Team Owner Alert Channel", await get_team_owner_alert_channel_id()),
                    ("LFP/Recruitment Channel", await get_team_announcements_channel_id()),
                    ("LFT (Looking for Team) Channel", await get_lft_channel_id()),
                    ("Team Owner Dashboard Channel", await get_team_owner_dashboard_channel_id())
                ]

                channel_text = ""
                for name, channel_id in channels:
                    if channel_id and channel_id != 0:
                        channel = interaction.guild.get_channel(channel_id)
                        if channel:
                            channel_text += f"**{name}:** {channel.mention}\n"
                        else:
                            channel_text += f"**{name}:** Not found (`{channel_id}`)\n"
                    else:
                        channel_text += f"**{name}:** Not configured\n"

                embed.add_field(name="📺 Channels", value=channel_text, inline=False)

                # Role configurations
                roles = [
                    ("Referee Role", await get_referee_role_id()),
                    ("Official Game Ping Role", await get_official_ping_role_id()),
                    ("Free Agent Role", await get_free_agent_role_id()),
                    ("Vice Captain Role", await get_vice_captain_role_id())
                ]

                role_text = ""
                for name, role_id in roles:
                    if role_id and role_id != 0:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            role_text += f"**{name}:** {role.mention}\n"
                        else:
                            role_text += f"**{name}:** Not found (`{role_id}`)\n"
                    else:
                        role_text += f"**{name}:** Not configured\n"

                embed.add_field(name="👥 Roles", value=role_text, inline=False)

                # Required roles for signing (ALL required)
                required_role_ids = await get_required_roles()
                if required_role_ids:
                    required_roles = []
                    missing_roles = []
                    
                    for role_id in required_role_ids:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            required_roles.append(role.mention)
                        else:
                            missing_roles.append(f"Missing (`{role_id}`)")
                    
                    required_text = ""
                    if required_roles:
                        required_text += ", ".join(required_roles)
                    if missing_roles:
                        if required_text:
                            required_text += "\n⚠️ "
                        required_text += ", ".join(missing_roles)
                    
                    embed.add_field(
                        name=f"🔒 Required Roles for Signing (ALL) - ({len(required_role_ids)})",
                        value=f"{required_text}\n*Users must have ALL of these roles*",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🔒 Required Roles for Signing (ALL)",
                        value="*None required*",
                        inline=False
                    )

                # One-of required roles for signing (AT LEAST ONE required)
                one_of_required_role_ids = await get_one_of_required_roles()
                if one_of_required_role_ids:
                    one_of_required_roles = []
                    one_of_missing_roles = []
                    
                    for role_id in one_of_required_role_ids:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            one_of_required_roles.append(role.mention)
                        else:
                            one_of_missing_roles.append(f"Missing (`{role_id}`)")
                    
                    one_of_required_text = ""
                    if one_of_required_roles:
                        one_of_required_text += ", ".join(one_of_required_roles)
                    if one_of_missing_roles:
                        if one_of_required_text:
                            one_of_required_text += "\n⚠️ "
                        one_of_required_text += ", ".join(one_of_missing_roles)
                    
                    embed.add_field(
                        name=f"🔀 One-Of Required Roles for Signing ({len(one_of_required_role_ids)})",
                        value=f"{one_of_required_text}\n*Users need AT LEAST ONE of these roles*",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🔀 One-Of Required Roles for Signing",
                        value="*None configured*",
                        inline=False
                    )

                # Other settings
                cap = await get_team_member_cap()
                signing_open = await is_signing_open()
                max_demands = await get_max_demands_allowed()
                
                settings_text = f"**Team Member Cap:** {cap} members\n**Signing Open:** {'✅ Yes' if signing_open else '❌ No'}\n**Max Demands Allowed:** {max_demands} per player"
                embed.add_field(name="⚙️ General Settings", value=settings_text, inline=False)

                # Add usage examples
                embed.add_field(
                    name="📝 Usage Examples",
                    value=(
                        "**Interactive (Recommended):** `/config`\n"
                        "**Legacy Channels:** `/config-legacy category:Channels setting:sign_log_channel value:<channel_id>`\n"
                        "**Legacy Roles:** `/config-legacy category:Roles setting:referee_role value:<role_id>`\n"
                        "**Legacy Settings:** `/config-legacy category:Settings setting:team_member_cap value:10`\n"
                        "**Legacy Dashboard:** `/config-legacy category:Dashboard action:setup value:<channel_id>`"
                    ),
                    inline=False
                )

                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            elif category.value == "channels":
                if not setting or not value:
                    await interaction.response.send_message(
                        "❌ For channel configuration, provide: `setting` and `value`\n"
                        "**Available settings:** sign_log_channel, schedule_log_channel, game_results_channel, "
                        "game_reminder_channel, demand_log_channel, blacklist_log_channel, team_owner_alert_channel, "
                        "team_announcements_channel, lft_channel\n\n"
                        "💡 **Tip:** Use `/config` for the new interactive configuration panel!",
                        ephemeral=True
                    )
                    return
                
                handler = ConfigHandler(interaction)
                embed = await handler.handle_channel_config(setting, setting.replace('_', ' ').title(), value)
                await interaction.response.send_message(embed=embed)

            elif category.value == "roles":
                if not setting:
                    await interaction.response.send_message(
                        "❌ For role configuration, provide: `setting` and (usually) `value`\n"
                        "**Available settings:** referee_role, official_ping_role, vice_captain_role, free_agent_role, "
                        "add_required_role, remove_required_role, clear_required_roles, "
                        "add_one_of_required_role, remove_one_of_required_role, clear_one_of_required_roles, "
                        "view_required_roles, view_one_of_required_roles\n\n"
                        "💡 **Tip:** Use `/config` for the new interactive configuration panel!",
                        ephemeral=True
                    )
                    return
                
                if setting in ["view_required_roles", "view_one_of_required_roles"]:
                    roles_handler = RequiredRolesHandler(interaction)
                    
                    if setting == "view_required_roles":
                        embed = await roles_handler.view_roles("all")
                    else:
                        embed = await roles_handler.view_roles("one_of")
                    
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                elif setting in ["clear_required_roles", "clear_one_of_required_roles"]:
                    roles_handler = RequiredRolesHandler(interaction)
                    
                    if setting == "clear_required_roles":
                        embed = await roles_handler.clear_roles("all")
                    else:
                        embed = await roles_handler.clear_roles("one_of")
                    
                    await interaction.response.send_message(embed=embed)
                else:
                    if not value:
                        await interaction.response.send_message(
                            f"❌ Setting `{setting}` requires a `value` parameter (role ID or mention).",
                            ephemeral=True
                        )
                        return
                    
                    if setting in ["add_required_role", "remove_required_role", "add_one_of_required_role", "remove_one_of_required_role"]:
                        roles_handler = RequiredRolesHandler(interaction)
                        
                        if setting == "add_required_role":
                            embed = await roles_handler.add_role("all", value)
                        elif setting == "remove_required_role":
                            embed = await roles_handler.remove_role("all", value)
                        elif setting == "add_one_of_required_role":
                            embed = await roles_handler.add_role("one_of", value)
                        elif setting == "remove_one_of_required_role":
                            embed = await roles_handler.remove_role("one_of", value)
                        
                        await interaction.response.send_message(embed=embed)
                    else:
                        handler = ConfigHandler(interaction)
                        embed = await handler.handle_role_config(setting, setting.replace('_', ' ').title(), value)
                        await interaction.response.send_message(embed=embed)

            elif category.value == "settings":
                if not setting or not value:
                    await interaction.response.send_message(
                        "❌ For settings configuration, provide: `setting` and `value`\n"
                        "**Available settings:** team_member_cap, max_demands_allowed\n\n"
                        "💡 **Tip:** Use `/config` for the new interactive configuration panel!",
                        ephemeral=True
                    )
                    return
                
                handler = ConfigHandler(interaction)
                embed = await handler.handle_number_config(setting, setting.replace('_', ' ').title(), value)
                await interaction.response.send_message(embed=embed)

            elif category.value == "dashboard":
                if not action:
                    await interaction.response.send_message(
                        "❌ For dashboard configuration, provide: `action`\n"
                        "**Available actions:** setup, stop, status\n"
                        "**For setup:** also provide `value` with channel ID\n\n"
                        "💡 **Tip:** Use `/config` for the new interactive configuration panel!",
                        ephemeral=True
                    )
                    return
                
                handler = ConfigHandler(interaction)
                embed = await handler.handle_dashboard_config(action, value)
                
                if action == "setup":
                    await interaction.followup.send(embed=embed)
                else:
                    if action == "status":
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                    else:
                        await interaction.response.send_message(embed=embed)

        except ValueError as e:
            if category.value == "dashboard" and action == "setup":
                await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
        except Exception as e:
            if category.value == "dashboard" and action == "setup":
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(AdminCommands(bot))
    print("🔧 AdminCommands cog setup completed!")