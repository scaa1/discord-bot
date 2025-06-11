# database/tickets.py
import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH
from typing import List, Tuple, Optional, Dict

async def init_tickets_table():
    """Initialize the tickets database table."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Create tickets table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    ticket_type TEXT NOT NULL CHECK (ticket_type IN ('support', 'team_registration')),
                    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'closed', 'resolved')),
                    title TEXT,
                    description TEXT,
                    assigned_to INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    closed_at TEXT,
                    closed_by INTEGER
                )
            """)
            
            # Create team registration data table for storing form responses
            await db.execute("""
                CREATE TABLE IF NOT EXISTS team_registration_data (
                    ticket_id INTEGER PRIMARY KEY,
                    team_name TEXT,
                    team_role_color TEXT,
                    invite_link TEXT,
                    logo_icon TEXT,
                    additional_notes TEXT,
                    completed BOOLEAN DEFAULT 0,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
                )
            """)
            
            # Create ticket messages table for logging
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    message_content TEXT,
                    message_type TEXT DEFAULT 'user' CHECK (message_type IN ('user', 'staff', 'system')),
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
                )
            """)
            
            await db.commit()
            print("✅ Tickets database tables initialized successfully")
            
    except Exception as e:
        print(f"❌ Error initializing tickets database: {e}")
        import traceback
        traceback.print_exc()

# ========================= TICKET FUNCTIONS =========================

async def create_ticket(channel_id: int, user_id: int, ticket_type: str, title: str = None, description: str = None) -> int:
    """Create a new ticket and return the ticket ID."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                INSERT INTO tickets (channel_id, user_id, ticket_type, title, description)
                VALUES (?, ?, ?, ?, ?)
            """, (channel_id, user_id, ticket_type, title, description))
            
            ticket_id = cursor.lastrowid
            
            # If it's a team registration ticket, create the form data entry
            if ticket_type == 'team_registration':
                await db.execute("""
                    INSERT INTO team_registration_data (ticket_id)
                    VALUES (?)
                """, (ticket_id,))
            
            await db.commit()
            return ticket_id
            
    except Exception as e:
        print(f"Error creating ticket: {e}")
        return None

async def get_ticket_by_channel(channel_id: int) -> Optional[Dict]:
    """Get ticket information by channel ID."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT ticket_id, channel_id, user_id, ticket_type, status, title, description,
                       assigned_to, created_at, updated_at, closed_at, closed_by
                FROM tickets
                WHERE channel_id = ?
            """, (channel_id,)) as cursor:
                result = await cursor.fetchone()
                
                if result:
                    return {
                        'ticket_id': result[0],
                        'channel_id': result[1],
                        'user_id': result[2],
                        'ticket_type': result[3],
                        'status': result[4],
                        'title': result[5],
                        'description': result[6],
                        'assigned_to': result[7],
                        'created_at': result[8],
                        'updated_at': result[9],
                        'closed_at': result[10],
                        'closed_by': result[11]
                    }
                return None
    except Exception as e:
        print(f"Error getting ticket by channel: {e}")
        return None

async def get_ticket_by_id(ticket_id: int) -> Optional[Dict]:
    """Get ticket information by ticket ID."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT ticket_id, channel_id, user_id, ticket_type, status, title, description,
                       assigned_to, created_at, updated_at, closed_at, closed_by
                FROM tickets
                WHERE ticket_id = ?
            """, (ticket_id,)) as cursor:
                result = await cursor.fetchone()
                
                if result:
                    return {
                        'ticket_id': result[0],
                        'channel_id': result[1],
                        'user_id': result[2],
                        'ticket_type': result[3],
                        'status': result[4],
                        'title': result[5],
                        'description': result[6],
                        'assigned_to': result[7],
                        'created_at': result[8],
                        'updated_at': result[9],
                        'closed_at': result[10],
                        'closed_by': result[11]
                    }
                return None
    except Exception as e:
        print(f"Error getting ticket by ID: {e}")
        return None

async def update_ticket_status(ticket_id: int, status: str, closed_by: int = None) -> bool:
    """Update ticket status."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if status == 'closed':
                await db.execute("""
                    UPDATE tickets
                    SET status = ?, updated_at = ?, closed_at = ?, closed_by = ?
                    WHERE ticket_id = ?
                """, (status, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), closed_by, ticket_id))
            else:
                await db.execute("""
                    UPDATE tickets
                    SET status = ?, updated_at = ?
                    WHERE ticket_id = ?
                """, (status, datetime.utcnow().isoformat(), ticket_id))
            
            await db.commit()
            return True
    except Exception as e:
        print(f"Error updating ticket status: {e}")
        return False

async def assign_ticket(ticket_id: int, assigned_to: int) -> bool:
    """Assign ticket to a staff member."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                UPDATE tickets
                SET assigned_to = ?, updated_at = ?
                WHERE ticket_id = ?
            """, (assigned_to, datetime.utcnow().isoformat(), ticket_id))
            
            await db.commit()
            return True
    except Exception as e:
        print(f"Error assigning ticket: {e}")
        return False

async def get_all_tickets(status: str = None, ticket_type: str = None, limit: int = 50) -> List[Dict]:
    """Get all tickets with optional filters."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            query = """
                SELECT ticket_id, channel_id, user_id, ticket_type, status, title, description,
                       assigned_to, created_at, updated_at, closed_at, closed_by
                FROM tickets
            """
            params = []
            conditions = []
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            if ticket_type:
                conditions.append("ticket_type = ?")
                params.append(ticket_type)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            async with db.execute(query, params) as cursor:
                results = await cursor.fetchall()
                
                tickets = []
                for result in results:
                    tickets.append({
                        'ticket_id': result[0],
                        'channel_id': result[1],
                        'user_id': result[2],
                        'ticket_type': result[3],
                        'status': result[4],
                        'title': result[5],
                        'description': result[6],
                        'assigned_to': result[7],
                        'created_at': result[8],
                        'updated_at': result[9],
                        'closed_at': result[10],
                        'closed_by': result[11]
                    })
                
                return tickets
    except Exception as e:
        print(f"Error getting tickets: {e}")
        return []

# ========================= TEAM REGISTRATION FUNCTIONS =========================

async def update_team_registration_data(ticket_id: int, **kwargs) -> bool:
    """Update team registration form data."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Build dynamic update query
            valid_fields = ['team_name', 'team_role_color', 'invite_link', 'logo_icon', 'additional_notes', 'completed']
            set_clauses = []
            params = []
            
            for field, value in kwargs.items():
                if field in valid_fields:
                    set_clauses.append(f"{field} = ?")
                    params.append(value)
            
            if not set_clauses:
                return False
            
            params.append(ticket_id)
            
            query = f"""
                UPDATE team_registration_data
                SET {', '.join(set_clauses)}
                WHERE ticket_id = ?
            """
            
            await db.execute(query, params)
            await db.commit()
            return True
            
    except Exception as e:
        print(f"Error updating team registration data: {e}")
        return False

async def get_team_registration_data(ticket_id: int) -> Optional[Dict]:
    """Get team registration form data."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT team_name, team_role_color, invite_link, logo_icon, 
                       additional_notes, completed
                FROM team_registration_data
                WHERE ticket_id = ?
            """, (ticket_id,)) as cursor:
                result = await cursor.fetchone()
                
                if result:
                    return {
                        'team_name': result[0],
                        'team_role_color': result[1],
                        'invite_link': result[2],
                        'logo_icon': result[3],
                        'additional_notes': result[4],
                        'completed': bool(result[5])
                    }
                return None
    except Exception as e:
        print(f"Error getting team registration data: {e}")
        return None

# ========================= MESSAGE LOGGING =========================

async def log_ticket_message(ticket_id: int, user_id: int, username: str, message_content: str, message_type: str = 'user') -> bool:
    """Log a message in the ticket."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO ticket_messages (ticket_id, user_id, username, message_content, message_type)
                VALUES (?, ?, ?, ?, ?)
            """, (ticket_id, user_id, username, message_content, message_type))
            
            await db.commit()
            return True
    except Exception as e:
        print(f"Error logging ticket message: {e}")
        return False

async def get_ticket_messages(ticket_id: int, limit: int = 100) -> List[Dict]:
    """Get messages from a ticket."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("""
                SELECT message_id, user_id, username, message_content, message_type, timestamp
                FROM ticket_messages
                WHERE ticket_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (ticket_id, limit)) as cursor:
                results = await cursor.fetchall()
                
                messages = []
                for result in results:
                    messages.append({
                        'message_id': result[0],
                        'user_id': result[1],
                        'username': result[2],
                        'message_content': result[3],
                        'message_type': result[4],
                        'timestamp': result[5]
                    })
                
                return messages
    except Exception as e:
        print(f"Error getting ticket messages: {e}")
        return []

# ========================= UTILITY FUNCTIONS =========================

async def get_ticket_stats() -> Dict:
    """Get ticket system statistics."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Total tickets
            async with db.execute("SELECT COUNT(*) FROM tickets") as cursor:
                total_tickets = (await cursor.fetchone())[0]
            
            # Open tickets
            async with db.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'") as cursor:
                open_tickets = (await cursor.fetchone())[0]
            
            # Support tickets
            async with db.execute("SELECT COUNT(*) FROM tickets WHERE ticket_type = 'support'") as cursor:
                support_tickets = (await cursor.fetchone())[0]
            
            # Team registration tickets
            async with db.execute("SELECT COUNT(*) FROM tickets WHERE ticket_type = 'team_registration'") as cursor:
                team_reg_tickets = (await cursor.fetchone())[0]
            
            # Completed team registrations
            async with db.execute("""
                SELECT COUNT(*) FROM team_registration_data WHERE completed = 1
            """) as cursor:
                completed_registrations = (await cursor.fetchone())[0]
            
            return {
                'total_tickets': total_tickets,
                'open_tickets': open_tickets,
                'support_tickets': support_tickets,
                'team_registration_tickets': team_reg_tickets,
                'completed_registrations': completed_registrations
            }
    except Exception as e:
        print(f"Error getting ticket stats: {e}")
        return {
            'total_tickets': 0,
            'open_tickets': 0,
            'support_tickets': 0,
            'team_registration_tickets': 0,
            'completed_registrations': 0
        }

async def cleanup_old_tickets(days_old: int = 30) -> int:
    """Clean up old closed tickets (returns number of deleted tickets)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cutoff_date = (datetime.utcnow() - timedelta(days=days_old)).isoformat()
            
            cursor = await db.execute("""
                DELETE FROM tickets
                WHERE status = 'closed' AND closed_at < ?
            """, (cutoff_date,))
            
            deleted_count = cursor.rowcount
            await db.commit()
            
            return deleted_count
    except Exception as e:
        print(f"Error cleaning up old tickets: {e}")
        return 0