import discord
from discord import ui
from database.games import add_referee_signup, get_referee_signups, check_existing_referee_signup
from database.settings import get_game_reminder_channel_id

class RefereeSignupModal(ui.Modal, title="Referee Signup"):
    def __init__(self, game_id: int, team1_name: str, team2_name: str, original_message=None, original_embed=None):
        super().__init__()
        self.game_id = game_id
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.original_message = original_message
        self.original_embed = original_embed

    username = ui.TextInput(
        label="Your Username/Gamertag",
        placeholder="Enter your in-game username or gamertag...",
        required=True,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Check if user already signed up
            if await check_existing_referee_signup(self.game_id, interaction.user.id):
                await interaction.response.send_message(
                    "❌ You have already signed up to referee this game!",
                    ephemeral=True
                )
                return

            # Add referee signup
            await add_referee_signup(
                self.game_id,
                interaction.user.id,
                self.username.value,
                str(interaction.user)
            )

            # Create confirmation embed
            embed = discord.Embed(
                title="✅ Referee Signup Confirmed",
                description=(
                    f"**Game:** {self.team1_name} vs {self.team2_name}\n"
                    f"**Referee:** {interaction.user.mention}\n"
                    f"**Username:** {self.username.value}"
                ),
                color=discord.Color.green()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Update the original message to show actual referees instead of role mention
            try:
                signups = await get_referee_signups(self.game_id)
                
                if self.original_message and self.original_embed:
                    # Create updated embed
                    updated_embed = discord.Embed(
                        title=self.original_embed.title,
                        description=self.original_embed.description,
                        color=self.original_embed.color
                    )
                    
                    # Copy all fields from original embed
                    for field in self.original_embed.fields:
                        updated_embed.add_field(
                            name=field.name,
                            value=field.value,
                            inline=field.inline
                        )
                    
                    # Find and update the referee field, or add it if it doesn't exist
                    referee_field_index = None
                    for i, field in enumerate(updated_embed.fields):
                        if "referee" in field.name.lower() or "🏁" in field.name:
                            referee_field_index = i
                            break
                    
                    # Create referee list
                    if signups:
                        referee_list = "\n".join([
                            f"• {interaction.guild.get_member(user_id).mention if interaction.guild.get_member(user_id) else discord_user} ({username})" 
                            for user_id, username, discord_user, _ in signups
                        ])
                        referee_field_value = f"**Signed Up ({len(signups)}):**\n{referee_list}"
                    else:
                        referee_field_value = "No referees signed up yet."
                    
                    # Update or add referee field
                    if referee_field_index is not None:
                        # Remove the old field and add updated one
                        updated_embed.remove_field(referee_field_index)
                        updated_embed.insert_field_at(
                            referee_field_index,
                            name="🏁 Referees",
                            value=referee_field_value,
                            inline=False
                        )
                    else:
                        # Add new referee field
                        updated_embed.add_field(
                            name="🏁 Referees",
                            value=referee_field_value,
                            inline=False
                        )
                    
                    # Get the view from the original message to preserve the button
                    from ui.views import RefereeSignupView
                    view = RefereeSignupView(self.game_id, self.team1_name, self.team2_name, self.original_message, updated_embed)
                    
                    # Edit the original message
                    await self.original_message.edit(embed=updated_embed, view=view)
                
                # Send update to the reminder channel as well
                reminder_channel_id = await get_game_reminder_channel_id()
                reminder_channel = interaction.guild.get_channel(reminder_channel_id)
                if reminder_channel:
                    signup_list = "\n".join([
                        f"• **{username}** ({discord_user})" 
                        for _, username, discord_user, _ in signups
                    ])
                    update_embed = discord.Embed(
                        title="🎯 Referee Update",
                        description=(
                            f"**Game:** {self.team1_name} vs {self.team2_name}\n"
                            f"**New Referee:** {interaction.user.mention} ({self.username.value})\n\n"
                            f"**All Referees ({len(signups)}):**\n{signup_list}"
                        ),
                        color=discord.Color.blue()
                    )
                    await reminder_channel.send(embed=update_embed)
                    
            except Exception as e:
                print(f"Error updating referee list: {e}")

        except Exception as e:
            print(f"Error in referee signup: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while signing up. Please try again.",
                ephemeral=True
            )