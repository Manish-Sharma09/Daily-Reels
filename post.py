#!/usr/bin/env python3
"""Runs on GitHub Actions. Posts the next scheduled reel to Instagram.

  python3 post.py next              -> prints "<tag> <asset> <id>" of the reel due now, or nothing
  python3 post.py post <video> <id> -> posts it and records it in posted.json
Needs env IG_TOKEN (GitHub secret). Times are IST.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
VER = "v23.0"
IG_USER_ID = "17841417953599900"   # @listenosho
HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, default):
    try:
        return json.load(open(os.path.join(HERE, name)))
    except FileNotFoundError:
        return default


def due():
    """Earliest unposted reel whose time has come; at most one post per day (catches up one missed day at a time)."""
    sched, posted = load("schedule.json", []), load("posted.json", {})
    now = datetime.now(IST)
    if any(p.get("posted_at", "")[:10] == now.strftime("%Y-%m-%d") for p in posted.values()):
        return None
    for it in sorted(sched, key=lambda x: x["at"]):
        if it["id"] not in posted and datetime.fromisoformat(it["at"]) <= now:
            return it
    return None


def http(method, url, params=None, data=None, headers=None, timeout=120):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from None


def post(video, item_id):
    tok = os.environ["IG_TOKEN"]
    api = f"https://graph.facebook.com/{VER}" if tok.startswith("EAA") else f"https://graph.instagram.com/{VER}"
    it = next(i for i in load("schedule.json", []) if i["id"] == item_id)
    c = http("POST", f"{api}/{IG_USER_ID}/media", {"media_type": "REELS", "upload_type": "resumable",
             "caption": it["caption"], "share_to_feed": "true", "thumb_offset": str(it.get("thumb_offset_ms", 0)),
             "access_token": tok})
    cid = c["id"]; uri = c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{VER}/{cid}"
    data = open(video, "rb").read()
    http("POST", uri, data=data, timeout=600, headers={"Authorization": f"OAuth {tok}", "offset": "0",
         "file_size": str(len(data)), "Content-Type": "application/octet-stream"})
    for _ in range(60):
        s = http("GET", f"{api}/{cid}", {"fields": "status_code,status", "access_token": tok})
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")
    mid = http("POST", f"{api}/{IG_USER_ID}/media_publish", {"creation_id": cid, "access_token": tok})["id"]
    link = http("GET", f"{api}/{mid}", {"fields": "permalink", "access_token": tok}).get("permalink", "")
    posted = load("posted.json", {})
    posted[item_id] = {"media_id": mid, "permalink": link, "posted_at": datetime.now(IST).isoformat(timespec="seconds")}
    json.dump(posted, open(os.path.join(HERE, "posted.json"), "w"), indent=1)
    print("posted", item_id, link)


if __name__ == "__main__":
    if sys.argv[1] == "next":
        d = due()
        if d:
            print(d["tag"], d["asset"], d["id"])
    elif sys.argv[1] == "post":
        post(sys.argv[2], sys.argv[3])
