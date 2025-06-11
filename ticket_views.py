# ui/ticket_views.py
import discord
from discord import app_commands
from typing import Optional, List, Dict
import asyncio
from datetime import datetime

from database.tickets import (
    create_ticket, get_ticket_by_channel, update_ticket_status,
    log_ticket_message, get_team_registration_data,
    update_team_registration_data, get_ticket_by_id
)
from database.settings import get_config_value
from utils.permissions import has_any_role
from config import ALLOWED_MANAGEMENT_ROLES


class TicketCreationView(discord.ui.View):
    """Base view for ticket creation - DO NOT USE DIRECTLY"""
    def __init__(self):
        super().__init__(timeout=None)


class SupportTicketCreationView(discord.ui.View):
    """View for creating support tickets."""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Create Support Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="create_support_ticket"
    )
    async def create_support_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create a new support ticket."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check for existing open ticket
            existing_tickets = await self._check_existing_tickets(interaction.user.id, 'support')
            if existing_tickets:
                # Try to find valid channel
                valid_channel = None
                for channel_id in existing_tickets:
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        valid_channel = channel
                        break
                
                if valid_channel:
                    await interaction.followup.send(
                        f"❌ You already have an open support ticket: {valid_channel.mention}",
                        ephemeral=True
                    )
                    return
                else:
                    # Clean up orphaned ticket
                    await self._cleanup_orphaned_tickets(existing_tickets)
            
            # Get ticket category
            category_id = await get_config_value("ticket_category_id")
            if not category_id:
                await interaction.followup.send(
                    "❌ Ticket system is not properly configured. Please contact an administrator.",
                    ephemeral=True
                )
                return
            
            category = interaction.guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send(
                    "❌ Ticket category not found. Please contact an administrator.",
                    ephemeral=True
                )
                return
            
            # Create ticket channel
            channel_name = f"support-{interaction.user.name}-{interaction.user.discriminator}"
            
            # Get staff roles
            staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_permissions=True
                )
            }
            
            # Add staff roles
            if staff_role_ids:
                role_ids = [int(rid.strip()) for rid in staff_role_ids.split(',') if rid.strip()]
                for role_id in role_ids:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True
                        )
            
            # Create channel
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Support ticket created by {interaction.user}"
            )
            
            # Create ticket in database
            ticket_id = await create_ticket(
                ticket_channel.id,
                interaction.user.id,
                'support',
                title=f"Support ticket by {interaction.user.display_name}"
            )
            
            # Create welcome embed
            embed = discord.Embed(
                title="🎫 Support Ticket",
                description=f"Welcome {interaction.user.mention}!\n\n"
                           "Please describe your issue in detail. A staff member will assist you shortly.",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="📋 Guidelines",
                value="• Be patient while waiting for staff\n"
                      "• Provide as much detail as possible\n"
                      "• Be respectful to staff members",
                inline=False
            )
            
            embed.set_footer(text=f"Ticket ID: {ticket_id}")
            
            # Send welcome message with control panel
            control_view = TicketControlView()
            await ticket_channel.send(
                content=f"{interaction.user.mention} - Your support ticket has been created!",
                embed=embed,
                view=control_view
            )
            
            # Send confirmation
            await interaction.followup.send(
                f"✅ Your support ticket has been created: {ticket_channel.mention}",
                ephemeral=True
            )
            
            # Log to ticket log channel
            await self._log_ticket_creation(interaction.guild, ticket_id, interaction.user, 'support', ticket_channel)
            
        except Exception as e:
            print(f"Error creating support ticket: {e}")
            await interaction.followup.send(
                "❌ An error occurred while creating your ticket. Please try again later.",
                ephemeral=True
            )
    
    async def _check_existing_tickets(self, user_id: int, ticket_type: str) -> List[int]:
        """Check if user has existing open tickets."""
        from database.tickets import get_all_tickets
        tickets = await get_all_tickets(status='open', ticket_type=ticket_type)
        return [t['channel_id'] for t in tickets if t['user_id'] == user_id]
    
    async def _cleanup_orphaned_tickets(self, channel_ids: List[int]):
        """Clean up tickets where channels no longer exist."""
        for channel_id in channel_ids:
            ticket = await get_ticket_by_channel(channel_id)
            if ticket:
                await update_ticket_status(ticket['ticket_id'], 'closed')
                print(f"Cleaned up orphaned ticket #{ticket['ticket_id']} (channel {channel_id} not found)")
    
    async def _log_ticket_creation(self, guild: discord.Guild, ticket_id: int, user: discord.User, 
                                  ticket_type: str, channel: discord.TextChannel):
        """Log ticket creation to the log channel."""
        log_channel_id = await get_config_value("ticket_log_channel_id")
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
        
        embed = discord.Embed(
            title="🎫 New Ticket Created",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Type", value=ticket_type.replace('_', ' ').title(), inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="ID", value=f"#{ticket_id}", inline=True)
        
        await log_channel.send(embed=embed)


class TeamRegistrationCreationView(discord.ui.View):
    """View for creating team registration tickets."""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Register Team",
        style=discord.ButtonStyle.success,
        emoji="🏐",
        custom_id="create_team_registration"
    )
    async def create_team_registration(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create a new team registration ticket."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check for existing registration ticket
            support_view = SupportTicketCreationView()  # Reuse check method
            existing_tickets = await support_view._check_existing_tickets(interaction.user.id, 'team_registration')
            if existing_tickets:
                # Try to find valid channel
                valid_channel = None
                for channel_id in existing_tickets:
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        valid_channel = channel
                        break
                
                if valid_channel:
                    await interaction.followup.send(
                        f"❌ You already have an open team registration: {valid_channel.mention}",
                        ephemeral=True
                    )
                    return
                else:
                    # Clean up orphaned tickets
                    await support_view._cleanup_orphaned_tickets(existing_tickets)
            
            # Get ticket category
            category_id = await get_config_value("ticket_category_id")
            if not category_id:
                await interaction.followup.send(
                    "❌ Ticket system is not properly configured. Please contact an administrator.",
                    ephemeral=True
                )
                return
            
            category = interaction.guild.get_channel(category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send(
                    "❌ Ticket category not found. Please contact an administrator.",
                    ephemeral=True
                )
                return
            
            # Create ticket channel
            channel_name = f"team-reg-{interaction.user.name}-{interaction.user.discriminator}"
            
            # Get staff roles
            staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_permissions=True
                )
            }
            
            # Add staff roles
            if staff_role_ids:
                role_ids = [int(rid.strip()) for rid in staff_role_ids.split(',') if rid.strip()]
                for role_id in role_ids:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True
                        )
            
            # Create channel
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                reason=f"Team registration created by {interaction.user}"
            )
            
            # Create ticket in database
            ticket_id = await create_ticket(
                ticket_channel.id,
                interaction.user.id,
                'team_registration',
                title=f"Team registration by {interaction.user.display_name}"
            )
            
            # Create welcome embed
            embed = discord.Embed(
                title="🏐 Team Registration",
                description=f"Welcome {interaction.user.mention}!\n\n"
                           "Let's get your team registered! Please provide the following information:",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="📋 Required Information",
                value="• **Team Name** - Your team's display name\n"
                      "• **Role Color** - Hex color code (e.g., #FF5733)\n"
                      "• **Server Link** - Discord invite to your team server\n"
                      "• **Logo** - Team logo or icon image",
                inline=False
            )
            
            embed.add_field(
                name="✅ Requirements Checklist",
                value="• 50+ members in your server\n"
                      "• Good scrim record\n"
                      "• Good reputation\n"
                      "• ORL partnered in your server\n"
                      "• Must put 'ORL' in server name",
                inline=False
            )
            
            embed.set_footer(text=f"Ticket ID: {ticket_id}")
            
            # Create registration form view
            form_view = CombinedTeamRegistrationView(ticket_id)
            
            # Send welcome message
            await ticket_channel.send(
                content=f"{interaction.user.mention} - Let's register your team!",
                embed=embed,
                view=form_view
            )
            
            # Send confirmation
            await interaction.followup.send(
                f"✅ Your team registration has been created: {ticket_channel.mention}",
                ephemeral=True
            )
            
            # Log to ticket log channel
            support_view = SupportTicketCreationView()
            await support_view._log_ticket_creation(interaction.guild, ticket_id, interaction.user, 'team_registration', ticket_channel)
            
        except Exception as e:
            print(f"Error creating team registration ticket: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                "❌ An error occurred while creating your registration. Please try again later.",
                ephemeral=True
            )


class TeamRegistrationView(discord.ui.View):
    """View for team registration form - LEGACY, use CombinedTeamRegistrationView instead."""
    def __init__(self, ticket_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id


class CombinedTeamRegistrationView(discord.ui.View):
    """Combined view with button to open modal and close ticket button."""
    def __init__(self, ticket_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
    
    @discord.ui.button(
        label="Fill Registration Form",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="open_registration_form"
    )
    async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the registration form modal."""
        # Check if user is ticket owner
        ticket = await get_ticket_by_channel(interaction.channel.id)
        if not ticket or ticket['user_id'] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Only the ticket owner can fill out this form.",
                ephemeral=True
            )
            return
        
        # Get existing data if any
        existing_data = await get_team_registration_data(self.ticket_id)
        
        # Create and send modal
        modal = TeamRegistrationModal(self.ticket_id, existing_data)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="close_team_reg_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the ticket."""
        # Check permissions
        ticket = await get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
            return
        
        # Check if user can close
        is_owner = ticket['user_id'] == interaction.user.id
        is_staff = await self._user_is_staff(interaction.user)
        
        if not (is_owner or is_staff):
            await interaction.response.send_message(
                "❌ Only the ticket owner or staff can close this ticket.",
                ephemeral=True
            )
            return
        
        # Show confirmation view
        confirm_view = TicketCloseConfirmView(interaction.user.id)
        await interaction.response.send_message(
            "⚠️ Are you sure you want to close this ticket?",
            view=confirm_view,
            ephemeral=True
        )
    
    async def _user_is_staff(self, user: discord.Member) -> bool:
        """Check if user is staff."""
        if await has_any_role(user, ALLOWED_MANAGEMENT_ROLES):
            return True
        
        staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
        if staff_role_ids:
            role_ids = [int(rid.strip()) for rid in staff_role_ids.split(',') if rid.strip()]
            user_role_ids = {role.id for role in user.roles}
            return any(role_id in user_role_ids for role_id in role_ids)
        
        return False


class TeamRegistrationModal(discord.ui.Modal):
    """Modal for team registration form."""
    def __init__(self, ticket_id: int, existing_data: Optional[Dict] = None):
        super().__init__(title="Team Registration Form")
        self.ticket_id = ticket_id
        
        # Team Name
        self.team_name = discord.ui.TextInput(
            label="Team Name",
            placeholder="Enter your team's name",
            required=True,
            max_length=100,
            default=existing_data['team_name'] if existing_data and existing_data['team_name'] else None
        )
        self.add_item(self.team_name)
        
        # Role Color
        self.role_color = discord.ui.TextInput(
            label="Role Color (Hex Code)",
            placeholder="e.g., #FF5733",
            required=True,
            max_length=7,
            min_length=7,
            default=existing_data['team_role_color'] if existing_data and existing_data['team_role_color'] else None
        )
        self.add_item(self.role_color)
        
        # Server Invite
        self.invite_link = discord.ui.TextInput(
            label="Discord Server Invite Link",
            placeholder="https://discord.gg/...",
            required=True,
            max_length=100,
            default=existing_data['invite_link'] if existing_data and existing_data['invite_link'] else None
        )
        self.add_item(self.invite_link)
        
        # Logo URL
        self.logo_url = discord.ui.TextInput(
            label="Team Logo URL (or describe it)",
            placeholder="Link to logo image or description",
            required=False,
            max_length=500,
            style=discord.TextStyle.long,
            default=existing_data['logo_icon'] if existing_data and existing_data['logo_icon'] else None
        )
        self.add_item(self.logo_url)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        try:
            # Validate hex color
            color_value = self.role_color.value.strip()
            if not color_value.startswith('#') or len(color_value) != 7:
                await interaction.response.send_message(
                    "❌ Invalid color format. Please use hex format like #FF5733",
                    ephemeral=True
                )
                return
            
            try:
                # Try to parse the color
                int(color_value[1:], 16)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid hex color code.",
                    ephemeral=True
                )
                return
            
            # Update database
            success = await update_team_registration_data(
                self.ticket_id,
                team_name=self.team_name.value.strip(),
                team_role_color=color_value,
                invite_link=self.invite_link.value.strip(),
                logo_icon=self.logo_url.value.strip() if self.logo_url.value else None,
                completed=True
            )
            
            if not success:
                await interaction.response.send_message(
                    "❌ Failed to save registration data.",
                    ephemeral=True
                )
                return
            
            # Create summary embed
            embed = discord.Embed(
                title="✅ Registration Form Submitted",
                color=int(color_value[1:], 16),  # Use their chosen color
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(name="Team Name", value=self.team_name.value, inline=True)
            embed.add_field(name="Role Color", value=color_value, inline=True)
            embed.add_field(name="Server Invite", value=self.invite_link.value, inline=False)
            
            if self.logo_url.value:
                embed.add_field(name="Logo", value=self.logo_url.value[:200], inline=False)
            
            embed.set_footer(text="A staff member will review your application soon!")
            
            await interaction.response.send_message(embed=embed)
            
            # Post the invite link in chat
            await interaction.followup.send(
                f"**Team Server Invite Link:** {self.invite_link.value.strip()}"
            )
            
            # Notify staff
            log_channel_id = await get_config_value("ticket_log_channel_id")
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    notify_embed = discord.Embed(
                        title="📝 Team Registration Form Completed",
                        description=f"User {interaction.user.mention} has completed their team registration form.",
                        color=discord.Color.blue(),
                        timestamp=datetime.utcnow()
                    )
                    notify_embed.add_field(
                        name="Team Name",
                        value=self.team_name.value,
                        inline=True
                    )
                    notify_embed.add_field(
                        name="Channel",
                        value=interaction.channel.mention,
                        inline=True
                    )
                    
                    await log_channel.send(embed=notify_embed)
            
        except Exception as e:
            print(f"Error in registration form submission: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while submitting your form.",
                ephemeral=True
            )


class TicketControlView(discord.ui.View):
    """Control panel for ticket management."""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the ticket."""
        # Get ticket info
        ticket = await get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ This channel is not a ticket.",
                ephemeral=True
            )
            return
        
        # Check permissions
        is_owner = ticket['user_id'] == interaction.user.id
        is_staff = await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES)
        
        # Check ticket staff roles
        if not is_staff:
            staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
            if staff_role_ids:
                role_ids = [int(rid.strip()) for rid in staff_role_ids.split(',') if rid.strip()]
                user_role_ids = {role.id for role in interaction.user.roles}
                is_staff = any(role_id in user_role_ids for role_id in role_ids)
        
        if not (is_owner or is_staff):
            await interaction.response.send_message(
                "❌ Only the ticket owner or staff can close tickets.",
                ephemeral=True
            )
            return
        
        # Show confirmation
        confirm_view = TicketCloseConfirmView(interaction.user.id)
        await interaction.response.send_message(
            "⚠️ Are you sure you want to close this ticket?\nThe channel will be deleted in 10 seconds after confirmation.",
            view=confirm_view,
            ephemeral=True
        )
    
    @discord.ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🙋",
        custom_id="claim_ticket"
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Claim the ticket (staff only)."""
        # Check if staff
        is_staff = await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES)
        
        if not is_staff:
            staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
            if staff_role_ids:
                role_ids = [int(rid.strip()) for rid in staff_role_ids.split(',') if rid.strip()]
                user_role_ids = {role.id for role in interaction.user.roles}
                is_staff = any(role_id in user_role_ids for role_id in role_ids)
        
        if not is_staff:
            await interaction.response.send_message(
                "❌ Only staff members can claim tickets.",
                ephemeral=True
            )
            return
        
        # Get ticket
        ticket = await get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ This channel is not a ticket.",
                ephemeral=True
            )
            return
        
        # Check if already assigned
        if ticket['assigned_to']:
            assigned_user = interaction.guild.get_member(ticket['assigned_to'])
            if assigned_user:
                await interaction.response.send_message(
                    f"❌ This ticket is already assigned to {assigned_user.mention}.",
                    ephemeral=True
                )
                return
        
        # Assign ticket
        from database.tickets import assign_ticket
        success = await assign_ticket(ticket['ticket_id'], interaction.user.id)
        
        if success:
            embed = discord.Embed(
                title="🙋 Ticket Claimed",
                description=f"This ticket has been claimed by {interaction.user.mention}",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            await interaction.response.send_message(embed=embed)
            
            # Log to ticket log
            log_channel_id = await get_config_value("ticket_log_channel_id")
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="🙋 Ticket Claimed",
                        color=discord.Color.blue(),
                        timestamp=datetime.utcnow()
                    )
                    log_embed.add_field(name="Ticket", value=f"#{ticket['ticket_id']}", inline=True)
                    log_embed.add_field(name="Claimed by", value=interaction.user.mention, inline=True)
                    log_embed.add_field(name="Channel", value=interaction.channel.mention, inline=True)
                    
                    await log_channel.send(embed=log_embed)
        else:
            await interaction.response.send_message(
                "❌ Failed to claim ticket.",
                ephemeral=True
            )


class TicketCloseConfirmView(discord.ui.View):
    """Confirmation view for closing tickets."""
    def __init__(self, user_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
    
    @discord.ui.button(
        label="Confirm Close",
        style=discord.ButtonStyle.danger,
        emoji="✅"
    )
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm ticket closure."""
        # Verify it's the same user
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Only the user who initiated the close can confirm.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        # Get ticket
        ticket = await get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.followup.send("❌ Ticket not found.")
            return
        
        # Update ticket status
        await update_ticket_status(ticket['ticket_id'], 'closed', interaction.user.id)
        
        # Log closure
        log_channel_id = await get_config_value("ticket_log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                ticket_user = interaction.guild.get_member(ticket['user_id'])
                
                embed = discord.Embed(
                    title="🔒 Ticket Closed",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                
                embed.add_field(
                    name="Ticket",
                    value=f"#{ticket['ticket_id']} - {ticket['title'] or 'No title'}",
                    inline=False
                )
                embed.add_field(
                    name="User",
                    value=ticket_user.mention if ticket_user else f"User ID: {ticket['user_id']}",
                    inline=True
                )
                embed.add_field(
                    name="Closed by",
                    value=interaction.user.mention,
                    inline=True
                )
                embed.add_field(
                    name="Type",
                    value=ticket['ticket_type'].replace('_', ' ').title(),
                    inline=True
                )
                
                # Add team registration info if applicable
                if ticket['ticket_type'] == 'team_registration':
                    reg_data = await get_team_registration_data(ticket['ticket_id'])
                    if reg_data and reg_data['completed']:
                        embed.add_field(
                            name="Team Name",
                            value=reg_data['team_name'] or "Not provided",
                            inline=True
                        )
                
                await log_channel.send(embed=embed)
        
        # Send closing message
        await interaction.followup.send(
            "🔒 Ticket closed. This channel will be deleted in 10 seconds..."
        )
        
        # Delete channel after delay
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except:
            pass
        
        self.stop()
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        emoji="❌"
    )
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel ticket closure."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Only the user who initiated the close can cancel.",
                ephemeral=True
            )
            return
        
        await interaction.response.edit_message(
            content="Ticket closure cancelled.",
            view=None
        )
        self.stop()


async def restore_ticket_views(bot):
    """Restore all active ticket views on bot startup."""
    try:
        from database.tickets import get_all_tickets
        from database.settings import get_config_value
        
        restored_count = 0
        
        # Restore ticket creation panels
        support_msg_id = await get_config_value("support_ticket_creation_message_id")
        team_reg_msg_id = await get_config_value("team_reg_creation_message_id")
        support_channel_id = await get_config_value("support_creation_channel_id")
        team_reg_channel_id = await get_config_value("team_reg_creation_channel_id")
        
        # Restore support ticket panel
        if support_msg_id and support_channel_id:
            for guild in bot.guilds:
                channel = guild.get_channel(support_channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(support_msg_id)
                        view = SupportTicketCreationView()
                        await message.edit(view=view)
                        restored_count += 1
                    except discord.NotFound:
                        print(f"Support ticket message {support_msg_id} not found")
                    except Exception as e:
                        print(f"Error restoring support ticket view: {e}")
        
        # Restore team registration panel
        if team_reg_msg_id and team_reg_channel_id:
            for guild in bot.guilds:
                channel = guild.get_channel(team_reg_channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(team_reg_msg_id)
                        view = TeamRegistrationCreationView()
                        await message.edit(view=view)
                        restored_count += 1
                    except discord.NotFound:
                        print(f"Team registration message {team_reg_msg_id} not found")
                    except Exception as e:
                        print(f"Error restoring team registration view: {e}")
        
        # Restore ticket control panels in open tickets
        open_tickets = await get_all_tickets(status='open')
        
        for ticket in open_tickets:
            channel_id = ticket['channel_id']
            
            # Find the channel
            channel = None
            for guild in bot.guilds:
                channel = guild.get_channel(channel_id)
                if channel:
                    break
            
            if not channel:
                continue
            
            # Look for messages with buttons in the first 10 messages
            try:
                async for message in channel.history(limit=10, oldest_first=True):
                    if message.author == bot.user and message.embeds:
                        # Check if it's the welcome message
                        if any("Guidelines" in field.name for embed in message.embeds for field in embed.fields):
                            if ticket['ticket_type'] == 'team_registration':
                                # Team registration form
                                view = CombinedTeamRegistrationView(ticket['ticket_id'])
                            else:
                                # Support ticket control
                                view = TicketControlView()
                            
                            await message.edit(view=view)
                            restored_count += 1
                            break
            except Exception as e:
                print(f"Error restoring view for ticket {ticket['ticket_id']}: {e}")
        
        return restored_count
        
    except Exception as e:
        print(f"Error in restore_ticket_views: {e}")
        import traceback
        traceback.print_exc()
        return 0