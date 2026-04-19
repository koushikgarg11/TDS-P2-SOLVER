# 🧅 TDS Onion Auto-Solver

Automatically solves all 12 TDS scraping tasks.  
Works directly on **Streamlit Cloud** — no local Tor needed.

---

## 🚀 Deploy in 5 minutes (GitHub + Streamlit Cloud)

### Step 1 — Push to GitHub

```
tds-onion-solver/
├── app.py             ← Streamlit UI
├── scraper.py         ← All 12 task scrapers  
├── tor_manager.py     ← Auto-starts Tor
├── packages.txt       ← Tells Streamlit Cloud to apt-install tor
├── requirements.txt   ← Python packages
└── README.md
```

1. Create a new **public** GitHub repo (e.g. `tds-onion-solver`)
2. Upload all these files to the repo root
3. That's it for GitHub

### Step 2 — Connect to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click **New app**
4. Choose your repo → branch: `main` → main file: `app.py`
5. Click **Deploy**

Streamlit Cloud will:
- Read `packages.txt` → run `apt-get install tor` automatically
- Read `requirements.txt` → pip install all Python deps
- Launch the app

### Step 3 — Use the app

1. Open your Streamlit app URL (e.g. `https://yourname-tds-onion-solver.streamlit.app`)
2. Enter your `@ds.study.iitm.ac.in` email
3. Click **⚡ Launch Tor Automatically** — waits ~30–60s for Tor to bootstrap
4. Click **🚀 Solve All 12 Tasks**
5. Watch results fill in live (takes 5–15 minutes depending on site speed)
6. Copy the JSON from the right panel → paste into exam → Save

---

## 📁 File breakdown

| File | Purpose |
|------|---------|
| `app.py` | Full Streamlit UI — email input, live task table, JSON output |
| `scraper.py` | All 12 scrapers with auto URL discovery, pagination, retry logic |
| `tor_manager.py` | Finds `tor` binary and launches it via `stem` or `subprocess` |
| `packages.txt` | **Critical** — tells Streamlit Cloud to `apt install tor` |
| `requirements.txt` | Python deps: streamlit, requests[socks], bs4, lxml, stem |

---

## 🔧 Local usage

```bash
# Install tor
brew install tor        # macOS
sudo apt install tor    # Ubuntu

# Start tor
tor   # or open Tor Browser

# Install Python deps
pip install -r requirements.txt

# Run
streamlit run app.py
```

---

## ⚠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| "Tor not detected" on Cloud | Click **Launch Tor Automatically** — it takes 30–60s |
| Timeout on a task | Tor can be slow; scraper retries 5× automatically |
| "Cannot find URL for category" | The site may use different URL paths — check `/category/` vs `/products/` |
| App restarts mid-scrape | Streamlit Cloud has a memory limit; run locally for reliability |

---

## 🔒 Access control

Only emails ending in `@ds.study.iitm.ac.in` are accepted.  
The email is used for validation only — it is not sent anywhere.
