# Rate-o-meter — LIVE setup (one time, ~20 minutes)

This kit makes the Rate-o-meter update itself. Every time someone opens the
link, the page loads the freshest numbers from `rateometer-data.json`, which a
robot refreshes automatically every 2 hours on weekdays.

**What updates automatically:** the 30-yr mortgage rate (pulled from Mortgage
News Daily, your preferred source), the live rate chart + TODAY pill + 12-month
stats, the 10-yr Treasury, and all timestamps. The page shows a red **LIVE**
badge when it's running.

**What stays human-verified:** Fed odds, the needle verdicts, news items, and
inflation/jobs report numbers — send Claude a "refresh" and you get an updated
`rateometer-data.json` to drop in (or update it whenever big news hits).

## Setup steps

1. Go to **github.com** → sign up (free) if you don't have an account.
2. Top right **+** → **New repository** → name it `rateometer` → set **Public**
   → Create repository.
3. Click **"uploading an existing file"** and drag in ALL of these:
   - `index.html`
   - `rateometer-data.json`
   - `update_data.py`
   - the `.github` folder (drag the whole folder so the workflow comes with it —
     if your Mac hides it, press Cmd+Shift+. in Finder to show hidden folders)
   Then click **Commit changes**.
4. **Settings → Pages** → under "Build and deployment," Source = **Deploy from
   a branch** → Branch = **main**, folder **/ (root)** → Save.
   Your live link appears at the top of that page in a minute:
   `https://YOURUSERNAME.github.io/rateometer/`
5. **Actions** tab → if it asks, click **"I understand… enable workflows"** →
   open **Update Rate-o-meter data** → **Run workflow** once to test.
   Green check = the robot works. It now runs itself every 2 hours, weekdays.

That's it. Bookmark your link, put it in your bio, QR it — every open shows
the latest data with the LIVE badge.

## Custom domain (optional, looks pro)
Settings → Pages → Custom domain → e.g. `rateometer.yourdomain.com`, then add
the CNAME record at your domain registrar per GitHub's instructions.

## Compliance note
The page's "About this data" + footer carry your NMLS + sources. The updater
only writes numbers it successfully pulled from the named source — if a fetch
fails, the last verified number and its original timestamp stay in place.
