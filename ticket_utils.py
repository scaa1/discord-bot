# utils/ticket_utils.py
import discord
from database.settings import get_config_value
from utils.permissions import has_any_role
from config import ALLOWED_MANAGEMENT_ROLES

async def user_has_ticket_staff_permission(user: discord.Member) -> bool:
    """Check if user has ticket staff permissions."""
    # Check if user has management roles
    if await has_any_role(user, ALLOWED_MANAGEMENT_ROLES):
        return True
    
    # Check if user has any of the configured ticket staff roles
    ticket_staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
    if ticket_staff_role_ids:
        role_ids = [int(rid.strip()) for rid in ticket_staff_role_ids.split(',') if rid.strip()]
        user_role_ids = {role.id for role in user.roles}
        return any(role_id in user_role_ids for role_id in role_ids)
    
    return False

async def get_ticket_staff_roles(guild: discord.Guild) -> list[discord.Role]:
    """Get all configured ticket staff roles."""
    ticket_staff_role_ids = await get_config_value("ticket_staff_role_ids", "")
    staff_roles = []
    
    if ticket_staff_role_ids:
        role_ids = [int(rid.strip()) for rid in ticket_staff_role_ids.split(',') if rid.strip()]
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role:
                staff_roles.append(role)
    
    return staff_roles

async def get_staff_role_names(guild: discord.Guild) -> str:
    """Get name string for all ticket staff roles (no mentions)."""
    staff_roles = await get_ticket_staff_roles(guild)
    return ", ".join([role.name for role in staff_roles]) if staff_roles else ""

async def validate_ticket_permissions(user: discord.Member, ticket_data: dict = None, require_ownership: bool = False) -> tuple[bool, str]:
    """
    Validate if user has permission to perform ticket actions.
    
    Returns:
        tuple: (has_permission: bool, reason: str)
    """
    # Check management permissions
    if await has_any_role(user, ALLOWED_MANAGEMENT_ROLES):
        return True, "Management access"
    
    # Check if user is ticket owner (if ticket data provided)
    if ticket_data and ticket_data.get('user_id') == user.id:
        if not require_ownership:
            return True, "Ticket owner"
        # For ownership-required actions, check if it's really their ticket
        return True, "Ticket owner"
    
    # Check staff roles
    if await user_has_ticket_staff_permission(user):
        return True, "Staff access"
    
    # No permissions found
    if require_ownership and ticket_data:
        return False, "Only the ticket owner can perform this action"
    else:
        return False, "You don't have permission to manage tickets"

def format_ticket_type_display(ticket_type: str) -> str:
    """Format ticket type for display."""
    type_mapping = {
        'support': '🎫 Support',
        'team_registration': '🏐 Team Registration'
    }
    return type_mapping.get(ticket_type, f"🎫 {ticket_type.replace('_', ' ').title()}")

def get_ticket_channel_name(ticket_type: str, username: str, discriminator: str) -> str:
    """Generate standardized ticket channel name."""
    if ticket_type == 'support':
        return f"support-{username}-{discriminator}"
    elif ticket_type == 'team_registration':
        return f"team-reg-{username}-{discriminator}"
    else:
        return f"ticket-{username}-{discriminator}"