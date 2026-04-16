import asyncio
from playwright.async_api import async_playwright

async def login_and_save_cookie():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Please scan the QR code to login to Kuaishou.")
        await page.goto("https://passport.kuaishou.com/pc/account/login/?sid=kuaishou.web.cp.api&callback=https%3A%2F%2Fcp.kuaishou.com%2Frest%2Finfra%2Fsts%3FfollowUrl%3Dhttps%253A%252F%252Fcp.kuaishou.com%252Fprofile%26setRootDomain%3Dtrue")
        
        # Switch to QR code login if not already
        try:
            await page.locator('div.platform-switch').click()
        except:
            pass
            
        print("Waiting for login to complete... (URL contains 'cp.kuaishou.com/profile')")
        
        while True:
            await asyncio.sleep(2)
            if 'cp.kuaishou.com/profile' in page.url:
                print("Login successful!")
                break
                
        # Wait a bit for cookies to settle
        await asyncio.sleep(3)
        
        # Save storage state
        await context.storage_state(path="ks_account.json")
        print("Cookies saved to ks_account.json")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(login_and_save_cookie())
