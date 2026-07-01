import importlib.util, json, os
from unittest import mock

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "kisti_client", os.path.join(_here, "..", "kisti_client.py"))
kc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(kc)

FIX = os.path.join(_here, "fixtures")


def test_aes_encrypt_is_url_safe_and_nonempty():
    enc = kc._aes_encrypt('{"datetime":"20260630170000","mac_address":"AA-BB"}',
                          "01234567890123456789012345678901")
    assert enc and "/" not in enc and "+" not in enc


def test_get_access_token_parses_response():
    tok = json.load(open(os.path.join(FIX, "kisti_token_sample.json"), encoding="utf-8"))
    tok["access_token"] = "ACCESS123"
    resp = mock.Mock(); resp.status_code = 200; resp.text = json.dumps(tok)
    with mock.patch.object(kc.requests, "get", return_value=resp) as g, \
         mock.patch.dict(os.environ, {"KISTI_CLIENT_ID": "cid",
                                      "KISTI_AUTH_KEY": "01234567890123456789012345678901",
                                      "KISTI_MAC": "AA-BB-CC"}):
        kc._TOKEN_CACHE.clear()
        assert kc.get_access_token() == "ACCESS123"
        url = g.call_args[0][0]
        assert "tokenrequest.do" in url and "client_id=cid" in url and "accounts=" in url


def test_get_access_token_requires_env():
    with mock.patch.dict(os.environ, {}, clear=True):
        kc._TOKEN_CACHE.clear()
        try:
            kc.get_access_token(); assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "KISTI_" in str(e)


def test_aes_encrypt_matches_official_sample():
    import importlib.util
    vpath = os.path.join(_here, "..", "..", "references",
                         "_vendor_kisti_token_sample", "AES256Util.py")
    vs = importlib.util.spec_from_file_location("aes256util", vpath)
    vmod = importlib.util.module_from_spec(vs); vs.loader.exec_module(vmod)
    plain = '{"datetime":"20260630170000","mac_address":"AA-BB"}'
    key = "01234567890123456789012345678901"
    expected = vmod.AESTestClass(plain, key).encrypt()
    assert kc._aes_encrypt(plain, key) == expected


def test_token_cache_reuses_then_force_refetches():
    resp = mock.Mock(); resp.status_code = 200
    resp.text = json.dumps({"access_token": "T1"})
    with mock.patch.object(kc.requests, "get", return_value=resp) as g, \
         mock.patch.dict(os.environ, {"KISTI_CLIENT_ID": "cid",
                                      "KISTI_AUTH_KEY": "01234567890123456789012345678901",
                                      "KISTI_MAC": "AA-BB-CC"}):
        kc._TOKEN_CACHE.clear()
        assert kc.get_access_token() == "T1"
        assert kc.get_access_token() == "T1"
        assert g.call_count == 1            # second call served from cache
        kc.get_access_token(force=True)
        assert g.call_count == 2            # force bypasses cache


_ALLOWED = {"title", "authors", "year", "venue", "doi", "arxiv_id", "pdf_url",
            "url", "citations", "abstract", "source", "query"}


def _read_fix(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def test_parse_arti_fixture():
    recs = kc._parse_records(_read_fix("kisti_arti_sample.xml"), "kisti-arti", "표면유속", "ARTI")
    assert len(recs) == 5
    r = recs[0]
    assert r["title"] == "표면유속을 이용한 평균유속 추정방법의 개발"
    assert "노영신" in r["authors"] and len(r["authors"]) == 3   # ';'-split, no trailing empty
    assert r["year"] == 2005
    assert r["doi"].endswith("10.3741/jkwra.2005.38.11.917")
    assert "Journal of Korea Water" in r["venue"]
    assert r["abstract"] and r["url"].startswith("http")
    assert r["source"] == "kisti-arti" and r["query"] == "표면유속"
    assert set(r) <= _ALLOWED                                    # no schema leakage


def test_parse_report_fixture():
    recs = kc._parse_records(_read_fix("kisti_report_sample.xml"), "kisti-report", "표면유속", "REPORT")
    assert len(recs) == 5
    r = recs[0]
    assert r["title"].startswith("임계열유속")
    assert "김무환" in r["authors"]                              # Author
    assert "김준원" in r["authors"]                              # Contributors merged in
    assert r["year"] == 2012
    assert r["venue"] == "포항공과대학교 산학협력단"
    assert "doi" not in r                                        # reports have no DOI
    assert set(r) <= _ALLOWED


def test_parse_patent_fixture():
    recs = kc._parse_records(_read_fix("kisti_patent_sample.xml"), "kisti-patent", "표면유속", "PATENT")
    assert len(recs) == 5
    r = recs[0]
    assert r["title"] == "전자파 표면 유속계"
    assert "한국수자원공사" in r["authors"]                      # Applicants -> authors
    assert r["year"] == 1996                                    # from ApplDate 19960201
    assert r["venue"] == "특허"
    assert set(r) <= _ALLOWED


def test_parse_rejects_non_200_status():
    bad = ('<?xml version="1.0" encoding="UTF-8"?><MetaData><resultSummary>'
           '<statusCode>401</statusCode></resultSummary><recordList>'
           '<record><item metaCode="Title">x</item></record></recordList></MetaData>')
    assert kc._parse_records(bad, "kisti-arti", "q", "ARTI") == []


def test_search_arti_uses_token_target_and_endpoint(monkeypatch):
    resp = mock.Mock(); resp.status_code = 200; resp.text = _read_fix("kisti_arti_sample.xml")
    monkeypatch.setattr(kc, "get_access_token", lambda force=False: "TOK")
    with mock.patch.object(kc.requests, "get", return_value=resp) as g, \
         mock.patch.dict(os.environ, {"KISTI_CLIENT_ID": "cid"}):
        out = kc.search_arti("표면유속", 5)
        assert len(out) == 5 and out[0]["source"] == "kisti-arti"
        url = g.call_args[0][0]
        assert "openapicall.do" in url and "target=ARTI" in url and "token=TOK" in url


def test_search_local_dispatch_has_kisti():
    sp = importlib.util.spec_from_file_location(
        "search_local", os.path.join(_here, "..", "search_local.py"))
    sl = importlib.util.module_from_spec(sp); sp.loader.exec_module(sl)
    assert "kisti" in sl.DISPATCH


def test_load_env_reads_dotenv_and_shell_wins(tmp_path):
    if importlib.util.find_spec("dotenv") is None:
        import pytest; pytest.skip("python-dotenv not installed")
    envf = tmp_path / ".env"
    envf.write_text("KISTI_CLIENT_ID=fromdotenv\nKISTI_MAC=DD-EE-FF\n", encoding="utf-8")
    for k in ("KISTI_CLIENT_ID", "KISTI_MAC"):
        os.environ.pop(k, None)
    try:
        # .env populates missing vars
        assert kc.load_env(str(envf)) is True
        assert os.environ["KISTI_CLIENT_ID"] == "fromdotenv"
        # existing shell env always wins (override=False)
        os.environ["KISTI_CLIENT_ID"] = "fromshell"
        kc.load_env(str(envf))
        assert os.environ["KISTI_CLIENT_ID"] == "fromshell"
    finally:
        for k in ("KISTI_CLIENT_ID", "KISTI_MAC"):
            os.environ.pop(k, None)
