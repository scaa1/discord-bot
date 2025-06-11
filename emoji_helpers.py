import re

def get_emoji_thumbnail_url(emoji_str: str) -> str:
    """
    Convert team emoji to a thumbnail URL for Discord embeds.
    Handles both Unicode emojis and custom Discord emojis.
    
    Args:
        emoji_str: The emoji string (Unicode or Discord custom emoji format)
        
    Returns:
        URL string for the emoji image, or None if conversion fails
    """
    if not emoji_str:
        return None
    
    # Check if it's a custom Discord emoji (format: <:name:id> or <a:name:id>)
    custom_emoji_match = re.match(r'<a?:(\w+):(\d+)>', emoji_str)
    if custom_emoji_match:
        emoji_id = custom_emoji_match.group(2)
        # For custom emojis, we can get the direct URL
        return f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
    
    # For Unicode emojis, convert to Twemoji URL
    try:
        # Convert emoji to Unicode codepoints
        codepoints = []
        for char in emoji_str:
            if ord(char) > 127:  # Non-ASCII character
                codepoints.append(f"{ord(char):x}")
        
        if codepoints:
            # Join multiple codepoints with hyphens for compound emojis
            unicode_str = "-".join(codepoints)
            return f"https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/{unicode_str}.png"
    except Exception:
        pass
    
    return None

def add_team_emoji_thumbnail(embed, team_emoji: str):
    """
    Add team emoji as thumbnail to an existing embed.
    
    Args:
        embed: Discord embed object
        team_emoji: The emoji string to use as thumbnail
        
    Returns:
        The modified embed object
    """
    thumbnail_url = get_emoji_thumbnail_url(team_emoji)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return embed