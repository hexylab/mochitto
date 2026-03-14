from unittest.mock import MagicMock, patch

from client.music_player import MusicPlayer


def test_build_youtube_url():
    player = MusicPlayer()
    url = player._build_url("abc123")
    assert url == "https://www.youtube.com/watch?v=abc123"


@patch("ytmusicapi.YTMusic")
def test_search_returns_video_id(mock_ytmusic_cls):
    mock_yt = MagicMock()
    mock_yt.search.return_value = [
        {"videoId": "xyz789", "title": "Test Song", "artists": [{"name": "Artist"}]}
    ]
    mock_ytmusic_cls.return_value = mock_yt

    player = MusicPlayer()
    result = player.search("test query")
    assert result["videoId"] == "xyz789"


def test_handle_music_action_stop():
    player = MusicPlayer()
    player._player = MagicMock()
    player._is_playing = True
    player.handle_action("stop")
    player._player.stop.assert_called_once()
    assert not player._is_playing
