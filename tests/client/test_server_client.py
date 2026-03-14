import json
from client.server_client import parse_multipart_response


def test_parse_multipart_response():
    boundary = "test_boundary"
    json_data = {"intent": "chat", "response_text": "テスト"}
    audio_data = b"FAKE_WAV"

    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json\r\n\r\n"
        f"{json.dumps(json_data)}"
        f"\r\n--{boundary}\r\n"
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()

    parsed_json, parsed_audio = parse_multipart_response(body, boundary)
    assert parsed_json["intent"] == "chat"
    assert parsed_audio == audio_data
