import threading
import unittest
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from desktop_py.core.browser_runtime import configure_playwright_environment, playwright_browsers_ready
from desktop_py.core.fetcher_page_strategy import resolve_frame_locator
from desktop_py.core.fetcher_support import business_iframe_selector, wait_for_iframe_ready
from desktop_py.core.session_persistence import analyze_storage_state, persist_storage_state

configure_playwright_environment()


@contextmanager
def _serve_directory(directory: Path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@unittest.skipUnless(playwright_browsers_ready(), "Playwright Chromium runtime not available")
class PlaywrightIntegrationTestCase(unittest.TestCase):
    def test_wait_for_iframe_ready_and_resolve_frame_locator_with_real_page(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "index.html").write_text(
                """
                <!doctype html>
                <html>
                  <head><meta charset="utf-8"></head>
                  <body>
                    <iframe id="js_iframe" src="/frame.html"></iframe>
                  </body>
                </html>
                """,
                encoding="utf-8",
            )
            (root / "frame.html").write_text(
                """
                <!doctype html>
                <html>
                  <head><meta charset="utf-8"></head>
                  <body>
                    <div>退款申请(0)</div>
                    <div>暂无内容</div>
                  </body>
                </html>
                """,
                encoding="utf-8",
            )

            from playwright.sync_api import sync_playwright

            configure_playwright_environment()
            with _serve_directory(root) as base_url, sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(f"{base_url}/index.html", wait_until="domcontentloaded")

                self.assertTrue(wait_for_iframe_ready(page, timeout_ms=5000))
                frame_locator = resolve_frame_locator(
                    page,
                    output_dir=root,
                    business_iframe_selector_fn=business_iframe_selector,
                    safe_page_content_fn=lambda current_page: current_page.content(),
                )
                body_text = frame_locator.locator("body").text_content(timeout=1500) or ""
                self.assertIn("退款申请(0)", body_text)

                context.close()
                browser.close()

    def test_persist_storage_state_and_analyze_with_real_browser_context(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "index.html").write_text(
                """
                <!doctype html>
                <html>
                  <head><meta charset="utf-8"></head>
                  <body>
                    <div>integration</div>
                    <script>
                      localStorage.setItem("session-key", "ready");
                      document.cookie = "wechat_session=1; path=/";
                    </script>
                  </body>
                </html>
                """,
                encoding="utf-8",
            )
            state_path = root / "storage.json"

            from playwright.sync_api import sync_playwright

            configure_playwright_environment()
            with _serve_directory(root) as base_url, sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(f"{base_url}/index.html", wait_until="domcontentloaded")

                persist_storage_state(context, str(state_path), page=page)
                report = analyze_storage_state(
                    str(state_path),
                    domain_keywords=("127.0.0.1", "localhost"),
                )

                self.assertTrue(report.exists)
                self.assertTrue(report.readable)
                self.assertTrue(report.has_reusable_state)
                self.assertGreaterEqual(report.cookies_count, 1)
                self.assertGreaterEqual(report.origins_count, 1)

                context.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
