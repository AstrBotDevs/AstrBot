"""Exercise the actual Vue card against the real stdio demo's recorded response.

Run the dashboard dev server, then run with a Python environment containing
AstrBot dependencies and playwright. Browser HTTP history/auth are mocked;
the MCP handshake, tool call, HTML resource and browser sandbox are real.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


async def demo_payload():
    """Collect the resource and tool response from the sample MCP server."""
    params = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "examples/mcp_apps/photo_picker.py")]
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            uri = tools.tools[0].meta["ui"]["resourceUri"]
            result = await session.call_tool("show_photo_picker", {})
            resource = await session.read_resource(uri)
            assert resource.contents[0].mimeType == "text/html;profile=mcp-app"
            return {
                "html": resource.contents[0].text,
                "arguments": {},
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }


def main():
    """Verify selection, review, rejection, lifecycle and sandbox isolation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--screenshot")
    args = parser.parse_args()
    payload = asyncio.run(demo_payload())
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.route(
                "**/api/v1/chat/sessions/session/messages/message/mcp-app/call",
                lambda route: route.fulfill(json={"status": "ok", "data": payload}),
            )
            page.goto(f"{args.url}/tests/fixtures/mcp-app.html")
            page.wait_for_load_state("networkidle")
            expect(
                page.get_by_role("button", name="Open interactive app")
            ).to_be_visible()
            page.get_by_role("button", name="Open interactive app").click()
            frame = page.frame_locator('iframe[title="Interactive tool"]')
            expect(
                frame.get_by_text("Sample illustrations", exact=False)
            ).to_be_visible()
            frame.get_by_role("checkbox", name="1 Forest").check()
            frame.get_by_role("checkbox", name="3 Ocean").check()
            frame.get_by_role("button", name="Use selection").click()
            expect(page.get_by_label("Message draft")).to_have_value("Existing draft")
            page.get_by_role("button", name="Dismiss", exact=True).click()
            expect(frame.get_by_role("status")).to_contain_text("dismissed")
            frame.get_by_role("checkbox", name="1 Forest").uncheck()
            frame.get_by_role("button", name="Use selection").click()
            page.get_by_role("button", name="Add to message", exact=True).click()
            expect(page.get_by_label("Message draft")).to_have_value(
                "Existing draft\n\nI selected illustrations 3. Please recommend how to use them for the cover."
            )
            child = page.frames[1]
            assert child.evaluate(
                "() => {try { parent.document.body; return false; } catch { return true; }}"
            )
            assert child.evaluate(
                "() => {try { localStorage.getItem('token'); return false; } catch { return true; }}"
            )
            assert child.evaluate(
                "async () => {try {await fetch('/api/v1/auth/me'); return false;} catch {return true;}}"
            )
            if args.screenshot:
                page.screenshot(path=args.screenshot, full_page=True)
            page.get_by_role("button", name="Close", exact=True).click()
            expect(page.locator("iframe")).to_have_count(0)
            page.get_by_role("button", name="Open interactive app").click()
            expect(page.frame_locator("iframe").get_by_role("checkbox")).to_have_count(
                3
            )
            print(
                json.dumps(
                    {
                        "browser": "passed",
                        "stdio_mcp": "passed",
                        "checks": [
                            "selection",
                            "explicit-review",
                            "decline-retry",
                            "preserve-draft",
                            "opaque-origin",
                            "storage-denied",
                            "fetch-denied",
                            "close-reopen",
                        ],
                    }
                )
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
