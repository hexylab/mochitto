from pydantic_settings import BaseSettings


class ClientConfig(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    server_url: str = "http://192.168.1.100:8000"
    porcupine_access_key: str
    wake_word_path: str = "mochitto.ppn"
    porcupine_model_path: str | None = None

    # Recording params
    silence_threshold: int = 500
    silence_duration: float = 1.5
    max_record_seconds: float = 15.0
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
