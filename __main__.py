#!/usr/bin/env python3
"""
Discord MCP Server
A Model Context Protocol server for Discord with smart target resolution.
"""

import asyncio
import os
from typing import Any
import discord
from discord.ext import commands
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

from discord_utils import DiscordResolver, MentionProcessor

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
mcp_server = Server("discord-mcp")

# Initialize resolver and mention processor
resolver = DiscordResolver(bot)
mention_processor = MentionProcessor(bot)


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Discord tools."""
    return [
        Tool(
            name="send_message",
            description="Send a message to a Discord channel or user DM. Target can be a channel name, channel ID, username, or user ID. For ambiguous channel names (like 'general'), use 'ServerName/channel' format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message content to send"
                    },
                    "target": {
                        "type": "string",
                        "description": "Channel name/ID or username/ID. Examples: 'general', 'MyServer/general', '@username', or snowflake IDs. Use 'ServerName/channel' for ambiguous channels."
                    }
                },
                "required": ["message", "target"]
            }
        ),
        Tool(
            name="edit_message",
            description="Edit or delete a message. If message is empty/blank, the message will be deleted. Message ID must be exact.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the message to edit/delete"
                    },
                    "message": {
                        "type": "string",
                        "description": "New message content. Leave empty to delete the message."
                    }
                },
                "required": ["message_id"]
            }
        ),
        Tool(
            name="read_messages",
            description="Read recent messages from a channel. Returns channel info and message history. Channel can be name or ID. For ambiguous names, use 'ServerName/channel' format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID. Examples: 'general', 'MyServer/general', or snowflake ID. Use 'ServerName/channel' for ambiguous channels."
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of messages to retrieve (default: 50, max: 100)",
                        "default": 50
                    }
                },
                "required": ["channel"]
            }
        ),
        Tool(
            name="list_servers",
            description="List all Discord servers (guilds) the bot has access to.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="list_channels",
            description="List all channels in a specific server. Server can be name or ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server": {
                        "type": "string",
                        "description": "Server name or ID"
                    }
                },
                "required": ["server"]
            }
        ),
        Tool(
            name="search_messages",
            description="Search for messages containing specific text in a channel. Channel can be name or ID. For ambiguous names, use 'ServerName/channel' format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID. Examples: 'general', 'MyServer/general', or snowflake ID"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query text"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of messages to search through (default: 100)",
                        "default": 100
                    }
                },
                "required": ["channel", "query"]
            }
        ),
        Tool(
            name="add_reaction",
            description="Add a reaction emoji to a message. Message ID must be exact.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the message to react to"
                    },
                    "emoji": {
                        "type": "string",
                        "description": "Emoji to react with (Unicode emoji or custom emoji name)"
                    }
                },
                "required": ["message_id", "emoji"]
            }
        )
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    
    try:
        if name == "send_message":
            message_text = arguments["message"]
            target = arguments["target"]
            
            # Parse server/channel format
            server_part, target_part = resolver.parse_target(target)
            guild = None
            
            if server_part:
                guild, error = await resolver.resolve_server(server_part)
                if not guild:
                    return [TextContent(type="text", text=error)]
            
            # Try as channel first
            channel, error = await resolver.resolve_channel(target_part, guild)
            if channel:
                # Process mentions in the message
                processed_message = await mention_processor.process_mentions(message_text, channel.guild)
                sent_msg = await channel.send(processed_message)
                return [TextContent(
                    type="text",
                    text=f"Message sent to #{channel.name} in {channel.guild.name} (Message ID: {sent_msg.id})"
                )]
            
            # If channel lookup failed with ambiguity error, return it
            if error and "Multiple channels" in error:
                return [TextContent(type="text", text=error)]
            
            # Try as user DM
            user, user_error = await resolver.resolve_user(target_part)
            if user:
                # Process mentions in the message (though less common in DMs)
                processed_message = await mention_processor.process_mentions(message_text)
                sent_msg = await user.send(processed_message)
                return [TextContent(
                    type="text",
                    text=f"DM sent to {user.name} (Message ID: {sent_msg.id})"
                )]
            
            # Provide combined error message
            combined_error = f"ERROR: Could not find channel or user '{target}'.\n\n"
            if error:
                combined_error += f"Channel lookup failed: {error}\n\n"
            if user_error:
                combined_error += f"User lookup failed: {user_error}"
            
            return [TextContent(type="text", text=combined_error)]
        
        elif name == "edit_message":
            message_id_str = arguments["message_id"]
            new_content = arguments.get("message", "")
            
            # Validate message ID format
            if not resolver.is_snowflake(message_id_str):
                return [TextContent(
                    type="text",
                    text=f"ERROR: '{message_id_str}' is not a valid message ID. Message IDs must be 17-20 digit numbers."
                )]
            
            message_id = int(message_id_str)
            
            # Search for message in all accessible channels
            message_obj = None
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    try:
                        message_obj = await channel.fetch_message(message_id)
                        break
                    except:
                        continue
                if message_obj:
                    break
            
            if not message_obj:
                return [TextContent(
                    type="text",
                    text=f"ERROR: Could not find message with ID {message_id}. The message may have been deleted, or the bot doesn't have access to the channel containing this message."
                )]
            
            # Delete if empty, edit otherwise
            if not new_content or new_content.strip() == "":
                await message_obj.delete()
                return [TextContent(
                    type="text",
                    text=f"Message {message_id} deleted successfully from #{message_obj.channel.name}"
                )]
            else:
                # Process mentions in the new content
                processed_content = await mention_processor.process_mentions(new_content, message_obj.guild)
                await message_obj.edit(content=processed_content)
                return [TextContent(
                    type="text",
                    text=f"Message {message_id} edited successfully in #{message_obj.channel.name}"
                )]
        
        elif name == "read_messages":
            channel_input = arguments["channel"]
            limit = min(int(arguments.get("limit", 50)), 100)
            
            # Parse server/channel format
            server_part, target_part = resolver.parse_target(channel_input)
            guild = None
            
            if server_part:
                guild, error = await resolver.resolve_server(server_part)
                if not guild:
                    return [TextContent(type="text", text=error)]
            
            channel, error = await resolver.resolve_channel(target_part, guild)
            if not channel:
                return [TextContent(type="text", text=error)]
            
            # Get channel info
            info = f"Channel: #{channel.name} (ID: {channel.id})\n"
            info += f"Type: {channel.type}\n"
            if channel.topic:
                info += f"Topic: {channel.topic}\n"
            info += f"Server: {channel.guild.name}\n\n"
            info += "=" * 50 + "\n\n"
            
            # Get messages
            messages = []
            async for msg in channel.history(limit=limit):
                timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                # Convert Discord mentions to readable @username format
                content = await mention_processor.humanize_mentions(msg.content)
                messages.append(
                    f"[{timestamp}] {msg.author.name}: {content}\n"
                    f"  (ID: {msg.id})\n"
                )
            
            messages.reverse()  # Show oldest first
            info += "\n".join(messages)
            
            return [TextContent(type="text", text=info)]
        
        elif name == "list_servers":
            servers = []
            for guild in bot.guilds:
                servers.append(
                    f"• {guild.name}\n"
                    f"  ID: {guild.id}\n"
                    f"  Members: {guild.member_count}\n"
                )
            
            result = f"Connected to {len(bot.guilds)} servers:\n\n" + "\n".join(servers)
            return [TextContent(type="text", text=result)]
        
        elif name == "list_channels":
            server_input = arguments["server"]
            guild, error = await resolver.resolve_server(server_input)
            
            if not guild:
                return [TextContent(type="text", text=error)]
            
            channels = []
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    channels.append(f"  • #{channel.name} (text) - ID: {channel.id}")
                elif isinstance(channel, discord.VoiceChannel):
                    channels.append(f"  • 🔊 {channel.name} (voice) - ID: {channel.id}")
                elif isinstance(channel, discord.ForumChannel):
                    channels.append(f"  • 💬 {channel.name} (forum) - ID: {channel.id}")
            
            result = f"Channels in {guild.name}:\n\n" + "\n".join(channels)
            return [TextContent(type="text", text=result)]
        
        elif name == "search_messages":
            channel_input = arguments["channel"]
            query = arguments["query"].lower()
            limit = min(int(arguments.get("limit", 100)), 500)
            
            # Parse server/channel format
            server_part, target_part = resolver.parse_target(channel_input)
            guild = None
            
            if server_part:
                guild, error = await resolver.resolve_server(server_part)
                if not guild:
                    return [TextContent(type="text", text=error)]
            
            channel, error = await resolver.resolve_channel(target_part, guild)
            if not channel:
                return [TextContent(type="text", text=error)]
            
            results = []
            async for msg in channel.history(limit=limit):
                if query in msg.content.lower():
                    timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    # Convert Discord mentions to readable @username format
                    content = await mention_processor.humanize_mentions(msg.content)
                    results.append(
                        f"[{timestamp}] {msg.author.name}: {content}\n"
                        f"  (ID: {msg.id})\n"
                    )
            
            if not results:
                return [TextContent(
                    type="text",
                    text=f"No messages found containing '{query}' in #{channel.name}"
                )]
            
            results.reverse()
            result = f"Found {len(results)} messages containing '{query}' in #{channel.name}:\n\n"
            result += "\n".join(results)
            
            return [TextContent(type="text", text=result)]
        
        elif name == "add_reaction":
            message_id_str = arguments["message_id"]
            emoji = arguments["emoji"]
            
            # Validate message ID format
            if not resolver.is_snowflake(message_id_str):
                return [TextContent(
                    type="text",
                    text=f"ERROR: '{message_id_str}' is not a valid message ID. Message IDs must be 17-20 digit numbers."
                )]
            
            message_id = int(message_id_str)
            
            # Search for message
            message_obj = None
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    try:
                        message_obj = await channel.fetch_message(message_id)
                        break
                    except:
                        continue
                if message_obj:
                    break
            
            if not message_obj:
                return [TextContent(
                    type="text",
                    text=f"ERROR: Could not find message with ID {message_id}. The message may have been deleted, or the bot doesn't have access to the channel containing this message."
                )]
            
            try:
                await message_obj.add_reaction(emoji)
                return [TextContent(
                    type="text",
                    text=f"Added reaction {emoji} to message {message_id} in #{message_obj.channel.name}"
                )]
            except discord.HTTPException as e:
                return [TextContent(
                    type="text",
                    text=f"ERROR: Could not add reaction '{emoji}'. The emoji may be invalid or the bot may not have permission to react. Discord error: {str(e)}"
                )]
        
        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


@bot.event
async def on_ready():
    """Called when the bot is ready."""
    print(f"Discord bot logged in as {bot.user}")
    print(f"Connected to {len(bot.guilds)} servers")


async def main():
    """Main entry point."""
    # Get Discord token from environment
    token = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_BOT_TOKEN or DISCORD_TOKEN environment variable not set")
    
    async def start_bot():
        """Start the Discord bot."""
        try:
            await bot.start(token)
        except Exception as e:
            print(f"Bot error: {e}")
            raise
    
    async def run_mcp():
        """Run the MCP server after bot is ready."""
        # Wait for bot to be ready
        await bot.wait_until_ready()
        print(f"Bot ready - starting MCP server...")
        
        # Run MCP server
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options()
            )
    
    # Run both tasks concurrently
    try:
        await asyncio.gather(
            start_bot(),
            run_mcp()
        )
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())