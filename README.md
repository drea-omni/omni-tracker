# Omni Changelog & Demos Tracker

Automatically scrapes [omni.co/changelog](https://omni.co/changelog) and [omni.co/demos](https://omni.co/demos) on a weekly schedule, commits updated JSON data to this repo, and powers a live explorer app.

---

## 📁 Repo Structure

```
omni-tracker/
├── .github/
│   └── workflows/
│       └── scrape_omni.yml      # GitHub Action (weekly + manual)
├── scraper/
│   ├── scrape_omni.py           # Python scraper
│   └── requirements.txt
├── data/
│   ├── omni_changelog.json      # All scraped changelog entries
│   ├── omni_demos.json          # All scraped demo weeks
│   └── last_scrape_report.md    # Auto-generated diff report from last run
└── README.md
```

---

## 🚀 Setup (5 minutes)

### 1. Create the GitHub repo

Create a **public** repo (so GitHub Pages works without a paid plan).

```bash
gh repo create omni-tracker --public --clone
cd omni-tracker
```

### 2. Add your files

Copy all files from this package into the repo.  
Copy your existing `omni_changelog.json` and `omni_demos.json` into the `data/` folder.

```bash
mkdir -p data .github/workflows scraper
# copy files...
git add .
git commit -m "init: add omni tracker"
git push
```

### 3. Enable GitHub Pages (for serving JSON)

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` → folder: `/ (root)`
4. Save

Your JSON files will be live at:
```
https://YOUR-USERNAME.github.io/omni-tracker/data/omni_changelog.json
https://YOUR-USERNAME.github.io/omni-tracker/data/omni_demos.json
```

> **Note:** It takes ~2 minutes for Pages to deploy after first enabling it.

### 4. Verify the Action has write permissions

1. Go to repo → **Settings** → **Actions** → **General**
2. Scroll to **Workflow permissions**
3. Select **Read and write permissions**
4. Save

---

## 🤖 Running the Scraper

### Automatic (weekly)
The Action runs every **Tuesday at 9am UTC** automatically. No setup needed beyond the above.

### Manual trigger
1. Go to your repo → **Actions** tab
2. Click **"Scrape Omni Changelog & Demos"** in the left sidebar
3. Click **"Run workflow"** (top right of the runs list)
4. Choose your options:

| Option | Description |
|--------|-------------|
| **Force re-scrape** | Re-fetches ALL weeks, not just new ones. Use after adding new parsing logic. |
| **Target** | `both` (default), `changelog-only`, or `demos-only` |
| **Dry run** | Shows what would change without writing files. Great for debugging. |

5. Click the green **"Run workflow"** button

### Local development
```bash
cd scraper
pip install -r requirements.txt

# Normal run (only fetches new weeks)
python scrape_omni.py

# Force re-scrape everything
python scrape_omni.py --force

# Dry run (see what would change)
python scrape_omni.py --dry-run

# Only scrape changelog
python scrape_omni.py --changelog-only
```

---

## 🌐 Using the Data in Your Explorer App

Once GitHub Pages is enabled, update your explorer app to fetch from:

```javascript
const CHANGELOG_URL = "https://YOUR-USERNAME.github.io/omni-tracker/data/omni_changelog.json";
const DEMOS_URL     = "https://YOUR-USERNAME.github.io/omni-tracker/data/omni_demos.json";
```

The explorer app can fetch these on load:
```javascript
const [changelog, setChangelog] = useState(null);
const [demos, setDemos]         = useState(null);

useEffect(() => {
  Promise.all([
    fetch(CHANGELOG_URL).then(r => r.json()),
    fetch(DEMOS_URL).then(r => r.json()),
  ]).then(([cl, dm]) => {
    setChangelog(cl);
    setDemos(dm);
  });
}, []);
```

---

## 📊 Monitoring

After each run (automatic or manual), GitHub Actions writes a **step summary** with:
- New changelog entries found
- New demo weeks found  
- Running totals

Find it: **Actions** → click any run → scroll to the bottom of the job log → **Summary** tab.

The report is also saved to `data/last_scrape_report.md` in the repo.

---

## 🔧 Customizing the Schedule

Edit the cron in `.github/workflows/scrape_omni.yml`:

```yaml
schedule:
  - cron: "0 9 * * 2"   # Every Tuesday 9am UTC
```

Common alternatives:
- `"0 9 * * 1"` — Every Monday
- `"0 9 * * 1,4"` — Monday and Thursday  
- `"0 0 * * *"` — Daily at midnight UTC

Use [crontab.guru](https://crontab.guru) to build custom expressions.

---

## ⚠️ Notes

- The scraper is polite — it waits 1.5s between requests
- Omni's pages are public, no auth needed
- If Omni changes their HTML structure, the parser may need updating — check the Action logs if entries stop appearing
- The `--force` flag is useful after parser updates to backfill older weeks

---

## 📝 License

For personal/internal use. Omni content belongs to Omni Analytics.
