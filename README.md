# HVTracker MCP

MCP server for checking supply-chain trust before connecting to AI agents,
frameworks, or MCP servers.

The hosted remote server is:

```json
{
  "mcpServers": {
    "hvtracker": {
      "url": "https://hvtracker.net/mcp"
    }
  }
}
```

This repository also provides a local stdio package for clients that prefer
package-based installation.

<!-- mcp-name: io.github.YugantM/hvtracker-mcp -->

## Tools

- `verify_mcp_server`: pre-connect trust verdict for an MCP server, package, GitHub repo, or agent name.
- `check_agent_trust`: compact trust profile for a tracked AI agent or framework.
- `search_agents`: search the HVTracker registry by name, repo, description, or category.

## Local Install

With npm:

```bash
npm install -g hvtracker-mcp
```

With PyPI:

```bash
python3 -m pip install hvtracker-mcp
```

Example MCP client config:

```json
{
  "mcpServers": {
    "hvtracker": {
      "command": "hvtracker-mcp"
    }
  }
}
```

## Development

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
hvtracker-mcp
```

Use a different HVTracker base URL while testing:

```bash
HVTRACKER_BASE_URL=http://localhost:8080 hvtracker-mcp
```

## Registry Publishing

The official MCP Registry manifest is `server.json`.

```bash
mcp-publisher login github
mcp-publisher publish
```

In GitHub Actions, run the "Publish MCP Registry" workflow after the npm,
PyPI, and GHCR packages for the same version are live.

The server name is:

```text
io.github.YugantM/hvtracker-mcp
```

## Claude Desktop Extension

Tagged releases build an `.mcpb` bundle for Claude Desktop from `manifest.json`.
To build it locally:

```bash
npm ci --omit=dev
npx @anthropic-ai/mcpb@2.1.2 pack
```

## Privacy

HVTracker MCP sends the user-supplied search string or server identifier to
`https://hvtracker.net` to fetch public trust data. It does not require an API
key and does not write to user systems. See the HVTracker site for current data
and methodology, and see `PRIVACY.md` for the repository privacy note.
