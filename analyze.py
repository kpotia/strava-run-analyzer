import os
import sys
import json
from datetime import datetime

from src.strava_client import StravaClient
from src.analysis_engine import calculate_metrics, streams_to_trackpoints, format_pace, format_time
from src.report_generator import render_run_report, render_dashboard
from src.dashboard_generator import LocalSiteManager
from src.email_sender import EmailSender


def make_email_body(activity_name, date_str, metrics, report_url):
    """Generates an HTML email body with coaching feedback and stats."""
    hr_text = f"<li><strong>Average Heart Rate:</strong> {metrics['avg_heartrate']:.1f} bpm</li>" if metrics.get('avg_heartrate') else ""
    cad_text = f"<li><strong>Average Cadence:</strong> {metrics['avg_cadence']:.1f} spm</li>" if metrics.get('avg_cadence') else ""

    # Generate notes list
    notes = []
    if metrics['pause_count'] > 0:
        notes.append(f"• {metrics['pause_count']} pause(s) detected — consider continuous running for endurance.")
    if metrics.get('negative_split'):
        notes.append("• Excellent negative split — strong finish!")
    elif metrics['split_delta_seconds'] and metrics['split_delta_seconds'] > 60:
        notes.append(f"• Significant fade in second half (+{metrics['split_delta_seconds']:.0f}s difference). Work on early pacing discipline.")
    if metrics['fatigue_onset_km']:
        notes.append(f"• Fatigue onset at KM {metrics['fatigue_onset_km']} — build aerobic base with consistent long runs.")

    notes_html = "".join([f"<li>{n}</li>" for n in notes]) if notes else "<li>Solid run! Keep building consistency.</li>"

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333333; line-height: 1.6;">
        <h2 style="color: #6366f1;">New Run Analysis: {activity_name}</h2>
        <p>A new run from <strong>{date_str}</strong> has been processed.</p>
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
          <ul style="list-style: none; padding-left: 0; margin: 0;">
            <li><strong>Distance:</strong> {metrics['total_distance_km']:.2f} km</li>
            <li><strong>Duration:</strong> {format_time(metrics['moving_time_seconds'])}</li>
            <li><strong>Average Pace:</strong> {format_pace(metrics['avg_pace_min_km'])} /km</li>
            {hr_text}
            {cad_text}
            <li><strong>Pacing Pattern:</strong> {metrics['pacing_pattern']}</li>
          </ul>
        </div>
        <h3 style="color: #4f46e5;">Coach Notes</h3>
        <ul style="padding-left: 20px; margin-bottom: 25px; color: #475569;">
          {notes_html}
        </ul>
        <p><a href="{report_url}" style="background-color: #6366f1; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">View Interactive Report</a></p>
        <p style="color: #64748b; font-size: 0.8rem; margin-top: 30px;">Sent automatically by RunLens Run Analysis Pipeline.</p>
      </body>
    </html>
    """
    return html


def main():
    print("Starting Strava Run Analysis Pipeline...")

    # ── 1. Load configurations from environment variables ──────────────
    strava_client_id     = os.environ.get('STRAVA_CLIENT_ID')
    strava_client_secret = os.environ.get('STRAVA_CLIENT_SECRET')
    strava_refresh_token = os.environ.get('STRAVA_REFRESH_TOKEN')

    sendgrid_key = os.environ.get('SENDGRID_API_KEY')
    email_to     = os.environ.get('EMAIL_TO')
    email_from   = os.environ.get('EMAIL_FROM')

    # Dashboard URL exposed by Vercel (used in email links and back-nav)
    dashboard_url = os.environ.get('DASHBOARD_URL', '')

    # Basic validation
    if not all([strava_client_id, strava_client_secret, strava_refresh_token]):
        print("Error: Missing Strava credentials. Set STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN.")
        sys.exit(1)

    # ── 2. Resolve directory paths ─────────────────────────────────────
    base_dir      = os.path.dirname(os.path.abspath(__file__))
    template_dir  = os.path.join(base_dir, 'templates')
    assets_dir    = os.path.join(base_dir, 'assets')

    # The output dir can be overridden by env var (used in CI where it is
    # checked out as a git worktree at a specific path).
    output_dir = os.environ.get('OUTPUT_DIR', os.path.join(base_dir, 'output'))

    # ── 3. Initialise clients ──────────────────────────────────────────
    strava = StravaClient(strava_client_id, strava_client_secret, strava_refresh_token)
    site   = LocalSiteManager(output_dir, assets_dir)
    email  = EmailSender(sendgrid_key, email_to, email_from) if email_to else None

    # Copy stylesheet into output/assets/
    site.sync_assets()

    # ── 4. Load historical run archive ─────────────────────────────────
    runs = site.load_runs()
    processed_ids = {run['id'] for run in runs}

    # ── 5. Fetch recent Strava activities ──────────────────────────────
    print("Fetching athlete activities from Strava...")
    try:
        activities = strava.get_recent_activities(limit=20)
    except Exception as e:
        print(f"Failed to fetch activities from Strava API: {e}")
        sys.exit(1)

    new_activities = [
        act for act in activities
        if act.get('type') == 'Run' and act.get('id') not in processed_ids
    ]

    if not new_activities:
        print("No new run activities found. Pipeline is up to date.")
        sys.exit(0)

    print(f"Found {len(new_activities)} new run(s) to process.")
    # Sort chronologically so the archive is updated oldest-first
    new_activities.sort(key=lambda x: x.get('start_date_local', ''))

    processed_any_new = False

    # ── 6. Process each new run ────────────────────────────────────────
    for act in new_activities:
        act_id    = act['id']
        act_name  = act.get('name', f"Run #{act_id}")
        start_str = act.get('start_date_local', '')
        date_part = start_str.split('T')[0] if 'T' in start_str else 'unknown'

        print(f"\nProcessing: {act_name} (ID: {act_id}, Date: {date_part})")

        try:
            # Fetch streams
            streams = strava.get_activity_streams(act_id)

            # Reconstruct trackpoints
            points = streams_to_trackpoints(streams, start_str)
            if len(points) < 2:
                print(f"Skipping {act_id} — insufficient stream data.")
                continue

            # Calculate metrics
            metrics = calculate_metrics(points)
            if not metrics:
                print(f"Skipping {act_id} — metric calculation returned None.")
                continue

            # Generate HTML report
            report_filename = f"{date_part}_run_{act_id}.html"
            local_report_path = site.report_path(report_filename)
            render_run_report(act, metrics, points, template_dir, local_report_path)

            # Build the relative URL used both in the dashboard and the email
            relative_url = site.report_url(report_filename)

            # Construct metadata record
            run_meta = {
                "id":                    act_id,
                "name":                  act_name,
                "date":                  date_part,
                "distance_km":           metrics['total_distance_km'],
                "elapsed_time_seconds":  metrics['elapsed_time_seconds'],
                "moving_time_seconds":   metrics['moving_time_seconds'],
                "avg_pace_min_km":       metrics['avg_pace_min_km'],
                "total_elevation_gain_m": metrics['total_elevation_gain_m'],
                "pacing_pattern":        metrics['pacing_pattern'],
                "avg_heartrate":         metrics['avg_heartrate'],
                "report_url":            relative_url,
            }
            runs.append(run_meta)
            processed_any_new = True

            # Send email notification
            if email:
                # Construct full URL: prefer the live dashboard URL, fall back to relative
                if dashboard_url:
                    full_report_url = f"{dashboard_url.rstrip('/')}/{relative_url}"
                else:
                    full_report_url = relative_url

                subject = (
                    f"Run Analysis — {date_part} | "
                    f"{metrics['total_distance_km']:.2f}km @ "
                    f"{format_pace(metrics['avg_pace_min_km'])}/km"
                )
                email_body = make_email_body(act_name, date_part, metrics, full_report_url)
                email.send_notification(subject, email_body)

        except Exception as e:
            print(f"Failed to process activity {act_id}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # ── 7. Rebuild dashboard & persist archive ─────────────────────────
    if processed_any_new:
        # Sort all runs newest-first for the dashboard
        runs.sort(key=lambda x: x['date'], reverse=True)

        # Aggregate stats
        total_runs      = len(runs)
        total_distance  = sum(r['distance_km'] for r in runs)
        total_elevation = sum(r['total_elevation_gain_m'] for r in runs)
        pace_values     = [r['avg_pace_min_km'] for r in runs if r.get('avg_pace_min_km')]
        avg_pace        = sum(pace_values) / len(pace_values) if pace_values else None

        stats = {
            "total_runs":      total_runs,
            "total_distance":  total_distance,
            "total_elevation": total_elevation,
            "avg_pace":        avg_pace,
        }

        # Render dashboard HTML
        dashboard_html = render_dashboard(runs, stats, template_dir)
        site.save_index(dashboard_html)

        # Persist updated archive
        site.save_runs(runs)

        print("\nPipeline complete. Dashboard and archive updated.")
    else:
        print("\nPipeline complete. No new data to save.")


if __name__ == '__main__':
    main()
