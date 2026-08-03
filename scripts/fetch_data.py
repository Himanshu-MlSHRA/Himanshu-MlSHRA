import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta

def fetch_github_data(username, token=None):
    if not token:
        token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    
    headers = {
        "User-Agent": "GitHub-Profile-Stats-Generator",
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"token {token}"
        
    graphql_url = "https://api.github.com/graphql"
    query = """
    query($username: String!) {
      user(login: $username) {
        contributionsCollection {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalRepositoryContributions
          contributionCalendar {
            totalContributions
            weeks {
              firstDay
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
          nodes {
            name
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
        }
      }
    }
    """
    
    if not token:
        print("Warning: No GH_PAT or GITHUB_TOKEN found. GraphQL API requires authentication.")
        print("Attempting REST fallback (limited data)...")
        return fetch_fallback_rest(username, headers)
    
    req_data = json.dumps({"query": query, "variables": {"username": username}}).encode("utf-8")
    gql_headers = dict(headers)
    gql_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(graphql_url, data=req_data, headers=gql_headers, method="POST")
    
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if "errors" in result:
                print(f"GraphQL Errors: {result['errors']}")
                return fetch_fallback_rest(username, headers)
            return process_github_response(result["data"]["user"])
    except Exception as e:
        print(f"Failed to fetch via GraphQL: {e}")
        return fetch_fallback_rest(username, headers)

def fetch_fallback_rest(username, headers):
    """REST API fallback — fetches real data from public endpoints.
    Returns None on complete failure so the caller preserves existing data.json."""
    print("Attempting REST fallback...")
    
    # ── 1. Fetch repos and language data ──
    url = f"https://api.github.com/users/{username}/repos?per_page=100&type=owner"
    req = urllib.request.Request(url, headers=headers)
    lang_totals = {}
    total_repos = 0
    repos_fetched = False
    
    try:
        with urllib.request.urlopen(req) as resp:
            repos = json.loads(resp.read().decode("utf-8"))
            total_repos = len([r for r in repos if not r.get("fork")])
            repos_fetched = True
            for repo in repos:
                if repo.get("fork"):
                    continue
                lang_url = repo.get("languages_url")
                if lang_url:
                    try:
                        l_req = urllib.request.Request(lang_url, headers=headers)
                        with urllib.request.urlopen(l_req) as l_resp:
                            langs = json.loads(l_resp.read().decode("utf-8"))
                            for l_name, size in langs.items():
                                lang_totals[l_name] = lang_totals.get(l_name, 0) + size
                    except Exception:
                        pass  # Skip individual repo language failures
    except Exception as e:
        print(f"REST repo fetch error: {e}")
    
    # ── 2. Fetch events to compute contribution stats ──
    total_commits = 0
    total_prs = 0
    active_dates = set()
    daily_counts = {}
    
    # Fetch up to 10 pages of events (max GitHub provides)
    for page in range(1, 11):
        events_url = f"https://api.github.com/users/{username}/events?per_page=100&page={page}"
        try:
            e_req = urllib.request.Request(events_url, headers=headers)
            with urllib.request.urlopen(e_req) as e_resp:
                events = json.loads(e_resp.read().decode("utf-8"))
                if not events:
                    break
                for event in events:
                    event_type = event.get("type", "")
                    created = event.get("created_at", "")[:10]  # YYYY-MM-DD
                    
                    if event_type == "PushEvent":
                        commit_count = len(event.get("payload", {}).get("commits", []))
                        total_commits += commit_count
                        if created:
                            active_dates.add(created)
                            daily_counts[created] = daily_counts.get(created, 0) + commit_count
                    elif event_type == "PullRequestEvent":
                        action = event.get("payload", {}).get("action", "")
                        if action == "opened":
                            total_prs += 1
                            if created:
                                active_dates.add(created)
                                daily_counts[created] = daily_counts.get(created, 0) + 1
                    elif event_type in ("IssuesEvent", "CreateEvent"):
                        if created:
                            active_dates.add(created)
                            daily_counts[created] = daily_counts.get(created, 0) + 1
        except Exception as e:
            print(f"REST events fetch error (page {page}): {e}")
            break
    
    # If we couldn't fetch repos OR events, return None to preserve existing data
    if not repos_fetched and not daily_counts:
        print("REST fallback: Could not fetch any data from GitHub API.")
        return None
    
    # ── 3. Compute weekly contributions for the chart ──
    today = datetime.utcnow().date()
    year_ago = today - timedelta(days=364)
    
    # Build weekly totals for last 52 weeks
    weekly_contributions = []
    month_labels = []
    
    for week_num in range(52):
        week_start = year_ago + timedelta(weeks=week_num)
        week_sum = 0
        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            day_str = day.strftime("%Y-%m-%d")
            week_sum += daily_counts.get(day_str, 0)
        weekly_contributions.append(week_sum)
        
        # Add month label if this week contains the 1st–7th of a month
        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            if day.day <= 7:
                month_labels.append({"index": week_num, "month": day.strftime("%b")})
                break
    
    # ── 4. Compute streaks ──
    all_dates_sorted = sorted(daily_counts.keys())
    
    current_streak = 0
    longest_streak = 0
    temp_streak = 0
    
    # Check all dates in the last year for streak calculation
    for i in range(365):
        day = year_ago + timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        if daily_counts.get(day_str, 0) > 0:
            temp_streak += 1
            longest_streak = max(longest_streak, temp_streak)
        else:
            temp_streak = 0
    
    # Current streak: count backward from today
    for i in range(365):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        if daily_counts.get(day_str, 0) > 0:
            current_streak += 1
        elif i == 0:
            # Today might not have activity yet, skip
            continue
        else:
            break
    
    # Best week
    best_week = max(weekly_contributions) if weekly_contributions else 0
    
    # Total contributions (events-based estimate)
    total_contributions = sum(daily_counts.values())
    
    # ── 5. Build language list ──
    total_bytes = sum(lang_totals.values()) or 1
    sorted_langs = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)[:6]
    
    theme_colors = ["#B7A9DE", "#78A6C2", "#8FBF9F", "#8B877E", "#B7A9DE", "#78A6C2"]
    languages = [
        {
            "name": name,
            "bytes": size,
            "pct": round((size / total_bytes) * 100, 2),
            "color": theme_colors[idx % len(theme_colors)]
        }
        for idx, (name, size) in enumerate(sorted_langs)
    ]
    
    return {
        "total_contributions": total_contributions,
        "active_days": len(active_dates),
        "best_week": best_week,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_commits": total_commits,
        "total_prs": total_prs,
        "repos_contributed": max(total_repos, 1),
        "weekly_contributions": weekly_contributions,
        "month_labels": month_labels,
        "languages": languages
    }

def get_language_color(lang_name):
    # Palette matching theme: purples, blues, greens, greys
    colors = {
        "JavaScript": "#B7A9DE",
        "TypeScript": "#78A6C2",
        "HTML": "#8FBF9F",
        "CSS": "#8B877E",
        "Python": "#78A6C2",
        "Java": "#B7A9DE",
        "C++": "#E7E3DC",
        "C": "#8B877E",
        "Go": "#8FBF9F",
        "Rust": "#E7E3DC",
        "PHP": "#B7A9DE",
        "Ruby": "#8FBF9F",
        "Shell": "#8B877E"
    }
    return colors.get(lang_name, "#B7A9DE")

def process_github_response(user_data):
    contribs = user_data["contributionsCollection"]
    calendar = contribs["contributionCalendar"]
    weeks = calendar["weeks"]
    
    total_contributions = calendar["totalContributions"]
    total_commits = contribs["totalCommitContributions"]
    total_prs = contribs["totalPullRequestContributions"]
    total_repos = contribs["totalRepositoryContributions"]
    
    # Process daily contributions
    all_days = []
    weekly_totals = []
    month_labels = []
    
    best_week = 0
    active_days = 0
    
    for i, week in enumerate(weeks):
        week_sum = 0
        first_day_of_week = week["contributionDays"][0]["date"] if week["contributionDays"] else None
        
        if first_day_of_week:
            dt = datetime.strptime(first_day_of_week, "%Y-%m-%d")
            # If start of month, add label position
            if dt.day <= 7:
                month_labels.append({"index": i, "month": dt.strftime("%b")})

        for day in week["contributionDays"]:
            c_count = day["contributionCount"]
            all_days.append({"date": day["date"], "count": c_count})
            week_sum += c_count
            if c_count > 0:
                active_days += 1
                
        weekly_totals.append(week_sum)
        if week_sum > best_week:
            best_week = week_sum

    # Calculate current and longest streak
    current_streak = 0
    longest_streak = 0
    temp_streak = 0
    
    # Sort days chronologically
    all_days.sort(key=lambda x: x["date"])
    
    for day in all_days:
        if day["count"] > 0:
            temp_streak += 1
            if temp_streak > longest_streak:
                longest_streak = temp_streak
        else:
            temp_streak = 0
            
    # Calculate current streak (working backward from latest day)
    # Allow today or yesterday to be active
    if all_days:
        idx = len(all_days) - 1
        # If today has 0, check if yesterday was active before breaking
        if all_days[idx]["count"] == 0 and idx > 0 and all_days[idx-1]["count"] > 0:
            idx -= 1
        
        while idx >= 0 and all_days[idx]["count"] > 0:
            current_streak += 1
            idx -= 1

    # Process Language distribution from repositories
    repos = user_data["repositories"]["nodes"]
    lang_bytes = {}
    lang_colors = {}
    
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size = edge["size"]
            color = edge["node"]["color"]
            lang_bytes[name] = lang_bytes.get(name, 0) + size
            if color:
                lang_colors[name] = color

    total_bytes = sum(lang_bytes.values()) or 1
    sorted_langs = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:6]
    
    theme_colors = ["#B7A9DE", "#78A6C2", "#8FBF9F", "#8B877E", "#B7A9DE", "#78A6C2"]
    languages = []
    for idx, (name, size) in enumerate(sorted_langs):
        pct = round((size / total_bytes) * 100, 2)
        color = theme_colors[idx % len(theme_colors)]
        languages.append({
            "name": name,
            "bytes": size,
            "pct": pct,
            "color": color
        })

    return {
        "total_contributions": total_contributions,
        "active_days": active_days,
        "best_week": best_week,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_commits": total_commits,
        "total_prs": total_prs,
        "repos_contributed": total_repos,
        "weekly_contributions": weekly_totals,
        "month_labels": month_labels,
        "languages": languages
    }

if __name__ == "__main__":
    target_user = sys.argv[1] if len(sys.argv) > 1 else "Himanshu-MlSHRA"
    token = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("GH_PAT")
    
    print(f"Fetching GitHub data for user: {target_user}...")
    data = fetch_github_data(target_user, token)
    
    if data:
        output_path = os.path.join(os.path.dirname(__file__), "data.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Data successfully fetched and saved to {output_path}")
    else:
        print("Failed to fetch any data. Existing data.json preserved.")
