#!/usr/bin/env python3
"""One-shot helper to capture REAL ScienceON search responses as test fixtures.

Run ONCE with your KISTI credentials in the environment. It reuses the verified
token manager (kisti_client.get_access_token) and saves the raw XML for the
論文/보고서/특허 search targets so the Task 4 parser can be written against real data.

Usage (PowerShell, with creds set):
    $env:KISTI_CLIENT_ID="..."; $env:KISTI_AUTH_KEY="...(32 bytes)..."; $env:KISTI_MAC="..."
    $env:PYTHONUTF8=1
    python skills/scholar-megasearch/scripts/tests/_capture_kisti_fixtures.py

It prints the HTTP status + the first ~1800 chars of each response so we can read
the actual XML element names, and writes the raw bodies to fixtures/.

NOTE: the search endpoint/params below are a BEST ESTIMATE of the ScienceON call
format and may need adjustment per the official docs:
  논문:  https://scienceon.kisti.re.kr/apigateway/api/way/service/arti/serviceArtiSearchApi.do
  특허:  https://scienceon.kisti.re.kr/apigateway/api/way/service/patent/servicePatentSearchApi.do
  API Test: https://scienceon.kisti.re.kr/por/api/apiTest/arti/
If a call returns an error/empty body, open the API Test page, run a sample query,
and copy the exact endpoint + parameter names here (or paste the result to Claude).
"""
import json
import os
import sys
from urllib.parse import quote

# import the verified token manager from the sibling scripts dir
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
import kisti_client as kc  # noqa: E402
import requests  # noqa: E402

FIX = os.path.join(_HERE, "fixtures")
os.makedirs(FIX, exist_ok=True)

# Candidate ScienceON search endpoint + params (ADJUST per official docs if needed).
SEARCH_URL = "https://apigateway.kisti.re.kr/openapicall.do"
QUERY = "표면유속"           # sample Korean query
ROWS = 5

TARGETS = [
    ("ARTI", "kisti_arti_sample.xml"),
    ("REPORT", "kisti_report_sample.xml"),
    ("PATENT", "kisti_patent_sample.xml"),
]


def main():
    try:
        token = kc.get_access_token()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"[token] FAILED: {e}\nCheck KISTI_CLIENT_ID / KISTI_AUTH_KEY (32 bytes) / KISTI_MAC.")
    print(f"[token] OK (len={len(token)})\n")

    cid = os.environ["KISTI_CLIENT_ID"]
    for target, fname in TARGETS:
        sq = quote(json.dumps({"BI": QUERY}, ensure_ascii=False))
        url = (f"{SEARCH_URL}?client_id={cid}&token={token}&version=1.0"
               f"&action=search&target={target}&searchQuery={sq}&curPage=1&rowCount={ROWS}")
        try:
            r = requests.get(url, timeout=60)
        except Exception as e:  # noqa: BLE001
            print(f"[{target}] request error: {e}\n")
            continue
        body = r.text or ""
        out = os.path.join(FIX, fname)
        with open(out, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"[{target}] HTTP {r.status_code}  -> wrote {out}  ({len(body)} chars)")
        print("---- first 1800 chars ----")
        print(body[:1800])
        print("---- end ----\n")

    print("DONE. Review the element names above, then tell Claude (or update "
          "references/kisti.md). The XML files are saved in fixtures/.")


if __name__ == "__main__":
    main()
