#!/usr/bin/env python3
"""
wechat_republish_playwright.py
==============================

This script provides a Playwright‑based solution to republish a WeChat
public article to your own WeChat Official Account.  Compared to the
Selenium version, Playwright offers smoother handling of modern web
interfaces and better resilience against unexpected page changes.

Overview
--------

1. Fetch the article from a public link using `requests` and
   parse its title and HTML body via `BeautifulSoup`.
2. Launch a browser using Playwright.  By default it launches a
   bundled Chromium binary; you can specify an explicit executable
   path if you prefer to use your own Chrome installation.
3. Navigate to the WeChat Official Account login page and wait for
   you to scan the QR code.  The script detects successful login
   automatically.
4. Navigate to the material management page, click the “新建图文”
   button, and open the editor.
5. Fill in the article title, switch to the content iframe, and
   inject the article's HTML body.  Then save the draft.

Prerequisites
-------------

* Python 3.8 or later
* Playwright installed (`pip install playwright`) and browsers
  downloaded (`playwright install`).
* BeautifulSoup and requests libraries (`pip install beautifulsoup4 requests`).

Usage
-----

::

   python3 wechat_republish_playwright.py --url <article_url>

Optionally specify a custom Chrome/Chromium executable:

::

   python3 wechat_republish_playwright.py --url <article_url> \
       --browser-path /usr/bin/google-chrome-stable

The script will open a browser window.  Scan the QR code to log into
your WeChat Official Account.  Once logged in, the script will
automatically create a draft of the article.  Check the results and
publish manually from the backend.

Limitations
-----------

* Changes in the WeChat backend UI may require you to adjust
  selectors.  The script includes helpful error messages if it
  fails to locate expected elements.
* Images referenced in the article remain external URLs.  When
  pasted into the WeChat editor, WeChat typically downloads these
  images automatically.  Verify in the draft and adjust as needed.
* The script saves the article as a draft, not a published post.

"""

import argparse
import random
import sys
import time
from dataclasses import dataclass
from typing import Optional

try:
    from bs4 import BeautifulSoup  # type: ignore
    import requests  # type: ignore
    from playwright.sync_api import sync_playwright  # type: ignore
except ImportError:
    print(
        "Required packages are missing. Install them via:\n"
        "pip install beautifulsoup4 requests playwright\n"
        "and then run 'playwright install' to download browsers.",
        file=sys.stderr,
    )
    sys.exit(1)


@dataclass
class Article:
    title: str
    body_html: str


def fetch_article(url: str) -> Article:
    """Download and parse a WeChat article from the given URL.

    Parameters
    ----------
    url: str
        The public article URL.

    Returns
    -------
    Article
        A dataclass containing the article's title and HTML body.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("h1", id="activity-name")
    if not title_tag:
        # Fallback to meta tags commonly used by WeChat
        title_tag = soup.find("meta", property="og:title")
        if title_tag:
            title = title_tag.get("content", "").strip()
        else:
            # Last ditch effort: document title
            title = soup.title.string.strip() if soup.title else "Untitled Article"
    else:
        title = title_tag.get_text(strip=True)
    
    if not title:
        raise RuntimeError("Could not locate article title. Is this a valid WeChat article?")
    content_div = soup.find("div", id="js_content")
    if not content_div:
        raise RuntimeError("Could not locate article content. The page format may have changed.")
    body_html = content_div.decode_contents()
    return Article(title=title, body_html=body_html)


def find_editor_frame(page):
    for frame in page.frames:
        try:
            if frame.query_selector(".ProseMirror, #js_content, .edui-editor-body, #js_editor"):
                return frame
        except Exception:
            continue
    return None


def inject_body_html(page, html):
    target_frame = find_editor_frame(page) or page.main_frame
    try:
        success = target_frame.evaluate(
            "(html) => {"
            "  const el = document.querySelector('.ProseMirror') || "
            "    document.querySelector('#js_content') || "
            "    document.querySelector('.edui-editor-body') || "
            "    document.querySelector('#js_editor');"
            "  if (!el) return false;"
            "  el.focus();"
            "  el.innerHTML = '';"
            "  el.insertAdjacentHTML('afterbegin', html);"
            "  const inputEvent = new InputEvent('input', { bubbles: true });"
            "  el.dispatchEvent(inputEvent);"
            "  ['change', 'blur', 'keyup', 'paste'].forEach((evName) => {"
            "    el.dispatchEvent(new Event(evName, { bubbles: true }));"
            "  });"
            "  return true;"
            "}",
            html,
        )
        return bool(success)
    except Exception:
        return False


def select_cover_image(page):
    trigger_selectors = [
        "text=拖拽或选择封面",
        "text=选择封面",
        "button:has-text('选择封面')",
        ".js_cover",
        ".weui-desktop-publish__cover",
        ".cover",
    ]
    trigger = None
    for selector in trigger_selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=2000):
                trigger = locator
                break
        except Exception:
            continue
    if not trigger:
        return False
    try:
        trigger.click()
    except Exception:
        return False

    menu_item_selectors = [
        "text=从正文选择",
        "text=从正文中选择",
        "li:has-text('从正文选择')",
        "li:has-text('从正文中选择')",
    ]
    for selector in menu_item_selectors:
        try:
            item = page.locator(selector).first
            if item.is_visible(timeout=2000):
                item.click()
                break
        except Exception:
            continue

    dialog = page.locator(
        ".weui-desktop-dialog, .weui-dialog, .weui-desktop-modal, .weui-desktop-popup"
    ).first
    try:
        dialog.wait_for(state="visible", timeout=5000)
    except Exception:
        pass

    cover_candidates = [
        ".js_cover_list img",
        ".cover_list img",
        ".weui-desktop-publish__cover__item img",
        ".weui-desktop-publish__cover img",
        ".weui-desktop-dialog img",
        ".weui-dialog img",
    ]
    selected = False
    for selector in cover_candidates:
        try:
            img_list = dialog.locator(selector)
            count = img_list.count()
            if count > 0:
                index = random.randint(0, count - 1)
                candidate = img_list.nth(index)
                if candidate.is_visible(timeout=2000):
                    candidate.scroll_into_view_if_needed()
                    candidate.click()
                    selected = True
                    break
        except Exception:
            continue
    if not selected:
        for selector in cover_candidates:
            try:
                img_list = page.locator(selector)
                count = img_list.count()
                if count > 0:
                    index = random.randint(0, count - 1)
                    candidate = img_list.nth(index)
                    if candidate.is_visible(timeout=2000):
                        candidate.scroll_into_view_if_needed()
                        candidate.click()
                        selected = True
                        break
            except Exception:
                continue
    if not selected:
        return False

    next_selectors = [
        "button:has-text('下一步')",
        "a:has-text('下一步')",
    ]
    for selector in next_selectors:
        try:
            btn = dialog.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                break
        except Exception:
            continue

    confirm_selectors = [
        "button:has-text('确定')",
        "button:has-text('完成')",
        "button:has-text('确定使用')",
        "button:has-text('使用')",
    ]
    for selector in confirm_selectors:
        try:
            btn = dialog.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                return True
        except Exception:
            continue
    for selector in confirm_selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                return True
        except Exception:
            continue
    return True


def republish_article(
    article: Article,
    browser_path: Optional[str] = None,
    timeout: int = 120,
    user_data_dir: str = "./wechat_session",
) -> None:
    """Automate the creation of a draft in WeChat Official Account using Playwright.

    Parameters
    ----------
    article: Article
        The article to republish.
    browser_path: Optional[str], optional
        A specific path to a Chrome/Chromium executable to use.  If None,
        Playwright's default bundled browser is used.
    timeout: int, optional
        Maximum time in seconds to wait for login.
    user_data_dir: str, optional
        Directory to store the browser session/cookies.
    """
    with sync_playwright() as p:
        # Determine which browser to launch.
        launch_kwargs = {
            "headless": False,
            "args": ["--start-maximized"],
        }
        if browser_path:
            launch_kwargs["executable_path"] = browser_path

        # Use persistent context to save login data (cookies, storage, etc.)
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **launch_kwargs
        )
        # Persistent context already creates the first page
        page = context.pages[0] if context.pages else context.new_page()

        # Step 1: Open WeChat login page
        page.goto("https://mp.weixin.qq.com/", timeout=60000)
        print("Please scan the QR code to log into your WeChat Official Account.")

        # Step 2: Wait for login to complete.
        import urllib.parse as urlparse
        start_time = time.time()
        token = ""
        print("Waiting for login detection...")

        while True:
            if time.time() - start_time > timeout:
                context.close()
                raise TimeoutError(
                    "Login not detected within the allotted time. Restart the script and try again."
                )
            try:
                current_url = page.url
                # Method 1: Check for token in URL
                if "token=" in current_url:
                    parsed = urlparse.urlparse(current_url)
                    qs = urlparse.parse_qs(parsed.query)
                    if "token" in qs:
                        token = qs["token"][0]
                        print(f"Detected Login via URL. Token: {token}")
                        break
                
                # Method 2: Check for dashboard elements if URL hasn't updated yet
                if page.get_by_text("首页").is_visible() or page.get_by_text("内容管理").is_visible():
                    # Try to extract from URL again as it might have just changed
                    parsed = urlparse.urlparse(page.url)
                    qs = urlparse.parse_qs(parsed.query)
                    token = qs.get("token", [""])[0]
                    if token:
                        print(f"Detected Login via Page Content. Token: {token}")
                        break
            except Exception:
                pass
            time.sleep(1)

        print("Login successful. Navigating to drafting area…")

        # Step 3: Navigate to the draft list page
        draft_url = (
            f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_list"
            f"&action=list&type=10&begin=0&count=5&token={token}&lang=zh_CN"
        )
        page.goto(draft_url, timeout=60000)

        # Step 4: Click the “新建图文” or "写文章" button
        # We try multiple common selectors for the creation button
        try:
            # Try specific "New Draft" text or its common containers
            page.wait_for_load_state("networkidle")
            create_btn = None
            for selector in ["text=新建图文", "text=写文章", "button:has-text('新建')"]:
                btn = page.query_selector(selector)
            selectors = [
                 "text=草稿箱", "text=新建图文", "text=写文章", ".weui-desktop-btn_primary"
            ]
            
            # If we are on the home page, we need to go to draft list first or click the big icon
            if "home" in page.url:
                print("On home page, looking for '文章' icon...")
                try:
                    create_btn = page.get_by_text("文章", exact=True)
                    if create_btn.is_visible():
                        create_btn.click()
                except:
                    pass
            
            if not create_btn:
                # Try navigating directly to the drafting area if we're stuck
                print(f"Navigating directly to draft list...")
                page.goto(f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_list&action=list&type=10&begin=0&count=5&token={token}&lang=zh_CN")
                page.wait_for_load_state("networkidle")
                page.get_by_role("button", name="新建图文").click()
        except Exception as e:
            print(f"Navigation/Click error: {e}. Trying fallback navigation...")
            page.goto(f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=10&token={token}&lang=zh_CN")

        # Step 5: Switch to the newly opened editor tab
        print("Waiting for editor tab to open...")
        editor_page = None
        # Poll for any page in the context that matches the editor URL
        for _ in range(15):
            for p in context.pages:
                try:
                    p_url = p.url
                    if "appmsg_edit" in p_url or "action=edit" in p_url:
                        editor_page = p
                        break
                except:
                    continue
            if editor_page:
                break
            time.sleep(1)
        
        if not editor_page:
            # Last ditch effort: if only one page exists and it's on a known editor URL pattern
            if len(context.pages) == 1:
                p = context.pages[0]
                if "appmsg" in p.url:
                    editor_page = p
        
        if not editor_page:
            print("❌ Error: Could not identify the WeChat editor page.")
            print("Current URLs in browser:")
            for i, p in enumerate(context.pages):
                print(f"  {i}: {p.url}")
            return

        editor_page.bring_to_front()
        print(f"Editor page identified: {editor_page.url}")
        print("Waiting for editor to stabilize...")
        time.sleep(5)
        editor_page.wait_for_load_state("networkidle")
        print("Stabilized. Filling content...")

        # Step 6: Fill in title
        try:
            print("Filling title...")
            title_field = editor_page.locator("#title, #js_title, .weui-desktop-textarea, [placeholder='请输入标题']").first
            if title_field.is_visible(timeout=5000):
                title_field.focus()
                title_field.fill(article.title)
                title_field.press("Tab")
                print(f"Title set: {article.title}")
        except Exception as e:
            print(f"Title Error: {e}")

        try:
            author_field = editor_page.locator("#author, #js_author, [placeholder='请输入作者']").first
            if author_field.is_visible(timeout=3000):
                author_field.focus()
                author_field.fill("观戏道人")
                author_field.press("Tab")
                print("Author set: 观戏道人")
        except:
            pass

        try:
            print("Locating BODY content area...")
            if inject_body_html(editor_page, article.body_html):
                print("✅ Body content injected successfully.")
            else:
                print("⚠️ Warning: Could not inject body content.")
        except Exception as e:
            print(f"Body Injection Error: {e}")

        # Step 7.5: Fill in Summary (Digest)
        # The user provided: <textarea id="js_description" ... name="digest" ...>
        try:
            print("Locating SUMMARY area (#js_description)...")
            summary_field = editor_page.locator("#js_description, [name='digest']").first
            if summary_field.is_visible(timeout=3000):
                digest_text = article.title[:120]
                summary_field.focus()
                summary_field.fill(digest_text)
                print(f"✅ Summary set: {digest_text[:30]}...")
        except:
            pass

        try:
            print("Selecting cover image...")
            if select_cover_image(editor_page):
                print("✅ Cover selected.")
            else:
                print("⚠️ Warning: Cover not selected.")
        except Exception as e:
            print(f"Cover Error: {e}")

        # Step 8: Save draft
        try:
            print("Attempting to save draft...")
            # Expand save button selectors
            save_button_selectors = [
                "button:has-text('保存'):not(:has-text('继续'))",
                "#js_save_temp",
                "#js_save",
                ".js_save_draft",
                "text=保存并预览"
            ]
            
            # Scroll to make buttons visible
            editor_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            saved = False
            for selector in save_button_selectors:
                try:
                    btn = editor_page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        btn.click()
                        saved = True
                        print(f"Clicked save button via: {selector}")
                        break
                except:
                    continue
            
            if saved:
                print("Save clicked. Waiting for confirmation...")
                try:
                    editor_page.wait_for_selector("text=已保存", timeout=10000)
                    print("\n✅ Article draft saved successfully!")
                except:
                    print("Save requested. Please verify '已保存' toast appears on screen.")
            else:
                print("Could not find a visible 'Save' button. Please save manually.")

            print("\n⚠️ Reminder: You MUST select a cover image (封面) before you can publish.")
        except Exception as e:
            print(f"Save Error: {e}")

        # Final Step: Keep context alive for 3 minutes for user review/publishing
        print(f"\nAutomation complete. The browser will stay open for 3 minutes (180s).")
        print("Please review the draft, select a cover, and click PUBLISH if desired.")
        
        time.sleep(180)


def main() -> None:
    parser = argparse.ArgumentParser(description="Republish a WeChat article via Playwright automation.")
    parser.add_argument("--url", required=True, help="URL of the WeChat article to republish.")
    parser.add_argument(
        "--browser-path",
        default=None,
        help=(
            "Optional path to a Chrome/Chromium executable.  If omitted, "
            "Playwright's bundled browser is used.  Ensure you have run 'playwright install'."
        ),
    )
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=120,
        help="Number of seconds to wait for QR code login before timing out (default: 120).",
    )
    args = parser.parse_args()

    article = fetch_article(args.url)
    print(f"Fetched article: {article.title}")
    republish_article(article, browser_path=args.browser_path, timeout=args.login_timeout)


if __name__ == "__main__":
    main()
