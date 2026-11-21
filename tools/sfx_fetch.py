#!/usr/bin/env python3
"""Find and download CC0 sound effects from Openverse (no API key needed).

  python3 tools/sfx_fetch.py "record scratch" --n 3 --max-ms 3000 --out sfx/
  python3 tools/sfx_fetch.py "snore" --list            # just print the matches

Notes (tested 2026-11-21):
- Anonymous limits: 20 requests/min, 200/day. One search = one request. Downloads come from the source CDN and do not count.
- Always pass license=cc0 (done here). Results are capped at 240 per query (48 pages of 5).
- Do NOT filter by category=sound_effect: Freesound items have category null, so it returns 0 results.
- The duration filter did nothing in tests; filter by the `duration` field (milliseconds) instead, as --max-ms does.
- The API sometimes answers 500 on the first try; this script retries a few times.
- `url` is a preview-quality mp3 from Freesound (about 128 to 200 kbps). Fine for phone video, not for studio work.
- CC0 needs no credit, but each download is logged in credits.json (title, creator, page) so a sound can be traced later.
"""
import argparse, json, sys, time, urllib.parse, urllib.request
from pathlib import Path

API = "https://api.openverse.org/v1/audio/"
UA = {"User-Agent": "legoreel-sfx/1.0"}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def search(q, page_size=20):
    params = {"q": q, "license": "cc0", "page_size": page_size}
    return json.loads(get(API + "?" + urllib.parse.urlencode(params)))["results"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--n", type=int, default=3, help="how many to download")
    ap.add_argument("--max-ms", type=int, default=4000, help="skip clips longer than this (ms)")
    ap.add_argument("--out", default="sfx")
    ap.add_argument("--list", action="store_true", help="print matches, download nothing")
    a = ap.parse_args()
    hits = [r for r in search(a.query) if r.get("duration") and r["duration"] <= a.max_ms and r.get("url")]
    for r in hits:
        print(f'{r["duration"]:>6} ms  {r["title"][:46]:<46} {r.get("creator","")[:18]:<18} {r["foreign_landing_url"]}')
    if a.list:
        return
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    log_path = out / "credits.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    for r in hits[: a.n]:
        name = "".join(c if c.isalnum() else "_" for c in a.query)[:24] + "_" + r["id"][:8] + ".mp3"
        (out / name).write_bytes(get(r["url"]))
        log.append({"file": name, "title": r["title"], "creator": r.get("creator"), "license": r["license"],
                    "page": r["foreign_landing_url"]})
        print("saved", out / name)
    log_path.write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    sys.exit(main())
