# RunLens: Automated Strava Run Analysis Pipeline

RunLens is a low-maintenance, zero-infrastructure, cost-effective run analysis pipeline. It automates the process of fetching your runs from Strava, conducting deep pacing and coaching analysis, uploading interactive visual reports to Google Cloud Storage (GCS), and notifying you via SendGrid email alerts.

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
                 +---------------+          +---------------+  +---------+
                 | GOOGLE CLOUD  |          |  SENDGRID API |  |  EMAIL  |
                 | STORAGE       |          |  (Email send) |  |  (You)  |
                 | (Reports +    |          |               |  +---------+
                 |  Static Site) |          +---------------+
                 +---------------+
```

1. **GitHub Actions Scheduler:** A cron job runs daily (or is manually triggered).
2. **Strava Streams Fetcher:** Refreshes OAuth credentials, queries recent athlete activities, identifies new run sessions, and downloads time-series streams (latitude/longitude, heart rate, cadence, speed, elevation).
3. **Pace Analysis Engine:** Performs haversine calculations, segment pause/break checks, split calculations, half-split negative/positive delta calculations, and fatigue onset detection.
4. **Static Report Generator:** Generates responsive HTML reports with interactive Chart.js graphs and updates the central training index page.
5. **GCS Uploader:** Interacts with Google Cloud Storage to upload reports, styles, and the updated metadata database.
6. **SendGrid Email Alert:** Dispatches a structured summary email to the athlete with coach feedback and a link to the GCS dashboard.

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
│   ├── analysis_engine.py     # Ported calculations & coach generator
│   ├── report_generator.py    # Jinja2 rendering logic (HTML + Chart.js)
│   ├── gcs_uploader.py        # GCP client wrapper
│   └── email_sender.py        # SendGrid wrapper
├── templates/
│   ├── report_template.html   # Report template
│   └── dashboard_template.html# Index page template
├── assets/
│   └── style.css              # Premium glassmorphic stylesheet
├── requirements.txt           # Pip dependencies
├── analyze.py                 # Main orchestration entry point
├── mock_run.py                # Local verification runner (mocks APIs)
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

### 2. Google Cloud Storage Bucket Setup

1. In the GCP Console, create a new Cloud Storage bucket (e.g. `your-run-bucket`).
2. Set access control to **Uniform** (recommended) or **Fine-grained**.
3. (Optional) Make the bucket a static website by making objects public:
   - Go to IAM & Admin -> Service Accounts and create a service account with **Storage Object Admin** role.
   - Download the service account JSON key, and encode it in base64:
     - Windows PowerShell:
       ```powershell
       [Convert]::ToBase64String([System.IO.File]::ReadAllBytes("path/to/key.json"))
       ```
     - Linux/macOS:
       ```bash
       base64 -i path/to/key.json
       ```
4. If your bucket permits public access, the dashboard and reports will be accessible at:
   `https://storage.googleapis.com/[BUCKET_NAME]/index.html`

### 3. SendGrid API Setup

1. Sign up for a free account at [SendGrid](https://sendgrid.com).
2. Complete **Single Sender Verification** or **Domain Authentication** (required for email delivery).
3. Create an API Key with **Mail Send** permissions.
4. Copy the API Key.

### 4. GitHub Secrets Configuration

Add the following secrets to your GitHub repository under **Settings -> Secrets and variables -> Actions**:

| Secret Name | Description | Example |
| :--- | :--- | :--- |
| `STRAVA_CLIENT_ID` | Your Strava app client ID | `12345` |
| `STRAVA_CLIENT_SECRET` | Your Strava app client secret | `ab12cd...34ef` |
| `STRAVA_REFRESH_TOKEN` | One-time OAuth refresh token | `xy78zw...90uv` |
| `SENDGRID_API_KEY` | SendGrid Mail Send API Key | `SG.abcdef...` |
| `GCS_BUCKET_NAME` | GCS target bucket name | `my-strava-run-bucket` |
| `GCS_SERVICE_ACCOUNT_KEY` | Base64-encoded GCP service account JSON key | `eyJhY2N...` |
| `EMAIL_TO` | Target recipient email address | `athlete@example.com` |
| `EMAIL_FROM` | Verified SendGrid sender email address | `athlete@example.com` |

---

## 🧪 Local Testing & Simulation

Before configuring secrets on GitHub, you can verify that the pacing engine, HTML templates, Chart.js, and email formats render correctly using mock data:

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
4. Examine the generated dashboard, run reports, and email notifications in the new `mock_gcs` directory:
   - Open `mock_gcs/index.html` in your browser.
   - Open `mock_gcs/email_preview.html` to preview the notification style.
