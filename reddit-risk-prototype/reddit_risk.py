#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, json, os, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from typing import Any

PROMO_MARKERS = ("onlyfans.com","fansly.com","t.me/","telegram.me/","snapchat.com","linktr.ee")
SOLICITATION = (
    r"\bdm me\b", r"\bmessage me\b", r"\blink in (?:my )?bio\b",
    r"\badd me on\b", r"\bmeet(?:ing)? (?:up )?(?:tonight|today|now)\b",
    r"\blooking (?:to meet|for someone)\b"
)
LOCATION_ALIASES = {
    "pittsburgh":"Pittsburgh, PA","pgh":"Pittsburgh, PA","pennsylvania":"Pennsylvania","pa":"Pennsylvania",
    "miami":"Miami, FL","florida":"Florida","fl":"Florida",
    "dallas":"Dallas, TX","texas":"Texas","tx":"Texas",
    "denver":"Denver, CO","colorado":"Colorado","co":"Colorado",
    "phoenix":"Phoenix, AZ","arizona":"Arizona","az":"Arizona"
}
LOCATION_RE = re.compile(
    r"(?<![a-z])(" + "|".join(sorted(map(re.escape, LOCATION_ALIASES), key=len, reverse=True)) + r")(?![a-z])",
    re.I
)

def text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(k) or "") for k in ("subreddit","title","selftext","body","url")).lower()

def extract_locations(item: dict[str, Any]) -> set[str]:
    return {LOCATION_ALIASES[m.group(1).lower()] for m in LOCATION_RE.finditer(text(item))}

def normalize(item: dict[str, Any]) -> str:
    s = " ".join(str(item.get(k) or "") for k in ("title","selftext","body")).lower()
    s = LOCATION_RE.sub("<location>", s)
    s = re.sub(r"https?://\S+", "<url>", s)
    return re.sub(r"\s+", " ", s).strip()

def windows(activity: list[dict[str, Any]], seconds: int):
    rows = sorted([x for x in activity if isinstance(x.get("created_utc"), (int,float))], key=lambda x:x["created_utc"])
    left = 0
    for right,row in enumerate(rows):
        while left < right and row["created_utc"] - rows[left]["created_utc"] > seconds:
            left += 1
        yield rows[left:right+1]

def score_account(account: dict[str, Any], activity: list[dict[str, Any]], now_utc: float|None=None) -> dict[str, Any]:
    now_utc = now_utc or time.time()
    findings = []

    def add(points:int, code:str, explanation:str):
        findings.append({"points":points,"code":code,"explanation":explanation})

    created = account.get("created_utc")
    if isinstance(created,(int,float)):
        age_days = max(0,(now_utc-created)/86400)
        if age_days < 14: add(15,"young_account",f"Account is approximately {age_days:.1f} days old.")

    karma = int(account.get("link_karma",0) or 0) + int(account.get("comment_karma",0) or 0)
    if karma < 100: add(8,"low_karma",f"Combined public karma is {karma}.")

    corpus = "\n".join(text(x) for x in activity)
    promo = sorted({m for m in PROMO_MARKERS if m in corpus})
    if promo: add(20,"promo_destination","Public activity contains promotional/external destinations: "+", ".join(promo)+".")

    matched = sum(bool(re.search(p, corpus, re.I)) for p in SOLICITATION)
    if matched >= 2: add(10,"solicitation_language",f"Matched {matched} solicitation/meetup language patterns.")

    best_locations = []
    for w in windows(activity, 6*3600):
        locs = sorted(set().union(*(extract_locations(x) for x in w)))
        if len(locs) > len(best_locations): best_locations = locs
    if len(best_locations) >= 3:
        add(35,"geographic_inconsistency",
            f"Public activity references {len(best_locations)} distinct locations within six hours: {', '.join(best_locations)}.")

    grouped = defaultdict(set)
    for item in activity:
        n = normalize(item)
        sub = str(item.get("subreddit") or "").lower()
        if len(n) >= 20 and sub: grouped[n].add(sub)
    repeated = max((len(v) for v in grouped.values()), default=0)
    if repeated >= 3: add(25,"repeated_crosspost",f"Near-identical text appears across {repeated} different subreddits.")

    max_subs = 0
    for w in windows(activity, 2*3600):
        max_subs = max(max_subs, len({str(x.get("subreddit") or "").lower() for x in w if x.get("subreddit")}))
    if max_subs >= 5: add(15,"rapid_cross_subreddit",f"Activity spans {max_subs} subreddits within two hours.")

    score = min(100, sum(f["points"] for f in findings))
    level = "high" if score >= 75 else "elevated" if score >= 45 else "moderate" if score >= 20 else "low"
    return {
        "username": account.get("name"), "risk_score": score, "risk_level": level,
        "findings": sorted(findings, key=lambda f:f["points"], reverse=True),
        "note":"Heuristic risk score only; not a claim that an account is definitively fake or automated."
    }

class RedditReadOnlyClient:
    def __init__(self, client_id:str, client_secret:str, user_agent:str):
        self.client_id, self.client_secret, self.user_agent = client_id, client_secret, user_agent
        self.token = None

    def authenticate(self):
        cred = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        req = urllib.request.Request(
            "https://www.reddit.com/api/v1/access_token",
            data=urllib.parse.urlencode({"grant_type":"client_credentials"}).encode(),
            method="POST",
            headers={"Authorization":"Basic "+cred,"User-Agent":self.user_agent,
                     "Content-Type":"application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            self.token = json.load(r)["access_token"]

    def get(self, path:str, **params):
        if not self.token: self.authenticate()
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            "https://oauth.reddit.com"+path+(("?"+q) if q else ""),
            headers={"Authorization":f"bearer {self.token}","User-Agent":self.user_agent}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    @staticmethod
    def children(payload):
        return [x.get("data",{}) for x in payload.get("data",{}).get("children",[])]

    def account_snapshot(self, username:str, limit:int=50):
        u = urllib.parse.quote(username)
        about = self.get(f"/user/{u}/about").get("data",{})
        posts = self.children(self.get(f"/user/{u}/submitted",limit=limit,sort="new"))
        comments = self.children(self.get(f"/user/{u}/comments",limit=limit,sort="new"))
        return about, posts+comments

    def newest_comment_authors(self, subreddit:str, limit:int=10):
        payload = self.get(f"/r/{urllib.parse.quote(subreddit)}/comments",limit=limit)
        out=[]; seen=set()
        for row in self.children(payload):
            a=row.get("author")
            if a and a not in {"[deleted]","AutoModerator"} and a not in seen:
                seen.add(a); out.append(a)
        return out

def client_from_env():
    missing=[k for k in ("REDDIT_CLIENT_ID","REDDIT_CLIENT_SECRET") if not os.environ.get(k)]
    if missing: raise SystemExit("Missing environment variables: "+", ".join(missing))
    return RedditReadOnlyClient(
        os.environ["REDDIT_CLIENT_ID"], os.environ["REDDIT_CLIENT_SECRET"],
        os.environ.get("REDDIT_USER_AGENT","public-risk-prototype/0.1 by u/freshie77")
    )

def main():
    p=argparse.ArgumentParser(description="Explainable public-activity risk scorer for Reddit accounts.")
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fixture")
    g.add_argument("--user")
    g.add_argument("--subreddit")
    p.add_argument("--limit",type=int,default=10)
    a=p.parse_args()

    if a.fixture:
        fixture=json.load(open(a.fixture,encoding="utf-8"))
        print(json.dumps(score_account(fixture["account"],fixture["activity"],fixture.get("now_utc")),indent=2))
        return 0

    c=client_from_env()
    if a.user:
        account,activity=c.account_snapshot(a.user,min(max(a.limit,1),100))
        print(json.dumps(score_account(account,activity),indent=2)); return 0

    for username in c.newest_comment_authors(a.subreddit,min(max(a.limit,1),25)):
        try:
            account,activity=c.account_snapshot(username,50)
            print(json.dumps(score_account(account,activity),separators=(",",":")))
        except Exception as e:
            print(json.dumps({"username":username,"error":str(e)}),file=sys.stderr)
        time.sleep(1)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
