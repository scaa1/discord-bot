# cog/ticket_commands.py
import discord
from discord import app_commands
from discord.ext import commands
from utils.permissions import has_any_role
from config import ALLOWED_MANAGEMENT_ROLES
from database.tickets import (
    init_tickets_table, get_all_tickets, get_ticket_by_channel, get_ticket_by_id,
    get_ticket_stats, cleanup_old_tickets, get_team_registration_data,
    update_ticket_status, assign_ticket
)
from database.settings import get_config_value, set_config_value
from ui.ticket_views import TicketCreationView, SupportTicketCreationView, TeamRegistrationCreationView, TicketControlView
from ui.views import PaginatorView

class TicketCommands(commands.Cog):
    """Commands for managing the ticket system."""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setuptickets", description="Set up the ticket system")
    @app_commands.describe(
        support_creation_channel="Channel where users can create support tickets",
        team_reg_creation_channel="Channel where users can create team registration tickets", 
        ticket_category="Category where all ticket channels will be created",
        log_channel="Channel for all ticket notifications",
        staff_roles="Comma-separated list of staff role mentions (e.g., @Staff1 @Staff2)"
    )
    async def setup_tickets(
        self,
        interaction: discord.Interaction,
        support_creation_channel: discord.TextChannel,
        team_reg_creation_channel: discord.TextChannel,
        ticket_category: discord.CategoryChannel,
        log_channel: discord.TextChannel,
        staff_roles: str
    ):
        """Set up the ticket system with configuration."""
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message(
                "❌ You don't have permission to set up tickets.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer()
            
            # Parse staff roles from mentions
            import re
            role_mentions = re.findall(r'<@&(\d+)>', staff_roles)
            
            if not role_mentions:
                await interaction.followup.send(
                    "❌ Invalid staff roles format. Please mention roles like: @Staff1 @Staff2",
                    ephemeral=True
                )
                return
            
            # Validate roles exist
            valid_roles = []
            for role_id in role_mentions:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    valid_roles.append(role)
                else:
                    await interaction.followup.send(
                        f"❌ Role with ID {role_id} not found.",
                        ephemeral=True
                    )
                    return
            
            # Initialize database
            await init_tickets_table()
            
            # Save configuration - FIXED VARIABLE NAMES
            await set_config_value("support_creation_channel_id", support_creation_channel.id)
            await set_config_value("team_reg_creation_channel_id", team_reg_creation_channel.id)
            await set_config_value("ticket_category_id", ticket_category.id)
            await set_config_value("ticket_log_channel_id", log_channel.id)  # Fixed variable name
            await set_config_value("ticket_staff_role_ids", ','.join(str(role.id) for role in valid_roles))
            
            # Create support ticket setup embed
            support_embed = discord.Embed(
                title="🎫 Support Ticket System",
                description="Need help with general questions, issues, or problems? Click the button below to create a support ticket!",
                color=discord.Color.blue()
            )
            
            support_embed.add_field(
                name="📋 Information",
                value=(
                    "• Tickets are private between you and staff\n"
                    "• Please be patient while waiting for a response\n"
                    "• Provide as much detail as possible"
                ),
                inline=False
            )
            
            support_embed.set_footer(text="Click the button below to create a support ticket!")
            
            # Create team registration setup embed
            team_reg_embed = discord.Embed(
                title="🏐 Team Registration System",
                description="Want to register your team to participate in the league? Click the button below to start the registration process!",
                color=discord.Color.green()
            )
            
            team_reg_embed.add_field(
                name="📋 Requirements to Register Team",
                value=(
                    "**MEMBER REQUIREMENT** 𝖨 40+ MEMBERS\n"
                    "**STATS** 𝖨 MUST HAVE A GOOD SCRIM RECORD\n"
                    "**REPUTATION** 𝖨 A GOOD REPUTATION\n"
                    "**PARTNERSHIP** 𝖨 HAVE OUR SERVER PARTNERED WITH YOUR TEAMS SERVER (@everyone ping somewhere in the discord)"
                ),
                inline=False
            )
            
            team_reg_embed.add_field(
                name="📝 Additional Requirements",
                value=(
                    "• **MUST PUT VER IN SERVER NAME**\n"
                    "• Inside the ticket put: Team Name, Role Color, Server Link, And Logo"
                ),
                inline=False
            )
            
            team_reg_embed.add_field(
                name="🎫 What to Include in Ticket",
                value=(
                    "• **Team Name** - Your team's display name\n"
                    "• **Role Color** - Hex color code (e.g., #FF5733)\n"
                    "• **Server Link** - Discord invite to your team server\n"
                    "• **Logo** - Team logo or icon image"
                ),
                inline=False
            )
            
            team_reg_embed.set_footer(text="Click the button below to start team registration!")
            
            # Create views
            support_view = SupportTicketCreationView()
            team_reg_view = TeamRegistrationCreationView()
            
            # Send to the designated channels
            support_message = await support_creation_channel.send(embed=support_embed, view=support_view)
            team_reg_message = await team_reg_creation_channel.send(embed=team_reg_embed, view=team_reg_view)
            
            # Save message IDs for persistence
            await set_config_value("support_ticket_creation_message_id", support_message.id)
            await set_config_value("team_reg_creation_message_id", team_reg_message.id)
            
            # Create configuration summary embed
            config_embed = discord.Embed(
                title="✅ Ticket System Configured",
                color=discord.Color.green()
            )
            
            config_embed.add_field(
                name="🎫 Support Creation Channel",
                value=support_creation_channel.mention,
                inline=True
            )
            
            config_embed.add_field(
                name="🏐 Team Reg Creation Channel",
                value=team_reg_creation_channel.mention,
                inline=True
            )
            
            config_embed.add_field(
                name="📁 Ticket Category",
                value=ticket_category.name,
                inline=True
            )
            
            config_embed.add_field(
                name="📢 Log Channel",
                value=log_channel.mention,
                inline=True
            )
            
            staff_role_names = ", ".join([role.name for role in valid_roles])
            config_embed.add_field(
                name="🛠️ Staff Roles",
                value=staff_role_names,
                inline=False
            )
            
            config_embed.set_footer(text="Ticket system is now active!")
            
            await interaction.followup.send(embed=config_embed)
            
        except Exception as e:
            print(f"Error setting up tickets: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                "❌ An error occurred while setting up the ticket system.",
                ephemeral=True
            )

    @app_commands.command(name="tickets", description="View and manage tickets")
    @app_commands.describe(
        status="Filter by ticket status",
        ticket_type="Filter by ticket type",
        user="Filter by user"
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="Open", value="open"),
        app_commands.Choice(name="Closed", value="closed"),
        app_commands.Choice(name="All", value="all")
    ])
    @app_commands.choices(ticket_type=[
        app_commands.Choice(name="Support", value="support"),
        app_commands.Choice(name="Team Registration", value="team_registration"),
        app_commands.Choice(name="All", value="all")
    ])
    async def list_tickets(
        self,
        interaction: discord.Interaction,
        status: str = "open",
        ticket_type: str = "all",
        user: discord.Member = None
    ):
        """List tickets with filters."""
        # Check permissions
        ticket_staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
        
        has_ticket_staff_role = False
        is_management = await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES)
        
        if ticket_staff_role_ids:
            role_ids = [int(rid.strip()) for rid in ticket_staff_role_ids.split(',') if rid.strip()]
            user_role_ids = {role.id for role in interaction.user.roles}
            has_ticket_staff_role = any(role_id in user_role_ids for role_id in role_ids)
        
        if not (is_management or has_ticket_staff_role):
            await interaction.response.send_message(
                "❌ You don't have permission to view tickets.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer()
            
            # Get tickets with filters
            filter_status = None if status == "all" else status
            filter_type = None if ticket_type == "all" else ticket_type
            
            tickets = await get_all_tickets(filter_status, filter_type)
            
            # Filter by user if specified
            if user:
                tickets = [t for t in tickets if t['user_id'] == user.id]
            
            # Note: Since we now have unified staff, no additional filtering needed
            
            if not tickets:
                embed = discord.Embed(
                    title="🎫 No Tickets Found",
                    description="No tickets match your filters.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Create paginated embeds
            embeds = []
            tickets_per_page = 10
            
            for i in range(0, len(tickets), tickets_per_page):
                page_tickets = tickets[i:i + tickets_per_page]
                
                embed = discord.Embed(
                    title="🎫 Ticket List",
                    color=discord.Color.blue()
                )
                
                for ticket in page_tickets:
                    # Get user
                    ticket_user = interaction.guild.get_member(ticket['user_id'])
                    user_display = ticket_user.display_name if ticket_user else f"User ID: {ticket['user_id']}"
                    
                    # Get assigned staff
                    assigned_display = "Unassigned"
                    if ticket['assigned_to']:
                        assigned_user = interaction.guild.get_member(ticket['assigned_to'])
                        assigned_display = assigned_user.display_name if assigned_user else f"User ID: {ticket['assigned_to']}"
                    
                    # Status emoji
                    status_emoji = "🟢" if ticket['status'] == 'open' else "🔴"
                    
                    # Type emoji
                    type_emoji = "🎫" if ticket['ticket_type'] == 'support' else "🏐"
                    
                    embed.add_field(
                        name=f"{status_emoji} {type_emoji} Ticket #{ticket['ticket_id']}",
                        value=(
                            f"**Title:** {ticket['title'] or 'No title'}\n"
                            f"**User:** {user_display}\n"
                            f"**Status:** {ticket['status'].title()}\n"
                            f"**Assigned:** {assigned_display}\n"
                            f"**Created:** <t:{int(discord.utils.parse_time(ticket['created_at']).timestamp())}:R>"
                        ),
                        inline=False
                    )
                
                embed.set_footer(text=f"Page {len(embeds) + 1} • Showing {len(page_tickets)} tickets")
                embeds.append(embed)
            
            # Send paginated response
            if len(embeds) == 1:
                await interaction.followup.send(embed=embeds[0])
            else:
                view = PaginatorView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)
                
        except Exception as e:
            print(f"Error listing tickets: {e}")
            await interaction.followup.send(
                "❌ An error occurred while retrieving tickets.",
                ephemeral=True
            )

    @app_commands.command(name="ticketinfo", description="Get detailed information about a ticket")
    @app_commands.describe(ticket_id="The ID of the ticket to view")
    async def ticket_info(self, interaction: discord.Interaction, ticket_id: int):
        """Get detailed information about a specific ticket."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Get ticket
            ticket = await get_ticket_by_id(ticket_id)
            if not ticket:
                await interaction.followup.send("❌ Ticket not found.", ephemeral=True)
                return
            
            # Check permissions
            ticket_staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
            is_management = await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES)
            is_ticket_owner = ticket['user_id'] == interaction.user.id
            
            can_view = is_management or is_ticket_owner
            
            if not can_view and ticket_staff_role_ids:
                role_ids = [int(rid.strip()) for rid in ticket_staff_role_ids.split(',') if rid.strip()]
                user_role_ids = {role.id for role in interaction.user.roles}
                can_view = any(role_id in user_role_ids for role_id in role_ids)
            
            if not can_view:
                await interaction.followup.send(
                    "❌ You don't have permission to view this ticket.",
                    ephemeral=True
                )
                return
            
            # Create detailed embed
            embed = discord.Embed(
                title=f"🎫 Ticket #{ticket_id} Details",
                color=discord.Color.blue()
            )
            
            # Get user info
            ticket_user = interaction.guild.get_member(ticket['user_id'])
            user_display = ticket_user.display_name if ticket_user else f"User ID: {ticket['user_id']}"
            
            # Get assigned staff info
            assigned_display = "Unassigned"
            if ticket['assigned_to']:
                assigned_user = interaction.guild.get_member(ticket['assigned_to'])
                assigned_display = assigned_user.display_name if assigned_user else f"User ID: {ticket['assigned_to']}"
            
            # Basic info
            embed.add_field(name="👤 User", value=user_display, inline=True)
            embed.add_field(name="📝 Type", value=ticket['ticket_type'].replace('_', ' ').title(), inline=True)
            embed.add_field(name="📊 Status", value=ticket['status'].title(), inline=True)
            
            embed.add_field(name="🏷️ Title", value=ticket['title'] or "No title", inline=False)
            
            if ticket['description']:
                embed.add_field(name="📄 Description", value=ticket['description'], inline=False)
            
            embed.add_field(name="👥 Assigned To", value=assigned_display, inline=True)
            
            # Timestamps
            created_time = int(discord.utils.parse_time(ticket['created_at']).timestamp())
            embed.add_field(name="🕐 Created", value=f"<t:{created_time}:F>", inline=True)
            
            if ticket['closed_at']:
                closed_time = int(discord.utils.parse_time(ticket['closed_at']).timestamp())
                embed.add_field(name="🔒 Closed", value=f"<t:{closed_time}:F>", inline=True)
            
            # For team registration tickets, show form data
            if ticket['ticket_type'] == 'team_registration':
                reg_data = await get_team_registration_data(ticket_id)
                if reg_data:
                    form_status = "✅ Complete" if reg_data['completed'] else "⚠️ Incomplete"
                    
                    form_info = f"**Status:** {form_status}\n"
                    if reg_data['team_name']:
                        form_info += f"**Team Name:** {reg_data['team_name']}\n"
                    if reg_data['team_role_color']:
                        form_info += f"**Role Color:** {reg_data['team_role_color']}\n"
                    
                    embed.add_field(name="🏐 Registration Form", value=form_info, inline=False)
            
            # Get channel info
            if ticket['channel_id']:
                channel = interaction.guild.get_channel(ticket['channel_id'])
                if channel:
                    embed.add_field(name="📺 Channel", value=channel.mention, inline=True)
            
            embed.timestamp = discord.utils.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error getting ticket info: {e}")
            await interaction.followup.send(
                "❌ An error occurred while retrieving ticket information.",
                ephemeral=True
            )

    @app_commands.command(name="assignticket", description="Assign a ticket to a staff member")
    @app_commands.describe(
        ticket_id="The ID of the ticket to assign",
        staff_member="The staff member to assign the ticket to"
    )
    async def assign_ticket_cmd(self, interaction: discord.Interaction, ticket_id: int, staff_member: discord.Member):
        """Assign a ticket to a staff member."""
        # Check permissions
        is_management = await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES)
        
        if not is_management:
            ticket_staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
            
            has_ticket_staff_role = False
            
            if ticket_staff_role_ids:
                role_ids = [int(rid.strip()) for rid in ticket_staff_role_ids.split(',') if rid.strip()]
                user_role_ids = {role.id for role in interaction.user.roles}
                has_ticket_staff_role = any(role_id in user_role_ids for role_id in role_ids)
            
            if not has_ticket_staff_role:
                await interaction.response.send_message(
                    "❌ You don't have permission to assign tickets.",
                    ephemeral=True
                )
                return

        try:
            await interaction.response.defer()
            
            # Get ticket
            ticket = await get_ticket_by_id(ticket_id)
            if not ticket:
                await interaction.followup.send("❌ Ticket not found.")
                return
            
            # Assign ticket
            success = await assign_ticket(ticket_id, staff_member.id)
            if not success:
                await interaction.followup.send("❌ Failed to assign ticket.")
                return
            
            # Create confirmation embed
            embed = discord.Embed(
                title="✅ Ticket Assigned",
                description=f"Ticket #{ticket_id} has been assigned to {staff_member.display_name}.",
                color=discord.Color.green()
            )
            
            embed.add_field(name="🎫 Ticket", value=f"#{ticket_id} - {ticket['title']}", inline=False)
            embed.add_field(name="👤 Assigned By", value=interaction.user.display_name, inline=True)
            embed.add_field(name="👥 Assigned To", value=staff_member.display_name, inline=True)
            
            await interaction.followup.send(embed=embed)
            
            # Notify in ticket channel if it exists
            if ticket['channel_id']:
                channel = interaction.guild.get_channel(ticket['channel_id'])
                if channel:
                    await channel.send(
                        f"📋 This ticket has been assigned to {staff_member.display_name} by {interaction.user.display_name}."
                    )
            
        except Exception as e:
            print(f"Error assigning ticket: {e}")
            await interaction.followup.send("❌ An error occurred while assigning the ticket.")

    @app_commands.command(name="ticketstats", description="View ticket system statistics")
    async def ticket_stats(self, interaction: discord.Interaction):
        """View ticket system statistics."""
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message(
                "❌ You don't have permission to view ticket statistics.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer()
            
            stats = await get_ticket_stats()
            
            embed = discord.Embed(
                title="📊 Ticket System Statistics",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🎫 Overall Stats",
                value=(
                    f"**Total Tickets:** {stats['total_tickets']}\n"
                    f"**Open Tickets:** {stats['open_tickets']}\n"
                    f"**Support Tickets:** {stats['support_tickets']}\n"
                    f"**Team Registration Tickets:** {stats['team_registration_tickets']}"
                ),
                inline=True
            )
            
            embed.add_field(
                name="🏐 Team Registrations",
                value=(
                    f"**Completed:** {stats['completed_registrations']}\n"
                    f"**In Progress:** {stats['team_registration_tickets'] - stats['completed_registrations']}"
                ),
                inline=True
            )
            
            # Calculate some percentages
            if stats['total_tickets'] > 0:
                open_percentage = round((stats['open_tickets'] / stats['total_tickets']) * 100, 1)
                support_percentage = round((stats['support_tickets'] / stats['total_tickets']) * 100, 1)
                team_reg_percentage = round((stats['team_registration_tickets'] / stats['total_tickets']) * 100, 1)
                
                embed.add_field(
                    name="📈 Breakdown",
                    value=(
                        f"**Open Rate:** {open_percentage}%\n"
                        f"**Support:** {support_percentage}%\n"
                        f"**Team Reg:** {team_reg_percentage}%"
                    ),
                    inline=True
                )
            
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text="Real-time statistics")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error getting ticket stats: {e}")
            await interaction.followup.send(
                "❌ An error occurred while retrieving statistics.",
                ephemeral=True
            )

    @app_commands.command(name="cleanuptickets", description="Clean up old closed tickets")
    @app_commands.describe(days="Number of days old tickets must be to be cleaned up (default: 30)")
    async def cleanup_tickets(self, interaction: discord.Interaction, days: int = 30):
        """Clean up old closed tickets."""
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message(
                "❌ You don't have permission to clean up tickets.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer()
            
            if days < 1:
                await interaction.followup.send("❌ Days must be at least 1.")
                return
            
            deleted_count = await cleanup_old_tickets(days)
            
            embed = discord.Embed(
                title="🧹 Ticket Cleanup Complete",
                description=f"Cleaned up {deleted_count} old closed tickets that were older than {days} days.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📊 Details",
                value=(
                    f"**Tickets Removed:** {deleted_count}\n"
                    f"**Age Threshold:** {days} days\n"
                    f"**Status:** Closed tickets only"
                ),
                inline=False
            )
            
            embed.timestamp = discord.utils.utcnow()
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error cleaning up tickets: {e}")
            await interaction.followup.send(
                "❌ An error occurred while cleaning up tickets.",
                ephemeral=True
            )

    @app_commands.command(name="forceclose", description="Force close a ticket")
    @app_commands.describe(ticket_id="The ID of the ticket to force close")
    async def force_close_ticket(self, interaction: discord.Interaction, ticket_id: int):
        """Force close a ticket (admin only)."""
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message(
                "❌ You don't have permission to force close tickets.",
                ephemeral=True
            )
            return

        try:
            await interaction.response.defer()
            
            # Get ticket
            ticket = await get_ticket_by_id(ticket_id)
            if not ticket:
                await interaction.followup.send("❌ Ticket not found.")
                return
            
            if ticket['status'] == 'closed':
                await interaction.followup.send("❌ Ticket is already closed.")
                return
            
            # Close ticket
            success = await update_ticket_status(ticket_id, 'closed', interaction.user.id)
            if not success:
                await interaction.followup.send("❌ Failed to close ticket.")
                return
            
            embed = discord.Embed(
                title="🔒 Ticket Force Closed",
                description=f"Ticket #{ticket_id} has been force closed by {interaction.user.display_name}.",
                color=discord.Color.red()
            )
            
            embed.add_field(name="🎫 Ticket", value=f"#{ticket_id} - {ticket['title']}", inline=False)
            embed.add_field(name="👤 Closed By", value=interaction.user.display_name, inline=True)
            embed.add_field(name="⚠️ Type", value="Force Close (Admin)", inline=True)
            
            await interaction.followup.send(embed=embed)
            
            # Notify in ticket channel if it exists
            if ticket['channel_id']:
                channel = interaction.guild.get_channel(ticket['channel_id'])
                if channel:
                    try:
                        await channel.send(
                            f"🔒 This ticket has been force closed by {interaction.user.display_name}.\nChannel will be deleted in 10 seconds."
                        )
                        
                        # Delete channel after delay
                        import asyncio
                        await asyncio.sleep(10)
                        await channel.delete()
                    except Exception as e:
                        print(f"Error deleting ticket channel: {e}")
            
        except Exception as e:
            print(f"Error force closing ticket: {e}")
            await interaction.followup.send("❌ An error occurred while force closing the ticket.")

    @app_commands.command(name="restoreticketviews", description="Manually restore all ticket button functionality")
    async def restore_ticket_views_command(self, interaction: discord.Interaction):
        """Manually restore all ticket views."""
        if not await has_any_role(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message(
                "❌ You don't have permission to restore ticket views.",
                ephemeral=True
            )
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            from ui.ticket_views import restore_ticket_views
            restored_count = await restore_ticket_views(self.bot)
            
            embed = discord.Embed(
                title="🔄 Ticket Views Restored",
                description=f"Successfully restored {restored_count} ticket views.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="What was restored:",
                value=(
                    "• Ticket creation panels\n"
                    "• Open ticket control buttons\n"
                    "• Team registration forms"
                ),
                inline=False
            )
            
            embed.timestamp = discord.utils.utcnow()
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error restoring ticket views: {e}")
            await interaction.followup.send(
                f"❌ Error restoring views: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(TicketCommands(bot))