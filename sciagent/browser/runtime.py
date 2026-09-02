import asyncio
import time
from typing import Optional

from playwright.async_api import async_playwright


class RateLimiter:
    def __init__(self, interval: float):
        self.interval = interval
        self.last_navigation = 0.0

    async def wait(self):
        elapsed = time.monotonic() - self.last_navigation
        remaining = self.interval - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self.last_navigation = time.monotonic()


class BrowserRuntime:
    def __init__(self, delay_seconds: float = 16.0, headless: bool = True):
        self.delay_seconds = delay_seconds
        self.headless = headless
        self.rate_limiter = RateLimiter(delay_seconds)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(viewport={"width": 1400, "height": 900})
        self.page = await self.context.new_page()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def goto(self, url: str):
        await self.rate_limiter.wait()
        response = await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        status = response.status if response else None
        if status in (403, 429):
            raise RuntimeError("arXiv blocked/throttled request with HTTP %s" % status)
        return response
