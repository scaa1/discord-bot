import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

# Import configuration
from config import DB_PATH, GUILD_ID

# Import database functions
from database.players import get_player, is_user_blacklisted
from database.settings import (
    get_team_announcements_channel_id, get_lft_channel_id, 
    get_team_member_cap, get_free_agent_role_id, get_required_roles,
    get_max_demands_allowed
)

# Import utility functions
from utils.permissions import user_is_team_owner, user_has_coach_role_async
from utils.emoji_helpers import get_emoji_thumbnail_url

# Import UI components
from ui.views import LFPAnnouncementView

class RecruitmentCommands(commands.Cog):
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

    @app_commands.command(name="lfp", description="Post a 'Looking for Players' recruitment message")
    @app_commands.describe(
        text="Your recruitment message (what you're looking for)",
        link="URL link to application/contact info"
    )
    async def lfp(self, interaction: discord.Interaction, text: str, link: str):
        try:
            # Check if user is authorized (team owner or vice captain)
            is_authorized = False
            user_team = None
            
            # Check if team owner
            if user_is_team_owner(interaction.user):
                is_authorized = True
                user_team = await self.get_user_team_by_role(interaction.user)
            else:
                # Check if vice captain
                has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                if has_coach_role:
                    is_authorized = True
                    user_team = await self.get_user_team_by_role(interaction.user)
            
            if not is_authorized:
                await interaction.response.send_message(
                    "❌ Only team owners and vice captains can post recruitment messages.", 
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            if not user_team:
                await interaction.followup.send(
                    "❌ You are not on any registered team.", 
                    ephemeral=True
                )
                return

            # Validate URL
            if not (link.startswith('http://') or link.startswith('https://')):
                await interaction.followup.send(
                    "❌ Please provide a valid URL (must start with http:// or https://)", 
                    ephemeral=True
                )
                return

            # Get team data
            team_id, role_id, team_emoji, team_name = user_team
            team_role = interaction.guild.get_role(role_id)
            
            if not team_role:
                await interaction.followup.send("❌ Your team role could not be found.", ephemeral=True)
                return

            # Get announcements channel
            announcements_channel_id = await get_team_announcements_channel_id()
            if not announcements_channel_id or announcements_channel_id == 0:
                await interaction.followup.send(
                    "❌ LFP/recruitment channel is not configured. Ask an admin to set it up with `/config`.", 
                    ephemeral=True
                )
                return

            announcements_channel = interaction.guild.get_channel(announcements_channel_id)
            if not announcements_channel:
                await interaction.followup.send(
                    "❌ LFP/recruitment channel not found. Please check configuration.", 
                    ephemeral=True
                )
                return

            # Determine user's role on the team
            user_role_title = "Team Member"
            if user_is_team_owner(interaction.user):
                user_role_title = "Team Owner"
            else:
                has_coach_role, coach_roles = await user_has_coach_role_async(interaction.user)
                if coach_roles:
                    # Use "Vice Captain" as the title
                    user_role_title = "Vice Captain"

            # Get current team size
            cap = await get_team_member_cap()
            current_size = len(team_role.members)
            spots_available = cap - current_size

            # Create the LFP embed with automatic team info
            embed = discord.Embed(
                title=f"🔍 {team_emoji} {team_name} - Looking for Players",
                description=text,
                color=discord.Color.green()
            )
            # Add team emoji thumbnail
            thumbnail_url = get_emoji_thumbnail_url(team_emoji)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            embed.add_field(
                name="🏐 Team", 
                value=f"{team_emoji} {team_role.mention}", 
                inline=True
            )
            
            embed.add_field(
                name="👥 Roster Status", 
                value=f"{current_size}/{cap} members\n{spots_available} spots available", 
                inline=True
            )
            
            embed.add_field(
                name="📞 Contact", 
                value=f"{interaction.user.mention} ({user_role_title})", 
                inline=True
            )
            
            if spots_available <= 0:
                embed.add_field(
                    name="⚠️ Notice", 
                    value="Team is currently full, but may have openings soon!", 
                    inline=False
                )
                embed.color = discord.Color.orange()
            
            embed.set_footer(text=f"Posted by {interaction.user.display_name} • Looking for Players")
            embed.timestamp = discord.utils.utcnow()

            # Create the view with link button (using default text "Join Here")
            view = LFPAnnouncementView(link, "🎮 Join Here")

            # Post to announcements channel
            try:
                await announcements_channel.send(embed=embed, view=view)
                
                # Send confirmation to user
                await interaction.followup.send(
                    f"✅ Looking for Players post sent successfully to {announcements_channel.mention}!\n\n"
                    f"**Team:** {team_emoji} {team_name}\n"
                    f"**Message:** {text[:100]}{'...' if len(text) > 100 else ''}\n"
                    f"**Link:** {link}", 
                    ephemeral=True
                )
                
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have permission to post in the LFP/recruitment channel.", 
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Error posting LFP message: {str(e)}", 
                    ephemeral=True
                )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in lfp command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ An error occurred while posting the LFP message: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ An error occurred while posting the LFP message: {str(e)}",
                    ephemeral=True
                )

    @app_commands.command(name="lft", description="Post a 'Looking for Team' message to find a team")
    @app_commands.describe(
        position="Your preferred position(s) (e.g., 'Setter/Libero', 'Outside Hitter')",
        availability="Your availability (e.g., 'Weekdays 7-10pm EST', 'Weekends anytime')",
        experience="Your experience level (e.g., 'Competitive 2 years', 'Casual player')",
        additional_info="Any additional information (optional)"
    )
    async def lft(
        self, 
        interaction: discord.Interaction, 
        position: str, 
        availability: str, 
        experience: str,
        additional_info: str = None
    ):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Check if user is already on a team
            user_team = await self.get_user_team_by_role(interaction.user)
            if user_team:
                team_id, role_id, team_emoji, team_name = user_team
                team_role = interaction.guild.get_role(role_id)
                await interaction.followup.send(
                    f"❌ You are already on {team_emoji} **{team_name}**. Leave your current team before looking for a new one.",
                    ephemeral=True
                )
                return
            
            # Check if user is blacklisted
            if await is_user_blacklisted(interaction.user.id):
                await interaction.followup.send(
                    "❌ You are currently blacklisted and cannot post LFT messages.",
                    ephemeral=True
                )
                return
            
            # Get LFT channel
            lft_channel_id = await get_lft_channel_id()
            if not lft_channel_id or lft_channel_id == 0:
                await interaction.followup.send(
                    "❌ LFT channel is not configured. Ask an admin to set it up with `/config`.",
                    ephemeral=True
                )
                return
            
            lft_channel = interaction.guild.get_channel(lft_channel_id)
            if not lft_channel:
                await interaction.followup.send(
                    "❌ LFT channel not found. Please check configuration.",
                    ephemeral=True
                )
                return
            
            # Check if user has free agent role (if configured)
            free_agent_role_id = await get_free_agent_role_id()
            has_free_agent_role = False
            if free_agent_role_id and free_agent_role_id != 0:
                free_agent_role = interaction.guild.get_role(free_agent_role_id)
                if free_agent_role and free_agent_role in interaction.user.roles:
                    has_free_agent_role = True
            
            # Get user's demand usage
            player = await get_player(interaction.user.id)
            demands_used = 0
            if player and len(player) > 6:
                demands_used = player[6]
            max_demands = await get_max_demands_allowed()
            
            # Create the LFT embed
            embed = discord.Embed(
                title="🔎 Looking for Team",
                color=discord.Color.blue()
            )
            
            # Player info at the top
            embed.add_field(
                name="👤 Player",
                value=interaction.user.mention,
                inline=True
            )
            
            embed.add_field(
                name="🏐 Position(s)",
                value=position,
                inline=True
            )
            
            embed.add_field(
                name="📊 Experience",
                value=experience,
                inline=True
            )
            
            embed.add_field(
                name="🕒 Availability",
                value=availability,
                inline=False
            )
            
            if additional_info:
                embed.add_field(
                    name="📝 Additional Info",
                    value=additional_info[:1024],  # Discord field limit
                    inline=False
                )
            
            # Status indicators
            status_parts = []
            
            # Free agent status
            if has_free_agent_role:
                status_parts.append("✅ Free Agent")
            else:
                status_parts.append("⚪ No Free Agent role")
            
            # Demand status
            if demands_used < max_demands:
                status_parts.append(f"📤 Demands: {demands_used}/{max_demands}")
            else:
                status_parts.append(f"❌ No demands left ({demands_used}/{max_demands})")
            
            # Required roles check
            required_role_ids = await get_required_roles()
            if required_role_ids:
                user_role_ids = [role.id for role in interaction.user.roles]
                has_all_required = all(role_id in user_role_ids for role_id in required_role_ids)
                
                if has_all_required:
                    status_parts.append("✅ Has required roles")
                else:
                    missing_count = len([r for r in required_role_ids if r not in user_role_ids])
                    status_parts.append(f"⚠️ Missing {missing_count} required role(s)")
            
            if status_parts:
                embed.add_field(
                    name="📋 Status",
                    value=" • ".join(status_parts),
                    inline=False
                )
            
            embed.set_author(
                name=interaction.user.display_name,
                icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
            )
            
            embed.set_footer(text="Team owners/vice captains: Use /sign to recruit this player")
            embed.timestamp = discord.utils.utcnow()
            
            # Post to LFT channel
            try:
                message = await lft_channel.send(embed=embed)
                
                # Add reactions for team owners to easily contact
                await message.add_reaction("👋")  # Wave emoji for interest
                
                await interaction.followup.send(
                    f"✅ Your LFT post has been sent to {lft_channel.mention}!\n\n"
                    f"**Position:** {position}\n"
                    f"**Availability:** {availability}\n"
                    f"**Experience:** {experience}",
                    ephemeral=True
                )
                
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have permission to post in the LFT channel.",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Error posting LFT message: {str(e)}",
                    ephemeral=True
                )
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in lft command: {error_details}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ An error occurred while posting the LFT message: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ An error occurred while posting the LFT message: {str(e)}",
                    ephemeral=True
                )

async def setup(bot):
    await bot.add_cog(RecruitmentCommands(bot))