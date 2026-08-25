from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    # 可选模型：deepseek-chat、deepseek-reasoner
    deepseek_model: str = "deepseek-chat"
    # Semantic Scholar（可选；不填也能用，但容易触发限流）
    semantic_scholar_api_key: str = ""
    # 可选：用外部 stdio MCP Server，例如 "python -m app.mcp_server"
    # 留空则使用内存传输连接本项目 FastMCP Server
    mcp_scholar_command: str = ""
    # Railway 注入 PORT；本地默认 8001
    port: int = 8001
    # RAG 分块与检索
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_top_k: int = 6
    # Agentic RAG：最大补充检索轮次、规划子查询数
    rag_agent_max_iterations: int = 2
    rag_agent_max_sub_queries: int = 3


settings = Settings()
