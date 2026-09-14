# Reddit Public-Activity Risk Prototype

A small, read-only proof of concept for an explainable Reddit account risk scorer.

The intended application is an anti-spam / anti-deception tool for Redditors. It examines **public** account activity and produces a transparent `0-100` risk score from observable behavioral signals. It does **not** claim to prove that an account is fake or automated.

## Current signals

- unusually young / very low-karma accounts;
- public promotional or off-platform destinations;
- solicitation / meetup language;
- near-identical cross-posting;
- rapid activity across many subreddits;
- geographically inconsistent public activity, such as an account claiming immediate meetup availability in several distant locations within a few hours.

The geographic vocabulary is intentionally tiny in this proof of concept. Production would use a maintained location dataset and calibrated thresholds.

## Read-only by design

The prototype does **not** access Reddit Chat/private messages, vote, post, message users, report users, ban users, remove content, or take automatic enforcement action.

## Run now without API access

```bash
python reddit_risk.py --fixture sample_activity.json
python -m unittest -v
```

No third-party packages are required.

## Reddit Data API mode

After Reddit approves API access and credentials are issued:

```bash
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
export REDDIT_USER_AGENT="public-risk-prototype/0.1 by u/freshie77"
```

Score one public account:

```bash
python reddit_risk.py --user example_username --limit 50
```

Inspect authors appearing in the newest comments of a selected public subreddit:

```bash
python reddit_risk.py --subreddit example_subreddit --limit 10
```

The program requests only public account metadata and recent public submissions/comments, emits explainable scores, sleeps between account checks in subreddit mode, and performs no write actions.

## Design principles

1. Public data only.
2. Minimum necessary data.
3. Read-only by default.
4. Explain every score.
5. Prefer behavioral evidence over guesses about writing style.
6. No automatic accusation or enforcement.
7. Treat scores as heuristics until a labeled validation set supports calibration.

## Status

The offline scoring path is functional now. Live Reddit access depends on Data API approval and credentials.
