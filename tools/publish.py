#!/usr/bin/env python3
"""Send approved posts from posts/queue.json to Buffer (custom-scheduled).

Usage:
  publish.py            send approved, unsent posts
  publish.py --dry-run  show what would be sent, call nothing
  publish.py --channels list Buffer channels (checks the key works)
Env: BUFFER_API_KEY (required except --dry-run), BUFFER_CHANNEL_ID (optional).
"""
import json, os, sys, pathlib, urllib.request, datetime

API = "https://api.buffer.com"
RAW = "https://raw.githubusercontent.com/saisurya76/propertyiq-marketing/main/posts/{id}.jpg"
MAX_QUEUED = 8  # Buffer free plan allows 10 queued posts per channel
root = pathlib.Path(__file__).resolve().parent.parent
qpath = root / "posts" / "queue.json"

def gql(query, variables=None):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": "Bearer " + os.environ["BUFFER_API_KEY"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Buffer HTTP {e.code}: {e.read().decode()[:400]}")
    if out.get("errors"):
        raise RuntimeError(json.dumps(out["errors"])[:600])
    return out["data"]

def channels():
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    res = []
    for o in orgs:
        res += gql('query { channels(input: { organizationId: "%s" }) { id name service } }' % o["id"])["channels"]
    return res

def instagram_channel():
    if os.environ.get("BUFFER_CHANNEL_ID"):
        return os.environ["BUFFER_CHANNEL_ID"]
    ig = [c for c in channels() if c["service"] == "instagram"]
    if len(ig) != 1:
        sys.exit(f"Expected exactly 1 Instagram channel, found {len(ig)}; set BUFFER_CHANNEL_ID")
    return ig[0]["id"]

MUT = """mutation($input: CreatePostInput!) { createPost(input: $input) {
 ... on PostActionSuccess { post { id dueAt } } ... on MutationError { message } } }"""

def send(post, channel):
    base = {"text": post["caption"], "channelId": channel, "schedulingType": "automatic",
            "mode": "customScheduled", "dueAt": post["scheduled_at"],
            "assets": [{"image": {"url": RAW.format(id=post["id"])}}]}
    last = None
    for meta in ({"instagram": {"type": "post", "shouldShareToFeed": True}}, None):
        inp = dict(base, **({"metadata": meta} if meta else {}))
        try:
            res = gql(MUT, {"input": inp})["createPost"]
        except RuntimeError as e:
            last = str(e); continue
        if "post" in res:
            return res["post"]["id"]
        last = res.get("message")
    raise RuntimeError(last)

def main():
    if "--channels" in sys.argv:
        for c in channels(): print(c)
        return
    dry = "--dry-run" in sys.argv
    posts = json.loads(qpath.read_text())
    now = datetime.datetime.now(datetime.timezone.utc)
    queued = sum(1 for p in posts if p["status"] == "queued")
    todo = [p for p in posts if p["status"] == "approved"]
    if not todo:
        print("nothing approved"); return
    channel = "DRY" if dry else instagram_channel()
    for p in todo:
        when = p.get("scheduled_at")
        if not when:
            print(f"skip {p['id']}: no scheduled_at"); continue
        if datetime.datetime.fromisoformat(when.replace("Z", "+00:00")) <= now:
            print(f"skip {p['id']}: scheduled time is in the past"); continue
        if queued >= MAX_QUEUED:
            print(f"stop: {queued} already queued (limit {MAX_QUEUED})"); break
        if dry:
            print(f"would send {p['id']} at {when}"); queued += 1; continue
        try:
            p["buffer_id"] = send(p, channel); p["status"] = "queued"; queued += 1
            print(f"queued {p['id']} -> {p['buffer_id']}")
        except RuntimeError as e:
            print(f"FAILED {p['id']}: {e}"); p["error"] = str(e)[:300]
        qpath.write_text(json.dumps(posts, indent=1) + "\n")

if __name__ == "__main__":
    main()
