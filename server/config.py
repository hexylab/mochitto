from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # SwitchBot
    switchbot_token: str
    switchbot_secret: str

    # VoiceVox
    voicevox_url: str = "http://voicevox:50021"

    # Whisper
    whisper_model: str = "large-v3"
