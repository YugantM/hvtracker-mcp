# Installing HVTracker MCP (for AI agents such as Cline)

HVTracker MCP needs no API key, account or environment variables. Use option 1
unless the user asks for a local install.

## Option 1: hosted server (recommended, nothing to install)

Add this to the MCP settings (`cline_mcp_settings.json` in Cline):

```json
{
  "mcpServers": {
    "hvtracker": {
      "type": "streamableHttp",
      "url": "https://hvtracker.net/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Keep `"type": "streamableHttp"`. The endpoint speaks Streamable HTTP only; a
config with just `"url"` makes Cline fall back to legacy SSE, which fails.

## Option 2: local stdio server (Node.js 20+)

```json
{
  "mcpServers": {
    "hvtracker": {
      "command": "npx",
      "args": ["-y", "hvtracker-mcp"],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Python alternative: `python3 -m pip install hvtracker-mcp`, then use
`"command": "hvtracker-mcp"` with no `args`.

## Verify

The server should connect with 8 tools: `verify_mcp_server`,
`check_agent_trust`, `compare_agents`, `search_agents`, `scan_stack`,
`list_categories`, `get_leaderboard`, `get_agent_history`.

Test call: `check_agent_trust` with `{"name_or_repo": "langgraph"}` returns
LangGraph's HVTrust score, grade and signals.
