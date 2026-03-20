from __future__ import annotations

import argparse
import json
import re
import random
import urllib.error
import urllib.request
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ConfigLoader
from tools.text_extractor import (
    IMAGE_SUFFIXES,
    VIDEO_SUFFIXES,
    _build_manifest_path,
    collect_items_from_manifest,
)


def emit(message: str) -> None:
    print(message, flush=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Xiaohongshu publish drafts from downloaded Douyin items.",
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
        "--aweme-id",
        action="append",
        dest="aweme_ids",
        default=[],
        help="Publish only the specified aweme_id(s); can be repeated",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:18060",
        help="Base URL of xiaohongshu-mcp HTTP service",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually call xiaohongshu-mcp publish API; default is draft-only",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        help="Randomly pick one matched item to process",
    )
    parser.add_argument(
        "--include-published",
        action="store_true",
        help="Allow republishing items that were already marked as published",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List matched items and their published state, then exit",
    )
    parser.add_argument(
        "--visibility",
        default="公开可见",
        help="Visibility for Xiaohongshu publish",
    )
    parser.add_argument(
        "--schedule-at",
        default="",
        help="Optional ISO8601 scheduled publish time",
    )
    parser.add_argument(
        "--tag",
        action="append",
        dest="extra_tags",
        default=[],
        help="Extra Xiaohongshu tag; can be repeated",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N items (0 = unlimited)",
    )
    return parser.parse_args(argv)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_desc(desc: str) -> str:
    desc = str(desc or "")
    desc = re.sub(r"#\S+", "", desc)
    desc = desc.replace("\n", " ").replace("\r", " ")
    return _normalize_spaces(desc)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _truncate_title(text: str) -> str:
    text = _normalize_spaces(text)
    if not text:
        return "抖音内容分享"
    limit_units = 40
    units = 0
    kept: List[str] = []
    for ch in text:
        if ord(ch) <= 0x7F:
            step = 1
        elif unicodedata.category(ch) == "So":
            step = 4
        else:
            step = 2
        if units + step > limit_units:
            break
        kept.append(ch)
        units += step
    result = "".join(kept).strip()
    if not result:
        result = text[:20].strip()
    return result.rstrip("，。！？；：、- ")


def _shorten_title_for_retry(text: str) -> str:
    text = _normalize_spaces(text)
    if not text:
        return "抖音内容分享"
    limit_units = 28
    units = 0
    kept: List[str] = []
    for ch in text:
        if ord(ch) <= 0x7F:
            step = 1
        elif unicodedata.category(ch) == "So":
            step = 4
        else:
            step = 2
        if units + step > limit_units:
            break
        kept.append(ch)
        units += step
    result = "".join(kept).strip()
    if not result:
        result = text[:12].strip()
    return result.rstrip("，。！？；：、- ")


def _is_title_length_error(body: str) -> bool:
    if not body:
        return False
    return "标题长度超过限制" in body or "title length" in body.lower()


def _normalize_transcript_lines(text: str) -> List[str]:
    lines: List[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        line = _normalize_spaces(raw_line)
        if not line:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def _build_content(desc: str, transcript_text: str, tags: List[str]) -> str:
    parts: List[str] = []
    cleaned_desc = _clean_desc(desc)
    if cleaned_desc and tags:
        parts.append(
            f"整理了一条和{'、'.join(tags[:3])}相关的视频内容，主题是「{cleaned_desc}」。"
        )
    elif cleaned_desc:
        parts.append(f"整理了一条视频内容，主题是「{cleaned_desc}」。")

    lines = _normalize_transcript_lines(transcript_text)
    if lines:
        preview_lines = lines[:8]
        preview = "\n".join(preview_lines).strip()
        if len(preview) > 700:
            preview = preview[:700].rstrip() + "..."
        if preview:
            label = "视频转写节选"
            if not _contains_cjk(preview):
                label = "视频转写节选（原文）"
            parts.append(f"{label}：\n{preview}")

    hashtags = [f"#{tag}" for tag in tags if str(tag).strip()]
    if hashtags:
        parts.append(" ".join(hashtags[:10]))

    content = "\n\n".join(part for part in parts if part).strip()
    return content or "内容整理中"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _find_transcript_path(item: Any) -> Optional[Path]:
    if item.media_type == "video" and item.primary_path:
        candidate = item.primary_path.with_suffix(".transcript.txt")
        if candidate.exists():
            return candidate
        candidate = item.primary_path.parent / f"{item.primary_path.stem}.transcript.txt"
        if candidate.exists():
            return candidate
        return None

    if item.media_type == "gallery" and item.image_paths:
        candidate = item.image_paths[0].parent / f"{item.aweme_id}.transcript.txt"
        if candidate.exists():
            return candidate
    return None


def _pick_images(item: Any) -> List[str]:
    image_paths: List[str] = []
    for image_path in item.image_paths:
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        image_paths.append(str(image_path.resolve()))
    return image_paths


def _pick_video(item: Any) -> str:
    if not item.primary_path:
        return ""
    if item.primary_path.suffix.lower() not in VIDEO_SUFFIXES:
        return ""
    return str(item.primary_path.resolve())


def _request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, method=method.upper(), data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = response.read().decode("utf-8", errors="ignore")
        return json.loads(raw or "{}")


def _check_login(base_url: str) -> Dict[str, Any]:
    return _request_json("GET", f"{base_url.rstrip('/')}/api/v1/login/status")


def _publish_payload(item: Any, args: argparse.Namespace) -> Dict[str, Any]:
    raw = item.raw
    desc = str(raw.get("desc") or "")
    transcript_path = _find_transcript_path(item)
    transcript_text = _read_text(transcript_path) if transcript_path else ""

    tags = [str(tag).strip() for tag in raw.get("tags") or [] if str(tag).strip()]
    for extra_tag in args.extra_tags:
        extra_tag = str(extra_tag).strip()
        if extra_tag and extra_tag not in tags:
            tags.append(extra_tag)

    title_seed = _clean_desc(desc) or (transcript_text.splitlines()[0] if transcript_text else "")
    title = _truncate_title(title_seed)
    content = _build_content(desc, transcript_text, tags)

    payload: Dict[str, Any] = {
        "aweme_id": item.aweme_id,
        "title": title,
        "content": content,
        "tags": tags[:10],
        "visibility": args.visibility,
        "schedule_at": args.schedule_at,
        "transcript_path": str(transcript_path.resolve()) if transcript_path else "",
    }

    if item.media_type == "video":
        payload["publish_endpoint"] = "/api/v1/publish_video"
        payload["video"] = _pick_video(item)
    else:
        payload["publish_endpoint"] = "/api/v1/publish"
        payload["images"] = _pick_images(item)

    return payload


def _draft_path_for_item(item: Any) -> Path:
    if item.media_type == "video" and item.primary_path:
        return item.primary_path.parent / f"{item.primary_path.stem}.xhs_draft.json"
    if item.media_type == "gallery" and item.image_paths:
        return item.image_paths[0].parent / f"{item.aweme_id}.xhs_draft.json"
    return Path.cwd() / f"{item.aweme_id}.xhs_draft.json"


def _write_draft_file(item: Any, payload: Dict[str, Any]) -> Path:
    draft_path = _draft_path_for_item(item)
    try:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return draft_path
    except OSError:
        fallback_path = Path.cwd() / "Downloaded" / "xhs_drafts" / f"{item.aweme_id}.xhs_draft.json"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return fallback_path


def _publish_state_path(draft_path: Path) -> Path:
    stem = draft_path.stem
    if stem.endswith(".xhs_draft"):
        stem = stem[: -len(".xhs_draft")]
    return draft_path.with_name(f"{stem}.xhs_publish_state.json")


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_published(draft_path: Path) -> bool:
    state_path = _publish_state_path(draft_path)
    if not state_path.exists():
        return False
    state = _read_json(state_path)
    return bool(state.get("published") is True or str(state.get("status", "")).lower() == "published")


def _write_publish_state(
    draft_path: Path,
    *,
    aweme_id: str,
    published: bool,
    status: str,
    endpoint: str,
    response: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> Path:
    state_path = _publish_state_path(draft_path)
    payload = {
        "aweme_id": aweme_id,
        "published": published,
        "status": status,
        "endpoint": endpoint,
        "response": response or {},
        "error": error,
    }
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return state_path
    except OSError:
        fallback_path = Path.cwd() / "Downloaded" / "xhs_drafts" / f"{aweme_id}.xhs_publish_state.json"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return fallback_path


def _publish_item(base_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    endpoint = str(payload.pop("publish_endpoint"))
    return _request_json("POST", f"{base_url.rstrip('/')}{endpoint}", payload)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    config = ConfigLoader(args.config)
    base_path = Path(config.get("path") or "./Downloaded")
    manifest_path = Path(args.manifest) if args.manifest else _build_manifest_path(base_path)

    items = collect_items_from_manifest(manifest_path, base_path)
    if args.aweme_ids:
        selected_ids = {str(value).strip() for value in args.aweme_ids if str(value).strip()}
        items = [item for item in items if item.aweme_id in selected_ids]

    if not items:
        emit(f"[xhs-publish] no items matched in {manifest_path}")
        return 1

    if args.random and args.aweme_ids:
        emit("[xhs-publish] --random cannot be combined with --aweme-id")
        return 2

    if args.random:
        random_pool = list(items)
        if args.publish and not args.include_published:
            random_pool = [
                item
                for item in random_pool
                if not _is_published(_draft_path_for_item(item))
            ]
        if not random_pool:
            emit("[xhs-publish] no eligible items available for random selection")
            return 1
        selected_item = random.choice(random_pool)
        items = [selected_item]
        emit(
            f"[xhs-publish] random_pick aweme_id={selected_item.aweme_id} "
            f"title={_truncate_title(_clean_desc(str(selected_item.raw.get('desc') or '')))}"
        )

    if args.list:
        for item in items:
            payload = _publish_payload(item, args)
            draft_path = _write_draft_file(item, payload)
            published = _is_published(draft_path)
            emit(
                f"[xhs-publish] aweme_id={item.aweme_id} published={'yes' if published else 'no'} "
                f"title={payload['title']} draft={draft_path}"
            )
        return 0

    if args.publish:
        try:
            login_status = _check_login(args.base_url)
            emit(f"[xhs-publish] login_status={json.dumps(login_status, ensure_ascii=False)}")
        except Exception as exc:
            emit(f"[xhs-publish] failed to check login status: {exc}")
            return 2

    processed = 0
    drafted = 0
    published = 0
    skipped = 0
    for item in items:
        if args.limit > 0 and processed >= args.limit:
            break
        processed += 1

        payload = _publish_payload(item, args)
        draft_path = _write_draft_file(item, payload)
        drafted += 1
        emit(f"[xhs-publish] aweme_id={item.aweme_id} draft={draft_path}")

        if not args.publish:
            continue

        if not args.include_published and _is_published(draft_path):
            skipped += 1
            emit(f"[xhs-publish] aweme_id={item.aweme_id} skip=already_published")
            continue

        publish_payload = dict(payload)
        publish_payload.pop("aweme_id", None)
        publish_payload.pop("transcript_path", None)
        try:
            response = _publish_item(args.base_url, publish_payload)
            _write_publish_state(
                draft_path,
                aweme_id=item.aweme_id,
                published=True,
                status="published",
                endpoint=str(payload.get("publish_endpoint", "")),
                response=response,
            )
            published += 1
            emit(f"[xhs-publish] aweme_id={item.aweme_id} published={json.dumps(response, ensure_ascii=False)}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if _is_title_length_error(body):
                shorter_title = _shorten_title_for_retry(payload.get("title", ""))
                if shorter_title and shorter_title != payload.get("title"):
                    payload["title"] = shorter_title
                    publish_payload["title"] = shorter_title
                    draft_path = _write_draft_file(item, payload)
                    try:
                        response = _publish_item(args.base_url, publish_payload)
                        _write_publish_state(
                            draft_path,
                            aweme_id=item.aweme_id,
                            published=True,
                            status="published",
                            endpoint=str(payload.get("publish_endpoint", "")),
                            response=response,
                        )
                        published += 1
                        emit(
                            f"[xhs-publish] aweme_id={item.aweme_id} published={json.dumps(response, ensure_ascii=False)}"
                        )
                        continue
                    except urllib.error.HTTPError as retry_exc:
                        body = retry_exc.read().decode("utf-8", errors="ignore")
                    except Exception as retry_exc:
                        body = str(retry_exc)
            _write_publish_state(
                draft_path,
                aweme_id=item.aweme_id,
                published=False,
                status="failed",
                endpoint=str(payload.get("publish_endpoint", "")),
                error=body,
            )
            emit(f"[xhs-publish] aweme_id={item.aweme_id} publish_failed status={exc.code} body={body}")
            return 3
        except Exception as exc:
            _write_publish_state(
                draft_path,
                aweme_id=item.aweme_id,
                published=False,
                status="failed",
                endpoint=str(payload.get("publish_endpoint", "")),
                error=str(exc),
            )
            emit(f"[xhs-publish] aweme_id={item.aweme_id} publish_failed error={exc}")
            return 3

    if args.publish:
        emit(
            f"[xhs-publish] done drafted={drafted} published={published} skipped={skipped}"
        )
    else:
        emit(f"[xhs-publish] done drafted={drafted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
