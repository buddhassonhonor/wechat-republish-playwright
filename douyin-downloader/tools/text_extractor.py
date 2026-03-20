from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import ConfigLoader
from core.transcript_manager import TranscriptManager
from storage import FileManager
from utils.logger import setup_logger

logger = setup_logger("TextExtractor")

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".m4a", ".mov", ".mkv"}


def emit(message: str) -> None:
    print(message, flush=True)


@dataclass
class ExtractionItem:
    aweme_id: str
    media_type: str
    primary_path: Optional[Path]
    image_paths: List[Path]
    raw: Dict[str, Any]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract text from already downloaded Douyin items.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yml",
        help="Config file path (default: config.yml)",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional download manifest path (default: <path>/download_manifest.jsonl)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild transcript files even if they already exist",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N items (0 = unlimited)",
    )
    parser.add_argument(
        "--aweme-id",
        action="append",
        dest="aweme_ids",
        default=[],
        help="Process only the specified aweme_id(s); can be repeated",
    )
    return parser.parse_args(argv)


def _as_path_list(values: Any, base_path: Path) -> List[Path]:
    if not isinstance(values, list):
        return []

    paths: List[Path] = []
    for value in values:
        if not value:
            continue
        raw_path = Path(str(value))
        if not raw_path.is_absolute():
            raw_path = base_path / raw_path
        if raw_path.exists() and raw_path.is_file():
            paths.append(raw_path)
    return paths


def _detect_media_type(record: Dict[str, Any], file_paths: Iterable[Path]) -> str:
    media_type = str(record.get("media_type") or "").strip().lower()
    if media_type in {"video", "gallery"}:
        return media_type

    has_video = any(path.suffix.lower() in VIDEO_SUFFIXES for path in file_paths)
    has_image = any(path.suffix.lower() in IMAGE_SUFFIXES for path in file_paths)
    if has_image and not has_video:
        return "gallery"
    if has_video:
        return "video"
    return "unknown"


def collect_items_from_manifest(manifest_path: Path, base_path: Path) -> List[ExtractionItem]:
    items: List[ExtractionItem] = []
    if not manifest_path.exists():
        return items

    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        logger.error("Failed to read manifest %s: %s", manifest_path, exc)
        return items

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if not isinstance(record, dict):
            continue

        aweme_id = str(record.get("aweme_id") or "").strip()
        if not aweme_id:
            continue

        file_paths = _as_path_list(record.get("file_paths"), base_path)
        if not file_paths:
            continue

        media_type = _detect_media_type(record, file_paths)
        image_paths = [
            path
            for path in file_paths
            if path.suffix.lower() in IMAGE_SUFFIXES
            and "_cover" not in path.stem
            and "_avatar" not in path.stem
        ]
        primary_path = None
        if media_type == "video":
            primary_path = next(
                (path for path in file_paths if path.suffix.lower() in VIDEO_SUFFIXES),
                None,
            )
        elif media_type == "gallery":
            if image_paths:
                primary_path = image_paths[0]
            else:
                primary_path = next(
                    (path for path in file_paths if path.suffix.lower() in VIDEO_SUFFIXES),
                    None,
                )

        if media_type == "unknown":
            continue

        items.append(
            ExtractionItem(
                aweme_id=aweme_id,
                media_type=media_type,
                primary_path=primary_path,
                image_paths=image_paths,
                raw=record,
            )
        )

    return items


def _build_manifest_path(base_path: Path) -> Path:
    return base_path / "download_manifest.jsonl"


def _should_skip_outputs(manager: TranscriptManager, item: ExtractionItem) -> bool:
    if item.media_type == "video" and item.primary_path:
        text_path, json_path = manager.build_output_paths(item.primary_path)
    elif item.media_type == "gallery" and item.image_paths:
        reference = item.image_paths[0].parent / f"{item.aweme_id}.jpg"
        text_path, json_path = manager.build_output_paths(reference)
    else:
        return True

    return text_path.exists() or json_path.exists()


async def process_items(
    manager: TranscriptManager,
    items: List[ExtractionItem],
    *,
    force: bool = False,
    limit: int = 0,
) -> Dict[str, int]:
    stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}
    total_candidates = len(items)
    emit(f"[text-extractor] candidates={total_candidates} force={force} limit={limit or 'all'}")

    for index, item in enumerate(items, start=1):
        if limit > 0 and stats["total"] >= limit:
            break

        if not item.primary_path and not item.image_paths:
            stats["skipped"] += 1
            emit(
                f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                f"type={item.media_type} -> skip(no files)"
            )
            continue

        emit(
            f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
            f"type={item.media_type} -> preparing"
        )
        if not force and _should_skip_outputs(manager, item):
            stats["skipped"] += 1
            emit(
                f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                f"-> skip(existing transcript)"
            )
            continue

        stats["total"] += 1
        try:
            if item.media_type == "video" and item.primary_path:
                emit(
                    f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                    f"-> video {item.primary_path.name}"
                )
                result = await manager.process_video(item.primary_path, item.aweme_id)
            elif item.media_type == "gallery" and item.image_paths:
                emit(
                    f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                    f"-> gallery {len(item.image_paths)} image(s)"
                )
                result = await manager.process_images(item.image_paths, item.aweme_id)
            else:
                stats["skipped"] += 1
                emit(
                    f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                    f"-> skip(unsupported)"
                )
                continue
        except Exception as exc:
            logger.error("Text extraction failed for %s: %s", item.aweme_id, exc)
            stats["failed"] += 1
            emit(
                f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                f"-> failed ({exc})"
            )
            continue

        status = str(result.get("status") or "").strip().lower()
        if status == "success":
            stats["success"] += 1
            emit(
                f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                f"-> success source={result.get('source', 'unknown')}"
            )
        elif status == "skipped":
            stats["skipped"] += 1
            emit(
                f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                f"-> skipped reason={result.get('reason', 'unknown')}"
            )
        else:
            stats["failed"] += 1
            emit(
                f"[{index}/{total_candidates}] aweme_id={item.aweme_id} "
                f"-> failed reason={result.get('reason', 'unknown')}"
            )

    return stats


async def main_async(args: argparse.Namespace) -> int:
    config = ConfigLoader(args.config)
    base_path = Path(config.get("path") or "./Downloaded")
    manifest_path = Path(args.manifest) if args.manifest else _build_manifest_path(base_path)

    transcript_cfg = dict(config.get("transcript", {}) or {})
    transcript_cfg.update(
        {
            "enabled": True,
            "ocr_enabled": True,
            "subtitle_enabled": True,
        }
    )
    config.update(transcript=transcript_cfg)

    file_manager = FileManager(str(base_path))
    manager = TranscriptManager(config, file_manager, database=None)

    items = collect_items_from_manifest(manifest_path, base_path)
    if args.aweme_ids:
        selected_ids = {str(value).strip() for value in args.aweme_ids if str(value).strip()}
        items = [item for item in items if item.aweme_id in selected_ids]
    if not items:
        logger.warning("No completed items found in %s", manifest_path)
        return 0

    emit(f"[text-extractor] manifest={manifest_path}")
    emit(f"[text-extractor] output_root={base_path}")

    stats = await process_items(
        manager,
        items,
        force=args.force,
        limit=args.limit,
    )

    summary_path = base_path / "text_extraction_summary.jsonl"
    try:
        with summary_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"stats": stats}, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to write summary: %s", exc)

    emit(
        f"[text-extractor] done total={stats['total']} success={stats['success']} "
        f"failed={stats['failed']} skipped={stats['skipped']}"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
