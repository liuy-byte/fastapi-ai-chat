from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有配置从环境变量或 .env 读取，代码里不写任何密钥。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+aiomysql://chat:chat@127.0.0.1:3306/ai_chat?charset=utf8mb4"

    # JWT：密钥必须从环境变量来，没配或太短直接起不来，免得带着弱密钥上线
    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = 60 * 24

    # 模型：任何 OpenAI 兼容接口都行，默认 MiniMax 国内站
    llm_base_url: str = "https://api.minimaxi.com/v1"
    llm_api_key: str = ""
    llm_model: str = "MiniMax-M3"
    # 设成 true 时用脚本化的假模型，不联网，本地调试和演示断线用
    llm_fake: bool = False


settings = Settings()
