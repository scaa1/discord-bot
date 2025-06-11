import discord
from discord import ui, ButtonStyle
import asyncio
from database.games import (
    add_referee_signup, get_referee_signups, check_existing_referee_signup
)
from database.settings import (
    get_game_reminder_channel_id, get_vice_captain_role_id, get_free_agent_role_id,
    get_sign_log_channel_id, get_active_dashboard, deactivate_dashboard, 
    update_dashboard_timestamp, set_dashboard_message
)
from database.players import remove_player_from_team
from database.teams import get_team_by_id

class LFPAnnouncementView(ui.View):
    def __init__(self, link_url: str, link_text: str = "Join Here"):
        super().__init__(timeout=None)  # Persistent view
        
        # Create the link button with proper URL
        self.link_button = ui.Button(
            label=link_text,
            style=discord.ButtonStyle.link,
            url=link_url
        )
        self.add_item(self.link_button)

class RefereeSignupView(ui.View):
    def __init__(self, game_id: int, team1_name: str, team2_name: str, original_message=None, original_embed=None):
        super().__init__(timeout=None)  # Persistent view
        self.game_id = game_id
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.original_message = original_message
        self.original_embed = original_embed

    @ui.button(label="🏁 Sign Up as Referee", style=ButtonStyle.blurple)
    async def signup_referee(self, interaction: discord.Interaction, button: ui.Button):
        from database.settings import get_referee_role_id
        from ui.modals import RefereeSignupModal
        
        # Check if user has referee role
        referee_role_id = await get_referee_role_id()
        referee_role = interaction.guild.get_role(referee_role_id)
        if not referee_role or referee_role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ You must have the Referee role to sign up as a referee.",
                ephemeral=True
            )
            return

        # Show the signup modal with message references
        modal = RefereeSignupModal(
            self.game_id, 
            self.team1_name, 
            self.team2_name, 
            self.original_message, 
            self.original_embed
        )
        await interaction.response.send_modal(modal)

class TeamOwnerDashboardView(ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=None)  # Persistent view
        self.pages = pages
        self.current = 0

        if len(pages) > 1:
            self.prev_button = ui.Button(label="⏮️ Previous", style=ButtonStyle.blurple, custom_id="dashboard_prev")
            self.next_button = ui.Button(label="⏭️ Next", style=ButtonStyle.blurple, custom_id="dashboard_next")

            self.prev_button.callback = self.prev_page
            self.next_button.callback = self.next_page

            self.add_item(self.prev_button)
            self.add_item(self.next_button)

    async def prev_page(self, interaction: discord.Interaction):
        self.current = (self.current - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current = (self.current + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

class PaginatorView(ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=180)
        self.pages = pages
        self.current = 0

        if len(pages) > 1:
            self.prev_button = ui.Button(label="⏮️ Previous", style=ButtonStyle.blurple)
            self.next_button = ui.Button(label="⏭️ Next", style=ButtonStyle.blurple)

            self.prev_button.callback = self.prev_page
            self.next_button.callback = self.next_page

            self.add_item(self.prev_button)
            self.add_item(self.next_button)

    async def prev_page(self, interaction: discord.Interaction):
        self.current = (self.current - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current = (self.current + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

class LeaveTeamView(ui.View):
    def __init__(self, team_id: int, team_role_id: int, signed_user_id: int):
        super().__init__(timeout=43200)  # 12-hour timeout (43200 seconds)
        self.team_id = team_id
        self.team_role_id = team_role_id
        self.signed_user_id = signed_user_id

    @ui.button(label="🚫 Forced Signed", style=ButtonStyle.red, custom_id="leave_team_button")
    async def leave_team(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Defer immediately to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            # Check if the user clicking is the one who was signed
            if interaction.user.id != self.signed_user_id:
                await interaction.followup.send(
                    "❌ Only the signed player can use this button.",
                    ephemeral=True
                )
                return

            # Get team role
            team_role = interaction.guild.get_role(self.team_role_id)
            if not team_role:
                await interaction.followup.send(
                    "❌ Team role not found.",
                    ephemeral=True
                )
                return

            # Check if user still has the team role
            if team_role not in interaction.user.roles:
                await interaction.followup.send(
                    "❌ You are no longer on this team.",
                    ephemeral=True
                )
                return

            print(f"Processing forced signing reversal for {interaction.user} from {team_role.name}")

            # Remove from database first
            try:
                await remove_player_from_team(interaction.user.id)
                print("Successfully removed from database")
            except Exception as db_error:
                print(f"Database error: {db_error}")
                await interaction.followup.send(
                    "❌ Database error occurred while processing reversal.",
                    ephemeral=True
                )
                return

            # Collect roles to remove
            roles_to_remove = [team_role]
            
            # Get vice captain role safely
            try:
                vice_captain_role_id = await get_vice_captain_role_id()
                if vice_captain_role_id and vice_captain_role_id != 0:
                    vice_captain_role = interaction.guild.get_role(vice_captain_role_id)
                    if vice_captain_role and vice_captain_role in interaction.user.roles:
                        roles_to_remove.append(vice_captain_role)
                        print(f"Will remove vice captain role: {vice_captain_role.name}")
            except Exception as vc_error:
                print(f"Error getting vice captain role: {vc_error}")
                # Continue without vice captain role

            # Remove roles
            try:
                await interaction.user.remove_roles(*roles_to_remove, reason="Player left team - forced signing reversed")
                print(f"Successfully removed {len(roles_to_remove)} roles")
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have permission to remove your roles.",
                    ephemeral=True
                )
                return
            except discord.HTTPException as http_error:
                print(f"HTTP error removing roles: {http_error}")
                await interaction.followup.send(
                    "❌ Discord error occurred while removing roles.",
                    ephemeral=True
                )
                return
            except Exception as role_error:
                print(f"Unexpected error removing roles: {role_error}")
                await interaction.followup.send(
                    "❌ An error occurred while removing roles.",
                    ephemeral=True
                )
                return

            # Add free agent role back if configured
            try:
                free_agent_role_id = await get_free_agent_role_id()
                if free_agent_role_id and free_agent_role_id != 0:
                    free_agent_role = interaction.guild.get_role(free_agent_role_id)
                    if free_agent_role and free_agent_role not in interaction.user.roles:
                        await interaction.user.add_roles(free_agent_role, reason="Left team - restored free agent status")
                        print("Successfully added free agent role back")
            except Exception as fa_error:
                print(f"Error adding free agent role: {fa_error}")
                # Continue without failing the entire operation

            # Get team data for embed
            try:
                team_data = await get_team_by_id(self.team_id)
                team_emoji = team_data[2] if team_data else "🔥"
            except Exception:
                team_emoji = "🔥"  # Default fallback

            # Create departure embed
            embed = discord.Embed(
                title="🚫 Forced Signing Reversed",
                description=f"{team_emoji} {interaction.user.mention} has reversed their forced signing from {team_role.mention}.",
                color=discord.Color.orange()
            )

            # Send to log channel
            try:
                log_channel_id = await get_sign_log_channel_id()
                if log_channel_id and log_channel_id != 0:
                    log_channel = interaction.guild.get_channel(log_channel_id)
                    if log_channel:
                        await log_channel.send(embed=embed)
            except Exception as log_error:
                print(f"Error sending to log channel: {log_error}")

            # Disable the button and send confirmation
            button.disabled = True
            button.label = "✅ Signing Reversed"
            button.style = ButtonStyle.gray
            
            # Try to edit the original message (this might be in DMs)
            try:
                if interaction.message:
                    await interaction.message.edit(view=self)
            except Exception as edit_error:
                print(f"Could not edit original message: {edit_error}")

            # Send confirmation
            await interaction.followup.send(
                f"✅ You have successfully reversed your forced signing from {team_role.mention}.",
                ephemeral=True
            )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"DETAILED ERROR in forced signing reversal button: {error_details}")
            
            try:
                await interaction.followup.send(
                    "❌ An error occurred while reversing the forced signing.",
                    ephemeral=True
                )
            except Exception as final_error:
                print(f"Could not send error message: {final_error}")

    async def on_timeout(self):
        """Called when the view times out after 12 hours."""
        for item in self.children:
            item.disabled = True
            if hasattr(item, 'label'):
                item.label = "⏰ Expired"
                item.style = ButtonStyle.gray
