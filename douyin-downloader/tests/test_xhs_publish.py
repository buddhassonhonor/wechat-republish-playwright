import json
from pathlib import Path

from tools import xhs_publish


def _write_manifest(base_path: Path, aweme_id: str) -> Path:
    manifest = base_path / "download_manifest.jsonl"
    record = {
        "aweme_id": aweme_id,
        "date": "2024-11-11",
        "desc": "耶鲁大学的课堂#耶鲁大学 #名校教育",
        "media_type": "video",
        "tags": ["耶鲁大学", "名校教育"],
        "file_names": ["demo.mp4", "demo.transcript.txt"],
        "file_paths": [
            f"self/like/{aweme_id}/demo.mp4",
            f"self/like/{aweme_id}/demo.transcript.txt",
        ],
    }
    manifest.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _append_manifest(base_path: Path, aweme_id: str, title: str) -> None:
    manifest = base_path / "download_manifest.jsonl"
    record = {
        "aweme_id": aweme_id,
        "date": "2024-11-11",
        "desc": title,
        "media_type": "video",
        "tags": ["耶鲁大学", "名校教育"],
        "file_names": ["demo.mp4", "demo.transcript.txt"],
        "file_paths": [
            f"self/like/{aweme_id}/demo.mp4",
            f"self/like/{aweme_id}/demo.transcript.txt",
        ],
    }
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_publish_marks_and_skips_published_item(tmp_path, monkeypatch):
    base_path = tmp_path / "Downloaded"
    item_dir = base_path / "self" / "like" / "7436012128940625178"
    item_dir.mkdir(parents=True, exist_ok=True)
    (item_dir / "demo.mp4").write_bytes(b"video")
    (item_dir / "demo.transcript.txt").write_text("转写内容", encoding="utf-8")
    manifest = _write_manifest(base_path, "7436012128940625178")

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"path: {base_path.as_posix()}/\ndatabase: true\ndatabase_path: publish_state.db\n",
        encoding="utf-8",
    )

    calls = []

    def _fake_check_login(_base_url):
        return {"success": True}

    def _fake_publish_item(_base_url, payload):
        calls.append(payload["title"])
        return {"success": True, "message": "published"}

    monkeypatch.setattr(xhs_publish, "_check_login", _fake_check_login)
    monkeypatch.setattr(xhs_publish, "_publish_item", _fake_publish_item)

    exit_code = xhs_publish.main(
        [
            "-c",
            str(config_path),
            "--aweme-id",
            "7436012128940625178",
            "--manifest",
            str(manifest),
            "--publish",
        ]
    )
    assert exit_code == 0
    assert len(calls) == 1


def test_random_pick_avoids_published_items(tmp_path, monkeypatch):
    base_path = tmp_path / "Downloaded"
    first_dir = base_path / "self" / "like" / "7436012128940625178"
    second_dir = base_path / "self" / "like" / "7436012128940625179"
    first_dir.mkdir(parents=True, exist_ok=True)
    second_dir.mkdir(parents=True, exist_ok=True)
    for item_dir in (first_dir, second_dir):
        (item_dir / "demo.mp4").write_bytes(b"video")
        (item_dir / "demo.transcript.txt").write_text("转写内容", encoding="utf-8")

    manifest = _write_manifest(base_path, "7436012128940625178")
    _append_manifest(base_path, "7436012128940625179", "第二条视频#名校教育")

    published_state = {
        "aweme_id": "7436012128940625178",
        "published": True,
        "status": "published",
        "endpoint": "/api/v1/publish_video",
        "response": {"success": True},
        "error": "",
    }
    (first_dir / "demo.xhs_publish_state.json").write_text(
        json.dumps(published_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"path: {base_path.as_posix()}/\ndatabase: true\ndatabase_path: publish_state.db\n",
        encoding="utf-8",
    )

    selected = []
    calls = []

    def _fake_choice(pool):
        selected.extend(item.aweme_id for item in pool)
        return pool[0]

    def _fake_check_login(_base_url):
        return {"success": True}

    def _fake_publish_item(_base_url, payload):
        calls.append(payload["title"])
        return {"success": True, "message": "published"}

    monkeypatch.setattr(xhs_publish.random, "choice", _fake_choice)
    monkeypatch.setattr(xhs_publish, "_check_login", _fake_check_login)
    monkeypatch.setattr(xhs_publish, "_publish_item", _fake_publish_item)

    exit_code = xhs_publish.main(
        [
            "-c",
            str(config_path),
            "--manifest",
            str(manifest),
            "--random",
            "--publish",
        ]
    )
    assert exit_code == 0
    assert selected == ["7436012128940625179"]
    assert len(calls) == 1

    state_path = item_dir / "demo.xhs_publish_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["published"] is True
    assert state["status"] == "published"

    exit_code = xhs_publish.main(
        [
            "-c",
            str(config_path),
            "--aweme-id",
            "7436012128940625178",
            "--manifest",
            str(manifest),
            "--publish",
        ]
    )
    assert exit_code == 0
    assert len(calls) == 1
