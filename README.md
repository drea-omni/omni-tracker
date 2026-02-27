# 🚀 Omni Changelog Explorer

**A powerful, interactive changelog and demo tracker** that automatically connects product releases with their first demonstrations, helping teams understand feature velocity and release patterns.

🔗 **Live Demo:** [Your GitHub Pages URL]

---

## ✨ Features

### 📊 **Smart Changelog & Demo Tracking**
- **Automatic Matching**: Intelligently connects changelog entries with demo videos using curated keyword matching
- **Confidence Scoring**: Each match is rated (confirmed ✦ / probable ~ / possible ?) 
- **Lag Tracking**: See how many days elapsed between first demo and official release
- **Visual Timeline**: Interleaved chronological view of shipped features and demos

### 🔍 **Powerful Filtering & Search**
- **Full-text search** across all features, APIs, and demos
- **Tag-based filtering** with instant visual feedback
- **Date range filters** (7d, 2w, 1mo, or custom date range)
- **Author filtering** for demos (collapsible when "🎬 Demoed" view is selected)
- **View modes**: All / 🚀 Released / 🎬 Demoed / 🚀✨ Demos Released
- **Sort toggle**: ↓ Newest First or ↑ Oldest First

### 🎬 **Rich Video Integration**
- **Embedded YouTube player** in modal (or open in new tab)
- **Playlist save** functionality
- **Video thumbnails** with metadata
- **Multi-video support** per demo week

### 🔐 **Admin Override System**
- **Manual corrections**: Detach incorrect auto-matches or attach the correct demo
- **Git-based persistence**: Overrides stored in repo for all users
- **Local testing**: Browser-stored overrides for testing before committing
- **Visual indicators**: 🟢 Git overrides / 🟡 Local overrides
- **Export to JSON**: Download overrides for easy Git commits

### 🎨 **Beautiful UI**
- **Dark/Light themes** with smooth transitions
- **Responsive design** works on mobile, tablet, and desktop
- **Smooth animations** and polished interactions
- **Collapsible sections** for clean information hierarchy

---

## 📁 Project Structure

```
omni-tracker/
├── index.html                    # Main application (React + Tailwind-inspired styles)
├── data/
│   ├── omni_changelog.json      # Scraped changelog data
│   ├── omni_demos.json          # Scraped demo week data
│   └── overrides.json           # Admin manual corrections (Git-based)
├── .github/
│   └── workflows/
│       ├── scrape-changelog.yml # Auto-scrapes changelog weekly
│       ├── scrape-demos.yml     # Auto-scrapes demos weekly
│       └── update-overrides.yml # Manual workflow for admin updates
└── README.md
```

---

## 🚀 Quick Start

### **1. Fork & Enable GitHub Pages**

1. **Fork this repository**
2. Go to **Settings** → **Pages**
3. Set **Source** to `main` branch, `/ (root)` folder
4. Save and wait for deployment

Your site will be live at: `https://[your-username].github.io/omni-tracker/`

### **2. Configure Data Sources**

Update the URLs in `index.html` (lines ~50-52):

```javascript
const CHANGELOG_URL = "https://your-username.github.io/omni-tracker/data/omni_changelog.json";
const DEMOS_URL     = "https://your-username.github.io/omni-tracker/data/omni_demos.json";
const OVERRIDES_URL = "https://your-username.github.io/omni-tracker/data/overrides.json";
```

### **3. Set Up Auto-Scraping (Optional)**

The GitHub Actions workflows automatically scrape data weekly:
- **Changelog scraper**: `scrape-changelog.yml`
- **Demos scraper**: `scrape-demos.yml`

Make sure your Actions are enabled in **Settings** → **Actions** → **General**.

---

## 🔧 How It Works

### **Data Flow**

```
┌─────────────────┐
│  Web Scraping   │  GitHub Actions run weekly
│  (omni.co)      │  → scrape changelog & demos
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  JSON Storage   │  Committed to /data/
│  (Git)          │  → omni_changelog.json
└────────┬────────┘     omni_demos.json
         │              overrides.json
         ▼
┌─────────────────┐
│  Smart Matcher  │  Curated keyword matching
│  (Runtime)      │  → High/Medium/Low confidence
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  React App      │  Interactive UI
│  (index.html)   │  → Filtering, search, admin
└─────────────────┘
```

### **Matching Algorithm**

The app uses a **curated keyword matching system** (see `HAND_MATCHES` in `index.html`):

1. **Keyword sets** for each demo date (e.g., `["cron expression", "natural language"]`)
2. **Fuzzy matching**: Hits 60%+ of keywords → potential match
3. **Confidence scoring** based on keyword specificity
4. **Date validation**: Demo must occur before changelog entry
5. **Admin overrides** for corrections

Example match:
```javascript
{
  keywords: ["AI summarize", "automatically name"],
  demoDate: "2025-12-01",
  confidence: "high"
}
```

### **Override System**

**Local Overrides** (browser-only):
- Stored in `localStorage`
- Used for testing before committing
- Indicated with 🟡 **LOCAL** badge

**Git Overrides** (production):
- Stored in `/data/overrides.json`
- Fetched on page load
- Indicated with 🟢 **GIT** badge
- Takes precedence over local

**Workflow**:
1. Enter admin mode (🔐 passcode: `omni2026`)
2. Make changes (detach/attach demos)
3. Export to JSON (💾 button)
4. Commit via GitHub Action (see below)

---

## 🔐 Admin Panel Usage

### **Entering Admin Mode**

1. Click **🔐 Enter Admin** in the header
2. Enter passcode: `omni2026`
3. Admin panel slides in from the right

### **Making Changes**

**Edit a specific entry:**
1. Click **🔧 edit** on any changelog entry
2. Search for the correct demo
3. Click **🔗 Attach Selected** or **🔓 Detach Current**

**Bulk review:**
- Open admin panel to see all overrides
- Edit or remove individual overrides
- See which are from Git vs Local

### **Committing Changes**

**Option 1: GitHub Actions Workflow** (Recommended)
1. Click **💾 Export to JSON** in admin panel
2. Copy the entire JSON content
3. Go to **GitHub** → **Actions** → **"Update Overrides"**
4. Click **Run workflow**
5. Paste JSON into the text box
6. Click **Run workflow**
7. ✅ Committed automatically!

**Option 2: Manual Commit**
1. Export JSON as above
2. Save as `/data/overrides.json` in your repo
3. Commit and push manually

### **Override Format**

```json
{
  "2025-12-01-5": {
    "detached": true
  },
  "2025-11-21-12": {
    "attached": {
      "date": "2025-11-21",
      "title": "User attributes and AI context",
      "youtube_id": "abc123xyz",
      "youtube_url": "https://youtube.com/watch?v=abc123xyz",
      "thumbnail": "https://i.ytimg.com/vi/abc123xyz/mqdefault.jpg"
    },
    "confidence": "manual"
  }
}
```

**Key format**: `{date}-{index}` (e.g., `2025-12-01-5` = 6th entry on Dec 1)

---

## 🛠️ Customization

### **Theming**

Edit the `THEMES` object in `index.html` (~lines 53-75):

```javascript
const THEMES = {
  dark: {
    bg: "#0A090E",
    accent: "#FF2D6B",
    text: "#E8E6EA",
    // ... more colors
  },
  light: {
    bg: "#FAFAFA",
    accent: "#CC1A52",
    text: "#1A1A1A",
    // ... more colors
  }
};
```

### **Adding Keywords for Matching**

Edit `HAND_MATCHES` array in `index.html` (~lines 102-141):

```javascript
const HAND_MATCHES = [
  {
    keywords: ["your feature", "related terms"],
    demoDate: "2026-01-15",
    confidence: "high" // or "medium" or "low"
  },
  // ... more matches
];
```

### **Changing Passcode**

Search for `omni2026` in `index.html` and replace with your passcode.

---

## 📊 Data Format

### **Changelog JSON** (`omni_changelog.json`)

```json
{
  "meta": {
    "last_scraped": "2026-02-27T12:00:00Z"
  },
  "entries": [
    {
      "date": "2025-12-19",
      "text": "AI_SUMMARIZE and AI_COMPLETE functions now available",
      "tags": ["ai", "functions", "analytics"]
    }
  ]
}
```

### **Demos JSON** (`omni_demos.json`)

```json
{
  "demos": [
    {
      "date": "2025-12-19",
      "weekTitle": "Demo Week - December 19, 2025",
      "author": "John Doe",
      "url": "https://omni.co/demos/2025-12-19",
      "videos": [
        {
          "title": "AI Functions Demo",
          "youtube_id": "abc123xyz",
          "youtube_url": "https://youtube.com/watch?v=abc123xyz",
          "thumbnail": "https://i.ytimg.com/vi/abc123xyz/mqdefault.jpg"
        }
      ]
    }
  ]
}
```


---

## 📄 License

MIT License - feel free to use this for your own projects!

---

## 🙏 Acknowledgments

- Built with **React** (via CDN)
- Styled with custom **Tailwind-inspired** utility classes
- Icons from Unicode emoji
- Fonts from Google Fonts (Inter, DM Mono, DM Sans)

---

## 📞 Support

Questions? Reach out or open an issue!

**Happy tracking! 🚀✨**
