import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        for ctx in browser.contexts:
            for page in ctx.pages:
                if "chatgpt.com" in page.url:
                    print("=== CHATGPT TAB INFO ===")
                    print("URL:", page.url)
                    print("Title:", await page.title())
                    
                    stats = await page.evaluate("""() => {
                        const msgs = document.querySelectorAll('[data-message-author-role]');
                        const totalText = document.body.innerText.length;
                        const toolCalls = document.querySelectorAll('[data-testid*="tool"], [class*="tool"]');
                        const codeBlocks = document.querySelectorAll('pre, code');
                        return {
                            msgCount: msgs.length,
                            bodyTextLength: totalText,
                            toolCallsCount: toolCalls.length,
                            codeBlocksCount: codeBlocks.length
                        };
                    }""")
                    print("Stats:", stats)

asyncio.run(inspect())
