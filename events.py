import discord
from database.teams import get_team_by_owner
from utils.alerts import send_team_owner_alert
from config import GUILD_ID
import aiosqlite
from config import DB_PATH

async def on_ready_handler(bot):
    """Handle bot ready event."""
    print(f"Logged in as {bot.user}")
    try:
        from database.models import init_db
        await init_db()
        
        # Auto-leave unauthorized guilds
        for guild_obj in bot.guilds:
            if guild_obj.id != GUILD_ID:
                print(f"Leaving unauthorized guild: {guild_obj.name}")
                await guild_obj.leave()
        
        # Start background tasks
        from tasks import game_reminder_task, update_team_owner_dashboard
        
        if not game_reminder_task.is_running():
            game_reminder_task.start(bot)
            print("🔔 Game reminder system started!")
        
        if not update_team_owner_dashboard.is_running():
            update_team_owner_dashboard.start(bot)
            print("🔄 Team owner dashboard update task started!")
            
    except Exception as e:
        print(f"Error in on_ready: {e}")
        import traceback
        traceback.print_exc()

async def on_guild_join_handler(guild):
    """Handle when bot joins a guild."""
    if guild.id != GUILD_ID:
        print(f"Auto-leaving unauthorized guild: {guild.name}")
        await guild.leave()

async def on_member_remove_handler(member, bot):
    """Handle when a member leaves the server - check if they were a team owner"""
    try:
        # Check if the leaving member was a team owner
        team = await get_team_by_owner(member.id)
        if team:
            print(f"Team owner {member} left the server - team {team[3]} now ownerless")
            
            # Remove owner from database
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE teams SET owner_id = NULL WHERE owner_id = ?", (member.id,))
                await db.commit()
            
            # Send alert
            await send_team_owner_alert(
                bot, 
                team, 
                "Left server", 
                f"Former owner: {member.display_name} ({member.id})"
            )
            
    except Exception as e:
         print(f"Error in on_member_remove for team owner check: {e}")