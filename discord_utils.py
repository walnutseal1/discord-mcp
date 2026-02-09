"""
Discord Utilities
Handles standardization and resolution of Discord objects (servers, channels, users).
"""

from typing import Optional, Union
import discord
import re


class DiscordResolver:
    """Handles resolution of Discord names/IDs to objects."""
    
    def __init__(self, bot):
        self.bot = bot
        self._cache = {
            "servers": {},  # name -> id
            "channels": {},  # name -> id
            "users": {}  # username -> id
        }
    
    @staticmethod
    def is_snowflake(s: str) -> bool:
        """Check if a string looks like a Discord snowflake ID."""
        return s.isdigit() and 17 <= len(s) <= 20
    
    @staticmethod
    def parse_target(target: str) -> tuple[Optional[str], str]:
        """
        Parse target string to extract server and channel/user.
        Formats supported:
        - "channel" -> (None, "channel")
        - "ServerName/channel" -> ("ServerName", "channel")
        - "123456789" -> (None, "123456789") [ID]
        
        Returns (server_part, target_part)
        """
        if "/" in target and not DiscordResolver.is_snowflake(target):
            parts = target.split("/", 1)
            return (parts[0].strip(), parts[1].strip())
        return (None, target.strip())
    
    async def resolve_server(self, server_input: str) -> tuple[Optional[discord.Guild], Optional[str]]:
        """
        Convert server name or ID to Guild object.
        Returns (guild, error_message) tuple.
        """
        if self.is_snowflake(server_input):
            guild = self.bot.get_guild(int(server_input))
            if guild:
                return (guild, None)
            return (None, f"ERROR: '{server_input}' is not a valid server ID. No server with this ID exists.")
        
        # Check cache
        if server_input.lower() in self._cache["servers"]:
            guild = self.bot.get_guild(self._cache["servers"][server_input.lower()])
            if guild:
                return (guild, None)
        
        # Search by name
        for guild in self.bot.guilds:
            if guild.name.lower() == server_input.lower():
                self._cache["servers"][server_input.lower()] = guild.id
                return (guild, None)
        
        # Provide helpful error with available servers
        available_servers = [g.name for g in self.bot.guilds]
        server_list = "\n".join([f"  • {name}" for name in available_servers])
        return (None, f"ERROR: '{server_input}' is not a valid server name. Available servers:\n{server_list}\n\nUse the exact server name or use list_servers tool to see all servers with IDs.")
    
    async def resolve_channel(
        self, 
        channel_input: str, 
        guild: Optional[discord.Guild] = None
    ) -> tuple[Optional[discord.TextChannel], Optional[str]]:
        """
        Convert channel name or ID to TextChannel object.
        If guild is provided, searches within that guild only.
        Returns (channel, error_message). Error message explains ambiguity if needed.
        """
        if self.is_snowflake(channel_input):
            channel = self.bot.get_channel(int(channel_input))
            if isinstance(channel, discord.TextChannel):
                return (channel, None)
            if channel is None:
                return (None, f"ERROR: '{channel_input}' is not a valid channel ID. No channel with this ID exists.")
            else:
                return (None, f"ERROR: '{channel_input}' is a valid ID but it's not a text channel (it's a {type(channel).__name__}).")
        
        # Check cache
        cache_key = f"{guild.id if guild else 'global'}:{channel_input.lower()}"
        if cache_key in self._cache["channels"]:
            channel = self.bot.get_channel(self._cache["channels"][cache_key])
            if channel:
                return (channel, None)
        
        # Search by name
        channels = list(guild.channels) if guild else list(self.bot.get_all_channels())
        matches = [ch for ch in channels if isinstance(ch, discord.TextChannel) and ch.name.lower() == channel_input.lower()]
        
        if len(matches) == 0:
            if guild:
                return (None, f"ERROR: There is no channel called '{channel_input}' in server '{guild.name}'. Use the list_channels tool to see available channels.")
            else:
                return (None, f"ERROR: There is no channel called '{channel_input}' in any server. Try specifying the server like 'ServerName/{channel_input}' or use the list_channels tool.")
        
        if len(matches) == 1:
            self._cache["channels"][cache_key] = matches[0].id
            return (matches[0], None)
        
        # Multiple matches - need server context
        if not guild:
            server_list = "\n".join([f"  • {ch.guild.name} → #{ch.name}" for ch in matches])
            return (None, f"ERROR: Multiple channels named '{channel_input}' found in different servers:\n{server_list}\n\nYou MUST specify which server using format 'ServerName/{channel_input}' or use the channel ID.")
        
        return (None, f"ERROR: Unexpected situation - multiple channels with same name in one server")
    
    async def resolve_user(self, user_input: str) -> tuple[Optional[discord.User], Optional[str]]:
        """
        Convert username or ID to User object.
        Supports @username format.
        Returns (user, error_message) tuple.
        """
        # Remove @ if present
        original_input = user_input
        user_input = user_input.lstrip('@')
        
        if self.is_snowflake(user_input):
            try:
                user = await self.bot.fetch_user(int(user_input))
                return (user, None)
            except discord.NotFound:
                return (None, f"ERROR: '{user_input}' is not a valid user ID. No user with this ID exists.")
            except Exception as e:
                return (None, f"ERROR: Could not fetch user with ID '{user_input}': {str(e)}")
        
        # Check cache
        if user_input.lower() in self._cache["users"]:
            try:
                user = await self.bot.fetch_user(self._cache["users"][user_input.lower()])
                return (user, None)
            except:
                # Cache was stale, remove it
                del self._cache["users"][user_input.lower()]
        
        # Search by username in all mutual guilds
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.name.lower() == user_input.lower() or \
                   (member.global_name and member.global_name.lower() == user_input.lower()):
                    self._cache["users"][user_input.lower()] = member.id
                    return (member, None)
        
        return (None, f"ERROR: No user found with username '{original_input}'. Make sure the username is spelled correctly or use the user's ID instead.")


class MentionProcessor:
    """Handles conversion of mentions between Discord format and human-readable format."""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def humanize_mentions(self, message: str) -> str:
        """
        Convert Discord mention format <@id> back to readable @username.
        This makes message history understandable for LLMs.
        
        Handles:
        - <@123456789> -> @username
        - <@!123456789> -> @username (nickname format)
        
        Returns the message with human-readable mentions.
        """
        # Pattern for Discord mentions: <@id> or <@!id>
        pattern = r'<@!?(\d+)>'
        
        async def replace_mention(match):
            user_id = match.group(1)
            
            # Try to fetch the user
            try:
                user = await self.bot.fetch_user(int(user_id))
                if user:
                    return f"@{user.name}"
            except:
                pass
            
            # If can't fetch, leave the ID but make it readable
            return f"@[{user_id}]"
        
        # Replace all mentions
        parts = []
        last_end = 0
        for match in re.finditer(pattern, message):
            parts.append(message[last_end:match.start()])
            replacement = await replace_mention(match)
            parts.append(replacement)
            last_end = match.end()
        parts.append(message[last_end:])
        
        return ''.join(parts)
    
    async def process_mentions(
        self, 
        message: str, 
        guild: Optional[discord.Guild] = None
    ) -> str:
        """
        Convert @username and raw IDs to proper Discord mention format <@id>.
        Discord bots need to use <@id> format to mention users.
        
        Handles:
        - @username -> <@id>
        - @123456789 -> <@123456789>
        - 123456789 (if looks like user ID in context) -> <@123456789>
        
        Returns the message with properly formatted mentions.
        """
        # Pattern 1: @username or @id
        pattern_at = r'@([a-zA-Z0-9_\.]+)'
        
        async def replace_at_mention(match):
            username = match.group(1)
            
            # If it's already a snowflake ID, just format it
            if DiscordResolver.is_snowflake(username):
                return f"<@{username}>"
            
            # Otherwise, look up the user
            resolver = DiscordResolver(self.bot)
            user = await resolver.resolve_user(username)
            if user:
                return f"<@{user.id}>"
            
            # If not found, leave as-is (will be plain text)
            return match.group(0)
        
        # Replace all @mentions
        parts = []
        last_end = 0
        for match in re.finditer(pattern_at, message):
            parts.append(message[last_end:match.start()])
            replacement = await replace_at_mention(match)
            parts.append(replacement)
            last_end = match.end()
        parts.append(message[last_end:])
        message = ''.join(parts)
        
        # Pattern 2: Raw snowflake IDs that aren't already in <@id> format
        # Look for standalone numbers that are 17-20 digits and might be user IDs
        # Only convert if they're isolated (surrounded by spaces or at start/end)
        pattern_raw = r'(?<![<@\w])(\d{17,20})(?![>\w])'
        
        async def replace_raw_id(match):
            user_id = match.group(1)
            
            # Check if this is actually a user ID by trying to fetch
            try:
                user = await self.bot.fetch_user(int(user_id))
                if user:
                    return f"<@{user_id}>"
            except:
                pass
            
            # If not a valid user, leave as-is
            return match.group(0)
        
        # Only process raw IDs if there are isolated numbers that look like IDs
        if re.search(pattern_raw, message):
            parts = []
            last_end = 0
            for match in re.finditer(pattern_raw, message):
                parts.append(message[last_end:match.start()])
                replacement = await replace_raw_id(match)
                parts.append(replacement)
                last_end = match.end()
            parts.append(message[last_end:])
            message = ''.join(parts)
        
        return message