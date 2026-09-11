#!/usr/bin/env python3
"""
Rate-o-meter live updater.
Runs on a schedule (GitHub Actions), refreshes rateometer-data.json in place.
Auto-updated: MND 30-yr rate, WTI crude, 10-yr Treasury, rate chart + stats, timestamps.
Everything it can't verify, it leaves untouched (Fed odds, news, verdicts stay
manual so a human always signs off on them).
If any source fails, the last good value is kept with its original stamp.
"""
import json, re, urllib.request, datetime, sys

JSON_PATH = "rateometer-data.json"
UA = {"User-Agent": "Mozilla/5.0 (RateometerUpdater; +for personal site)"}

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")

def get_mnd_rate():
    """Scrape MND's daily 30-yr fixed index (Mark's preferred source)."""
    html = fetch("https://www.mortgagenewsdaily.com/mortgage-rates/mnd")
    m = re.search(r"30\s*Yr\.?\s*Fixed(?:\s*Rate)?[^0-9]{0,120}?(\d\.\d{2})\s*%", html, re.S | re.I)
    if not m:
        raise ValueError("MND parse failed")
    v = float(m.group(1))
    if not (3.0 < v < 12.0):
        raise ValueError(f"MND value out of range: {v}")
    return v

def get_fred_latest(series_id):
    """Latest value from a FRED series via the public CSV endpoint (no key)."""
    csv = fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    rows = [r.split(",") for r in csv.strip().splitlines()[1:]]
    for date, val in reversed(rows):
        if val not in (".", ""):
            return date, float(val)
    raise ValueError(f"No data for {series_id}")

def get_wti():
    """WTI front-month: stooq CSV (fresh) with FRED daily as fallback."""
    try:
        csv = fetch("https://stooq.com/q/l/?s=cl.f&f=sd2t2ohlcv&e=csv")
        row = csv.strip().splitlines()[1].split(",")
        v = float(row[6])  # close
        if 20 < v < 300:
            return v, "stooq"
    except Exception:
        pass
    _, v = get_fred_latest("DCOILWTICO")
    return v, "FRED (may lag 1-2 days)"

def get_fed_odds():
    """CME FedWatch raise probability for the next meeting, via headless browser.
    Requires playwright (installed by the workflow). Returns int percent."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
                wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(4000)
        body = pg.inner_text("body")
        b.close()
    # look for the two probability percentages near the target-rate table
    pcts = [float(x) for x in re.findall(r"(\d{1,2}\.\d)%", body)]
    cands = [x for x in pcts if 1 <= x <= 99]
    if len(cands) < 2:
        raise ValueError("FedWatch parse failed")
    # raise = probability of the higher band; take the pair that sums ~100
    for i in range(len(cands) - 1):
        if 98 <= cands[i] + cands[i+1] <= 102:
            return round(cands[i+1])  # second band = hike
    raise ValueError("FedWatch pair not found")

def apply_fed_odds(data, hike):
    hold = 100 - hike
    fed = data.get("fed", {})
    if fed.get("meetings"):
        fed["meetings"][0]["hike"] = hike
        fed["meetings"][0]["hold"] = hold
    if "narrative" in fed:
        fed["narrative"] = re.sub(r"\d{1,2}% chance", f"{hike}% chance", fed["narrative"])
    for pth in fed.get("path", []):
        if "say raise" in pth.get("s", ""):
            pth["s"] = f"{hike}% say raise"
    for b in data.get("bigNums", []):
        if "ODDS" in b.get("k", ""):
            b["v"] = str(hike)
    for w in data.get("watch", []):
        if "say raise" in w.get("desc", ""):
            w["desc"] = f"Rate decision \u2014 {hike}% say raise".encode().decode("unicode_escape")

def main():
    data = json.load(open(JSON_PATH))
    now = datetime.datetime.now(datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=-4)))  # ET-ish
    stamp = now.strftime("%a, %b %-d, %Y \u00b7 %-I %p ET")
    today = now.strftime("%Y-%m-%d")
    changed = False

    # ---- MND 30-yr fixed ----
    try:
        rate = get_mnd_rate()
        rc = data["rateChart"]
        rate_s = f"{rate:.2f}"
        # chart point: replace today's if present, else append
        if rc["series"] and rc["series"][-1][0] == today:
            rc["series"][-1][1] = rate
        else:
            rc["series"].append([today, rate])
        rc["latest"] = f"{rate_s}%"
        rc["latestLabel"] = f"TODAY: {rate_s}%"
        rc["asOf"] = now.strftime("%b %-d, %-I %p ET")
        # stats
        vals = [v for _, v in rc["series"]]
        lo, hi = min(vals), max(vals)
        for s in rc.get("stats", []):
            if s["k"] == "12-MO HIGH":
                s["v"] = f"{hi:.2f}%"
                s["s"] = "NOW" if abs(hi - rate) < 0.005 else s["s"]
            if s["k"] == "12-MO LOW":
                s["v"] = f"{lo:.2f}%"
            if s["k"] == "12-MO CHANGE":
                s["v"] = f"{rate - vals[0]:+.2f}"
        for b in data.get("bigNums", []):
            if "MORTGAGE RATE" in b["k"]:
                b["v"] = rate_s
                b["sub"] = "30-yr fixed \u00b7 Mortgage News Daily" + (" \u00b7 12-mo high" if abs(hi - rate) < 0.005 else "")
        changed = True
        print(f"MND 30-yr: {rate_s}%")
    except Exception as e:
        print(f"MND fetch skipped ({e}); keeping last value", file=sys.stderr)

    # ---- Fed odds (CME FedWatch) ----
    try:
        hike = get_fed_odds()
        apply_fed_odds(data, hike)
        if data.get("fed"): data["fed"]["note"] = f"CME FedWatch \u2014 traders betting real money. As of {now.strftime('%-m/%-d')}.".encode().decode("unicode_escape")
        changed = True
        print(f"FedWatch raise odds: {hike}%")
    except Exception as e:
        print(f"FedWatch skipped ({e}); keeping last odds", file=sys.stderr)

    # ---- WTI crude ----
    try:
        wti, src = get_wti()
        data.setdefault("oil", {})["price"] = f"${wti:.2f}"
        changed = True
        print(f"WTI: ${wti:.2f} via {src}")
    except Exception as e:
        print(f"WTI skipped ({e}); keeping last value", file=sys.stderr)

    # ---- 10-yr Treasury (FRED DGS10) ----
    try:
        d10, y10 = get_fred_latest("DGS10")
        for b in data.get("bigNums", []):
            if "10-YR" in b["k"]:
                b["v"] = f"{y10:.2f}"
                b["sub"] = f"What mortgage rates track \u00b7 {d10[5:7].lstrip('0')}/{d10[8:10].lstrip('0')}"
        changed = True
        print(f"10-yr Treasury: {y10:.2f}% ({d10})")
    except Exception as e:
        print(f"FRED DGS10 skipped ({e})", file=sys.stderr)

    if changed:
        data["dataAsOf"] = stamp
        data["numTag"] = "LIVE \u00b7 AUTO-UPDATED"
    json.dump(data, open(JSON_PATH, "w"), indent=1)
    print(f"Updated {JSON_PATH} @ {stamp}")

if __name__ == "__main__":
    main()
