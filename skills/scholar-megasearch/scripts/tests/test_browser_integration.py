"""Opt-in local integration test for the real Playwright acquisition path."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import sys
import threading
import unittest


_here = os.path.dirname(__file__)
_scripts = os.path.abspath(os.path.join(_here, ".."))
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from browser_acquire import BrowserAcquirer  # noqa: E402


class _PublisherFixture(BaseHTTPRequestHandler):
    pdf_requests = 0

    def do_GET(self):
        if self.path == "/article":
            body = (
                b"<html><head><meta name='citation_pdf_url' content='/paper.pdf'>"
                b"</head><body>Institutionally entitled article</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", "institution=granted; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/paper.pdf":
            type(self).pdf_requests += 1
            if "institution=granted" not in self.headers.get("Cookie", ""):
                self.send_response(403)
                self.end_headers()
                return
            body = b"%PDF-1.7\n% local entitled fixture\n%%EOF\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_):
        return


@unittest.skipUnless(
    os.environ.get("SCHOLAR_BROWSER_INTEGRATION") == "1",
    "set SCHOLAR_BROWSER_INTEGRATION=1 to launch a real browser",
)
class BrowserIntegrationTest(unittest.TestCase):
    def test_temporary_browser_extracts_and_downloads_pdf(self):
        _PublisherFixture.pdf_requests = 0
        server = ThreadingHTTPServer(("127.0.0.1", 0), _PublisherFixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        acquirer = BrowserAcquirer(mode="headless", timeout_seconds=15)
        try:
            host, port = server.server_address
            result = acquirer.acquire(None, landing_url=f"http://{host}:{port}/article")
        finally:
            acquirer.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.status, "ok", result.detail)
        self.assertTrue(result.data.startswith(b"%PDF-"))
        self.assertEqual(result.candidate_count, 1)
        self.assertIn(result.backend, ("chrome", "msedge", "chromium"))
        self.assertEqual(_PublisherFixture.pdf_requests, 1)


if __name__ == "__main__":
    unittest.main()
