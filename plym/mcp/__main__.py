from plym.mcp.server import mcp
from plym.mcp.settings import mcp_settings

if __name__ == "__main__":
    if mcp_settings.transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport="http",
            host=mcp_settings.host,
            port=mcp_settings.port,
            path=mcp_settings.path,
        )
