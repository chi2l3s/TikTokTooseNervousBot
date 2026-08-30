from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
    WHISPER_MODEL: str = "large-v3-turbo"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    HTTP_PROXY: str | None = None
    MUSIC_DIR: Path = Path("./music")
    TEMP_DIR: Path = Path("./temp")
    FONTS_DIR: Path = Path("./fonts")
    MAX_CLIPS: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

config = Settings()
config.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
config.FONTS_DIR.mkdir(parents=True, exist_ok=True)