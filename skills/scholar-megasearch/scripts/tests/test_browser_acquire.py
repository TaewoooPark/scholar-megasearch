import importlib.util
import os
import sys


_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "browser_acquire", os.path.join(_here, "..", "browser_acquire.py"))
ba = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ba
_spec.loader.exec_module(ba)


def test_normalize_doi_accepts_common_forms():
    assert ba.normalize_doi("DOI: 10.1234/ABC") == "10.1234/ABC"
    assert ba.normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/ABC"
    assert ba.doi_url("10.1234/a b") == "https://doi.org/10.1234/a%20b"


def test_extract_pdf_candidates_ranks_metadata_and_deduplicates():
    html = """
    <html><head>
      <meta name="citation_pdf_url" content="/paper/main.pdf">
      <link rel="alternate" type="application/pdf" href="/paper/alternate.pdf">
    </head><body>
      <a href="/doi/pdf/10.1234/example?download=true">PDF</a>
      <a href="/paper/main.pdf#page=2">duplicate</a>
      <a href="javascript:alert(1)">unsafe</a>
    </body></html>
    """
    assert ba.extract_pdf_candidates(html, "https://publisher.example/article/1") == [
        "https://publisher.example/paper/main.pdf",
        "https://publisher.example/paper/alternate.pdf",
        "https://publisher.example/doi/pdf/10.1234/example?download=true",
    ]


def test_extract_pdf_candidates_reads_rendered_data_attributes():
    html = '<button data-pdf-url="https://cdn.example/file.pdf">Download</button>'
    assert ba.extract_pdf_candidates(html, "https://publisher.example/article") == [
        "https://cdn.example/file.pdf"
    ]


def test_pdf_validation_requires_magic_bytes():
    assert ba.is_pdf_bytes(b"%PDF-1.7\nexample")
    assert ba.is_pdf_bytes(b"  \n%PDF-1.4\nexample")
    assert not ba.is_pdf_bytes(b"<html>access denied</html>")


def test_failure_classification_is_specific_and_stable():
    assert ba.classify_failure("Verify you are human", "https://x", [403]) == "captcha"
    assert ba.classify_failure("", "https://x", [429]) == "rate_limited"
    assert ba.classify_failure("", "https://x/login", []) == "auth_required"
    assert ba.classify_failure("", "https://x", [403]) == "not_entitled"
    assert ba.classify_failure("Check access", "https://x", []) == "not_entitled"
    assert ba.classify_failure("", "https://x", [], saw_invalid_pdf=True) == "invalid_pdf"
    assert ba.classify_failure("ordinary article page", "https://x", []) == "failed"


def test_missing_identifier_does_not_start_browser():
    result = ba.BrowserAcquirer().acquire("")
    assert result.status == "no_doi"
    assert result.backend is None
