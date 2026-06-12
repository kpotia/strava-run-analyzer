# RunLens: Automated Strava Run Analysis Pipeline

RunLens is a low-maintenance static reporting pipeline that automates fetching Strava runs, performing pacing and coaching analysis, generating interactive HTML reports, and sending notification emails via Resend.

---

## 📊 How it Works

```
+---------------+     +----------------+     +---------------+
|  STRAVA API   |---->| GITHUB ACTIONS |---->| PYTHON SCRIPT |
| (OAuth 2.0)   |     | (Cron: daily)  |     | (Analysis +   |
|               |     |                |     |  Report Gen)  |
+---------------+     +----------------+     +-------+-------+
                                                     |
                          +--------------------------+-----------+
                          |                          |           |
                          v                          v           v
                 +----------------------+    +----------------+  +---------+
                 | Static Site Builder  |    |  Resend API    |  |  EMAIL  |
                 |  (output/ + deploy)  |    |  (Notification) |  |  (You)  |
                 +----------------------+    +----------------+  +---------+
```

1. **GitHub Actions Scheduler:** A cron trigger or manual dispatch runs the pipeline.
2. **Strava Streams Fetcher:** Refreshes OAuth tokens, queries recent activities, and downloads streams (`latlng`, `time`, `altitude`, `heartrate`, `cadence`, `velocity_smooth`).
3. **Pace Analysis Engine:** Reconstructs trackpoints and calculates distance, pacing, pause detection, split paces, and fatigue signals.
4. **Static Report Generator:** Renders individual run HTML reports and a dashboard index with Jinja2 templates.
5. **Deploy Branch Output:** Writes generated site assets to `output/` locally and commits them to the `deploy` branch for static hosting.
6. **Resend Email Alert:** Sends coach-style summary emails with a link to the generated report.

---

## 📁 File Structure

```
strava-run-analyzer/
├── .github/
│   └── workflows/
│       └── analyze-run.yml    # GitHub Actions workflow
├── src/
│   ├── __init__.py
│   ├── strava_client.py       # Strava OAuth + Streams API wrapper
│   ├── analysis_engine.py     # Run metrics and pacing engine
│   ├── report_generator.py    # Jinja2 rendering logic (HTML + chart data)
│   ├── dashboard_generator.py # Local site output manager
│   └── email_sender.py        # Resend email wrapper
├── templates/
│   ├── report_template.html   # Report template
│   └── dashboard_template.html # Dashboard template
├── assets/
│   └── style.css              # Shared stylesheet
├── requirements.txt           # Pip dependencies
├── analyze.py                 # Main orchestration entry point
├── mock_run.py                # Local mock pipeline simulation
└── README.md                  # Documentation
```

---

## ⚙️ Setup Instructions

### 1. Strava API Setup & Refresh Token

Since Strava does not expose a simple GPX download endpoint, this pipeline uses the Streams API. You need to register an API app to get credentials and perform a one-time OAuth flow to capture a long-lived `refresh_token`.

1. Go to [Strava API Settings](https://www.strava.com/settings/api) and create an application:
   - **Application Name:** e.g., RunLens Analyzer
   - **Category:** e.g., Optimizer
   - **Website:** `localhost`
   - **Authorization Callback Domain:** `localhost`
2. Save your **Client ID** and **Client Secret**.
3. Direct your browser to the following URL (replace `[CLIENT_ID]` with yours) to request authorization with the `activity:read_all` scope:
   ```
   https://www.strava.com/oauth/authorize?client_id=[CLIENT_ID]&redirect_uri=http://localhost&response_type=code&scope=activity:read_all
   ```
4. Click **Authorize**. Your browser will redirect to `http://localhost/?state=&code=[AUTHORIZATION_CODE]&scope=read,activity:read_all`.
5. Copy the `[AUTHORIZATION_CODE]` from the address bar.
6. Swap the authorization code for your tokens by running this request in your terminal (using cURL):
   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -F client_id=[CLIENT_ID] \
     -F client_secret=[CLIENT_SECRET] \
     -F code=[AUTHORIZATION_CODE] \
     -F grant_type=authorization_code
   ```
7. Note down the **`refresh_token`** in the JSON response. This token is persistent and handles subsequent access token requests automatically.

### 2. Static Site Deployment

This repository generates a static site into `output/` locally or `source/output/` in GitHub Actions. The workflow in `.github/workflows/analyze-run.yml` commits generated reports, the dashboard, and run history to the `deploy` branch.

- The generated static site includes:
  - `index.html` dashboard
  - `assets/style.css`
  - `data/runs.json`
  - `reports/*.html`
- `DASHBOARD_URL` is used for absolute links in notification emails.
- You can host the `deploy` branch with Vercel, GitHub Pages, or any branch-based static host.

### 3. Resend API Setup

1. Sign up for a free account at [Resend](https://resend.com).
2. Verify your sending domain or sender email address in the Resend dashboard.
3. Create an API Key.
4. Copy the API Key.

### 4. GitHub Secrets Configuration

Add the following secrets to your GitHub repository under **Settings -> Secrets and variables -> Actions**:

| Secret Name | Description | Example |
| :--- | :--- | :--- |
| `STRAVA_CLIENT_ID` | Your Strava app client ID | `12345` |
| `STRAVA_CLIENT_SECRET` | Your Strava app client secret | `ab12cd...34ef` |
| `STRAVA_REFRESH_TOKEN` | Strava refresh token | `xy78zw...90uv` |
| `RESEND_API_KEY` | Resend API Key | `re_abcdef...` |
| `EMAIL_TO` | Target recipient email address | `athlete@example.com` |
| `EMAIL_FROM` | Verified sender email address | `athlete@example.com` |
| `DASHBOARD_URL` | Public site URL for report links | `https://your-site.example.com` |

---

## 🧪 Local Testing & Simulation

Before configuring secrets on GitHub, you can verify the pacing engine, HTML templates, chart generation, and email formats using mock data:

1. Navigate to the project directory:
   ```bash
   cd strava-run-analyzer
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the local mock verification script:
   ```bash
   python mock_run.py
   ```
4. Examine the generated dashboard, run reports, and email preview in `mock_output/`:
   - Open `mock_output/index.html` in your browser.
   - Open `mock_output/email_preview.html` to preview the notification style.
