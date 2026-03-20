import asyncio
import json

import pytest

from config import ConfigLoader
from core.transcript_manager import TranscriptManager
from storage import FileManager


class _FakeDatabase:
    def __init__(self):
        self.rows = []

    async def upsert_transcript_job(self, payload):
        self.rows.append(payload)


def test_transcript_default_disabled():
    loader = ConfigLoader()
    transcript_cfg = loader.get("transcript", {})

    assert transcript_cfg.get("enabled") is False
    assert transcript_cfg.get("backend") == "openai_api"
    assert (
        transcript_cfg.get("api_url")
        == "https://api.openai.com/v1/audio/transcriptions"
    )


def test_transcript_skip_when_missing_api_key(tmp_path):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "ocr_enabled": False,
            "subtitle_enabled": False,
            "api_key_env": "OPENAI_API_KEY",
            "api_key": "",
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )

    file_manager = FileManager(str(tmp_path / "Downloaded"))
    database = _FakeDatabase()
    manager = TranscriptManager(config, file_manager, database=database)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    result = asyncio.run(manager.process_video(video_path, aweme_id="123"))

    assert result["status"] == "skipped"
    assert result["reason"] == "missing_api_key"
    assert database.rows[-1]["status"] == "skipped"
    assert database.rows[-1]["skip_reason"] == "missing_api_key"


def test_transcript_video_falls_back_to_ocr_without_api_key(tmp_path, monkeypatch):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "ocr_enabled": True,
            "subtitle_enabled": False,
            "api_key_env": "OPENAI_API_KEY",
            "api_key": "",
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )

    file_manager = FileManager(str(tmp_path / "Downloaded"))
    database = _FakeDatabase()
    manager = TranscriptManager(config, file_manager, database=database)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    async def _fake_ocr(_video_path):
        return "图片里提取到的文案"

    monkeypatch.setattr(manager, "_extract_text_from_video_ocr", _fake_ocr)

    result = asyncio.run(manager.process_video(video_path, aweme_id="123"))

    assert result["status"] == "success"
    assert result["source"] == "ocr"
    assert database.rows[-1]["status"] == "success"
    assert database.rows[-1]["model"] == "gpt-4o-mini-transcribe"
    assert (video_path.parent / "demo.transcript.txt").exists()


def test_transcript_video_prefers_audio_when_available(tmp_path, monkeypatch):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "ocr_enabled": True,
            "subtitle_enabled": True,
            "api_key": "test-key",
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )

    file_manager = FileManager(str(tmp_path / "Downloaded"))
    database = _FakeDatabase()
    manager = TranscriptManager(config, file_manager, database=database)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    async def _fake_audio(*, api_key, video_path, model):
        assert api_key == "test-key"
        return {
            "text": "完整音频转写文本",
            "duration_seconds": 45,
            "chunk_count": 1,
            "input_type": "audio",
        }

    async def _fake_ocr(_video_path):
        raise AssertionError("ocr should not run when audio transcription succeeds")

    monkeypatch.setattr(manager, "_transcribe_audio_from_video", _fake_audio)
    monkeypatch.setattr(manager, "_extract_text_from_video_ocr", _fake_ocr)

    result = asyncio.run(manager.process_video(video_path, aweme_id="123"))

    assert result["status"] == "success"
    assert result["source"] == "audio"
    payload = json.loads((video_path.parent / "demo.transcript.json").read_text(encoding="utf-8"))
    assert payload["aweme_id"] == "123"
    assert payload["source"] == "audio"
    assert payload["chunk_count"] == 1


def test_transcript_video_short_audio_falls_back_to_ocr_for_long_media(
    tmp_path, monkeypatch
):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "ocr_enabled": True,
            "subtitle_enabled": False,
            "api_key": "test-key",
            "output_dir": "",
            "response_formats": ["txt", "json"],
            "audio_force_chunking_above_seconds": 120,
            "audio_min_text_chars": 40,
        }
    )

    file_manager = FileManager(str(tmp_path / "Downloaded"))
    database = _FakeDatabase()
    manager = TranscriptManager(config, file_manager, database=database)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    async def _fake_audio(*, api_key, video_path, model):
        return {
            "text": "太短了",
            "duration_seconds": 210,
            "chunk_count": 3,
            "input_type": "audio",
        }

    async def _fake_ocr(_video_path):
        return "OCR 兜底拿到的完整文案"

    monkeypatch.setattr(manager, "_transcribe_audio_from_video", _fake_audio)
    monkeypatch.setattr(manager, "_extract_text_from_video_ocr", _fake_ocr)

    result = asyncio.run(manager.process_video(video_path, aweme_id="123"))

    assert result["status"] == "success"
    assert result["source"] == "ocr"
    payload = json.loads((video_path.parent / "demo.transcript.json").read_text(encoding="utf-8"))
    assert payload["source"] == "ocr"
    assert payload["audio_reason"] == "audio_transcript_too_short"
    assert payload["text"] == "OCR 兜底拿到的完整文案"


def test_transcript_video_local_backend_works_without_api_key(tmp_path, monkeypatch):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "backend": "faster_whisper_local",
            "local_model": "distil-large-v3",
            "ocr_enabled": True,
            "subtitle_enabled": True,
            "api_key": "",
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )

    file_manager = FileManager(str(tmp_path / "Downloaded"))
    database = _FakeDatabase()
    manager = TranscriptManager(config, file_manager, database=database)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    async def _fake_local_audio(*, video_path, model):
        assert model == "distil-large-v3"
        return {
            "text": "本地 whisper 转写结果",
            "duration_seconds": 50,
            "chunk_count": 1,
            "input_type": "audio",
            "model": model,
        }

    async def _fake_ocr(_video_path):
        raise AssertionError("ocr should not run when local audio transcription succeeds")

    monkeypatch.setattr(manager, "_transcribe_local_audio_from_video", _fake_local_audio)
    monkeypatch.setattr(manager, "_extract_text_from_video_ocr", _fake_ocr)

    result = asyncio.run(manager.process_video(video_path, aweme_id="123"))

    assert result["status"] == "success"
    assert result["source"] == "audio"
    assert database.rows[-1]["model"] == "faster-whisper:distil-large-v3"
    payload = json.loads((video_path.parent / "demo.transcript.json").read_text(encoding="utf-8"))
    assert payload["aweme_id"] == "123"
    assert payload["source"] == "audio"


def test_transcript_video_local_backend_falls_back_to_ocr_when_unavailable(
    tmp_path, monkeypatch
):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "backend": "faster_whisper_local",
            "local_model": "distil-large-v3",
            "ocr_enabled": True,
            "subtitle_enabled": False,
            "api_key": "",
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )

    file_manager = FileManager(str(tmp_path / "Downloaded"))
    database = _FakeDatabase()
    manager = TranscriptManager(config, file_manager, database=database)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    async def _fake_local_audio(*, video_path, model):
        raise RuntimeError("local_backend_unavailable")

    async def _fake_ocr(_video_path):
        return "OCR 兜底文案"

    monkeypatch.setattr(manager, "_transcribe_local_audio_from_video", _fake_local_audio)
    monkeypatch.setattr(manager, "_extract_text_from_video_ocr", _fake_ocr)

    result = asyncio.run(manager.process_video(video_path, aweme_id="123"))

    assert result["status"] == "success"
    assert result["source"] == "ocr"
    payload = json.loads((video_path.parent / "demo.transcript.json").read_text(encoding="utf-8"))
    assert payload["audio_reason"] == "local_backend_unavailable"
    assert database.rows[-1]["status"] == "success"


def test_transcript_images_use_ocr(tmp_path, monkeypatch):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "ocr_enabled": True,
            "subtitle_enabled": False,
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )

    file_manager = FileManager(str(tmp_path / "Downloaded"))
    database = _FakeDatabase()
    manager = TranscriptManager(config, file_manager, database=database)

    image_path = tmp_path / "Downloaded" / "author" / "like" / "frame_1.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"image")

    async def _fake_ocr(_image_paths):
        return "图文中的文案"

    monkeypatch.setattr(manager, "_extract_text_from_images", _fake_ocr)

    result = asyncio.run(manager.process_images([image_path], aweme_id="456"))

    assert result["status"] == "success"
    assert result["source"] == "ocr"
    assert database.rows[-1]["status"] == "success"
    assert (image_path.parent / "456.transcript.txt").exists()


def test_transcript_output_dir_defaults_to_video_dir(tmp_path):
    config = ConfigLoader()
    config.update(transcript={"enabled": True, "output_dir": ""})
    file_manager = FileManager(str(tmp_path / "Downloaded"))
    manager = TranscriptManager(config, file_manager, database=None)

    video_path = tmp_path / "Downloaded" / "a" / "post" / "x.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    resolved = manager.resolve_output_dir(video_path)
    assert resolved == video_path.parent


def test_transcript_output_dir_mirrors_video_tree(tmp_path):
    config = ConfigLoader()
    output_root = tmp_path / "Transcripts"
    config.update(transcript={"enabled": True, "output_dir": str(output_root)})
    file_manager = FileManager(str(tmp_path / "Downloaded"))
    manager = TranscriptManager(config, file_manager, database=None)

    video_path = tmp_path / "Downloaded" / "a" / "post" / "2026-02-18_demo" / "x.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    resolved = manager.resolve_output_dir(video_path)
    expected = output_root / "a" / "post" / "2026-02-18_demo"
    assert resolved == expected


def test_transcript_file_names(tmp_path):
    config = ConfigLoader()
    config.update(transcript={"enabled": True, "output_dir": ""})
    file_manager = FileManager(str(tmp_path / "Downloaded"))
    manager = TranscriptManager(config, file_manager, database=None)

    video_path = tmp_path / "Downloaded" / "a" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    text_path, json_path = manager.build_output_paths(video_path)
    assert text_path.name == "demo.transcript.txt"
    assert json_path.name == "demo.transcript.json"


def test_transcribe_audio_from_video_merges_chunk_results(tmp_path, monkeypatch):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "api_key": "test-key",
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )
    file_manager = FileManager(str(tmp_path / "Downloaded"))
    manager = TranscriptManager(config, file_manager, database=None)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    chunk_calls = []

    monkeypatch.setattr(manager, "_resolve_ffmpeg_exe", lambda: "fake-ffmpeg")
    monkeypatch.setattr(
        manager,
        "_probe_media",
        lambda _video_path, _ffmpeg_exe: {"duration_seconds": 210, "has_audio": True},
    )

    async def _fake_extract_audio(_video_path, audio_path, _ffmpeg_exe):
        audio_path.write_bytes(b"audio")
        return True

    async def _fake_build_chunks(*, audio_path, duration_seconds, ffmpeg_exe):
        chunk_1 = audio_path.parent / "chunk_001.mp3"
        chunk_2 = audio_path.parent / "chunk_002.mp3"
        chunk_1.write_bytes(b"chunk1")
        chunk_2.write_bytes(b"chunk2")
        return [chunk_1, chunk_2]

    async def _fake_openai(api_key, media_path, model):
        chunk_calls.append(media_path.name)
        if media_path.name == "chunk_001.mp3":
            return {"text": "第一段"}
        if media_path.name == "chunk_002.mp3":
            return {"text": "第二段"}
        raise AssertionError(f"unexpected chunk {media_path.name}")

    monkeypatch.setattr(manager, "_extract_audio_track", _fake_extract_audio)
    monkeypatch.setattr(manager, "_build_audio_chunks", _fake_build_chunks)
    monkeypatch.setattr(manager, "_call_openai_transcription", _fake_openai)

    payload = asyncio.run(
        manager._transcribe_audio_from_video(
            api_key="test-key",
            video_path=video_path,
            model="gpt-4o-mini-transcribe",
        )
    )

    assert chunk_calls == ["chunk_001.mp3", "chunk_002.mp3"]
    assert payload["text"] == "第一段\n第二段"
    assert payload["chunk_count"] == 2
    assert payload["duration_seconds"] == 210
    assert payload["input_type"] == "audio"


def test_transcribe_local_audio_from_video_merges_chunk_results(tmp_path, monkeypatch):
    config = ConfigLoader()
    config.update(
        transcript={
            "enabled": True,
            "backend": "faster_whisper_local",
            "local_model": "distil-large-v3",
            "output_dir": "",
            "response_formats": ["txt", "json"],
        }
    )
    file_manager = FileManager(str(tmp_path / "Downloaded"))
    manager = TranscriptManager(config, file_manager, database=None)

    video_path = tmp_path / "Downloaded" / "author" / "post" / "demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")

    chunk_calls = []

    monkeypatch.setattr(manager, "_resolve_ffmpeg_exe", lambda: "fake-ffmpeg")
    monkeypatch.setattr(
        manager,
        "_probe_media",
        lambda _video_path, _ffmpeg_exe: {"duration_seconds": 210, "has_audio": True},
    )

    async def _fake_extract_audio(_video_path, audio_path, _ffmpeg_exe):
        audio_path.write_bytes(b"audio")
        return True

    async def _fake_build_chunks(*, audio_path, duration_seconds, ffmpeg_exe):
        chunk_1 = audio_path.parent / "chunk_001.mp3"
        chunk_2 = audio_path.parent / "chunk_002.mp3"
        chunk_1.write_bytes(b"chunk1")
        chunk_2.write_bytes(b"chunk2")
        return [chunk_1, chunk_2]

    async def _fake_local(media_path, model):
        chunk_calls.append(media_path.name)
        if media_path.name == "chunk_001.mp3":
            return {"text": "第一段", "model": model}
        if media_path.name == "chunk_002.mp3":
            return {"text": "第二段", "model": model}
        raise AssertionError(f"unexpected chunk {media_path.name}")

    monkeypatch.setattr(manager, "_extract_audio_track", _fake_extract_audio)
    monkeypatch.setattr(manager, "_build_audio_chunks", _fake_build_chunks)
    monkeypatch.setattr(manager, "_call_local_transcription", _fake_local)

    payload = asyncio.run(
        manager._transcribe_local_audio_from_video(
            video_path=video_path,
            model="distil-large-v3",
        )
    )

    assert chunk_calls == ["chunk_001.mp3", "chunk_002.mp3"]
    assert payload["text"] == "第一段\n第二段"
    assert payload["chunk_count"] == 2
    assert payload["duration_seconds"] == 210
    assert payload["input_type"] == "audio"
    assert payload["model"] == "distil-large-v3"
