import discord
from datetime import datetime
from database.settings import get_team_owner_alert_channel_id
from utils.emoji_helpers import get_emoji_thumbnail_url, add_team_emoji_thumbnail

async def send_team_owner_alert(bot_instance, team_data, reason, additional_info=""):
    """
    Send an alert when a team loses its owner
    
    Args:
        bot_instance: The bot instance
        team_data: Tuple of (team_id, role_id, emoji, name, owner_id)
        reason: Reason for losing owner (e.g., "left server", "unappointed", "role removed")
        additional_info: Additional context information
    """
    try:
        alert_channel_id = await get_team_owner_alert_channel_id()
        if not alert_channel_id or alert_channel_id == 0:
            print("Team owner alert channel not configured")
            return
        
        # Find the channel across all guilds
        alert_channel = None
        for guild in bot_instance.guilds:
            channel = guild.get_channel(alert_channel_id)
            if channel:
                alert_channel = channel
                break
        
        if not alert_channel:
            print(f"Team owner alert channel {alert_channel_id} not found")
            return

        team_id, role_id, team_emoji, team_name, former_owner_id = team_data
        guild = alert_channel.guild
        
        # Get team role and current member count
        team_role = guild.get_role(role_id)
        member_count = len(team_role.members) if team_role else 0
        
        # Create alert embed
        embed = discord.Embed(
            title="⚠️ Team Owner Alert",
            description=f"Team **{team_emoji} {team_name}** no longer has an owner!",
            color=discord.Color.orange()
        )
        
        # Add team emoji thumbnail
        thumbnail_url = get_emoji_thumbnail_url(team_emoji)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        
        embed.add_field(
            name="🏐 Team Details",
            value=(
                f"**Name:** {team_emoji} {team_name}\n"
                f"**Role:** {team_role.mention if team_role else 'Role not found'}\n"
                f"**Members:** {member_count}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📋 Issue Details",
            value=(
                f"**Reason:** {reason}\n"
                f"**When:** <t:{int(datetime.utcnow().timestamp())}:R>"
                + (f"\n**Info:** {additional_info}" if additional_info else "")
            ),
            inline=True
        )
        
        # Add former owner info if available
        if former_owner_id:
            former_owner = guild.get_member(former_owner_id)
            if former_owner:
                embed.add_field(
                    name="👤 Former Owner",
                    value=f"{former_owner.mention} ({former_owner.display_name})",
                    inline=False
                )
            else:
                embed.add_field(
                    name="👤 Former Owner",
                    value=f"User ID: {former_owner_id} (no longer in server)",
                    inline=False
                )
        
        embed.add_field(
            name="🛠️ Action Required",
            value=(
                f"Use `/appoint user:@NewOwner team_role:{team_role.mention if team_role else '@TeamRole'}` "
                f"to assign a new owner to this team."
            ),
            inline=False
        )
        
        embed.set_footer(text="Team Owner Alert System")
        embed.timestamp = discord.utils.utcnow()
        
        await alert_channel.send(embed=embed)
        print(f"Sent team owner alert for {team_name}")
        
    except Exception as e:
        print(f"Error sending team owner alert: {e}")