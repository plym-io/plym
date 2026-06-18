from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLYM_MCP_", env_file=".env", extra="ignore")

    base_url: str = "http://localhost:9173"
    request_timeout: float = 30.0

    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"


mcp_settings = McpSettings()
