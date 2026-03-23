from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, Sequence


def emit(message: str) -> None:
    print(message, flush=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Login to Kuaishou creator backend and save Playwright storage state.",
    )
    parser.add_argument(
        "--account-file",
        default="../matrix/ks_uploader/account/default_account.json",
        help="Output storage-state JSON path.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=float,
        default=5.0,
        help="Maximum minutes to wait for login completion.",
    )
    parser.add_argument(
        "--browser",
        default="chromium",
        choices=["chromium", "chrome", "msedge"],
        help="Browser channel to launch.",
    )
    return parser.parse_args(argv)


def _resolve_account_file(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path(__file__).resolve().parent / path).resolve()


async def _wait_for_login(page, timeout_ms: int) -> None:
    deadline = asyncio.get_running_loop().time() + max(1, timeout_ms) / 1000
    while True:
        current_url = page.url
        if "cp.kuaishou.com/profile" in current_url or "cp.kuaishou.com/article" in current_url:
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("login timed out before reaching Kuaishou creator center")
        await asyncio.sleep(1)


async def main_async(args: argparse.Namespace) -> int:
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:
        emit(f"[ks-login] missing_dependency={exc.name}")
        emit("[ks-login] install with: pip install playwright && playwright install chromium")
        return 2

    account_file = _resolve_account_file(args.account_file)
    account_file.parent.mkdir(parents=True, exist_ok=True)
    timeout_ms = int(max(1, args.timeout_minutes) * 60 * 1000)

    launch_options = {"headless": False}
    channel = None
    if args.browser == "chrome":
        channel = "chrome"
    elif args.browser == "msedge":
        channel = "msedge"

    emit(f"[ks-login] account_file={account_file}")
    emit("[ks-login] browser opened, please finish QR login in the window")

    async with async_playwright() as playwright:
        browser_launcher = playwright.chromium
        if channel:
            browser = await browser_launcher.launch(channel=channel, **launch_options)
        else:
            browser = await browser_launcher.launch(**launch_options)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(
            "https://passport.kuaishou.com/pc/account/login/"
            "?sid=kuaishou.web.cp.api&callback=https%3A%2F%2Fcp.kuaishou.com%2Frest%2Finfra%2Fsts"
            "%3FfollowUrl%3Dhttps%253A%252F%252Fcp.kuaishou.com%252Fprofile%26setRootDomain%3Dtrue",
            timeout=30000,
        )

        try:
            switcher = page.locator("div.platform-switch")
            if await switcher.count():
                await switcher.click()
        except PlaywrightTimeoutError:
            pass
        except Exception:
            pass

        try:
            await _wait_for_login(page, timeout_ms)
        except TimeoutError as exc:
            emit(f"[ks-login] failed={exc}")
            await context.close()
            await browser.close()
            return 2

        profile_url = page.url
        await context.storage_state(path=str(account_file))
        cookies = await context.cookies()
        payload = {
            "account_file": str(account_file),
            "url": profile_url,
            "cookie_count": len(cookies),
        }
        emit(f"[ks-login] saved={json.dumps(payload, ensure_ascii=False)}")
        await context.close()
        await browser.close()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
