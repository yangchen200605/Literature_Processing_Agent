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
    # Railway 注入 PORT；本地默认 8001
    port: int = 8001


settings = Settings()