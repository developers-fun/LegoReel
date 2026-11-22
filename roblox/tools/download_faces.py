#!/usr/bin/env python3
"""Download Roblox face assets into assets/faces/ and (re)build index.json.

Stages (all resumable; each stage skips work already recorded in assets/faces/_cache/):

  python tools/download_faces.py search     # catalog keyword search -> candidate asset ids
  python tools/download_faces.py details    # catalog details (name, description, assetType)
  python tools/download_faces.py images     # decal PNG first, thumbnail fallback -> png/<id>.png
  python tools/download_faces.py index      # tag, apply overrides, dedupe, write index.json (no network)
  python tools/download_faces.py all        # the four stages above in order

Only catalog items whose assetType is 18 (Face) or 42 (FaceAccessory) are kept; the
Faces category search also returns hats, emotes, bundles and other accessories.

Image source per item:
  1. assetdelivery PNG for the asset itself (kind "decal"), or
  2. a texture id referenced inside the returned rbxm/XML that serves a PNG (kind "decal"), or
  3. the 420x420 thumbnail from thumbnails.roblox.com (kind "thumbnail").

Decals are padded to square RGBA 256x256. Thumbnails are saved at 420x420.

Manual corrections live in assets/faces/overrides.json:
  {"exclude": [ids], "add_tags": {"id": [tags]}, "remove_tags": {"id": [tags]}}

Only the Python standard library plus Pillow and requests are used. Nothing here imports r6reel.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import io
import json
import random
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FACES = ROOT / "assets" / "faces"
PNG_DIR = FACES / "png"
CACHE = FACES / "_cache"
SEARCH_FILE = CACHE / "search.json"
DETAILS_FILE = CACHE / "details.json"
IMAGES_FILE = CACHE / "images.json"
OVERRIDES_FILE = FACES / "overrides.json"
INDEX_FILE = FACES / "index.json"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
FACE_TYPES = {18, 42}          # 18 = Face, 42 = FaceAccessory (what the Faces category returns)
SEARCH_PAGES = 3               # cursor pages per keyword, 120 items each
WORKERS = 4
DEFAULT_SMILE = 144080495      # classic default 'Smile' face (not in catalog search)

# keyword -> tags it implies. Keywords are sent to the catalog search verbatim.
KEYWORDS: dict[str, list[str]] = {
    "face": [], "faces": [], "default": ["default"], "classic": ["classic"], "roblox": [],
    "happy": ["happy"], "smile": ["happy", "smile"], "smiling": ["happy", "smile"],
    "grin": ["happy", "smile"], "laughing": ["laughing", "happy"], "laugh": ["laughing", "happy"],
    "lol": ["laughing"], "lmao": ["laughing"], "crying": ["crying", "sad"], "cry": ["crying", "sad"],
    "tears": ["crying", "sad"], "sad": ["sad"], "pout": ["sad"], "emo": ["sad"],
    "angry": ["angry"], "mad": ["angry"], "rage": ["angry"], "scream": ["angry", "scared"],
    "shocked": ["shocked", "surprised"], "surprised": ["surprised"], "gasp": ["shocked", "surprised"],
    "scared": ["scared", "shocked"], "worried": ["worried", "nervous"], "nervous": ["nervous", "worried"],
    "sweat": ["nervous"], "sleepy": ["sleepy", "tired"], "tired": ["tired", "sleepy"],
    "yawn": ["sleepy"], "bored": ["bored"], "confused": ["confused"], "smirk": ["smirk"],
    "cool": ["cool"], "sunglasses": ["cool", "sunglasses"], "silly": ["silly"], "derp": ["silly"],
    "goofy": ["silly"], "funny": ["silly"], "tongue": ["tongue", "silly"], "wink": ["wink"],
    "blush": ["blush", "cute"], "shy": ["embarrassed", "blush"], "love": ["love"],
    "heart eyes": ["love"], "hearts": ["love"], "evil": ["evil"], "vampire": ["evil"],
    "creepy": ["creepy"], "monster": ["creepy"], "ghost": ["creepy"], "innocent": ["innocent", "cute"],
    "crazy": ["crazy", "silly"], "dizzy": ["dizzy"], "sick": ["sick"], "determined": ["determined", "serious"],
    "disgusted": ["disgusted"], "embarrassed": ["embarrassed", "blush"], "suspicious": ["suspicious"],
    "serious": ["serious", "neutral"], "deadpan": ["neutral", "serious"], "neutral": ["neutral"],
    "cute": ["cute"], "kawaii": ["cute", "anime"], "chibi": ["cute", "anime"], "uwu": ["cute"],
    "anime": ["anime"], "meme": ["meme"], "troll": ["meme", "silly"], "skull": ["skull"],
    "robot": ["robot"], "cat": ["cat"], "dog": ["dog"], "pizza": ["pizza"], "clown": ["silly"],
    "teeth": ["open_mouth"], "open mouth": ["open_mouth"], "big eyes": ["big_eyes"],
    "closed eyes": ["closed_eyes"], "eyebrows": ["eyebrows"], "realistic": ["realistic"],
    "gamer": ["cool"], "pumpkin": [], "mask": [], "pirate": [], "ninja": [], "noob": [],
    "emoji": [], "sparkle": ["cute"], "excited": ["happy", "surprised"],
    # extra keywords to fill thin emotions (sick had 6 faces after the first pass)
    "sick face": ["sick"], "nauseous": ["sick"], "vomit": ["sick"], "puke": ["sick"],
    "fever": ["sick"], "queasy": ["sick"], "green face": ["sick"], "yuck": ["disgusted", "sick"],
}

# Name/description evidence. Each pattern adds its tags when it matches (case-insensitive).
PATTERNS: list[tuple[str, list[str]]] = [
    (r"\blol|lmao|haha|laugh|giggl|hehe", ["laughing", "happy"]),
    (r"\bhapp|\bsmil|grin|\bjoy|cheer", ["happy"]),
    (r"\bsmil", ["smile"]),
    (r"\bcr(?:y|ying|ied)\b|\btears|\bsob|\bweep", ["crying", "sad"]),
    (r"\bsad\b|unhappy|depress|gloom|\bpout|\bemo\b", ["sad"]),
    (r"\bangr|\brage|\bmad\b|furious|\bhate\b|annoy|pissed", ["angry"]),
    (r"shock|\bomg\b|surpris|gasp|\bwow\b", ["shocked", "surprised"]),
    (r"\bscar(?:e|ed|y)\b|\bfear|terrif|panic|\bhorror", ["scared"]),
    (r"worr|anxious|uneasy", ["worried"]),
    (r"nervous|\bsweat|awkward", ["nervous"]),
    (r"sleep|yawn|zzz|tired|exhaust", ["sleepy"]),
    (r"bored|\bbore\b|\bmeh\b", ["bored"]),
    (r"confus|\bhuh\b|\?\?", ["confused"]),
    (r"smirk|smug", ["smirk"]),
    (r"\bcool\b|sunglass|shades|\bswag\b", ["cool"]),
    (r"silly|derp|goofy|\bdumb\b|funny|clown", ["silly"]),
    (r"\blove|\bheart|adore|\bkiss|romantic", ["love"]),
    (r"\bevil|devil|demon|villain|sinister|\bdark\b", ["evil"]),
    (r"creep|eerie|spooky|\bscary\b|\bskull|skeleton", ["creepy"]),
    (r"dizzy|spiral|woozy", ["dizzy"]),
    (r"\bsick\b|vomit|nause|\bfever\b", ["sick"]),
    (r"determin|\bintense\b", ["determined"]),
    (r"disgust|\bgross\b|\byuck", ["disgusted"]),
    (r"embarass|\bshy\b", ["embarrassed"]),
    (r"blush", ["blush"]),
    (r"suspic|\bsus\b", ["suspicious"]),
    (r"serious|\bstern\b|stoic", ["serious"]),
    (r"neutral|deadpan|expressionless|emotionless", ["neutral"]),
    (r"\bcute\b|kawaii|\buwu\b|chibi|adorable", ["cute"]),
    (r"anime|manga|kemono", ["anime"]),
    (r"\bmeme|\btroll", ["meme"]),
    (r"\brobot|cyber|\bmech\b", ["robot"]),
    (r"\bcat\b|kitty|kitten|neko", ["cat"]),
    (r"\bdog\b|puppy|doggo", ["dog"]),
    (r"pizza", ["pizza"]),
    (r"\btongue|\bblep", ["tongue"]),
    (r"\bwink", ["wink"]),
    (r"sunglass", ["sunglasses"]),
    (r"open mouth|o mouth|screaming|\bteeth\b", ["open_mouth"]),
    (r"big eyes|anime eyes|huge eyes", ["big_eyes"]),
    (r"closed eyes|shut eyes|eyes closed|\^\^", ["closed_eyes"]),
    (r"eyebrow", ["eyebrows"]),
    (r"\bclassic\b", ["classic"]),
    (r"realistic|\bcinematic\b", ["realistic"]),
]

PATTERNS_RE = [(re.compile(p, re.I), tags) for p, tags in PATTERNS]
SKIP_FACE_TAGS = {"face"}   # generic word, never a tag

_session_local = requests.Session()
_session_local.headers["User-Agent"] = UA


def _sleep():
    time.sleep(random.uniform(0.3, 0.5))


def http(method: str, url: str, session: requests.Session | None = None, **kw) -> requests.Response:
    """Request with polite pacing and backoff on 429 and 5xx."""
    s = session or _session_local
    r = None
    for attempt in range(6):
        try:
            r = s.request(method, url, timeout=60, **kw)
        except requests.RequestException as exc:  # dropped connection, reset, timeout
            wait = 2 ** attempt + random.random()
            print(f"  network error on {url[:70]} ({exc.__class__.__name__}), retry in {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
            continue
        _sleep()
        if r.status_code == 429 or r.status_code >= 500:
            wait = 2 ** attempt + random.random()
            print(f"  {r.status_code} on {url[:70]}, backing off {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
            continue
        return r
    if r is None:
        r = requests.Response()
        r.status_code = 0  # treated as a miss by callers
        return r
    return r


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True))
    tmp.replace(path)


# ---------------------------------------------------------------- stage 1: search

def stage_search():
    state = load_json(SEARCH_FILE, {"done": [], "items": {}})
    done = set(state["done"])
    for kw in KEYWORDS:
        if kw in done:
            continue
        cursor = None
        for _ in range(SEARCH_PAGES):
            params = {"category": "Faces", "limit": 120, "keyword": kw}
            if cursor:
                params["cursor"] = cursor
            r = http("GET", "https://catalog.roblox.com/v1/search/items", params=params)
            if r.status_code != 200:
                print(f"search '{kw}' -> HTTP {r.status_code}", file=sys.stderr)
                break
            body = r.json() or {}
            for it in body.get("data") or []:
                if it.get("itemType") != "Asset":
                    continue
                entry = state["items"].setdefault(str(it["id"]), {"keywords": []})
                if kw not in entry["keywords"]:
                    entry["keywords"].append(kw)
            cursor = body.get("nextPageCursor")
            if not cursor:
                break
        state["done"].append(kw)
        done.add(kw)
        save_json(SEARCH_FILE, state)
        print(f"search '{kw}': {len(state['items'])} candidate assets so far")
    save_json(SEARCH_FILE, state)


# ---------------------------------------------------------------- stage 2: details

def _csrf_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.post("https://catalog.roblox.com/v1/catalog/items/details", json={"items": []})
    token = r.headers.get("x-csrf-token")
    if token:
        s.headers["X-CSRF-TOKEN"] = token
    return s


def stage_details():
    search = load_json(SEARCH_FILE, {"items": {}})
    details = load_json(DETAILS_FILE, {})
    todo = [i for i in search["items"] if i not in details]
    if not todo:
        print("details: nothing to do")
        return
    s = _csrf_session()
    for start in range(0, len(todo), 120):
        chunk = todo[start:start + 120]
        payload = {"items": [{"itemType": "Asset", "id": int(i)} for i in chunk]}
        r = http("POST", "https://catalog.roblox.com/v1/catalog/items/details", session=s, json=payload)
        if r.status_code == 403 and "x-csrf-token" in r.headers:
            s.headers["X-CSRF-TOKEN"] = r.headers["x-csrf-token"]
            r = http("POST", "https://catalog.roblox.com/v1/catalog/items/details", session=s, json=payload)
        if r.status_code != 200:
            print(f"details chunk {start}: HTTP {r.status_code}", file=sys.stderr)
            continue
        for it in r.json().get("data", []):
            details[str(it["id"])] = {
                "name": it.get("name", ""),
                "description": (it.get("description") or "")[:600],
                "assetType": it.get("assetType"),
                "creator": it.get("creatorName", ""),
                "price": it.get("price"),
            }
        for i in chunk:  # remember misses so they are not retried forever
            details.setdefault(i, {"missing": True})
        save_json(DETAILS_FILE, details)
        print(f"details: {min(start + 120, len(todo))}/{len(todo)}")
    save_json(DETAILS_FILE, details)


# ---------------------------------------------------------------- stage 3: images

def is_png(b: bytes) -> bool:
    return b[:8] == b"\x89PNG\r\n\x1a\n"


TEX_RE = re.compile(rb"(?:rbxassetid://|asset/\?id=|asset/\?id%3D|id=)(\d{6,})")


def fetch_decal(asset_id: str) -> bytes | None:
    """Return PNG bytes for a flat decal, or None."""
    r = http("GET", f"https://assetdelivery.roblox.com/v1/asset?id={asset_id}")
    if r.status_code != 200:
        return None
    if is_png(r.content):
        return r.content
    tex_ids = list(dict.fromkeys(TEX_RE.findall(r.content)))[:6]
    for tid in tex_ids:
        t = http("GET", f"https://assetdelivery.roblox.com/v1/asset?id={tid.decode()}")
        if t.status_code == 200 and is_png(t.content):
            return t.content
    return None


def to_square_rgba(png: bytes, size: int = 256) -> tuple[bytes, dict]:
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    w, h = img.size
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    canvas = canvas.resize((size, size), Image.LANCZOS)
    alpha = canvas.getchannel("A")
    transparent = alpha.getextrema()[0] == 0
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue(), {"w": w, "h": h, "transparent": transparent}


def fetch_thumbnail_urls(ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        r = http("GET", "https://thumbnails.roblox.com/v1/assets",
                 params={"assetIds": ",".join(chunk), "size": "420x420", "format": "Png"})
        if r.status_code != 200:
            print(f"thumbnail batch {start}: HTTP {r.status_code}", file=sys.stderr)
            continue
        for row in r.json().get("data", []):
            if row.get("state") == "Completed" and row.get("imageUrl"):
                out[str(row["targetId"])] = row["imageUrl"]
    return out


def face_ids() -> list[str]:
    details = load_json(DETAILS_FILE, {})
    ids = [i for i, d in details.items() if d.get("assetType") in FACE_TYPES]
    # the classic default Smile is not returned by the catalog, so add it by hand
    if str(DEFAULT_SMILE) not in ids:
        ids.append(str(DEFAULT_SMILE))
    return sorted(set(ids), key=int)


EMOTION_TAGS = {
    "happy", "smile", "laughing", "sad", "crying", "angry", "shocked", "surprised", "scared",
    "worried", "nervous", "sleepy", "tired", "bored", "confused", "smirk", "cool", "silly", "love",
    "evil", "creepy", "dizzy", "sick", "determined", "disgusted", "embarrassed", "suspicious",
    "serious", "neutral", "cute", "blush", "wink", "tongue", "anime", "meme", "innocent", "crazy",
    "skull", "default", "classic",
}
# accessories that are not a face on their own (checked against the item name)
NON_FACE_NAME = re.compile(
    r"sunglass|glasses|shades|aura|flame|fire|wings?\b|halo|horn|\bears?\b|tail|piercing|hair|"
    r"\bhat\b|crown|collar|choker|bandage|tape|hearts?\b|paper|shirt|neck|shoulder|backpack|"
    r"eyelash|lashes|\blips?\b|nose|cheek|\bbow\b|\bring\b|beard|mustache|moustache|earring|"
    r"butterfly|dragon|sword|cape|\bgem|rose|scarf|chain", re.I)
MAX_IMAGES = 1200
EXPRESSION_TAGS = {
    "happy", "smile", "laughing", "sad", "crying", "angry", "shocked", "surprised", "scared",
    "worried", "nervous", "sleepy", "tired", "bored", "confused", "smirk", "cool", "silly", "love",
    "evil", "creepy", "dizzy", "sick", "determined", "disgusted", "embarrassed", "suspicious",
    "serious", "neutral", "blush", "wink", "tongue", "innocent", "crazy",
}
MAX_EXPRESSION_TAGS = 6


def selected_ids() -> list[str]:
    """Face-type assets with emotion evidence, sampled round-robin across search keywords.

    The catalog search returns about 7,400 face-type items; the library needs far fewer,
    and each one is checked by eye later. Items matched by more search keywords go first.
    """
    search = load_json(SEARCH_FILE, {"items": {}})["items"]
    details = load_json(DETAILS_FILE, {})
    if not details:
        return []
    buckets: dict[str, list[tuple[int, str]]] = {}
    for i in face_ids():
        if i == str(DEFAULT_SMILE):
            continue
        kws = search.get(i, {}).get("keywords", [])
        if not (derive_tags(i, {"keywords": kws}, details) & EMOTION_TAGS):
            continue
        if NON_FACE_NAME.search(details.get(i, {}).get("name", "")):
            continue
        key = max(kws, key=lambda k: (len(KEYWORDS.get(k, [])) > 0, k)) if kws else "_"
        buckets.setdefault(key, []).append((-len(kws), i))
    for b in buckets.values():
        b.sort()
    out, keys = [str(DEFAULT_SMILE)], sorted(buckets)
    while len(out) < MAX_IMAGES and any(buckets.values()):
        for k in keys:
            if buckets[k] and len(out) < MAX_IMAGES:
                out.append(buckets[k].pop(0)[1])
    return out


def stage_images():
    images = load_json(IMAGES_FILE, {})
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    wanted = selected_ids()
    ids = [i for i in wanted if i not in images]
    print(f"images: {len(ids)} to process (of {len(wanted)} tagged face assets)")

    def work(i: str):
        try:
            raw = fetch_decal(i)
        except Exception as exc:  # keep the batch going; the id is retried on the next run
            print(f"  decal error {i}: {exc}", file=sys.stderr)
            raw = None
        if raw is None:
            return i, None
        png, meta = to_square_rgba(raw)
        return i, (png, meta)

    no_decal = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, (i, res) in enumerate(pool.map(work, ids), 1):
            if res is None:
                no_decal.append(i)
            else:
                png, meta = res
                (PNG_DIR / f"{i}.png").write_bytes(png)
                images[i] = {"kind": "decal", "file": f"png/{i}.png", **meta}
            if n % 50 == 0:
                save_json(IMAGES_FILE, images)
                print(f"  decal pass {n}/{len(ids)}, decals so far {sum(1 for v in images.values() if v.get('kind') == 'decal')}")
    save_json(IMAGES_FILE, images)

    urls = fetch_thumbnail_urls(no_decal)
    def grab(item):
        i, url = item
        r = http("GET", url)
        if r.status_code != 200 or not is_png(r.content):
            return i, None
        buf = io.BytesIO()
        Image.open(io.BytesIO(r.content)).convert("RGBA").save(buf, "PNG", optimize=True)
        return i, buf.getvalue()
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, data in pool.map(grab, urls.items()):
            if data:
                (PNG_DIR / f"{i}.png").write_bytes(data)
                images[i] = {"kind": "thumbnail", "file": f"png/{i}.png"}
    for i in no_decal:
        images.setdefault(i, {"kind": "none"})
    save_json(IMAGES_FILE, images)
    kinds = {}
    for v in images.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print("images:", kinds)


# ---------------------------------------------------------------- stage 4: tags and index

def ranked_tags(asset_id: str, search: dict, details: dict) -> list[str]:
    """Every tag the item earns, strongest evidence first: name, then search keyword, then description."""
    d = details.get(asset_id, {})
    name = d.get("name", "")
    desc = d.get("description", "")
    ordered: list[str] = []
    def add(tags):
        for t in tags:
            if t not in SKIP_FACE_TAGS and t not in ordered:
                ordered.append(t)
    for rx, tags in PATTERNS_RE:
        if rx.search(name):
            add(tags)
    for kw in search.get("keywords", []):
        add(KEYWORDS.get(kw, []))
    for rx, tags in PATTERNS_RE:
        if rx.search(desc):
            add(tags)
    return ordered


def derive_tags(asset_id: str, search: dict, details: dict) -> set[str]:
    tags = set(ranked_tags(asset_id, search, details))
    # a face that matches many expressions is usually a keyword pile-up (e.g. an emoji mask
    # found by "happy", "sad", "angry" ...): keep the strongest few expression tags only
    expr = [t for t in ranked_tags(asset_id, search, details) if t in EXPRESSION_TAGS]
    if len(expr) > MAX_EXPRESSION_TAGS:
        tags -= set(expr)
        tags |= set(expr[:MAX_EXPRESSION_TAGS])
    return tags


def slug_name(name: str, asset_id: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    return name or f"face {asset_id}"


def stage_index():
    search = load_json(SEARCH_FILE, {"items": {}})["items"]
    details = load_json(DETAILS_FILE, {})
    images = load_json(IMAGES_FILE, {})
    overrides = load_json(OVERRIDES_FILE, {"exclude": [], "add_tags": {}, "remove_tags": {}})
    exclude = {str(x) for x in overrides.get("exclude", [])}

    entries, seen_hash = [], {}
    for asset_id in sorted(images, key=int):
        img = images[asset_id]
        if img.get("kind") not in ("decal", "thumbnail") or asset_id in exclude:
            continue
        path = PNG_DIR / f"{asset_id}.png"
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen_hash:      # identical picture under two asset ids
            continue
        seen_hash[digest] = asset_id
        tags = derive_tags(asset_id, search.get(asset_id, {}), details)
        if asset_id == str(DEFAULT_SMILE):
            tags |= {"default", "happy", "smile"}
        tags |= set(overrides.get("add_tags", {}).get(asset_id, []))
        tags -= set(overrides.get("remove_tags", {}).get(asset_id, []))
        if not tags:
            tags = {"face"}
        d = details.get(asset_id, {})
        if asset_id == str(DEFAULT_SMILE) and not d.get("name"):
            d = {"name": "Smile (default)", "creator": "Roblox"}
        entries.append({
            "id": asset_id,
            "name": slug_name(d.get("name", ""), asset_id),
            "file": img["file"],
            "tags": sorted(tags),
            "asset_id": int(asset_id),
            "source": "roblox catalog",
            "kind": img["kind"],
            "creator": d.get("creator", "Roblox"),
            "search_keywords": search.get(asset_id, {}).get("keywords", []),
        })
    save_json(INDEX_FILE, entries)
    # drop PNGs that the index no longer references (excluded, duplicate or retired items);
    # to fetch an excluded item again, remove its line from _cache/images.json and rerun `images`
    live = {e["file"] for e in entries}
    for p in PNG_DIR.glob("*.png"):
        if f"png/{p.name}" not in live:
            p.unlink()
    counts = {}
    for e in entries:
        for t in e["tags"]:
            counts[t] = counts.get(t, 0) + 1
    kinds = {}
    for e in entries:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"index: {len(entries)} faces, kinds {kinds}")
    print("tags:", dict(sorted(counts.items(), key=lambda kv: -kv[1])))


# ---------------------------------------------------------------- contact sheets

PRIMARY_ORDER = [
    "happy", "smile", "laughing", "sad", "crying", "angry", "shocked", "surprised", "scared",
    "worried", "nervous", "sleepy", "tired", "bored", "confused", "smirk", "cool", "silly", "love",
    "evil", "creepy", "dizzy", "sick", "determined", "disgusted", "embarrassed", "suspicious",
    "serious", "neutral", "cute", "blush", "wink", "tongue", "anime", "meme", "innocent", "crazy",
    "skull", "robot", "cat", "dog", "pizza", "default", "classic",
]


DOC_SHEET_TAGS = {
    "happy", "laughing", "sad", "crying", "angry", "shocked", "surprised", "scared", "worried",
    "nervous", "sleepy", "bored", "confused", "smirk", "cool", "silly", "love", "evil",
    "embarrassed", "suspicious", "serious", "neutral", "sick", "dizzy", "smile", "default",
}


def _sheet(items: list[tuple[str, Path]], out: Path, cols: int, cell: int) -> None:
    from PIL import ImageDraw
    rows = max(1, (len(items) + cols - 1) // cols)
    label_h = 14
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (235, 235, 235))
    draw = ImageDraw.Draw(sheet)
    for k, (label, path) in enumerate(items):
        x, y = (k % cols) * cell, (k // cols) * (cell + label_h)
        try:
            im = Image.open(path).convert("RGBA").resize((cell - 6, cell - 6), Image.LANCZOS)
            bg = Image.new("RGBA", im.size, (150, 150, 150, 255))
            bg.alpha_composite(im)
            sheet.paste(bg.convert("RGB"), (x + 3, y + 3))
        except OSError:
            pass
        draw.text((x + 3, y + cell), label, fill=(0, 0, 0))
    sheet.save(out, optimize=True)


def stage_sheets(out_dir: str | None, per_sheet: int, cols: int, cell: int):
    """Numbered review sheets (out_dir) or, with no out_dir, docs/faces_<tag>.png per tag."""
    index = load_json(INDEX_FILE, [])
    if out_dir:
        # review mode: one pass over the library, ordered by primary emotion, numbered 1..N
        order = {t: n for n, t in enumerate(PRIMARY_ORDER)}
        def primary(e):
            return min((order.get(t, 999) for t in e["tags"]), default=999)
        ordered = sorted(index, key=lambda e: (primary(e), int(e["id"])))
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        mapping = {}
        for s in range(0, len(ordered), per_sheet):
            chunk = ordered[s:s + per_sheet]
            items = []
            for k, e in enumerate(chunk, start=s + 1):
                mapping[k] = e["id"]
                items.append((f"{k}", FACES / e["file"]))
            _sheet(items, out / f"review_{s // per_sheet + 1:02d}.png", cols, cell)
        save_json(out / "map.json", mapping)
        print(f"review: {len(ordered)} faces in {len(range(0, len(ordered), per_sheet))} sheets under {out}")
        return
    docs = ROOT / "docs"
    counts = {}
    for e in index:
        for t in e["tags"]:
            counts[t] = counts.get(t, 0) + 1
    for tag, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n < 15 or tag not in DOC_SHEET_TAGS:
            continue
        members = sorted((e for e in index if tag in e["tags"]), key=lambda e: int(e["id"]))
        items = [(e["id"][-5:], FACES / e["file"]) for e in members]
        _sheet(items, docs / f"faces_{tag}.png", cols=10, cell=100)
        print(f"docs/faces_{tag}.png: {n} faces")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["search", "details", "images", "index", "sheets", "all"])
    ap.add_argument("--review-dir", help="sheets: write numbered review sheets here instead of docs/")
    ap.add_argument("--per-sheet", type=int, default=80)
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--cell", type=int, default=120)
    args = ap.parse_args()
    if args.stage in ("search", "all"):
        stage_search()
    if args.stage in ("details", "all"):
        stage_details()
    if args.stage in ("images", "all"):
        stage_images()
    if args.stage in ("index", "all"):
        stage_index()
    if args.stage == "sheets":
        stage_sheets(args.review_dir, args.per_sheet, args.cols, args.cell)


if __name__ == "__main__":
    main()
