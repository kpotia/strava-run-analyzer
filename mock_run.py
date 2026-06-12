"""
mock_run.py — Local simulation of the analysis pipeline.

Patches StravaClient and EmailSender with lightweight mocks so the full
pipeline can be exercised without real credentials.  All generated output
is written to mock_output/ (mirrors what the CI job writes to output/).
"""
import os
import sys
import math
import shutil

# ── Environment stubs so analyze.py validation passes ─────────────────────
os.environ.setdefault('STRAVA_CLIENT_ID',     'mock_id')
os.environ.setdefault('STRAVA_CLIENT_SECRET', 'mock_secret')
os.environ.setdefault('STRAVA_REFRESH_TOKEN', 'mock_refresh')
os.environ.setdefault('EMAIL_TO',             'runner@example.com')
os.environ.setdefault('DASHBOARD_URL',        'http://localhost/mock_output')

# Point the pipeline at our local mock output directory
MOCK_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_output')
os.environ['OUTPUT_DIR'] = MOCK_OUTPUT_DIR

# ── Import modules before patching ─────────────────────────────────────────
import src.strava_client
import src.email_sender
import analyze


# ══════════════════════════════════════════════════════════════════════════
# Mock: Strava client — returns two synthetic runs
# ══════════════════════════════════════════════════════════════════════════
class MockStravaClient:
    def __init__(self, client_id, client_secret, refresh_token):
        pass

    def get_recent_activities(self, limit=10, after_timestamp=None):
        return [
            {
                "id": 100000001,
                "name": "Tempo Session along the Seine",
                "type": "Run",
                "start_date_local": "2026-06-11T08:30:00Z",
            },
            {
                "id": 100000002,
                "name": "Sleek Glassmorphic Morning Run",
                "type": "Run",
                "start_date_local": "2026-06-12T07:15:00Z",
            },
        ]

    def get_activity_streams(self, activity_id):
        """Simulates a 6 km run (~25 min) with realistic pace/HR/cadence."""
        num_points = 500
        time_data  = [i * 3 for i in range(num_points)]

        lat_start, lon_start = 48.853, 2.3499
        latlng_data = [
            [lat_start + i * 0.00008, lon_start + i * 0.00012]
            for i in range(num_points)
        ]

        altitude_data = [
            35.0 + 15.0 * math.sin(i / 40.0) + (i * 0.02)
            for i in range(num_points)
        ]

        heartrate_data = []
        for i in range(num_points):
            if i < 100:
                hr = 100 + i * 0.4
            elif i > 450:
                hr = 140 + (i - 450) * 0.8
            else:
                hr = 140 + 5.0 * math.sin(i / 10.0)
            heartrate_data.append(int(hr + (i % 3)))

        cadence_data  = [88 + int(2 * math.sin(i / 15.0)) for i in range(num_points)]

        velocity_data = []
        for i in range(num_points):
            if i < 100:
                vel = 2.8 + (i * 0.005)
            elif i > 380:
                vel = 3.3 - ((i - 380) * 0.006)
            else:
                vel = 3.3 + 0.1 * math.sin(i / 20.0)
            velocity_data.append(vel)

        return {
            "time":           {"data": time_data},
            "latlng":         {"data": latlng_data},
            "altitude":       {"data": altitude_data},
            "heartrate":      {"data": heartrate_data},
            "cadence":        {"data": cadence_data},
            "velocity_smooth":{"data": velocity_data},
        }


# ══════════════════════════════════════════════════════════════════════════
# Mock: Email sender — saves the HTML to mock_output/email_preview.html
# ══════════════════════════════════════════════════════════════════════════
class MockEmailSender:
    def __init__(self, api_key, email_to, email_from=None):
        os.makedirs(MOCK_OUTPUT_DIR, exist_ok=True)

    def send_notification(self, subject, html_content):
        preview_path = os.path.join(MOCK_OUTPUT_DIR, 'email_preview.html')
        with open(preview_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[Mock Email] Preview saved -> {preview_path}")
        return True


# ══════════════════════════════════════════════════════════════════════════
# Monkeypatch
# ══════════════════════════════════════════════════════════════════════════
src.strava_client.StravaClient = MockStravaClient
src.email_sender.EmailSender   = MockEmailSender
analyze.StravaClient           = MockStravaClient
analyze.EmailSender            = MockEmailSender


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    # Wipe the mock output dir on each run so we always get a clean slate
    if os.path.exists(MOCK_OUTPUT_DIR):
        shutil.rmtree(MOCK_OUTPUT_DIR)
    os.makedirs(MOCK_OUTPUT_DIR)

    print("=" * 60)
    print("RunLens — Local Mock Simulation")
    print("=" * 60)

    analyze.main()

    print("\n" + "=" * 60)
    print("Simulation complete!  Inspect the generated site:")
    print(f"  Dashboard : file:///{os.path.join(MOCK_OUTPUT_DIR, 'index.html').replace(os.sep, '/')}")
    print(f"  Email     : file:///{os.path.join(MOCK_OUTPUT_DIR, 'email_preview.html').replace(os.sep, '/')}")
