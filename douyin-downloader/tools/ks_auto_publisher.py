import argparse
import random
import sys
import time
from datetime import datetime, timedelta
from typing import Sequence

from tools import ks_publish


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto publish random items to Kuaishou in a loop.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yml",
        help="Config file path (default: config.yml).",
    )
    parser.add_argument(
        "--account-file",
        default="../matrix/ks_uploader/account/default_account.json",
        help="Kuaishou Playwright storage-state JSON path.",
    )
    parser.add_argument(
        "--min-hours",
        type=float,
        default=3.0,
        help="Minimum hours to wait between publishes (default: 3).",
    )
    parser.add_argument(
        "--max-hours",
        type=float,
        default=5.0,
        help="Maximum hours to wait between publishes (default: 5).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Publish only once and exit.",
    )
    parser.add_argument(
        "--retry-minutes",
        type=float,
        default=3.0,
        help="Retry wait minutes after a failed publish (default: 3).",
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


def _normalize_hours(min_hours: float, max_hours: float) -> tuple[float, float]:
    if min_hours <= 0 or max_hours <= 0:
        raise ValueError("min-hours and max-hours must be positive")
    if min_hours > max_hours:
        min_hours, max_hours = max_hours, min_hours
    return min_hours, max_hours


def _run_once(config_path: str, account_file: str, browser: str, headless: bool) -> int:
    args = [
        "-c",
        config_path,
        "--random",
        "--publish",
        "--account-file",
        account_file,
        "--browser",
        browser,
    ]
    if headless:
        args.append("--headless")
    return ks_publish.main(args)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or [])
    min_hours, max_hours = _normalize_hours(args.min_hours, args.max_hours)
    random.seed()
    run_count = 0
    while True:
        run_count += 1
        started_at = datetime.now()
        print(f"[ks-auto-publish] run={run_count} start={started_at:%Y-%m-%d %H:%M:%S}")
        try:
            exit_code = _run_once(args.config, args.account_file, args.browser, args.headless)
        except Exception as exc:
            exit_code = 2
            print(f"[ks-auto-publish] run={run_count} error={exc}")
        finished_at = datetime.now()
        print(
            f"[ks-auto-publish] run={run_count} end={finished_at:%Y-%m-%d %H:%M:%S} "
            f"exit_code={exit_code}"
        )
        if args.once:
            return exit_code
        if exit_code != 0:
            wait_seconds = max(1, int(args.retry_minutes * 60))
        else:
            wait_hours = random.uniform(min_hours, max_hours)
            wait_seconds = max(1, int(wait_hours * 3600))
        next_run = datetime.now() + timedelta(seconds=wait_seconds)
        print(
            f"[ks-auto-publish] next_run={next_run:%Y-%m-%d %H:%M:%S} "
            f"sleep_seconds={wait_seconds}"
        )
        time.sleep(wait_seconds)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
