import re
import pytz
from datetime import datetime, timedelta
from dateutil import parser
from dateutil.relativedelta import relativedelta


def parse_flexible_datetime(when_str, timezone_str="EST"):
    """
    FIXED: Improved flexible datetime parser with better error handling
    Supports formats like:
    - "tomorrow 7pm"
    - "Friday 3:30pm" 
    - "12/25 2pm"
    - "Dec 25 14:00"
    - "next week 8pm"
    - "in 2 days 7pm"
    - "2025-01-15 19:30"
    """
    # Clean up input
    when_str = when_str.strip().lower()
    
    # Timezone mapping
    timezone_map = {
        'est': 'US/Eastern', 'edt': 'US/Eastern', 'eastern': 'US/Eastern',
        'cst': 'US/Central', 'cdt': 'US/Central', 'central': 'US/Central',
        'mst': 'US/Mountain', 'mdt': 'US/Mountain', 'mountain': 'US/Mountain',
        'pst': 'US/Pacific', 'pdt': 'US/Pacific', 'pacific': 'US/Pacific',
        'utc': 'UTC', 'gmt': 'UTC'
    }
    
    tz_name = timezone_map.get(timezone_str.lower(), 'US/Eastern')
    try:
        local_tz = pytz.timezone(tz_name)
    except:
        local_tz = pytz.timezone('US/Eastern')  # Fallback
        
    now = datetime.now(local_tz)
    
    # Handle "in X days/hours" format
    relative_in_match = re.search(r'in\s+(\d+)\s+(day|days|hour|hours)\s*(.*)', when_str)
    if relative_in_match:
        amount = int(relative_in_match.group(1))
        unit = relative_in_match.group(2)
        rest_of_string = relative_in_match.group(3).strip()
        
        if unit in ['day', 'days']:
            base_date = now + timedelta(days=amount)
        else:  # hours
            base_date = now + timedelta(hours=amount)
            
        # If there's time info in the rest, parse it
        if rest_of_string:
            when_str = rest_of_string
        else:
            # Default to current time if no specific time given
            return base_date.astimezone(pytz.utc)
    else:
        base_date = now

    # Handle other relative dates
    relative_patterns = {
        r'\btomorrow\b': now + timedelta(days=1),
        r'\bnext week\b': now + timedelta(weeks=1),
        r'\bnext month\b': now + relativedelta(months=1),
        r'\btoday\b': now,
    }
    
    # Check for relative dates
    for pattern, relative_date in relative_patterns.items():
        if re.search(pattern, when_str):
            base_date = relative_date
            when_str = re.sub(pattern, '', when_str).strip()
            break
    
    # Handle day names with better logic
    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for i, day in enumerate(day_names):
        if day in when_str:
            days_ahead = (i - now.weekday()) % 7
            if days_ahead == 0:  # If it's today, assume next week unless "today" was specified
                if 'today' not in when_str.lower():
                    days_ahead = 7
            base_date = now + timedelta(days=days_ahead)
            when_str = when_str.replace(day, '').strip()
            break
    
    # FIXED: Extract and parse time component with improved regex handling
    time_patterns = [
        (r'(\d{1,2}):(\d{2})\s*(am|pm|a\.?m\.?|p\.?m\.?)?', 'time_with_minutes'),  # 7:30pm, 19:30
        (r'(\d{1,2})\s*(am|pm|a\.?m\.?|p\.?m\.?)', 'time_with_ampm'),  # 7pm, 7 pm
        (r'(\d{1,2})\.(\d{2})', 'time_decimal'),  # 7.30 format
    ]
    
    time_match = None
    match_type = None
    for pattern, pattern_type in time_patterns:
        time_match = re.search(pattern, when_str.lower())
        if time_match:
            match_type = pattern_type
            break
    
    if time_match:
        # Handle different time patterns correctly
        if match_type == 'time_with_minutes':
            # Pattern: (\d{1,2}):(\d{2})\s*(am|pm|a\.?m\.?|p\.?m\.?)?
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            ampm = time_match.group(3) if time_match.group(3) else None
            
        elif match_type == 'time_with_ampm':
            # Pattern: (\d{1,2})\s*(am|pm|a\.?m\.?|p\.?m\.?)
            hour = int(time_match.group(1))
            minute = 0  # No minutes specified
            ampm = time_match.group(2) if time_match.group(2) else None
            
        elif match_type == 'time_decimal':
            # Pattern: (\d{1,2})\.(\d{2})
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            ampm = None
        
        # Handle AM/PM conversion
        if ampm:
            ampm_clean = ampm.replace('.', '').lower()
            if ampm_clean.startswith('p') and hour != 12:
                hour += 12
            elif ampm_clean.startswith('a') and hour == 12:
                hour = 0
        
        # If hour > 12 and no AM/PM specified, assume 24-hour format
        if hour > 12 and not ampm:
            pass  # Keep as-is for 24-hour format
        elif hour <= 12 and not ampm:
            # Guess AM/PM based on current time and hour
            if hour < 8:  # Before 8, assume PM
                hour += 12
            # 8-12 assume as-is (AM for 8-11, PM for 12)
        
        # Validate hour and minute ranges
        if hour < 0 or hour > 23:
            raise ValueError(f"Invalid hour: {hour}. Must be between 0-23.")
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}. Must be between 0-59.")
        
        # Create the result datetime
        try:
            result_datetime = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError as ve:
            raise ValueError(f"Invalid time values: hour={hour}, minute={minute}. {str(ve)}")
    else:
        # Try to parse the entire string with dateutil as fallback
        try:
            # Remove any remaining relative words that might confuse dateutil
            clean_when = re.sub(r'\b(at|on|the|in)\b', '', when_str).strip()
            if clean_when and clean_when not in ['', 'am', 'pm']:
                # Try to parse with dateutil, using base_date as default
                parsed = parser.parse(clean_when, default=base_date.replace(tzinfo=None))
                result_datetime = local_tz.localize(parsed.replace(tzinfo=None))
            else:
                # No specific time found, use base_date
                result_datetime = base_date
        except Exception as parse_error:
            raise ValueError(f"Could not parse '{when_str}'. Error: {str(parse_error)}. Try formats like 'tomorrow 7pm', 'Friday 3:30pm', 'in 2 days 8pm', or 'Dec 25 14:00'")
    
    # Convert to UTC and validate
    try:
        utc_result = result_datetime.astimezone(pytz.utc)
        
        # Validate that the result is not too far in the past (allow 1 hour buffer for timezone issues)
        if utc_result < datetime.now(pytz.utc) - timedelta(hours=1):
            raise ValueError(f"Parsed time '{utc_result}' appears to be in the past. Please specify a future time.")
        
        return utc_result
    except Exception as tz_error:
        raise ValueError(f"Timezone conversion error: {str(tz_error)}")
    
def parse_flexible_datetime_allow_past(when_str, timezone_str="EST"):
    """
    Same as parse_flexible_datetime but allows past dates (for finding old games to reschedule)
    """
    import re
    from dateutil import parser
    from dateutil.relativedelta import relativedelta
    
    # Clean up input
    when_str = when_str.strip().lower()
    
    # Timezone mapping
    timezone_map = {
        'est': 'US/Eastern', 'edt': 'US/Eastern', 'eastern': 'US/Eastern',
        'cst': 'US/Central', 'cdt': 'US/Central', 'central': 'US/Central',
        'mst': 'US/Mountain', 'mdt': 'US/Mountain', 'mountain': 'US/Mountain',
        'pst': 'US/Pacific', 'pdt': 'US/Pacific', 'pacific': 'US/Pacific',
        'utc': 'UTC', 'gmt': 'UTC'
    }
    
    tz_name = timezone_map.get(timezone_str.lower(), 'US/Eastern')
    try:
        local_tz = pytz.timezone(tz_name)
    except:
        local_tz = pytz.timezone('US/Eastern')
        
    now = datetime.now(local_tz)
    
    # Handle "X days/hours ago" format for past dates
    relative_ago_match = re.search(r'(\d+)\s+(day|days|hour|hours|week|weeks)\s+ago', when_str)
    if relative_ago_match:
        amount = int(relative_ago_match.group(1))
        unit = relative_ago_match.group(2)
        
        if unit in ['day', 'days']:
            base_date = now - timedelta(days=amount)
        elif unit in ['hour', 'hours']:
            base_date = now - timedelta(hours=amount)
        elif unit in ['week', 'weeks']:
            base_date = now - timedelta(weeks=amount)
        
        # Remove the "ago" part from the string for further time parsing
        when_str = re.sub(r'\d+\s+(day|days|hour|hours|week|weeks)\s+ago', '', when_str).strip()
    else:
        base_date = now
    
    # Handle "in X days/hours" format (future)
    relative_in_match = re.search(r'in\s+(\d+)\s+(day|days|hour|hours)\s*(.*)', when_str)
    if relative_in_match:
        amount = int(relative_in_match.group(1))
        unit = relative_in_match.group(2)
        rest_of_string = relative_in_match.group(3).strip()
        
        if unit in ['day', 'days']:
            base_date = now + timedelta(days=amount)
        else:  # hours
            base_date = now + timedelta(hours=amount)
            
        if rest_of_string:
            when_str = rest_of_string
        else:
            return base_date.astimezone(pytz.utc)

    # Handle relative dates (including past ones)
    relative_patterns = {
        r'\byesterday\b': now - timedelta(days=1),
        r'\blast week\b': now - timedelta(weeks=1),
        r'\blast month\b': now - relativedelta(months=1),
        r'\btoday\b': now,
        r'\btomorrow\b': now + timedelta(days=1),
        r'\bnext week\b': now + timedelta(weeks=1),
        r'\bnext month\b': now + relativedelta(months=1),
    }
    
    # Handle "last [day]" pattern
    last_day_match = re.search(r'\blast\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', when_str)
    if last_day_match:
        target_day_name = last_day_match.group(1)
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        target_day_num = day_names.index(target_day_name)
        
        # Calculate days back to last occurrence of this day
        days_back = (now.weekday() - target_day_num) % 7
        if days_back == 0:
            days_back = 7  # If today is the target day, go back a week
        
        base_date = now - timedelta(days=days_back)
        when_str = re.sub(r'\blast\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', '', when_str).strip()
    
    # Check for other relative dates
    for pattern, relative_date in relative_patterns.items():
        if re.search(pattern, when_str):
            base_date = relative_date
            when_str = re.sub(pattern, '', when_str).strip()
            break
    
    # Handle regular day names
    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for i, day in enumerate(day_names):
        if day in when_str and 'last' not in when_str:  # Skip if already handled by "last [day]"
            days_ahead = (i - now.weekday()) % 7
            if days_ahead == 0:
                if 'today' not in when_str.lower():
                    days_ahead = 7
            base_date = now + timedelta(days=days_ahead)
            when_str = when_str.replace(day, '').strip()
            break
    
    # Time parsing (same as original)
    time_patterns = [
        (r'(\d{1,2}):(\d{2})\s*(am|pm|a\.?m\.?|p\.?m\.?)?', 'time_with_minutes'),
        (r'(\d{1,2})\s*(am|pm|a\.?m\.?|p\.?m\.?)', 'time_with_ampm'),
        (r'(\d{1,2})\.(\d{2})', 'time_decimal'),
    ]
    
    time_match = None
    match_type = None
    for pattern, pattern_type in time_patterns:
        time_match = re.search(pattern, when_str.lower())
        if time_match:
            match_type = pattern_type
            break
    
    if time_match:
        if match_type == 'time_with_minutes':
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            ampm = time_match.group(3) if time_match.group(3) else None
        elif match_type == 'time_with_ampm':
            hour = int(time_match.group(1))
            minute = 0
            ampm = time_match.group(2) if time_match.group(2) else None
        elif match_type == 'time_decimal':
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            ampm = None
        
        if ampm:
            ampm_clean = ampm.replace('.', '').lower()
            if ampm_clean.startswith('p') and hour != 12:
                hour += 12
            elif ampm_clean.startswith('a') and hour == 12:
                hour = 0
        
        if hour > 12 and not ampm:
            pass
        elif hour <= 12 and not ampm:
            if hour < 8:
                hour += 12
        
        if hour < 0 or hour > 23:
            raise ValueError(f"Invalid hour: {hour}. Must be between 0-23.")
        if minute < 0 or minute > 59:
            raise ValueError(f"Invalid minute: {minute}. Must be between 0-59.")
        
        try:
            result_datetime = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError as ve:
            raise ValueError(f"Invalid time values: hour={hour}, minute={minute}. {str(ve)}")
    else:
        try:
            clean_when = re.sub(r'\b(at|on|the|in)\b', '', when_str).strip()
            if clean_when and clean_when not in ['', 'am', 'pm']:
                parsed = parser.parse(clean_when, default=base_date.replace(tzinfo=None))
                result_datetime = local_tz.localize(parsed.replace(tzinfo=None))
            else:
                result_datetime = base_date
        except Exception as parse_error:
            raise ValueError(f"Could not parse '{when_str}'. Error: {str(parse_error)}. Try formats like 'yesterday 7pm', 'last Friday 3:30pm', '2 days ago 8pm', or 'Dec 25 14:00'")
    
    # Convert to UTC WITHOUT past validation
    try:
        utc_result = result_datetime.astimezone(pytz.utc)
        return utc_result
    except Exception as tz_error:
        raise ValueError(f"Timezone conversion error: {str(tz_error)}")