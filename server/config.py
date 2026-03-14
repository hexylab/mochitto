from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # SwitchBot
    switchbot_token: str
    switchbot_secret: str

    # VoiceVox
    voicevox_url: str = "http://localhost:50021"

    # Whisper
    whisper_model: str = "large-v3"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
