import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import aiosqlite
import asyncio
import json
import sqlite3
from typing import Optional, Dict, Any, List

# Import configuration
try:
    from config import DB_PATH, ALLOWED_MANAGEMENT_ROLES
except ImportError:
    print("⚠️ Could not import from config, using defaults")
    DB_PATH = "database.db"
    ALLOWED_MANAGEMENT_ROLES = ["Admin", "Moderator", "Staff"]

# Global bot reference for sending embeds
_bot_instance = None

# ========================= DATABASE SETUP =========================

async def init_audit_logs_table():
    """Initialize the audit logging database with all required tables."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if table exists and get its structure
            async with db.execute("PRAGMA table_info(audit_logs)") as cursor:
                columns = await cursor.fetchall()
                existing_columns = [col[1] for col in columns] if columns else []
            
            if not existing_columns:
                # Create new table if it doesn't exist
                await db.execute("""
                    CREATE TABLE audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        user_id INTEGER,
                        user_name TEXT,
                        target_id INTEGER,
                        target_name TEXT,
                        moderator_id INTEGER,
                        moderator_name TEXT,
                        channel_id INTEGER,
                        channel_name TEXT,
                        reason TEXT,
                        before_value TEXT,
                        after_value TEXT,
                        timestamp TEXT NOT NULL,
                        additional_data TEXT
                    )
                """)
                print("✅ Created new audit_logs table")
            else:
                # Add missing columns to existing table
                required_columns = [
                    ('event_type', 'TEXT'),
                    ('user_name', 'TEXT'),
                    ('target_id', 'INTEGER'),
                    ('target_name', 'TEXT'),
                    ('moderator_id', 'INTEGER'),
                    ('moderator_name', 'TEXT'),
                    ('channel_name', 'TEXT'),
                    ('reason', 'TEXT'),
                    ('before_value', 'TEXT'),
                    ('after_value', 'TEXT'),
                    ('additional_data', 'TEXT')
                ]
                
                for column_name, column_type in required_columns:
                    if column_name not in existing_columns:
                        try:
                            await db.execute(f"ALTER TABLE audit_logs ADD COLUMN {column_name} {column_type}")
                            print(f"✅ Added column: {column_name}")
                        except Exception as e:
                            print(f"⚠️ Could not add column {column_name}: {e}")
                
                # Ensure event_type has default value for existing records
                if 'event_type' not in existing_columns:
                    await db.execute("UPDATE audit_logs SET event_type = 'legacy_event' WHERE event_type IS NULL")
                    print("✅ Updated existing records with default event_type")
            
            # Check audit_settings table structure
            async with db.execute("PRAGMA table_info(audit_settings)") as cursor:
                settings_columns = await cursor.fetchall()
                existing_settings_columns = [col[1] for col in settings_columns] if settings_columns else []
            
            if not existing_settings_columns:
                # Create audit settings table
                await db.execute("""
                    CREATE TABLE audit_settings (
                        guild_id INTEGER PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        log_channel_id INTEGER,
                        log_moderation BOOLEAN DEFAULT TRUE,
                        log_messages BOOLEAN DEFAULT TRUE,
                        log_voice BOOLEAN DEFAULT TRUE,
                        log_members BOOLEAN DEFAULT TRUE,
                        log_roles BOOLEAN DEFAULT TRUE,
                        log_server BOOLEAN DEFAULT TRUE,
                        log_stage BOOLEAN DEFAULT TRUE,
                        log_avatars BOOLEAN DEFAULT TRUE,
                        retention_days INTEGER DEFAULT 30
                    )
                """)
                print("✅ Created new audit_settings table")
            else:
                # Add missing columns to audit_settings
                settings_required_columns = [
                    ('log_channel_id', 'INTEGER'),
                    ('log_moderation', 'BOOLEAN DEFAULT TRUE'),
                    ('log_messages', 'BOOLEAN DEFAULT TRUE'),
                    ('log_voice', 'BOOLEAN DEFAULT TRUE'),
                    ('log_members', 'BOOLEAN DEFAULT TRUE'),
                    ('log_roles', 'BOOLEAN DEFAULT TRUE'),
                    ('log_server', 'BOOLEAN DEFAULT TRUE'),
                    ('log_stage', 'BOOLEAN DEFAULT TRUE'),
                    ('log_avatars', 'BOOLEAN DEFAULT TRUE'),
                    ('retention_days', 'INTEGER DEFAULT 30')
                ]
                
                for column_name, column_def in settings_required_columns:
                    base_column_name = column_name.split(' ')[0]  # Remove DEFAULT part
                    if base_column_name not in existing_settings_columns:
                        try:
                            await db.execute(f"ALTER TABLE audit_settings ADD COLUMN {column_name}")
                            print(f"✅ Added settings column: {base_column_name}")
                        except Exception as e:
                            print(f"⚠️ Could not add settings column {base_column_name}: {e}")
            
            # Create voice sessions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS voice_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT,
                    channel_id INTEGER NOT NULL,
                    channel_name TEXT,
                    channel_type TEXT,
                    join_time TEXT NOT NULL,
                    leave_time TEXT,
                    duration_seconds INTEGER,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            
            # Create indexes for performance
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_guild_timestamp ON audit_logs(guild_id, timestamp)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_logs(event_type)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_voice_sessions_active ON voice_sessions(guild_id, is_active)")
            
            await db.commit()
            print("✅ Audit database initialized successfully!")
            
    except Exception as e:
        print(f"❌ Error initializing audit database: {e}")
        import traceback
        traceback.print_exc()

# ========================= SETTINGS MANAGEMENT =========================

async def get_audit_settings(guild_id: int) -> Dict[str, Any]:
    """Get audit settings for a guild."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM audit_settings WHERE guild_id = ?", (guild_id,)) as cursor:
                result = await cursor.fetchone()
                
                if result:
                    return {
                        'enabled': bool(result[1]),
                        'log_channel_id': result[2],
                        'log_moderation': bool(result[3]) if len(result) > 3 else True,
                        'log_messages': bool(result[4]) if len(result) > 4 else True,
                        'log_voice': bool(result[5]) if len(result) > 5 else True,
                        'log_members': bool(result[6]) if len(result) > 6 else True,
                        'log_roles': bool(result[7]) if len(result) > 7 else True,
                        'log_server': bool(result[8]) if len(result) > 8 else True,
                        'log_stage': bool(result[9]) if len(result) > 9 else True,
                        'log_avatars': bool(result[10]) if len(result) > 10 else True,
                        'retention_days': result[11] if len(result) > 11 else 30
                    }
                else:
                    # Create default settings
                    await db.execute("""
                        INSERT INTO audit_settings 
                        (guild_id, enabled, log_channel_id, log_moderation, log_messages, 
                         log_voice, log_members, log_roles, log_server, log_stage, log_avatars, retention_days)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (guild_id, False, None, True, True, True, True, True, True, True, True, 30))
                    await db.commit()
                    
                    return {
                        'enabled': False,
                        'log_channel_id': None,
                        'log_moderation': True,
                        'log_messages': True,
                        'log_voice': True,
                        'log_members': True,
                        'log_roles': True,
                        'log_server': True,
                        'log_stage': True,
                        'log_avatars': True,
                        'retention_days': 30
                    }
                    
    except Exception as e:
        print(f"Error getting audit settings: {e}")
        return {'enabled': False, 'log_channel_id': None}

async def save_audit_settings(guild_id: int, **settings):
    """Save audit settings for a guild."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if record exists
            async with db.execute("SELECT guild_id FROM audit_settings WHERE guild_id = ?", (guild_id,)) as cursor:
                exists = await cursor.fetchone()
            
            if exists:
                # Update existing record
                update_parts = []
                update_values = []
                
                for key, value in settings.items():
                    if key in ['enabled', 'log_channel_id', 'log_moderation', 'log_messages', 
                              'log_voice', 'log_members', 'log_roles', 'log_server', 'log_stage', 
                              'log_avatars', 'retention_days']:
                        update_parts.append(f"{key} = ?")
                        update_values.append(value)
                
                if update_parts:
                    update_values.append(guild_id)
                    query = f"UPDATE audit_settings SET {', '.join(update_parts)} WHERE guild_id = ?"
                    await db.execute(query, update_values)
            else:
                # Create new record with defaults
                defaults = {
                    'enabled': False, 'log_channel_id': None, 'log_moderation': True,
                    'log_messages': True, 'log_voice': True, 'log_members': True,
                    'log_roles': True, 'log_server': True, 'log_stage': True, 
                    'log_avatars': True, 'retention_days': 30
                }
                defaults.update(settings)
                
                await db.execute("""
                    INSERT INTO audit_settings 
                    (guild_id, enabled, log_channel_id, log_moderation, log_messages, 
                     log_voice, log_members, log_roles, log_server, log_stage, log_avatars, retention_days)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    guild_id, 
                    defaults['enabled'], 
                    defaults['log_channel_id'],
                    defaults['log_moderation'],
                    defaults['log_messages'],
                    defaults['log_voice'],
                    defaults['log_members'],
                    defaults['log_roles'],
                    defaults['log_server'],
                    defaults['log_stage'],
                    defaults['log_avatars'],
                    defaults['retention_days']
                ))
            
            await db.commit()
            print(f"✅ Saved audit settings for guild {guild_id}")
            
    except Exception as e:
        print(f"Error saving audit settings: {e}")

# ========================= LOGGING FUNCTIONS =========================

async def log_audit_event(guild_id: int, event_type: str, **kwargs):
    """Log an audit event to the database and send to channel."""
    try:
        print(f"🔍 Attempting to log event: {event_type} for guild {guild_id}")
        
        settings = await get_audit_settings(guild_id)
        print(f"🔧 Settings retrieved: enabled={settings.get('enabled')}, channel={settings.get('log_channel_id')}")
        
        # Check if logging is enabled and this event type should be logged
        if not settings.get('enabled') or not settings.get('log_channel_id'):
            print(f"⚠️ Logging disabled or no channel set for guild {guild_id}")
            return
        
        # Check event type filters
        event_categories = {
            'moderation': ['member_ban', 'member_unban', 'member_kick', 'member_timeout', 'member_untimeout', 'voice_disconnect'],
            'messages': ['message_delete', 'message_edit', 'message_bulk_delete'],
            'voice': ['voice_join', 'voice_leave', 'voice_move', 'voice_mute', 'voice_unmute', 'voice_deafen', 'voice_undeafen', 'voice_disconnect'],
            'members': ['member_join', 'member_leave', 'member_update', 'nickname_change', 'avatar_change'],
            'roles': ['role_add', 'role_remove', 'role_create', 'role_delete', 'role_update'],
            'server': ['channel_create', 'channel_delete', 'channel_update', 'emoji_create', 'emoji_delete', 'emoji_update', 'guild_update'],
            'stage': ['stage_speaker_add', 'stage_speaker_remove', 'stage_listener_add', 'stage_invite_sent', 'stage_request_speak', 'stage_start', 'stage_end'],
            'avatars': ['avatar_change']
        }
        
        should_log = False
        for category, events in event_categories.items():
            if event_type in events and settings.get(f'log_{category}', True):
                should_log = True
                break
        
        if not should_log:
            print(f"⚠️ Event type {event_type} filtered out by settings")
            return
        
        print(f"✅ Event {event_type} passed filters, logging to database...")
        
        # Store in database
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO audit_logs 
                (guild_id, event_type, user_id, user_name, target_id, target_name, 
                 moderator_id, moderator_name, channel_id, channel_name, reason, 
                 before_value, after_value, timestamp, additional_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                guild_id, event_type,
                kwargs.get('user_id'), kwargs.get('user_name'),
                kwargs.get('target_id'), kwargs.get('target_name'),
                kwargs.get('moderator_id'), kwargs.get('moderator_name'),
                kwargs.get('channel_id'), kwargs.get('channel_name'),
                kwargs.get('reason'), kwargs.get('before_value'), kwargs.get('after_value'),
                datetime.utcnow().isoformat(),
                json.dumps(kwargs.get('additional_data', {}))
            ))
            await db.commit()
        
        print(f"✅ Event stored in database, sending to channel...")
        
        # Send to log channel
        await send_audit_log_embed(guild_id, event_type, **kwargs)
        
    except sqlite3.OperationalError as e:
        if "no column named" in str(e):
            print(f"❌ Database schema issue: {e}")
            print("🔄 Attempting to fix database schema...")
            await init_audit_logs_table()
            print("✅ Database schema updated. Please try the action again.")
        else:
            print(f"❌ Database error logging audit event {event_type}: {e}")
    except Exception as e:
        print(f"❌ Error logging audit event {event_type}: {e}")
        import traceback
        traceback.print_exc()

async def send_audit_log_embed(guild_id: int, event_type: str, **kwargs):
    """Send an audit log embed to the configured channel."""
    try:
        global _bot_instance
        if not _bot_instance:
            print("❌ Bot instance not set for audit logging")
            return
        
        settings = await get_audit_settings(guild_id)
        if not settings.get('log_channel_id'):
            print(f"❌ No log channel set for guild {guild_id}")
            return
        
        guild = _bot_instance.get_guild(guild_id)
        if not guild:
            print(f"❌ Could not find guild {guild_id}")
            return
        
        channel = guild.get_channel(settings['log_channel_id'])
        if not channel:
            print(f"❌ Could not find channel {settings['log_channel_id']} in guild {guild_id}")
            return
        
        embed = create_audit_embed(event_type, **kwargs)
        if embed:
            await channel.send(embed=embed)
            print(f"✅ Sent audit log embed for {event_type} to {channel.name}")
        else:
            print(f"❌ Could not create embed for event type {event_type}")
            
    except Exception as e:
        print(f"❌ Error sending audit log embed: {e}")
        import traceback
        traceback.print_exc()

def create_audit_embed(event_type: str, **kwargs) -> Optional[discord.Embed]:
    """Create an embed for different audit events."""
    
    # Define embed configurations for each event type
    embed_configs = {
        # Moderation Events
        'member_ban': {
            'title': '🔨 Member Banned',
            'color': discord.Color.red(),
            'description': lambda k: f"**{k.get('target_name', 'Unknown')}** was banned" + (f" (<@{k.get('target_id')}>)" if k.get('target_id') else "")
        },
        'member_unban': {
            'title': '🔓 Member Unbanned',
            'color': discord.Color.green(),
            'description': lambda k: f"**{k.get('target_name', 'Unknown')}** was unbanned" + (f" (<@{k.get('target_id')}>)" if k.get('target_id') else "")
        },
        'member_kick': {
            'title': '🦵 Member Kicked',
            'color': discord.Color.orange(),
            'description': lambda k: f"**{k.get('target_name', 'Unknown')}** was kicked" + (f" (<@{k.get('target_id')}>)" if k.get('target_id') else "")
        },
        'member_timeout': {
            'title': '⏰ Member Timed Out',
            'color': discord.Color.orange(),
            'description': lambda k: f"**{k.get('target_name', 'Unknown')}** was timed out" + (f" (<@{k.get('target_id')}>)" if k.get('target_id') else "")
        },
        'member_untimeout': {
            'title': '⏰ Member Timeout Removed',
            'color': discord.Color.green(),
            'description': lambda k: f"**{k.get('target_name', 'Unknown')}**'s timeout was removed" + (f" (<@{k.get('target_id')}>)" if k.get('target_id') else "")
        },
        
        # Voice Events
        'voice_join': {
            'title': '🔊 Voice Channel Joined',
            'color': discord.Color.green(),
            'description': lambda k: f"<@{k.get('user_id')}> joined **{k.get('channel_name', 'Unknown')}**" if k.get('user_id') else f"**{k.get('user_name', 'Unknown')}** joined **{k.get('channel_name', 'Unknown')}**"
        },
        'voice_leave': {
            'title': '🔇 Voice Channel Left',
            'color': discord.Color.red(),
            'description': lambda k: f"<@{k.get('user_id')}> left **{k.get('channel_name', 'Unknown')}**" if k.get('user_id') else f"**{k.get('user_name', 'Unknown')}** left **{k.get('channel_name', 'Unknown')}**"
        },
        'voice_move': {
            'title': '🔀 Voice Channel Moved',
            'color': discord.Color.blue(),
            'description': lambda k: f"<@{k.get('user_id')}> was moved" if k.get('user_id') else f"**{k.get('user_name', 'Unknown')}** was moved"
        },
        'voice_disconnect': {
            'title': '🔌 Disconnected from Voice',
            'color': discord.Color.dark_red(),
            'description': lambda k: f"<@{k.get('target_id')}> was disconnected from voice" if k.get('target_id') else f"**{k.get('target_name', 'Unknown')}** was disconnected"
        },
        'voice_mute': {
            'title': '🔇 Voice Muted',
            'color': discord.Color.red(),
            'description': lambda k: f"<@{k.get('target_id')}> was voice muted" if k.get('target_id') else f"**{k.get('target_name', 'Unknown')}** was voice muted"
        },
        'voice_unmute': {
            'title': '🔊 Voice Unmuted',
            'color': discord.Color.green(),
            'description': lambda k: f"<@{k.get('target_id')}> was voice unmuted" if k.get('target_id') else f"**{k.get('target_name', 'Unknown')}** was voice unmuted"
        },
        'voice_deafen': {
            'title': '🔕 Voice Deafened',
            'color': discord.Color.red(),
            'description': lambda k: f"<@{k.get('target_id')}> was deafened" if k.get('target_id') else f"**{k.get('target_name', 'Unknown')}** was deafened"
        },
        'voice_undeafen': {
            'title': '🔉 Voice Undeafened',
            'color': discord.Color.green(),
            'description': lambda k: f"<@{k.get('target_id')}> was undeafened" if k.get('target_id') else f"**{k.get('target_name', 'Unknown')}** was undeafened"
        },
        
        # Message Events
        'message_delete': {
            'title': '🗑️ Message Deleted',
            'color': discord.Color.red(),
            'description': lambda k: f"Message by <@{k.get('user_id')}> was deleted" if k.get('user_id') else f"Message by **{k.get('user_name', 'Unknown')}** was deleted"
        },
        'message_edit': {
            'title': '📝 Message Edited',
            'color': discord.Color.blue(),
            'description': lambda k: f"Message by <@{k.get('user_id')}> was edited" if k.get('user_id') else f"Message by **{k.get('user_name', 'Unknown')}** was edited"
        },
        'message_bulk_delete': {
            'title': '🗑️ Messages Bulk Deleted',
            'color': discord.Color.dark_red(),
            'description': lambda k: f"**{k.get('additional_data', {}).get('total_count', 'Unknown')}** messages were bulk deleted"
        },
        
        # Member Events
        'member_join': {
            'title': '👋 Member Joined',
            'color': discord.Color.green(),
            'description': lambda k: f"<@{k.get('user_id')}> joined the server" if k.get('user_id') else f"**{k.get('user_name', 'Unknown')}** joined the server"
        },
        'member_leave': {
            'title': '👋 Member Left',
            'color': discord.Color.red(),
            'description': lambda k: f"<@{k.get('user_id')}> left the server" if k.get('user_id') else f"**{k.get('user_name', 'Unknown')}** left the server"
        },
        'nickname_change': {
            'title': '📝 Nickname Changed',
            'color': discord.Color.blue(),
            'description': lambda k: f"<@{k.get('target_id')}>'s nickname was changed" if k.get('target_id') else f"**{k.get('user_name', 'Unknown')}**'s nickname was changed"
        },
        'avatar_change': {
            'title': '🖼️ Avatar Changed',
            'color': discord.Color.purple(),
            'description': lambda k: f"<@{k.get('user_id')}> changed their avatar" if k.get('user_id') else f"**{k.get('user_name', 'Unknown')}** changed their avatar"
        },
        
        # Role Events
        'role_add': {
            'title': '➕ Role Added',
            'color': discord.Color.green(),
            'description': lambda k: f"Role **{k.get('after_value', 'Unknown')}** given to <@{k.get('target_id')}>" if k.get('target_id') else f"Role **{k.get('after_value', 'Unknown')}** given to **{k.get('target_name', 'Unknown')}**"
        },
        'role_remove': {
            'title': '➖ Role Removed',
            'color': discord.Color.red(),
            'description': lambda k: f"Role **{k.get('before_value', 'Unknown')}** removed from <@{k.get('target_id')}>" if k.get('target_id') else f"Role **{k.get('before_value', 'Unknown')}** removed from **{k.get('target_name', 'Unknown')}**"
        },
        'role_create': {
            'title': '🎭 Role Created',
            'color': discord.Color.green(),
            'description': lambda k: f"Role **{k.get('after_value', 'Unknown')}** was created"
        },
        'role_delete': {
            'title': '🎭 Role Deleted',
            'color': discord.Color.red(),
            'description': lambda k: f"Role **{k.get('before_value', 'Unknown')}** was deleted"
        },
        
        # Server Events
        'channel_create': {
            'title': '📋 Channel Created',
            'color': discord.Color.green(),
            'description': lambda k: f"Channel **{k.get('channel_name', 'Unknown')}** was created"
        },
        'channel_delete': {
            'title': '📋 Channel Deleted',
            'color': discord.Color.red(),
            'description': lambda k: f"Channel **{k.get('channel_name', 'Unknown')}** was deleted"
        },
        'channel_update': {
            'title': '📋 Channel Updated',
            'color': discord.Color.blue(),
            'description': lambda k: f"Channel **{k.get('channel_name', 'Unknown')}** was updated"
        },
        'emoji_create': {
            'title': '😀 Emoji Created',
            'color': discord.Color.green(),
            'description': lambda k: f"Emoji **{k.get('after_value', 'Unknown')}** was created"
        },
        'emoji_delete': {
            'title': '😀 Emoji Deleted',
            'color': discord.Color.red(),
            'description': lambda k: f"Emoji **{k.get('before_value', 'Unknown')}** was deleted"
        },
        
        # Stage Events with enhanced descriptions
        'stage_speaker_add': {
            'title': '🎙️ Stage Speaker',
            'color': discord.Color.green(),
            'description': lambda k: f"**<@{k.get('target_id')}>** became a speaker" + 
                                    (f" (invited by **<@{k.get('moderator_id')}>**)" if k.get('moderator_id') else "") + 
                                    f" in **{k.get('channel_name', 'Unknown')}**"
        },
        'stage_speaker_remove': {
            'title': '👤 Stage Listener',
            'color': discord.Color.orange(),
            'description': lambda k: f"**<@{k.get('target_id')}>** became a listener" +
                                    (f" (moved to audience by **<@{k.get('moderator_id')}>**)" if k.get('moderator_id') else "") +
                                    f" in **{k.get('channel_name', 'Unknown')}**"
        },
        'stage_request_speak': {
            'title': '✋ Stage Speaking Request',
            'color': discord.Color.blue(),
            'description': lambda k: f"**<@{k.get('user_id')}>** requested to speak in **{k.get('channel_name', 'Unknown')}**"
        },
        'stage_start': {
            'title': '🎙️ Stage Started',
            'color': discord.Color.green(),
            'description': lambda k: f"Stage **{k.get('after_value', 'Unknown Topic')}** started in **{k.get('channel_name', 'Unknown')}**"
        },
        'stage_end': {
            'title': '🎙️ Stage Ended',
            'color': discord.Color.red(),
            'description': lambda k: f"Stage **{k.get('before_value', 'Unknown Topic')}** ended in **{k.get('channel_name', 'Unknown')}**"
        }
    }
    
    config = embed_configs.get(event_type)
    if not config:
        print(f"⚠️ No embed config found for event type: {event_type}")
        return None
    
    try:
        embed = discord.Embed(
            title=config['title'],
            description=config['description'](kwargs),
            color=config['color'],
            timestamp=datetime.utcnow()
        )
        
        # Add common fields
        if kwargs.get('moderator_name') and event_type not in ['stage_speaker_add', 'stage_speaker_remove', 'voice_disconnect']:
            moderator_text = kwargs['moderator_name']
            if kwargs.get('moderator_id'):
                moderator_text = f"<@{kwargs['moderator_id']}> ({kwargs['moderator_name']})"
            embed.add_field(name="Moderator", value=moderator_text, inline=True)
        
        if kwargs.get('reason'):
            embed.add_field(name="Reason", value=kwargs['reason'][:1024], inline=True)
        
        if kwargs.get('channel_name') and event_type not in ['voice_join', 'voice_leave', 'stage_speaker_add', 'stage_speaker_remove', 'stage_request_speak']:
            embed.add_field(name="Channel", value=f"#{kwargs['channel_name']}", inline=True)
        
        # Add before/after values for changes
        if event_type == 'avatar_change':
            # Special handling for avatar changes
            if kwargs.get('before_value'):
                embed.add_field(name="Old Avatar", value=f"[Link]({kwargs['before_value']})", inline=True)
            if kwargs.get('after_value'):
                embed.add_field(name="New Avatar", value=f"[Link]({kwargs['after_value']})", inline=True)
                embed.set_thumbnail(url=kwargs['after_value'])
        elif kwargs.get('before_value') and kwargs.get('after_value') and event_type not in ['role_add', 'role_remove']:
            embed.add_field(name="Before", value=str(kwargs['before_value'])[:1024], inline=True)
            embed.add_field(name="After", value=str(kwargs['after_value'])[:1024], inline=True)
        elif kwargs.get('before_value') and event_type != 'role_remove':
            embed.add_field(name="Previous Value", value=str(kwargs['before_value'])[:1024], inline=False)
        elif kwargs.get('after_value') and event_type != 'role_add':
            embed.add_field(name="New Value", value=str(kwargs['after_value'])[:1024], inline=False)
        
        # Add duration for voice events
        if event_type == 'voice_leave' and kwargs.get('additional_data', {}).get('duration'):
            duration = kwargs['additional_data']['duration']
            embed.add_field(name="Session Duration", value=format_duration(duration), inline=True)
        
        # Add message content for message events
        if event_type in ['message_delete', 'message_edit']:
            if event_type == 'message_delete' and kwargs.get('before_value'):
                embed.add_field(name="Content", value=kwargs['before_value'][:1024], inline=False)
            elif event_type == 'message_edit':
                if kwargs.get('before_value'):
                    embed.add_field(name="Before", value=kwargs['before_value'][:1024], inline=False)
                if kwargs.get('after_value'):
                    embed.add_field(name="After", value=kwargs['after_value'][:1024], inline=False)
        
        # Add member count for join events
        if event_type == 'member_join' and kwargs.get('additional_data', {}).get('member_count'):
            member_count = kwargs['additional_data']['member_count']
            embed.add_field(name="Member Count", value=f"{member_count} members", inline=True)
        
        # Add account age for join events
        if event_type == 'member_join' and kwargs.get('additional_data', {}).get('account_created'):
            try:
                created_dt = datetime.fromisoformat(kwargs['additional_data']['account_created'])
                account_age = datetime.utcnow() - created_dt.replace(tzinfo=None)
                if account_age.days < 1:
                    age_text = f"{account_age.seconds // 3600}h {(account_age.seconds % 3600) // 60}m old"
                elif account_age.days < 30:
                    age_text = f"{account_age.days} days old"
                else:
                    age_text = f"{account_age.days // 30} months old"
                embed.add_field(name="Account Age", value=age_text, inline=True)
            except:
                pass
        
        # Add stage topic if available
        if event_type.startswith('stage_') and kwargs.get('additional_data', {}).get('stage_topic'):
            embed.add_field(
                name="Stage Topic",
                value=kwargs['additional_data']['stage_topic'],
                inline=True
            )
        
        # Add user ID in footer
        if kwargs.get('target_id'):
            embed.set_footer(text=f"User ID: {kwargs['target_id']}")
        elif kwargs.get('user_id'):
            embed.set_footer(text=f"User ID: {kwargs['user_id']}")
        
        return embed
        
    except Exception as e:
        print(f"❌ Error creating embed for {event_type}: {e}")
        return None

def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}m {seconds}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

# ========================= MODERATOR DETECTION =========================

async def get_moderator_from_audit_log(guild: discord.Guild, target_id: int, action_type, lookback_seconds: int = 10):
    """Get moderator who performed an action from Discord's audit log."""
    try:
        cutoff_time = datetime.utcnow() - timedelta(seconds=lookback_seconds)
        
        async for entry in guild.audit_logs(limit=10, after=cutoff_time):
            if (entry.target and hasattr(entry.target, 'id') and 
                entry.target.id == target_id and entry.action == action_type):
                return entry.user, entry.reason
        
        return None, None
        
    except Exception as e:
        print(f"Error getting moderator from audit log: {e}")
        return None, None

# ========================= VOICE SESSION TRACKING =========================

async def start_voice_session(guild_id: int, user_id: int, user_name: str, channel_id: int, channel_name: str, channel_type: str):
    """Start tracking a voice session."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # End any existing active sessions for this user
            await db.execute("""
                UPDATE voice_sessions 
                SET is_active = FALSE, leave_time = ?, 
                    duration_seconds = CAST((julianday(?) - julianday(join_time)) * 86400 AS INTEGER)
                WHERE guild_id = ? AND user_id = ? AND is_active = TRUE
            """, (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), guild_id, user_id))
            
            # Start new session
            await db.execute("""
                INSERT INTO voice_sessions 
                (guild_id, user_id, user_name, channel_id, channel_name, channel_type, join_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (guild_id, user_id, user_name, channel_id, channel_name, channel_type, datetime.utcnow().isoformat()))
            
            await db.commit()
            print(f"✅ Started voice session for {user_name} in {channel_name}")
            
    except Exception as e:
        print(f"Error starting voice session: {e}")

async def end_voice_session(guild_id: int, user_id: int):
    """End a voice session and return duration."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Get active session
            async with db.execute("""
                SELECT join_time FROM voice_sessions 
                WHERE guild_id = ? AND user_id = ? AND is_active = TRUE 
                ORDER BY join_time DESC LIMIT 1
            """, (guild_id, user_id)) as cursor:
                result = await cursor.fetchone()
            
            if result:
                join_time_str = result[0]
                join_time = datetime.fromisoformat(join_time_str)
                leave_time = datetime.utcnow()
                duration_seconds = int((leave_time - join_time).total_seconds())
                
                # Update session
                await db.execute("""
                    UPDATE voice_sessions 
                    SET is_active = FALSE, leave_time = ?, duration_seconds = ?
                    WHERE guild_id = ? AND user_id = ? AND is_active = TRUE
                """, (leave_time.isoformat(), duration_seconds, guild_id, user_id))
                
                await db.commit()
                print(f"✅ Ended voice session, duration: {duration_seconds}s")
                return duration_seconds
        
        return 0
        
    except Exception as e:
        print(f"Error ending voice session: {e}")
        return 0

# ========================= CLEANUP TASK =========================

@tasks.loop(hours=24)
async def cleanup_old_logs():
    """Clean up old audit logs based on retention settings."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Get all guild retention settings
            async with db.execute("SELECT guild_id, retention_days FROM audit_settings WHERE retention_days > 0") as cursor:
                guilds = await cursor.fetchall()
            
            for guild_id, retention_days in guilds:
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                cutoff_str = cutoff_date.isoformat()
                
                # Delete old audit logs
                await db.execute(
                    "DELETE FROM audit_logs WHERE guild_id = ? AND timestamp < ?",
                    (guild_id, cutoff_str)
                )
                
                # Delete old voice sessions
                await db.execute(
                    "DELETE FROM voice_sessions WHERE guild_id = ? AND is_active = FALSE AND join_time < ?",
                    (guild_id, cutoff_str)
                )
            
            await db.commit()
            print("✅ Audit log cleanup completed")
            
    except Exception as e:
        print(f"Error during audit log cleanup: {e}")

# ========================= PERMISSION HELPER =========================

def check_audit_permissions(user, roles_list):
    """Check if user has required permissions for audit commands."""
    if user.guild_permissions.administrator:
        return True
    user_roles = [role.name for role in user.roles]
    return any(role in user_roles for role in roles_list)

# ========================= EVENT HANDLER COG =========================

class AuditEventHandler(commands.Cog):
    """Handles all audit events and detection."""
    
    def __init__(self, bot):
        self.bot = bot
        global _bot_instance
        _bot_instance = bot
        print("🔍 Audit Event Handler initialized!")

    # ========================= MEMBER EVENTS =========================
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle member join events."""
        if not member.guild:
            return
            
        print(f"📥 Member joined: {member} in {member.guild.name}")
        
        try:
            await log_audit_event(
                member.guild.id,
                'member_join',
                user_id=member.id,
                user_name=str(member),
                additional_data={
                    'account_created': member.created_at.isoformat(),
                    'member_count': member.guild.member_count
                }
            )
        except Exception as e:
            print(f"❌ Error logging member join: {e}")
    
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Handle member leave/kick/ban events with smart detection."""
        print(f"📤 Member removed: {member} from {member.guild.name}")
        
        guild_id = member.guild.id
        user_id = member.id
        user_name = str(member)
        
        # Wait a moment for audit logs to populate
        await asyncio.sleep(2)
        
        # Check for kick
        moderator, reason = await get_moderator_from_audit_log(
            member.guild, user_id, discord.AuditLogAction.kick
        )
        
        if moderator:
            await log_audit_event(
                guild_id, 'member_kick',
                target_id=user_id, target_name=user_name,
                moderator_id=moderator.id, moderator_name=str(moderator),
                reason=reason
            )
            return
        
        # Check for ban
        moderator, reason = await get_moderator_from_audit_log(
            member.guild, user_id, discord.AuditLogAction.ban
        )
        
        if moderator:
            await log_audit_event(
                guild_id, 'member_ban',
                target_id=user_id, target_name=user_name,
                moderator_id=moderator.id, moderator_name=str(moderator),
                reason=reason
            )
            return
        
        # Regular leave
        await log_audit_event(
            guild_id, 'member_leave',
            user_id=user_id, user_name=user_name
        )
    
    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        """Handle member ban events (backup detection)."""
        print(f"🔨 Member banned: {user} from {guild.name}")
        
        await asyncio.sleep(1)
        
        moderator, reason = await get_moderator_from_audit_log(
            guild, user.id, discord.AuditLogAction.ban
        )
        
        await log_audit_event(
            guild.id, 'member_ban',
            target_id=user.id, target_name=str(user),
            moderator_id=moderator.id if moderator else None,
            moderator_name=str(moderator) if moderator else None,
            reason=reason
        )
    
    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        """Handle member unban events."""
        print(f"🔓 Member unbanned: {user} from {guild.name}")
        
        await asyncio.sleep(1)
        
        moderator, reason = await get_moderator_from_audit_log(
            guild, user.id, discord.AuditLogAction.unban
        )
        
        await log_audit_event(
            guild.id, 'member_unban',
            target_id=user.id, target_name=str(user),
            moderator_id=moderator.id if moderator else None,
            moderator_name=str(moderator) if moderator else None,
            reason=reason
        )
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Handle member updates (nickname changes, timeouts, avatar changes, etc.)."""
        guild_id = after.guild.id
        
        # Check for avatar changes
        if before.display_avatar.url != after.display_avatar.url:
            print(f"🖼️ Avatar changed: {after}")
            
            await log_audit_event(
                guild_id, 'avatar_change',
                user_id=after.id,
                user_name=str(after),
                before_value=before.display_avatar.url,
                after_value=after.display_avatar.url
            )
        
        # Check for nickname changes
        if before.nick != after.nick:
            print(f"📝 Nickname changed: {before.nick} -> {after.nick} for {after}")
            
            await log_audit_event(
                guild_id, 'nickname_change',
                target_id=after.id, target_name=str(after),
                before_value=before.nick or before.name,
                after_value=after.nick or after.name
            )
        
        # Check for timeout changes
        if before.timed_out_until != after.timed_out_until:
            await asyncio.sleep(1)
            
            if after.timed_out_until and not before.timed_out_until:
                print(f"⏰ Member timed out: {after}")
                
                moderator, reason = await get_moderator_from_audit_log(
                    after.guild, after.id, discord.AuditLogAction.member_update
                )
                
                await log_audit_event(
                    guild_id, 'member_timeout',
                    target_id=after.id, target_name=str(after),
                    moderator_id=moderator.id if moderator else None,
                    moderator_name=str(moderator) if moderator else None,
                    reason=reason,
                    after_value=after.timed_out_until.isoformat() if after.timed_out_until else None
                )
            
            elif before.timed_out_until and not after.timed_out_until:
                print(f"⏰ Timeout removed: {after}")
                
                moderator, reason = await get_moderator_from_audit_log(
                    after.guild, after.id, discord.AuditLogAction.member_update
                )
                
                await log_audit_event(
                    guild_id, 'member_untimeout',
                    target_id=after.id, target_name=str(after),
                    moderator_id=moderator.id if moderator else None,
                    moderator_name=str(moderator) if moderator else None,
                    reason=reason
                )
        
        # Check for role changes
        if before.roles != after.roles:
            await self.handle_role_changes(before, after)

    async def handle_role_changes(self, before, after):
        """Handle role additions and removals."""
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        
        added_roles = after_roles - before_roles
        removed_roles = before_roles - after_roles
        
        await asyncio.sleep(1)
        
        # Log added roles
        for role in added_roles:
            print(f"➕ Role added: {role.name} to {after}")
            
            moderator, reason = await get_moderator_from_audit_log(
                after.guild, after.id, discord.AuditLogAction.member_role_update
            )
            
            await log_audit_event(
                after.guild.id, 'role_add',
                target_id=after.id, target_name=str(after),
                moderator_id=moderator.id if moderator else None,
                moderator_name=str(moderator) if moderator else None,
                after_value=role.name,
                reason=reason
            )
        
        # Log removed roles
        for role in removed_roles:
            print(f"➖ Role removed: {role.name} from {after}")
            
            moderator, reason = await get_moderator_from_audit_log(
                after.guild, after.id, discord.AuditLogAction.member_role_update
            )
            
            await log_audit_event(
                after.guild.id, 'role_remove',
                target_id=after.id, target_name=str(after),
                moderator_id=moderator.id if moderator else None,
                moderator_name=str(moderator) if moderator else None,
                before_value=role.name,
                reason=reason
            )

    # ========================= MESSAGE EVENTS =========================
    
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Handle message deletion events."""
        if message.author.bot or not message.guild:
            return
        
        print(f"🗑️ Message deleted by {message.author} in #{message.channel.name}")
        
        try:
            await log_audit_event(
                message.guild.id, 'message_delete',
                user_id=message.author.id, user_name=str(message.author),
                channel_id=message.channel.id, channel_name=message.channel.name,
                before_value=message.content[:1900] if message.content else "[No content]",
                additional_data={
                    'message_id': message.id,
                    'attachments': [{'filename': att.filename, 'size': att.size} for att in message.attachments],
                    'embeds_count': len(message.embeds)
                }
            )
        except Exception as e:
            print(f"❌ Error logging message delete: {e}")
    
    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        """Handle bulk message deletion events."""
        if not messages:
            return
        
        # Get the channel from the first message
        channel = messages[0].channel
        guild = channel.guild
        
        if not guild:
            return
        
        print(f"🗑️ Bulk delete: {len(messages)} messages in #{channel.name}")
        
        try:
            # Count non-bot messages
            user_messages = [msg for msg in messages if not msg.author.bot]
            
            await log_audit_event(
                guild.id, 'message_bulk_delete',
                channel_id=channel.id, channel_name=channel.name,
                additional_data={
                    'total_count': len(messages),
                    'user_messages': len(user_messages),
                    'bot_messages': len(messages) - len(user_messages)
                }
            )
        except Exception as e:
            print(f"❌ Error logging bulk message delete: {e}")
    
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        """Handle message edit events."""
        if before.author.bot or before.content == after.content or not before.guild:
            return
        
        print(f"📝 Message edited by {before.author} in #{before.channel.name}")
        
        try:
            await log_audit_event(
                before.guild.id, 'message_edit',
                user_id=before.author.id, user_name=str(before.author),
                channel_id=before.channel.id, channel_name=before.channel.name,
                before_value=before.content[:900] if before.content else "[No content]",
                after_value=after.content[:900] if after.content else "[No content]",
                additional_data={'message_id': before.id}
            )
        except Exception as e:
            print(f"❌ Error logging message edit: {e}")

    # ========================= VOICE AND STAGE EVENTS =========================
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle comprehensive voice state updates including stage changes."""
        guild_id = member.guild.id
        user_id = member.id
        user_name = str(member)
        
        try:
            # Voice channel join
            if before.channel is None and after.channel is not None:
                print(f"🔊 {user_name} joined voice channel {after.channel.name}")
                
                channel_type = "Stage" if isinstance(after.channel, discord.StageChannel) else "Voice"
                
                await start_voice_session(
                    guild_id, user_id, user_name, 
                    after.channel.id, after.channel.name, channel_type
                )
                
                await log_audit_event(
                    guild_id, 'voice_join',
                    user_id=user_id, user_name=user_name,
                    channel_id=after.channel.id, channel_name=after.channel.name,
                    additional_data={'channel_type': channel_type}
                )
            
            # Voice channel leave
            elif before.channel is not None and after.channel is None:
                print(f"🔇 {user_name} left voice channel {before.channel.name}")
                
                duration = await end_voice_session(guild_id, user_id)
                
                # Check if this was a disconnect by moderator
                await asyncio.sleep(1)
                moderator, reason = await get_moderator_from_audit_log(
                    member.guild, user_id, discord.AuditLogAction.member_disconnect
                )
                
                if moderator:
                    # This was a moderator disconnect
                    await log_audit_event(
                        guild_id, 'voice_disconnect',
                        target_id=user_id, target_name=user_name,
                        moderator_id=moderator.id, moderator_name=str(moderator),
                        channel_id=before.channel.id, channel_name=before.channel.name,
                        reason=reason,
                        additional_data={'duration': duration}
                    )
                else:
                    # Normal leave
                    await log_audit_event(
                        guild_id, 'voice_leave',
                        user_id=user_id, user_name=user_name,
                        channel_id=before.channel.id, channel_name=before.channel.name,
                        additional_data={'duration': duration}
                    )
            
            # Voice channel move
            elif before.channel is not None and after.channel is not None and before.channel != after.channel:
                print(f"🔀 {user_name} moved from {before.channel.name} to {after.channel.name}")
                
                # End old session and start new one
                duration = await end_voice_session(guild_id, user_id)
                
                channel_type = "Stage" if isinstance(after.channel, discord.StageChannel) else "Voice"
                await start_voice_session(
                    guild_id, user_id, user_name,
                    after.channel.id, after.channel.name, channel_type
                )
                
                # Check if it was a move by moderator
                await asyncio.sleep(1)
                moderator, reason = await get_moderator_from_audit_log(
                    member.guild, user_id, discord.AuditLogAction.member_move
                )
                
                await log_audit_event(
                    guild_id, 'voice_move',
                    user_id=user_id, user_name=user_name,
                    moderator_id=moderator.id if moderator else None,
                    moderator_name=str(moderator) if moderator else None,
                    before_value=before.channel.name,
                    after_value=after.channel.name,
                    reason=reason,
                    additional_data={'previous_duration': duration}
                )
            
            # Handle voice state changes (mute, deafen, etc.)
            if before.channel and after.channel:
                await self.handle_voice_state_changes(member, before, after)
            
            # Handle stage-specific state changes
            if isinstance(after.channel, discord.StageChannel):
                await self.handle_stage_state_changes(member, before, after)
                
        except Exception as e:
            print(f"❌ Error handling voice state update: {e}")

    async def handle_voice_state_changes(self, member, before, after):
        """Handle voice mute/deafen changes."""
        guild_id = member.guild.id
        user_id = member.id
        user_name = str(member)
        
        try:
            await asyncio.sleep(1)
            
            # Server mute changes
            if before.mute != after.mute:
                print(f"🔇 {user_name} {'muted' if after.mute else 'unmuted'}")
                
                moderator, reason = await get_moderator_from_audit_log(
                    member.guild, user_id, discord.AuditLogAction.member_update
                )
                
                event_type = 'voice_mute' if after.mute else 'voice_unmute'
                await log_audit_event(
                    guild_id, event_type,
                    target_id=user_id, target_name=user_name,
                    moderator_id=moderator.id if moderator else None,
                    moderator_name=str(moderator) if moderator else None,
                    channel_id=after.channel.id, channel_name=after.channel.name,
                    reason=reason
                )
            
            # Server deafen changes
            if before.deaf != after.deaf:
                print(f"🔕 {user_name} {'deafened' if after.deaf else 'undeafened'}")
                
                moderator, reason = await get_moderator_from_audit_log(
                    member.guild, user_id, discord.AuditLogAction.member_update
                )
                
                event_type = 'voice_deafen' if after.deaf else 'voice_undeafen'
                await log_audit_event(
                    guild_id, event_type,
                    target_id=user_id, target_name=user_name,
                    moderator_id=moderator.id if moderator else None,
                    moderator_name=str(moderator) if moderator else None,
                    channel_id=after.channel.id, channel_name=after.channel.name,
                    reason=reason
                )
        except Exception as e:
            print(f"❌ Error handling voice state changes: {e}")

    async def handle_stage_state_changes(self, member, before, after):
        """Handle stage speaker/listener changes with detailed information."""
        
        # Check if user became a speaker (was suppressed, now isn't)
        if before.suppress and not after.suppress:
            print(f"🎙️ {member} became a speaker in {after.channel.name}")
            
            # Wait for audit log
            await asyncio.sleep(1)
            
            # Try to find who invited them to speak
            moderator = None
            reason = None
            
            # Check for stage moderator action
            try:
                async for entry in member.guild.audit_logs(limit=5, after=datetime.utcnow() - timedelta(seconds=5)):
                    if (entry.action in [discord.AuditLogAction.stage_instance_update, 
                                       discord.AuditLogAction.member_update]):
                        if entry.target and hasattr(entry.target, 'id') and entry.target.id == member.id:
                            moderator = entry.user
                            reason = entry.reason
                            break
            except:
                pass
            
            # Get stage topic if available
            stage_topic = None
            try:
                if hasattr(after.channel, 'instance') and after.channel.instance:
                    stage_topic = after.channel.instance.topic
            except:
                pass
            
            await log_audit_event(
                member.guild.id, 'stage_speaker_add',
                target_id=member.id,
                target_name=str(member),
                moderator_id=moderator.id if moderator else None,
                moderator_name=str(moderator) if moderator else None,
                channel_id=after.channel.id,
                channel_name=after.channel.name,
                reason=reason,
                additional_data={
                    'invited_by': str(moderator) if moderator else 'Self-requested',
                    'stage_topic': stage_topic
                }
            )
        
        # Check if user became a listener (wasn't suppressed, now is)
        elif not before.suppress and after.suppress:
            print(f"👤 {member} became a listener in {after.channel.name}")
            
            # Wait for audit log
            await asyncio.sleep(1)
            
            # Try to find who moved them to audience
            moderator = None
            reason = None
            
            try:
                async for entry in member.guild.audit_logs(limit=5, after=datetime.utcnow() - timedelta(seconds=5)):
                    if (entry.action in [discord.AuditLogAction.stage_instance_update, 
                                       discord.AuditLogAction.member_update]):
                        if entry.target and hasattr(entry.target, 'id') and entry.target.id == member.id:
                            moderator = entry.user
                            reason = entry.reason
                            break
            except:
                pass
            
            # Get stage topic if available
            stage_topic = None
            try:
                if hasattr(after.channel, 'instance') and after.channel.instance:
                    stage_topic = after.channel.instance.topic
            except:
                pass
            
            await log_audit_event(
                member.guild.id, 'stage_speaker_remove',
                target_id=member.id,
                target_name=str(member),
                moderator_id=moderator.id if moderator else None,
                moderator_name=str(moderator) if moderator else None,
                channel_id=after.channel.id,
                channel_name=after.channel.name,
                reason=reason,
                additional_data={
                    'moved_by': str(moderator) if moderator else 'Self-moved',
                    'stage_topic': stage_topic
                }
            )
        
        # Check if user requested to speak (hand raised) - safely check for attribute
        if hasattr(before, 'request_to_speak_timestamp') and hasattr(after, 'request_to_speak_timestamp'):
            if not before.request_to_speak_timestamp and after.request_to_speak_timestamp:
                print(f"✋ {member} requested to speak in {after.channel.name}")
                
                # Get stage topic if available
                stage_topic = None
                try:
                    if hasattr(after.channel, 'instance') and after.channel.instance:
                        stage_topic = after.channel.instance.topic
                except:
                    pass
                
                await log_audit_event(
                    member.guild.id, 'stage_request_speak',
                    user_id=member.id,
                    user_name=str(member),
                    channel_id=after.channel.id,
                    channel_name=after.channel.name,
                    additional_data={
                        'request_time': after.request_to_speak_timestamp.isoformat(),
                        'stage_topic': stage_topic
                    }
                )

    # ========================= STAGE INSTANCE EVENTS =========================
    
    @commands.Cog.listener()
    async def on_stage_instance_create(self, stage_instance):
        """Handle stage instance creation."""
        print(f"🎙️ Stage started: {stage_instance.topic} in {stage_instance.channel.name}")
        
        await log_audit_event(
            stage_instance.guild.id, 'stage_start',
            channel_id=stage_instance.channel.id,
            channel_name=stage_instance.channel.name,
            after_value=stage_instance.topic,
            additional_data={
                'privacy_level': stage_instance.privacy_level.name,
                'discoverable': stage_instance.is_public() if hasattr(stage_instance, 'is_public') else False
            }
        )

    @commands.Cog.listener()
    async def on_stage_instance_delete(self, stage_instance):
        """Handle stage instance deletion."""
        print(f"🎙️ Stage ended: {stage_instance.topic} in {stage_instance.channel.name}")
        
        await log_audit_event(
            stage_instance.guild.id, 'stage_end',
            channel_id=stage_instance.channel.id,
            channel_name=stage_instance.channel.name,
            before_value=stage_instance.topic
        )

    # ========================= SERVER EVENTS =========================
    
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        """Handle channel creation events."""
        print(f"📋 Channel created: {channel.name} in {channel.guild.name}")
        
        await asyncio.sleep(1)
        
        moderator, reason = await get_moderator_from_audit_log(
            channel.guild, channel.id, discord.AuditLogAction.channel_create
        )
        
        await log_audit_event(
            channel.guild.id, 'channel_create',
            moderator_id=moderator.id if moderator else None,
            moderator_name=str(moderator) if moderator else None,
            channel_id=channel.id, channel_name=channel.name,
            after_value=f"{channel.type.name.title()} Channel",
            reason=reason
        )
    
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Handle channel deletion events."""
        print(f"📋 Channel deleted: {channel.name} from {channel.guild.name}")
        
        await asyncio.sleep(1)
        
        moderator, reason = await get_moderator_from_audit_log(
            channel.guild, channel.id, discord.AuditLogAction.channel_delete
        )
        
        await log_audit_event(
            channel.guild.id, 'channel_delete',
            moderator_id=moderator.id if moderator else None,
            moderator_name=str(moderator) if moderator else None,
            channel_name=channel.name,
            before_value=f"{channel.type.name.title()} Channel",
            reason=reason
        )
    
    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        """Handle role creation events."""
        print(f"🎭 Role created: {role.name} in {role.guild.name}")
        
        await asyncio.sleep(1)
        
        moderator, reason = await get_moderator_from_audit_log(
            role.guild, role.id, discord.AuditLogAction.role_create
        )
        
        await log_audit_event(
            role.guild.id, 'role_create',
            moderator_id=moderator.id if moderator else None,
            moderator_name=str(moderator) if moderator else None,
            after_value=role.name,
            reason=reason
        )
    
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        """Handle role deletion events."""
        print(f"🎭 Role deleted: {role.name} from {role.guild.name}")
        
        await asyncio.sleep(1)
        
        moderator, reason = await get_moderator_from_audit_log(
            role.guild, role.id, discord.AuditLogAction.role_delete
        )
        
        await log_audit_event(
            role.guild.id, 'role_delete',
            moderator_id=moderator.id if moderator else None,
            moderator_name=str(moderator) if moderator else None,
            before_value=role.name,
            reason=reason
        )

# ========================= COMMAND COG =========================

class AuditCommands(commands.Cog):
    """Audit logging configuration commands."""
    
    def __init__(self, bot):
        self.bot = bot
        print("⚙️ Audit Commands initialized!")

    @app_commands.command(name="auditsetup", description="🔧 Set up audit logging for your server")
    async def audit_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set up audit logging in a channel."""
        if not check_audit_permissions(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("❌ You don't have permission to configure audit logging.", ephemeral=True)
            return
        
        # Check bot permissions in the channel
        permissions = channel.permissions_for(interaction.guild.me)
        if not all([permissions.send_messages, permissions.embed_links, permissions.view_channel]):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description=f"I need the following permissions in {channel.mention}:",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Required Permissions",
                value="• View Channel\n• Send Messages\n• Embed Links",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Save settings
        await save_audit_settings(
            interaction.guild.id,
            enabled=True,
            log_channel_id=channel.id
        )
        
        # Create success embed
        embed = discord.Embed(
            title="✅ Audit Logging Configured",
            description=f"Audit logs will now be sent to {channel.mention}",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="📋 What will be logged:",
            value=(
                "🔨 **Moderation**: Bans, kicks, timeouts, mutes/deafens, disconnects\n"
                "💬 **Messages**: Edits, deletions, bulk deletions with content\n"
                "🔊 **Voice**: Joins, leaves, moves, session durations\n"
                "👤 **Members**: Joins, leaves, nickname changes, avatar changes\n"
                "🎭 **Roles**: Role additions, removals, creations\n"
                "🏠 **Server**: Channel changes, emoji updates\n"
                "🎙️ **Stage**: Speaker/listener changes with moderator info\n"
                "🖼️ **Avatars**: Member avatar changes with preview\n"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Next Steps:",
            value="• Use `/auditdisable` to turn off logging\n• Use `/auditlogs` to view recent events",
            inline=False
        )
        
        embed.set_footer(text=f"Configured by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)
        
        # Send test message to audit channel
        test_embed = discord.Embed(
            title="🔍 Audit Logging Test",
            description=f"**Audit logging is now active!**\n\nThis channel will receive comprehensive audit logs for {interaction.guild.name}.",
            color=discord.Color.blue()
        )
        
        test_embed.add_field(
            name="✨ Enhanced Features",
            value=(
                "• **Moderator Disconnect Detection** - See who disconnected members\n"
                "• **Message Content Preservation** - Deleted message content saved\n"
                "• **Avatar Change Tracking** - Visual preview of avatar changes\n"
                "• **Enhanced Stage Detection** - Fixed stage event tracking"
            ),
            inline=False
        )
        
        test_embed.set_footer(text=f"Configured by {interaction.user.display_name}")
        test_embed.timestamp = datetime.utcnow()
        
        try:
            await channel.send(embed=test_embed)
        except:
            pass  # Don't fail if we can't send test message

    @app_commands.command(name="auditdisable", description="🔴 Disable audit logging")
    async def audit_disable(self, interaction: discord.Interaction):
        """Disable audit logging."""
        if not check_audit_permissions(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("❌ You don't have permission to configure audit logging.", ephemeral=True)
            return
        
        await save_audit_settings(interaction.guild.id, enabled=False)
        
        embed = discord.Embed(
            title="🔴 Audit Logging Disabled",
            description="Audit logging has been disabled for this server.",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="ℹ️ Note:",
            value="Existing logs are preserved. You can re-enable logging anytime with `/auditsetup`.",
            inline=False
        )
        
        embed.set_footer(text=f"Disabled by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="auditlogs", description="📋 View recent audit logs")
    @app_commands.describe(
        limit="Number of logs to show (1-20)",
        event_type="Filter by event type"
    )
    async def audit_logs(self, interaction: discord.Interaction, limit: int = 10, event_type: str = None):
        """View recent audit logs."""
        if not check_audit_permissions(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("❌ You don't have permission to view audit logs.", ephemeral=True)
            return
        
        limit = max(1, min(20, limit))
        
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                query = "SELECT event_type, user_name, target_name, moderator_name, channel_name, reason, timestamp FROM audit_logs WHERE guild_id = ?"
                params = [interaction.guild.id]
                
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                async with db.execute(query, params) as cursor:
                    logs = await cursor.fetchall()
            
            if not logs:
                embed = discord.Embed(
                    title="📋 Audit Logs",
                    description="No audit logs found.",
                    color=discord.Color.orange()
                )
            else:
                embed = discord.Embed(
                    title="📋 Recent Audit Logs",
                    description=f"Showing {len(logs)} most recent events",
                    color=discord.Color.blue()
                )
                
                for i, log in enumerate(logs[:10], 1):
                    event_type_val, user_name, target_name, moderator_name, channel_name, reason, timestamp = log
                    
                    # Format timestamp
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        time_str = f"<t:{int(dt.timestamp())}:R>"
                    except:
                        time_str = timestamp
                    
                    # Build description
                    description = f"**{event_type_val.replace('_', ' ').title()}**"
                    if user_name:
                        description += f" by {user_name}"
                    if target_name and target_name != user_name:
                        description += f" → {target_name}"
                    if moderator_name and moderator_name not in [user_name, target_name]:
                        description += f" (by {moderator_name})"
                    
                    if channel_name:
                        description += f" in #{channel_name}"
                    
                    if reason:
                        description += f"\n*{reason[:100]}{'...' if len(reason) > 100 else ''}*"
                    
                    embed.add_field(
                        name=f"{i}. {time_str}",
                        value=description,
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error retrieving logs: {str(e)}", ephemeral=True)

    @app_commands.command(name="audittest", description="🧪 Test audit logging")
    async def audit_test(self, interaction: discord.Interaction):
        """Test audit logging system."""
        if not check_audit_permissions(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("❌ You don't have permission to test audit logging.", ephemeral=True)
            return
        
        # Test by creating a fake audit event
        await log_audit_event(
            interaction.guild.id,
            'member_join',
            user_id=interaction.user.id,
            user_name=str(interaction.user),
            additional_data={'test_event': True}
        )
        
        embed = discord.Embed(
            title="🧪 Audit Test Complete",
            description="A test audit event has been sent. Check your audit channel!",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="auditfix", description="🔧 Fix audit database schema")
    async def audit_fix(self, interaction: discord.Interaction):
        """Fix audit database schema issues."""
        if not check_audit_permissions(interaction.user, ALLOWED_MANAGEMENT_ROLES):
            await interaction.response.send_message("❌ You don't have permission to fix audit database.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # First, let's check what the current table looks like
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("PRAGMA table_info(audit_logs)") as cursor:
                    columns = await cursor.fetchall()
                    column_info = [(col[1], col[2]) for col in columns] if columns else []
            
            info_text = "**Current table structure:**\n"
            if column_info:
                for col_name, col_type in column_info:
                    info_text += f"• {col_name} ({col_type})\n"
            else:
                info_text += "No table found.\n"
            
            # Now fix the schema
            await init_audit_logs_table()
            
            # Check the updated structure
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("PRAGMA table_info(audit_logs)") as cursor:
                    columns = await cursor.fetchall()
                    new_column_info = [(col[1], col[2]) for col in columns] if columns else []
            
            info_text += "\n**Updated table structure:**\n"
            if new_column_info:
                for col_name, col_type in new_column_info:
                    info_text += f"• {col_name} ({col_type})\n"
            
            embed = discord.Embed(
                title="✅ Database Schema Fixed",
                description="The audit database schema has been updated.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Schema Information",
                value=info_text[:1024],  # Discord embed field limit
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Database Fix Failed",
                description=f"Error fixing database: {str(e)}",
                color=discord.Color.red()
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)

# ========================= MAIN COG =========================

class AuditLogs(commands.Cog):
    """Main audit logging system coordinator."""
    
    def __init__(self, bot):
        self.bot = bot
        print("🔍✨ Enhanced Audit Logging System initialized!")
    
    async def cog_load(self):
        """Initialize the audit system when the cog loads."""
        print("🔍 Initializing Enhanced Audit Logging System...")
        
        # Initialize database
        await init_audit_logs_table()
        
        # Start cleanup task
        if not cleanup_old_logs.is_running():
            cleanup_old_logs.start()
            print("🧹 Audit log cleanup task started")
        
        print("✅ Enhanced Audit Logging System ready!")
    
    async def cog_unload(self):
        """Clean up when the cog unloads."""
        if cleanup_old_logs.is_running():
            cleanup_old_logs.cancel()
            print("🧹 Audit log cleanup task stopped")
        
        print("🔍 Enhanced Audit Logging System unloaded")

async def setup(bot):
    """Setup function to load all audit components."""
    try:
        # Load main audit system
        await bot.add_cog(AuditLogs(bot))
        
        # Load event handler
        await bot.add_cog(AuditEventHandler(bot))
        
        # Load commands
        await bot.add_cog(AuditCommands(bot))
        
        print("✅✨ Complete Enhanced Audit Logging System loaded successfully!")
        
    except Exception as e:
        print(f"❌ Failed to setup Enhanced Audit Logging System: {e}")
        raise