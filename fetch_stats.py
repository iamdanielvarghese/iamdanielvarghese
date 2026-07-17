"""
Fetch live GitHub contribution stats and write stats.json.

Run daily by .github/workflows/update-profile-card.yml. Needs a token with
`read:user` scope in the GH_STATS_TOKEN env var - the default GITHUB_TOKEN
cannot query contributionsCollection (it's an App-installation token, not
a real user token), so this must be a Personal Access Token added as a
repo secret. See README setup notes for how to create it.

No third-party dependencies - stdlib only (urllib), matching the rest of
this project's "no dependencies in the workflow" approach.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

LOGIN = "iamdanielvarghese"
API_GRAPHQL = "https://api.github.com/graphql"
API_REST_USER = f"https://api.github.com/users/{LOGIN}"
SPARKLINE_DAYS = 28

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def _request(url, token, data=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": LOGIN,
        "Accept": "application/vnd.github+json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fmt_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_year_chunk(token, frm, to):
    payload = {"query": QUERY, "variables": {
        "login": LOGIN, "from": fmt_utc(frm), "to": fmt_utc(to)}}
    data = _request(API_GRAPHQL, token, payload)
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = {}
    for week in cal["weeks"]:
        for d in week["contributionDays"]:
            days[d["date"]] = d["contributionCount"]
    return cal["totalContributions"], days


def compute_streaks(sorted_dates, counts, today_str):
    # current streak: walk backward from most recent day; if the most
    # recent day is today and has 0 contributions yet, start from
    # yesterday instead so an in-progress day doesn't zero the streak
    i = len(sorted_dates) - 1
    if i >= 0 and sorted_dates[i] == today_str and counts[i] == 0:
        i -= 1
    current = 0
    while i >= 0 and counts[i] > 0:
        current += 1
        i -= 1

    longest = 0
    run = 0
    for c in counts:
        if c > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return current, longest


def plural(n):
    return f"{n} day" if n == 1 else f"{n} days"


def main():
    token = os.environ.get("GH_STATS_TOKEN")
    if not token:
        print("GH_STATS_TOKEN not set - skipping stats refresh.", file=sys.stderr)
        sys.exit(1)

    try:
        user_info = _request(API_REST_USER, token)
        created_at = datetime.fromisoformat(user_info["created_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        all_days = {}
        total = 0
        frm = created_at
        while frm < now:
            to = min(frm + timedelta(days=365), now)
            chunk_total, chunk_days = fetch_year_chunk(token, frm, to)
            total += chunk_total
            all_days.update(chunk_days)
            frm = to

        sorted_dates = sorted(all_days.keys())
        counts = [all_days[d] for d in sorted_dates]
        today_str = now.strftime("%Y-%m-%d")

        current_streak, longest_streak = compute_streaks(sorted_dates, counts, today_str)
        sparkline = counts[-SPARKLINE_DAYS:] if len(counts) >= SPARKLINE_DAYS else counts

        created_label = created_at.strftime("%b %Y")
        ist = timezone(timedelta(hours=5, minutes=30))
        last_updated = now.astimezone(ist).strftime("%d %b %Y, %H:%M IST")

        stats = {
            "contributions": f"{total} ({created_label} - Present)",
            "streak": plural(current_streak),
            "longest": plural(longest_streak),
            "sparkline": sparkline,
            "last_updated": last_updated,
        }
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, RuntimeError) as e:
        # Don't touch stats.json on failure - keep last known-good data
        # rather than overwriting with something broken.
        print(f"Failed to fetch stats, leaving stats.json untouched: {e}", file=sys.stderr)
        sys.exit(1)

    with open("stats.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
