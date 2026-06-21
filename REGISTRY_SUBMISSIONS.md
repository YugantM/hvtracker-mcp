# Registry Submission Notes

Use these fields when submitting HVTracker MCP to directories.

## Canonical

- Name: HVTracker MCP
- Registry name: `io.github.YugantM/hvtracker-mcp`
- Repo: `https://github.com/YugantM/hvtracker-mcp`
- Remote endpoint: `https://hvtracker.net/mcp`
- npm package: `hvtracker-mcp`
- PyPI package: `hvtracker-mcp`
- OCI image: `ghcr.io/yugantm/hvtracker-mcp:v0.1.1`
- Homepage: `https://hvtracker.net`
- License: MIT
- Category: Security, Developer Tools, AI Agents
- Short description: Pre-connect trust checks for AI agents and MCP servers.

## Longer Description

HVTracker MCP lets AI clients check independent trust signals before installing
or connecting to AI agents, frameworks, packages, and MCP servers. It exposes
tools for pre-connect MCP trust verdicts, compact agent trust profiles, and
searching the HVTracker registry.

## Directories

- Official MCP Registry: publish `server.json` with `mcp-publisher publish`.
- GitHub MCP Registry: publish to the official registry first, then request onboarding.
- Smithery: publish the URL `https://hvtracker.net/mcp` or upload a package.
- Glama: should index from official registry; claim/verify if needed.
- PulseMCP: submit the repo and remote endpoint.
- mcp.so: create a submission issue with the fields above.
- mcpservers.org: submit via the website form.
- awesome-mcp-servers: open a PR adding the repo to the relevant security/developer-tools section.
- Claude Desktop Extensions: attach the `.mcpb` bundle from the GitHub release and use `PRIVACY.md` as the privacy-policy URL.
