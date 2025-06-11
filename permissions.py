import discord
from database.settings import get_vice_captain_role_id
import aiosqlite  # ADD THIS
from config import TEAM_OWNER_ROLE_NAME, DB_PATH

async def has_any_role(member: discord.Member, role_names: list[str]) -> bool:
    """Check if a member has any of the specified roles by name."""
    member_roles = [role.name for role in member.roles]
    return any(role in role_names for role in member_roles)

def user_is_team_owner(user: discord.Member) -> bool:
    """Check if user has team owner role."""
    owner_role = discord.utils.get(user.guild.roles, name=TEAM_OWNER_ROLE_NAME)
    return owner_role in user.roles if owner_role else False

async def user_has_coach_role_async(user: discord.Member) -> tuple[bool, list]:
    """Check if user has the vice captain role."""
    coach_roles_found = []
    vice_captain_role_id = await get_vice_captain_role_id()
    
    if vice_captain_role_id and vice_captain_role_id != 0:
        role = user.guild.get_role(vice_captain_role_id)
        if role and role in user.roles:
            coach_roles_found.append("vice captain")
    
    return len(coach_roles_found) > 0, coach_roles_found

async def get_valid_coach_roles(guild: discord.Guild) -> list[discord.Role]:
    """Get the valid vice captain role from the guild."""
    roles = []
    vice_captain_role_id = await get_vice_captain_role_id()
    if vice_captain_role_id and vice_captain_role_id != 0:
        role = guild.get_role(vice_captain_role_id)
        if role:
            roles.append(role)
    return roles


async def user_has_team_role(user: discord.Member, guild: discord.Guild) -> tuple[discord.Role, dict] | tuple[None, None]:
    """Check if user has any team role by checking actual Discord roles and database."""
    try:
        from database.teams import get_team_by_role
        
        # Get all team roles from database
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT role_id, emoji, name FROM teams") as cursor:
                teams = await cursor.fetchall()
        
        # Check if user has any of these team roles
        for role_id, emoji, name in teams:
            team_role = guild.get_role(role_id)
            if team_role and team_role in user.roles:
                # Get full team data
                team_data = await get_team_by_role(role_id)
                if team_data:
                    team_info = {
                        'team_id': team_data[0],
                        'role_id': team_data[1], 
                        'emoji': team_data[2],
                        'name': team_data[3],
                        'owner_id': team_data[4] if len(team_data) > 4 else None
                    }
                    return team_role, team_info
        
        return None, None
        
    except Exception as e:
        print(f"Error checking team role: {e}")
        return None, None