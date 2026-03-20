from pathlib import Path

from tools.text_extractor import collect_items_from_manifest, process_items


class _FakeManager:
    def __init__(self):
        self.video_calls = []
        self.image_calls = []

    def build_output_paths(self, path: Path):
        return path.with_suffix(".transcript.txt"), path.with_suffix(".transcript.json")

    async def process_video(self, video_path: Path, aweme_id: str):
        self.video_calls.append((video_path.name, aweme_id))
        return {"status": "success", "source": "audio"}

    async def process_images(self, image_paths, aweme_id: str):
        self.image_calls.append(([p.name for p in image_paths], aweme_id))
        return {"status": "success", "source": "ocr"}


def test_collect_items_from_manifest_detects_video_and_gallery(tmp_path):
    base_path = tmp_path / "Downloaded"
    base_path.mkdir()
    video = base_path / "author" / "post" / "a.mp4"
    image1 = base_path / "author" / "like" / "b_1.jpg"
    image2 = base_path / "author" / "like" / "b_2.png"
    video.parent.mkdir(parents=True, exist_ok=True)
    image1.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"v")
    image1.write_bytes(b"i1")
    image2.write_bytes(b"i2")

    manifest = base_path / "download_manifest.jsonl"
    manifest.write_text(
        "\n".join(
            [
                '{"aweme_id":"111","media_type":"video","file_paths":["author/post/a.mp4"]}',
                '{"aweme_id":"222","media_type":"gallery","file_paths":["author/like/b_1.jpg","author/like/b_2.png"]}',
            ]
        ),
        encoding="utf-8",
    )

    items = collect_items_from_manifest(manifest, base_path)

    assert [item.aweme_id for item in items] == ["111", "222"]
    assert items[0].primary_path == video
    assert [p.name for p in items[1].image_paths] == ["b_1.jpg", "b_2.png"]


def test_process_items_skips_existing_outputs(tmp_path):
    manager = _FakeManager()
    base_path = tmp_path / "Downloaded"
    base_path.mkdir()
    video = base_path / "author" / "post" / "a.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"v")
    (video.with_suffix(".transcript.txt")).write_text("done", encoding="utf-8")

    items = collect_items_from_manifest(
        base_path / "download_manifest.jsonl",
        base_path,
    )
    items.append(
        type("Item", (), {
            "aweme_id": "111",
            "media_type": "video",
            "primary_path": video,
            "image_paths": [],
            "raw": {},
        })()
    )

    import asyncio

    stats = asyncio.run(process_items(manager, items, force=False))

    assert stats["skipped"] >= 1
    assert manager.video_calls == []
