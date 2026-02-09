# Discord MCP Server

A streamlined Model Context Protocol server for Discord with smart target resolution. No more hallucinated IDs!

## Features

- 🎯 **Smart Target Resolution**: Use channel names, usernames, or IDs - no need to memorize snowflakes
- 🧠 **LLM-Friendly**: Reduces hallucination by accepting human-readable names
- 💬 **Automatic Mention Processing**: Converts @username to proper Discord `<@id>` format automatically
- 📦 **Streamlined API**: Only 7 essential tools, no redundancy
- 💾 **Smart Caching**: Automatically caches name→ID mappings
- 🔀 **Ambiguity Handling**: Detects when channel names collide and guides to use `ServerName/channel` format

## Tools

1. **send_message** - Send to channels or DMs (accepts names or IDs)
2. **edit_message** - Edit or delete messages (empty content = delete)
3. **read_messages** - Read channel history + channel info
4. **list_servers** - List all accessible servers
5. **list_channels** - List channels in a server
6. **search_messages** - Search for messages in a channel
7. **add_reaction** - React to messages with emoji

## Setup

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to "Bot" section and click "Add Bot"
4. Enable these Privileged Gateway Intents:
   - Message Content Intent
   - Server Members Intent
   - Presence Intent (optional)
5. Click "Reset Token" and copy your bot token
6. Go to "OAuth2" → "URL Generator"
   - Select scopes: `bot`
   - Select permissions: `Send Messages`, `Read Message History`, `Add Reactions`, `Manage Messages`
7. Use the generated URL to invite the bot to your server

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Environment Variable

```bash
export DISCORD_TOKEN="your_bot_token_here"
```

Or on Windows:
```cmd
set DISCORD_TOKEN=your_bot_token_here
```

### 4. Run the Server

```bash
python discord_mcp_server.py
```

## Usage Examples

### With Claude Desktop (config)

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "discord": {
      "command": "python",
      "args": ["/path/to/discord-mcp/main.py"],
      "env": {
        "DISCORD_TOKEN": "your_bot_token_here"
      }
    }
  }
}
```

### Example Prompts for Claude

**Send a message:**
```
Send "Hello everyone!" to the general channel
Send "Meeting in 5 mins" to Work Server/announcements
```

**Read messages:**
```
Read the last 20 messages from announcements
Read messages from Gaming Server/general
```

**Search:**
```
Search for messages containing "meeting" in the team-chat channel
Search for "bug report" in Dev Team/bugs
```

**Edit/Delete:**
```
Edit message 123456789 to say "Updated: Meeting at 3pm"
Delete message 987654321
```

## Smart Target Resolution

The server automatically handles both names and IDs:

| Input Type | Example | How It Works |
|------------|---------|--------------|
| Channel name | `"general"` | Searches for channel by name |
| Server/Channel | `"MyServer/general"` | **Searches in specific server (solves ambiguity)** |
| Channel with # | `"#announcements"` | Strips # and searches by name |
| Username | `"john"` | Searches for user by username |
| Username with @ | `"@alice"` | Strips @ and searches by username |
| Snowflake ID | `"123456789012345678"` | Uses ID directly (17-20 digits) |

### Handling Ambiguous Channel Names

Since most Discord servers have channels with common names like "general" or "announcements", the server handles ambiguity intelligently:

**If a channel name is unique:** Just use the name
```
Send "Hello!" to announcements
```

**If a channel name appears in multiple servers:** The server will tell you which servers have that channel and ask you to specify:
```
Error: Multiple channels named 'general' found:
  • My Gaming Server → #general
  • Work Team → #general
  • Friend Group → #general

Please specify format: 'ServerName/channel' or use channel ID
```

**Use the ServerName/channel format:**
```
Send "Hello team!" to Work Team/general
Read the last 10 messages from My Gaming Server/general
```

This completely eliminates the need for the AI to remember or hallucinate long channel IDs!

### Automatic User Mention Processing

Discord bots can only mention users using the `<@user_id>` format, but LLMs naturally want to use `@username`. The server automatically handles **bidirectional conversion**:

**When SENDING messages (AI → Discord):**
```
AI writes: "Hey @john, can you check this?"
Discord receives: "Hey <@789012345678901234>, can you check this?"
```

**When READING messages (Discord → AI):**
```
Discord has: "Meeting with <@789012345678901234> at 3pm"
AI sees: "Meeting with @john at 3pm"
```

**Sending - Handles:**
- `@username` → Looks up user and converts to `<@id>`
- `@123456789` → Recognizes as ID and formats to `<@123456789>`
- `123456789` → Detects raw IDs and converts to `<@123456789>` if valid user
- Non-existent users → Left as plain text (won't create broken mentions)

**Reading - Handles:**
- `<@123456789>` → Fetches user and converts to `@username`
- `<@!123456789>` → Handles nickname format, converts to `@username`
- Unknown user IDs → Shows as `@[123456789]` (fallback format)

This bidirectional conversion means:
- ✅ The AI can write natural messages with @mentions
- ✅ The AI can read and understand who's being mentioned in chat history
- ✅ The AI can quote or reference previous mentions correctly
- ✅ No confusion with long user IDs

### Caching

The server caches name→ID mappings to improve performance and reduce API calls. Cache is maintained in memory during runtime.

## Architecture

```
discord_mcp_server.py
│
├─ parse_target()         - Parses "ServerName/channel" format
├─ process_mentions()     - Converts @username and raw IDs to <@id> format (AI → Discord)
├─ humanize_mentions()    - Converts <@id> back to @username format (Discord → AI)
├─ standardize_server()   - Resolves server names/IDs to Guild objects
├─ standardize_channel()  - Resolves channel names/IDs to Channel objects
│                           Returns (channel, error) for ambiguity handling
├─ standardize_user()     - Resolves usernames/IDs to User objects
│
└─ MCP Tools:
   ├─ send_message        - Uses parse_target(), process_mentions(), standardize functions
   ├─ edit_message        - Uses process_mentions() + direct message ID lookup
   ├─ read_messages       - Uses parse_target(), humanize_mentions(), standardize functions
   ├─ list_servers        - No resolution needed
   ├─ list_channels       - Uses standardize_server()
   ├─ search_messages     - Uses parse_target(), humanize_mentions(), standardize functions
   └─ add_reaction        - Direct message ID lookup
```

## Error Handling

The server provides clear error messages:
- "Could not find channel 'xyz'" - Channel name/ID not found
- "Could not find server 'xyz'" - Server name/ID not found
- "Could not find message with ID xyz" - Message doesn't exist or bot lacks access

## Permissions

Ensure your bot has these permissions:
- Read Messages/View Channels
- Send Messages
- Read Message History
- Add Reactions
- Manage Messages (for editing/deleting)

## Troubleshooting

**Bot not responding:**
- Check that `DISCORD_TOKEN` is set correctly
- Verify bot is invited to the server
- Ensure bot has necessary permissions

**"Could not find channel" errors:**
- Check channel name spelling
- Verify bot has access to the channel
- Try using the channel ID instead

**Message edit/delete fails:**
- Bot can only edit/delete its own messages
- Ensure the message ID is correct
- Check bot has "Manage Messages" permission

## License

MIT License - feel free to modify and use as needed!