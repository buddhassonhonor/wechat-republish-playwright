from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config import ConfigLoader
from tools.text_extractor import (
    IMAGE_SUFFIXES,
    VIDEO_SUFFIXES,
    _build_manifest_path,
    collect_items_from_manifest,
)


def emit(message: str) -> None:
    print(message, flush=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish downloaded Douyin videos to Kuaishou.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yml",
        help="Config file path (default: config.yml).",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional download manifest path (default: <path>/download_manifest.jsonl).",
    )
    parser.add_argument(
        "--aweme-id",
        action="append",
        dest="aweme_ids",
        default=[],
        help="Publish only the specified aweme_id(s); can be repeated.",
    )
    parser.add_argument(
        "--account-file",
        default="../matrix/ks_uploader/account/default_account.json",
        help="Kuaishou Playwright storage-state JSON path.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Actually publish to Kuaishou; default is draft-only.",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        help="Randomly pick one matched item to process.",
    )
    parser.add_argument(
        "--include-published",
        action="store_true",
        help="Allow republishing items already marked as published.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List matched items and their published state, then exit.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N items (0 = unlimited).",
    )
    parser.add_argument(
        "--browser",
        default="chromium",
        choices=["chromium", "chrome", "msedge"],
        help="Browser channel to launch.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Launch browser in headless mode when publishing.",
    )
    return parser.parse_args(argv)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_desc(desc: str) -> str:
    desc = str(desc or "")
    desc = re.sub(r"#\S+", "", desc)
    desc = desc.replace("\r", " ").replace("\n", " ")
    return _normalize_spaces(desc)


def _truncate_title(text: str, limit_units: int = 30) -> str:
    text = _normalize_spaces(text)
    if not text:
        return "抖音内容分享"
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
    return result.rstrip("，。！？；：、- ") or "抖音内容分享"


def _resolve_account_file(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path(__file__).resolve().parent / raw_path).resolve()


def _pick_video(item: Any) -> str:
    if not item.primary_path:
        return ""
    if item.primary_path.suffix.lower() not in VIDEO_SUFFIXES:
        return ""
    return str(item.primary_path.resolve())


def _pick_cover(item: Any) -> str:
    if item.primary_path:
        sibling_covers = sorted(item.primary_path.parent.glob("*_cover.*"))
        for candidate in sibling_covers:
            if candidate.suffix.lower() in IMAGE_SUFFIXES:
                return str(candidate.resolve())
    return ""


def _extract_tags(item: Any) -> List[str]:
    seen: set[str] = set()
    tags: List[str] = []
    for raw_tag in item.raw.get("tags") or []:
        tag = _normalize_spaces(str(raw_tag))
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


@dataclass
class PublishDraft:
    aweme_id: str
    title: str
    video_path: str
    cover_path: str
    tags: List[str]


def _build_draft(item: Any) -> PublishDraft:
    desc = str(item.raw.get("desc") or "")
    title = _truncate_title(_clean_desc(desc))
    return PublishDraft(
        aweme_id=item.aweme_id,
        title=title,
        video_path=_pick_video(item),
        cover_path=_pick_cover(item),
        tags=_extract_tags(item),
    )


def _draft_path_for_item(item: Any) -> Path:
    if item.primary_path:
        return item.primary_path.parent / f"{item.primary_path.stem}.ks_draft.json"
    return Path.cwd() / f"{item.aweme_id}.ks_draft.json"


def _publish_state_path(draft_path: Path) -> Path:
    stem = draft_path.stem
    if stem.endswith(".ks_draft"):
        stem = stem[: -len(".ks_draft")]
    return draft_path.with_name(f"{stem}.ks_publish_state.json")


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


def _write_draft_file(item: Any, draft: PublishDraft) -> Path:
    draft_path = _draft_path_for_item(item)
    payload = {
        "aweme_id": draft.aweme_id,
        "title": draft.title,
        "video_path": draft.video_path,
        "cover_path": draft.cover_path,
        "tags": draft.tags,
    }
    try:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return draft_path
    except OSError:
        fallback_path = Path.cwd() / "Downloaded" / "ks_drafts" / f"{draft.aweme_id}.ks_draft.json"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return fallback_path


def _write_publish_state(
    draft_path: Path,
    *,
    aweme_id: str,
    published: bool,
    status: str,
    account_file: Path,
    error: str = "",
) -> Path:
    payload = {
        "aweme_id": aweme_id,
        "published": published,
        "status": status,
        "account_file": str(account_file),
        "error": error,
    }
    state_path = _publish_state_path(draft_path)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return state_path
    except OSError:
        fallback_path = Path.cwd() / "Downloaded" / "ks_drafts" / f"{aweme_id}.ks_publish_state.json"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return fallback_path


async def _save_debug_screenshot(page, label: str) -> Optional[Path]:
    try:
        debug_dir = Path.cwd() / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = debug_dir / f"ks_publish_{label}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        return screenshot_path
    except Exception:
        return None


async def _wait_for_upload_success(page) -> None:
    for _ in range(600):
        if await page.locator('span:has-text("上传成功")').count():
            return
        if await page.get_by_role("button", name="编辑封面").count():
            return
        if await page.get_by_role("button", name="发布", exact=True).count():
            return
        if await page.get_by_text("作品描述").count():
            return
        if await page.get_by_text("封面设置").count():
            return
        if await page.get_by_text("作品分类").count():
            return
        if await page.get_by_text("预览作品").count():
            return
        if await page.locator("textarea").count():
            return
        await asyncio.sleep(1)
    raise TimeoutError("video upload did not finish in time")


async def _fill_title(page, title: str) -> bool:
    title = str(title or "").strip()[:30]
    if not title:
        return False

    try:
        result = await page.evaluate(
            """(value) => {
                const visible = (node) => {
                    if (!node) return false;
                    const style = window.getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0;
                };

                const candidates = Array.from(
                    document.querySelectorAll('textarea, [contenteditable="true"], input, .notranslate')
                ).filter(visible);

                const score = (node) => {
                    const text = ((node.getAttribute('placeholder') || '') + ' ' + (node.innerText || '')).trim();
                    let s = 0;
                    if (node.tagName === 'TEXTAREA') s += 5;
                    if (text.includes('描述')) s += 5;
                    if (text.includes('推荐')) s += 3;
                    if (node.getAttribute('contenteditable') === 'true') s += 2;
                    return s;
                };

                candidates.sort((a, b) => score(b) - score(a));
                const target = candidates[0];
                if (!target) return false;

                target.focus();
                if ('value' in target) {
                    target.value = value;
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                    target.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }

                target.textContent = value;
                target.dispatchEvent(new InputEvent('input', { bubbles: true, data: value }));
                return true;
            }""",
            title,
        )
        if result:
            return True
    except Exception:
        pass

    locators = [
        page.get_by_placeholder("添加合适的话题和描述，作品能获得更多推荐～"),
        page.get_by_placeholder(re.compile("描述|推荐")),
        page.locator("textarea").first,
        page.locator("[contenteditable='true']").first,
        page.locator(".notranslate").first,
    ]

    for locator in locators:
        try:
            if await locator.count() == 0:
                continue
            await locator.click(timeout=800, force=True)
            try:
                await locator.fill("", timeout=800)
                await locator.fill(title, timeout=800)
            except Exception:
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")
                await page.keyboard.type(title)
            return True
        except Exception:
            continue
    return False


async def _maybe_upload_cover(page, cover_path: str) -> None:
    if not cover_path:
        return
    edit_button = page.get_by_role("button", name="编辑封面")
    if not await edit_button.count():
        return
    await edit_button.click()
    await asyncio.sleep(1)
    upload_tab = page.get_by_role("tab", name="上传封面")
    if await upload_tab.count():
        await upload_tab.click()
    preview_upload = page.get_by_role("tabpanel", name="上传封面").locator("div").nth(1)
    async with page.expect_file_chooser() as chooser_info:
        await preview_upload.click()
    chooser = await chooser_info.value
    await chooser.set_files(cover_path)
    confirm = page.get_by_role("button", name="确认")
    if await confirm.count():
        await confirm.click()
    await asyncio.sleep(3)


async def _click_publish(page) -> bool:
    locators = [
        page.locator("div._button_3a3lq_1._button-primary_3a3lq_60").filter(has_text="发布").first,
        page.locator("div._button-primary_3a3lq_60").filter(has_text="发布").first,
        page.locator("div:has(> div:text-is('发布'))").first,
        page.locator("div:text-is('发布')").first,
        page.get_by_role("button", name="发布", exact=True),
        page.get_by_role("button", name=re.compile("发布")),
        page.locator("button:has-text('发布')").first,
        page.locator("[role='button']:has-text('发布')").first,
    ]

    for locator in locators:
        try:
            if await locator.count() == 0:
                continue
            await locator.scroll_into_view_if_needed()
            await locator.click(timeout=3000)
            return True
        except Exception:
            continue
    return False


async def _dismiss_onboarding_popup(page) -> bool:
    dismissed = False
    for _ in range(6):
        progressed = False

        next_candidates = [
            page.get_by_role("button", name="下一步"),
            page.locator("button:has-text('下一步')"),
            page.locator("div:has-text('下一步')"),
            page.get_by_text("下一步"),
        ]
        for next_button in next_candidates:
            try:
                if await next_button.count():
                    await next_button.last.click(timeout=2000, force=True)
                    await asyncio.sleep(0.8)
                    dismissed = True
                    progressed = True
                    break
            except Exception:
                continue

        close_button = page.locator("div[role='dialog'], div[class*='modal'], div[class*='drawer']").get_by_role(
            "button", name=re.compile("关闭|知道了|完成|跳过")
        )
        try:
            if await close_button.count():
                await close_button.first.click(timeout=2000)
                await asyncio.sleep(0.8)
                dismissed = True
                progressed = True
        except Exception:
            pass

        close_icon = page.locator(
            "div[role='dialog'] .close, div[class*='modal'] .close, div[class*='drawer'] .close, "
            "div[role='dialog'] [aria-label='关闭'], div[class*='modal'] [aria-label='关闭']"
        )
        try:
            if await close_icon.count():
                await close_icon.first.click(timeout=2000)
                await asyncio.sleep(0.8)
                dismissed = True
                progressed = True
        except Exception:
            pass

        guide_text = page.get_by_text(re.compile("作品信息|便捷填写作品关键信息|创作助手"))
        try:
            if await guide_text.count() and not progressed:
                guide_card = guide_text.first.locator("xpath=ancestor::div[1]")
                try:
                    await guide_card.click(position={"x": 250, "y": 110}, timeout=1000, force=True)
                    await asyncio.sleep(0.8)
                    dismissed = True
                    progressed = True
                except Exception:
                    pass
            if await guide_text.count() and not progressed:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.8)
                dismissed = True
                progressed = True
        except Exception:
            pass

        if not progressed:
            break

    return dismissed


async def _publish_single(
    draft: PublishDraft,
    account_file: Path,
    browser_name: str,
    headless: bool,
) -> None:
    from playwright.async_api import async_playwright

    launch_options: Dict[str, Any] = {"headless": headless}
    channel = None
    if browser_name == "chrome":
        channel = "chrome"
    elif browser_name == "msedge":
        channel = "msedge"

    async with async_playwright() as playwright:
        chromium = playwright.chromium
        if channel:
            browser = await chromium.launch(channel=channel, **launch_options)
        else:
            browser = await chromium.launch(**launch_options)
        context = await browser.new_context(storage_state=str(account_file))
        page = await context.new_page()
        await page.goto("https://cp.kuaishou.com/article/publish/video", timeout=30000)
        await page.wait_for_url("https://cp.kuaishou.com/article/publish/video")
        emit("[ks-publish] phase=open_publish_page")

        upload_button = page.get_by_role("button", name="上传视频")
        async with page.expect_file_chooser() as chooser_info:
            await upload_button.click()
        chooser = await chooser_info.value
        await chooser.set_files(draft.video_path)
        emit(f"[ks-publish] phase=video_selected path={draft.video_path}")

        await asyncio.sleep(1)
        known_button = page.get_by_role("button", name="我知道了")
        if await known_button.count():
            await known_button.click()
        emit("[ks-publish] phase=wait_upload_success")
        await _wait_for_upload_success(page)
        emit("[ks-publish] phase=upload_success")

        dismissed = await _dismiss_onboarding_popup(page)
        emit(f"[ks-publish] phase=dismiss_popup success={'yes' if dismissed else 'no'}")

        title_filled = await _fill_title(page, draft.title)
        emit(f"[ks-publish] phase=fill_title success={'yes' if title_filled else 'no'} title={draft.title}")

        if draft.cover_path:
            try:
                await _maybe_upload_cover(page, draft.cover_path)
                emit(f"[ks-publish] phase=cover_attempt path={draft.cover_path}")
            except Exception as exc:
                emit(f"[ks-publish] phase=cover_skip error={exc}")

        for _ in range(240):
            await _dismiss_onboarding_popup(page)
            clicked = await _click_publish(page)
            if clicked:
                emit("[ks-publish] phase=publish_clicked")
            try:
                await page.wait_for_url(
                    "https://cp.kuaishou.com/article/manage/video?status=2&from=publish",
                    timeout=1500,
                )
                await context.storage_state(path=str(account_file))
                await context.close()
                await browser.close()
                return
            except Exception:
                await asyncio.sleep(1)

        screenshot_path = await _save_debug_screenshot(page, "publish_timeout")
        await context.close()
        await browser.close()
        if screenshot_path:
            raise TimeoutError(f"publish did not complete in time; screenshot={screenshot_path}")
        raise TimeoutError("publish did not complete in time")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    config = ConfigLoader(args.config)
    base_path = Path(config.get("path") or "./Downloaded")
    manifest_path = Path(args.manifest) if args.manifest else _build_manifest_path(base_path)
    account_file = _resolve_account_file(args.account_file)

    items = collect_items_from_manifest(manifest_path, base_path)
    items = [item for item in items if item.media_type == "video" and _pick_video(item)]
    if args.aweme_ids:
        selected_ids = {str(value).strip() for value in args.aweme_ids if str(value).strip()}
        items = [item for item in items if item.aweme_id in selected_ids]

    if not items:
        emit(f"[ks-publish] no video items matched in {manifest_path}")
        return 1

    if args.random and args.aweme_ids:
        emit("[ks-publish] --random cannot be combined with --aweme-id")
        return 2

    if args.random:
        random_pool = list(items)
        if args.publish and not args.include_published:
            random_pool = [
                item for item in random_pool if not _is_published(_draft_path_for_item(item))
            ]
        if not random_pool:
            emit("[ks-publish] no eligible items available for random selection")
            return 1
        selected_item = random.choice(random_pool)
        items = [selected_item]
        emit(f"[ks-publish] random_pick aweme_id={selected_item.aweme_id}")

    if args.list:
        for item in items:
            draft = _build_draft(item)
            draft_path = _write_draft_file(item, draft)
            published = _is_published(draft_path)
            emit(
                f"[ks-publish] aweme_id={item.aweme_id} published={'yes' if published else 'no'} "
                f"title={draft.title} draft={draft_path}"
            )
        return 0

    if args.publish and not account_file.exists():
        emit(f"[ks-publish] account_file_missing={account_file}")
        emit("[ks-publish] run: python -m tools.ks_login")
        return 2

    processed = 0
    drafted = 0
    published_count = 0
    skipped = 0
    for item in items:
        if args.limit > 0 and processed >= args.limit:
            break
        processed += 1

        draft = _build_draft(item)
        if not draft.video_path:
            emit(f"[ks-publish] aweme_id={item.aweme_id} skip=no_video")
            continue
        draft_path = _write_draft_file(item, draft)
        drafted += 1
        emit(f"[ks-publish] aweme_id={item.aweme_id} draft={draft_path}")

        if not args.publish:
            continue

        if not args.include_published and _is_published(draft_path):
            skipped += 1
            emit(f"[ks-publish] aweme_id={item.aweme_id} skip=already_published")
            continue

        try:
            asyncio.run(
                _publish_single(
                    draft=draft,
                    account_file=account_file,
                    browser_name=args.browser,
                    headless=args.headless,
                )
            )
            _write_publish_state(
                draft_path,
                aweme_id=item.aweme_id,
                published=True,
                status="published",
                account_file=account_file,
            )
            published_count += 1
            emit(f"[ks-publish] aweme_id={item.aweme_id} published=true")
        except Exception as exc:
            _write_publish_state(
                draft_path,
                aweme_id=item.aweme_id,
                published=False,
                status="failed",
                account_file=account_file,
                error=str(exc),
            )
            emit(f"[ks-publish] aweme_id={item.aweme_id} publish_failed error={exc}")
            return 3

    if args.publish:
        emit(f"[ks-publish] done drafted={drafted} published={published_count} skipped={skipped}")
    else:
        emit(f"[ks-publish] done drafted={drafted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
