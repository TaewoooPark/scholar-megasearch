import importlib.util
import json
import os
import sys


_here = os.path.dirname(__file__)
_scripts = os.path.abspath(os.path.join(_here, ".."))
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
_spec = importlib.util.spec_from_file_location(
    "fetch_pdfs", os.path.join(_scripts, "fetch_pdfs.py"))
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)


class _FakeBrowser:
    calls = []

    def __init__(self, *, mode, timeout_seconds):
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.closed = False

    def acquire(self, doi, *, landing_url=None):
        self.__class__.calls.append((doi, landing_url))
        return fp.BrowserResult(
            status="ok",
            data=b"%PDF-1.7\nfake institutional paper",
            candidate_url="https://publisher.example/paper.pdf",
            landing_url="https://publisher.example/article",
            backend="chromium",
            headed=False,
            http_status=200,
            candidate_count=1,
        )

    def close(self):
        self.closed = True


def _run_main(monkeypatch, corpus_path, out_dir, *extra):
    monkeypatch.setattr(fp, "ROUTES", [("oa", lambda rec, email: (None, None))])
    monkeypatch.setattr(fp, "BrowserAcquirer", _FakeBrowser)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fetch_pdfs.py", str(corpus_path), "-o", str(out_dir),
            "--email", "test@example.com", *extra,
        ],
    )
    fp.main()


def test_browser_fallback_writes_verified_pdf_and_manifest(tmp_path, monkeypatch):
    _FakeBrowser.calls = []
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([{"rank": 1, "title": "Paper", "doi": "10.1/example"}]))
    out = tmp_path / "pdfs"

    _run_main(monkeypatch, corpus, out)

    rows = json.loads((out / "manifest.json").read_text())
    assert rows[0]["status"] == "ok"
    assert rows[0]["route"] == "institutional_browser"
    assert rows[0]["browser_backend"] == "chromium"
    assert (out / "01_paper.pdf").read_bytes().startswith(b"%PDF-")
    assert _FakeBrowser.calls == [("10.1/example", None)]


def test_retry_unresolved_keeps_success_and_retries_only_failure(tmp_path, monkeypatch):
    _FakeBrowser.calls = []
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([
        {"rank": 1, "title": "Already Here", "doi": "10.1/ok"},
        {"rank": 2, "title": "Retry Me", "doi": "10.1/retry"},
    ]))
    out = tmp_path / "pdfs"
    out.mkdir()
    existing_pdf = out / "01_already-here.pdf"
    existing_pdf.write_bytes(b"%PDF-1.4\nexisting")
    (out / "manifest.json").write_text(json.dumps([
        {"i": 1, "rank": 1, "title": "Already Here", "doi": "10.1/ok",
         "status": "ok", "route": "unpaywall", "file": str(existing_pdf)},
        {"i": 2, "rank": 2, "title": "Retry Me", "doi": "10.1/retry",
         "status": "not_entitled"},
    ]))

    _run_main(monkeypatch, corpus, out, "--retry-unresolved")

    rows = json.loads((out / "manifest.json").read_text())
    assert rows[0]["route"] == "unpaywall"
    assert rows[1]["previous_status"] == "not_entitled"
    assert rows[1]["status"] == "ok"
    assert _FakeBrowser.calls == [("10.1/retry", None)]


def test_no_browser_records_explicit_status(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([{"rank": 1, "title": "OA only", "doi": "10.1/x"}]))
    out = tmp_path / "pdfs"

    _run_main(monkeypatch, corpus, out, "--no-browser")

    row = json.loads((out / "manifest.json").read_text())[0]
    assert row["status"] == "browser_disabled"
    assert row["detail"] == "browser fallback disabled by --no-browser"


def test_mime_header_alone_is_not_accepted_as_pdf():
    assert not fp._is_pdf(b"<html>forbidden</html>", "application/pdf")


def test_retry_identity_prefers_doi_over_mutable_rank():
    assert fp._record_key({"rank": 1, "doi": "https://doi.org/10.1/ABC"}) == (
        "doi", "10.1/abc"
    )
    assert fp._record_key({"rank": 99, "doi": "doi:10.1/abc"}) == ("doi", "10.1/abc")
