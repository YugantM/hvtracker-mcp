FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/YugantM/hvtracker-mcp"
LABEL org.opencontainers.image.description="HVTracker MCP server"
LABEL org.opencontainers.image.licenses="MIT"
LABEL io.modelcontextprotocol.server.name="io.github.YugantM/hvtracker-mcp"

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir .

ENTRYPOINT ["hvtracker-mcp"]
