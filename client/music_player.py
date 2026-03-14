import logging
from typing import Any

logger = logging.getLogger(__name__)


class MusicPlayer:
    def __init__(self):
        self._player = None
        self._is_playing = False
        self._original_volume: int = 100

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def _ensure_player(self):
        if self._player is None:
            import mpv
            self._player = mpv.MPV(ytdl=True, video=False)

    def _build_url(self, video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"

    def search(self, query: str) -> dict[str, Any] | None:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        results = yt.search(query, filter="songs")
        if results:
            return results[0]
        return None

    def play(self, query: str) -> str | None:
        result = self.search(query)
        if not result:
            return None

        video_id = result.get("videoId")
        if not video_id:
            return None

        title = result.get("title", "不明")
        url = self._build_url(video_id)

        self._ensure_player()
        self._player.play(url)
        self._is_playing = True
        logger.info("再生開始: %s (%s)", title, url)
        return title

    def handle_action(self, action: str) -> None:
        if not self._player:
            return

        if action == "stop":
            self._player.stop()
            self._is_playing = False
        elif action == "pause":
            self._player.pause = True
        elif action == "resume":
            self._player.pause = False
        elif action == "volume_up":
            self._player.volume = min(150, (self._player.volume or 100) + 10)
        elif action == "volume_down":
            self._player.volume = max(0, (self._player.volume or 100) - 10)

    def duck(self) -> None:
        if self._player and self._is_playing:
            self._original_volume = self._player.volume or 100
            self._player.volume = max(0, int(self._original_volume * 0.2))

    def unduck(self) -> None:
        if self._player and self._is_playing:
            self._player.volume = self._original_volume
