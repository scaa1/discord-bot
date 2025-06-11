import asyncio
import discord
from discord.ext import commands

# Import configuration
from config import TOKEN, intents, GUILD_ID, ALLOWED_MANAGEMENT_ROLES

# Import event handlers
from events import on_ready_handler, on_guild_join_handler, on_member_remove_handler

# Import cogs
from cogs.league_commands import LeagueCommands

# Import utilities
from utils.permissions import has_any_role

# Initialize bot
bot = commands.Bot(command_prefix="!", intents=intents)

# ========================= EVENT HANDLERS =========================

@bot.event
async def on_ready():
    await on_ready_handler(bot)
    
    # Add the cog
    if not bot.get_cog("LeagueCommands"):
        await bot.add_cog(LeagueCommands(bot))
        print("LeagueCommands cog loaded!")
    
    # Sync commands to the specific guild
    guild = discord.Object(id=GUILD_ID)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands to guild {GUILD_ID}.")
    
    # Also try a global sync as backup
    if len(synced) == 0:
        print("Guild sync failed, trying global sync...")
        global_synced = await bot.tree.sync()
        print(f"Global synced {len(global_synced)} commands.")

@bot.event
async def on_guild_join(guild):
    await on_guild_join_handler(guild)

@bot.event
async def on_member_remove(member):
    await on_member_remove_handler(member, bot)

# ========================= TEMPORARY ADMIN COMMAND =========================

@bot.command(name="force_sync")
async def force_sync_commands(ctx):
    # Check if user has any of the allowed management roles
    if await has_any_role(ctx.author, ALLOWED_MANAGEMENT_ROLES):
        try:
            guild = discord.Object(id=GUILD_ID)
            synced = await bot.tree.sync(guild=guild)
            await ctx.send(f"✅ Force synced {len(synced)} slash commands!")
            print(f"Commands synced: {[cmd.name for cmd in synced]}")
        except Exception as e:
            await ctx.send(f"❌ Failed to sync: {e}")
    else:
        allowed_roles_text = ", ".join(ALLOWED_MANAGEMENT_ROLES)
        await ctx.send(f"❌ You need one of these roles to sync commands: {allowed_roles_text}")

# ========================= MAIN FUNCTION =========================

async def main():
    try:
        from database.models import init_db
        await init_db()
        print("Database initialized!")
        
        # Add cog BEFORE starting the bot
        await bot.add_cog(LeagueCommands(bot))
        print("LeagueCommands cog loaded!")
        
        await bot.start(TOKEN)
    except Exception as e:
        print(f"Error starting bot: {e}")
        import traceback
        traceback.print_exc()
    finally:
        from tasks import game_reminder_task, update_team_owner_dashboard
        
        if game_reminder_task.is_running():
            game_reminder_task.cancel()
            print("🔔 Game reminder system stopped!")
        
        if update_team_owner_dashboard.is_running():
            update_team_owner_dashboard.cancel()
            print("🔄 Team owner dashboard update task stopped!")

if __name__ == "__main__":
    asyncio.run(main())