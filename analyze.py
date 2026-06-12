import os
import sys
import json
from datetime import datetime
import base64

from src.strava_client import StravaClient
from src.analysis_engine import calculate_metrics, streams_to_trackpoints, format_pace, format_time
from src.report_generator import render_run_report, render_dashboard
from src.gcs_uploader import GCSUploader
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
    
    # 1. Load Configurations from Environment Variables
    strava_client_id = os.environ.get('STRAVA_CLIENT_ID')
    strava_client_secret = os.environ.get('STRAVA_CLIENT_SECRET')
    strava_refresh_token = os.environ.get('STRAVA_REFRESH_TOKEN')
    
    sendgrid_key = os.environ.get('SENDGRID_API_KEY')
    email_to = os.environ.get('EMAIL_TO')
    email_from = os.environ.get('EMAIL_FROM')
    
    gcs_bucket_name = os.environ.get('GCS_BUCKET_NAME')
    
    # Basic Validation
    if not all([strava_client_id, strava_client_secret, strava_refresh_token]):
        print("Error: Missing Strava client configurations. Please set STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, and STRAVA_REFRESH_TOKEN.")
        sys.exit(1)
        
    if not gcs_bucket_name:
        print("Error: GCS_BUCKET_NAME is not set.")
        sys.exit(1)

    # Local Directory Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    temp_output_dir = os.path.join(base_dir, 'temp_output')
    os.makedirs(temp_output_dir, exist_ok=True)
    
    # 2. Initialize Clients
    strava = StravaClient(strava_client_id, strava_client_secret, strava_refresh_token)
    gcs = GCSUploader(gcs_bucket_name)
    email = EmailSender(sendgrid_key, email_to, email_from) if email_to else None
    
    # 3. Retrieve processed runs log from GCS
    runs_log_blob = 'data/runs.json'
    runs_log_str = gcs.download_as_string(runs_log_blob)
    
    if runs_log_str:
        try:
            runs = json.loads(runs_log_str)
            print(f"Loaded {len(runs)} previously processed activities from GCS.")
        except Exception as e:
            print(f"Error parsing runs.json log from GCS: {e}. Starting fresh.")
            runs = []
    else:
        print("No existing runs.json log found on GCS. Starting fresh.")
        runs = []
        
    processed_ids = {run['id'] for run in runs}
    
    # 4. Fetch recent activities from Strava
    print("Fetching athlete activities from Strava...")
    try:
        activities = strava.get_recent_activities(limit=20)
    except Exception as e:
        print(f"Failed to fetch activities from Strava API: {e}")
        sys.exit(1)
        
    new_activities = []
    for act in activities:
        # We only analyze activities that are Runs and not yet processed
        if act.get('type') == 'Run' and act.get('id') not in processed_ids:
            new_activities.append(act)
            
    if not new_activities:
        print("No new run activities found to process. Pipeline is up to date.")
        sys.exit(0)
        
    print(f"Found {len(new_activities)} new run activities to process.")
    
    # Sort chronologically so we update the dashboard database oldest-first
    new_activities.sort(key=lambda x: x.get('start_date_local', ''))
    
    processed_any_new = False
    
    # 5. Process each new run
    for act in new_activities:
        act_id = act['id']
        act_name = act.get('name', f"Run #{act_id}")
        start_date_str = act.get('start_date_local', '')
        date_part = start_date_str.split('T')[0] if 'T' in start_date_str else 'unknown'
        
        print(f"\nProcessing activity: {act_name} (ID: {act_id}, Date: {date_part})")
        
        try:
            # Fetch streams
            streams = strava.get_activity_streams(act_id)
            
            # Reconstruct trackpoints
            points = streams_to_trackpoints(streams, start_date_str)
            if len(points) < 2:
                print(f"Skipping activity {act_id} - insufficient stream trackpoints.")
                continue
                
            # Calculate metrics
            metrics = calculate_metrics(points)
            if not metrics:
                print(f"Skipping activity {act_id} - metric calculation returned None.")
                continue
                
            # Generate local HTML report
            report_filename = f"{date_part}_run_{act_id}.html"
            local_report_path = os.path.join(temp_output_dir, 'reports', report_filename)
            render_run_report(act, metrics, points, template_dir, local_report_path)
            
            # Upload HTML report to GCS
            gcs_report_blob = f"reports/{report_filename}"
            public_report_url = gcs.upload_file(local_report_path, gcs_report_blob, content_type='text/html', make_public=True)
            
            # Construct metadata
            run_meta = {
                "id": act_id,
                "name": act_name,
                "date": date_part,
                "distance_km": metrics['total_distance_km'],
                "elapsed_time_seconds": metrics['elapsed_time_seconds'],
                "moving_time_seconds": metrics['moving_time_seconds'],
                "avg_pace_min_km": metrics['avg_pace_min_km'],
                "total_elevation_gain_m": metrics['total_elevation_gain_m'],
                "pacing_pattern": metrics['pacing_pattern'],
                "avg_heartrate": metrics['avg_heartrate'],
                "report_url": gcs_report_blob # Relative URL works best for static site
            }
            
            runs.append(run_meta)
            processed_any_new = True
            
            # Send Email Notification
            if email:
                # Use public URL for email link
                # E.g. https://storage.googleapis.com/{bucket_name}/reports/{report_filename}
                full_report_url = f"https://storage.googleapis.com/{gcs_bucket_name}/reports/{report_filename}"
                subject = f"Run Analysis — {date_part} | {metrics['total_distance_km']:.2f}km @ {format_pace(metrics['avg_pace_min_km'])}/km"
                email_body = make_email_body(act_name, date_part, metrics, full_report_url)
                email.send_notification(subject, email_body)
                
        except Exception as e:
            print(f"Failed to process activity {act_id}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # 6. Re-generate Dashboard Index and assets if any run was processed
    if processed_any_new:
        # Sort all runs descending by date
        runs.sort(key=lambda x: x['date'], reverse=True)
        
        # Calculate training statistics
        total_runs = len(runs)
        total_distance = sum(r['distance_km'] for r in runs)
        total_elevation = sum(r['total_elevation_gain_m'] for r in runs)
        
        pace_valid_runs = [r['avg_pace_min_km'] for r in runs if r.get('avg_pace_min_km')]
        avg_pace = sum(pace_valid_runs) / len(pace_valid_runs) if pace_valid_runs else None
        
        stats = {
            "total_runs": total_runs,
            "total_distance": total_distance,
            "total_elevation": total_elevation,
            "avg_pace": avg_pace
        }
        
        # Render main dashboard index
        local_index_path = os.path.join(temp_output_dir, 'index.html')
        render_dashboard(runs, stats, template_dir, local_index_path)
        
        # Upload index.html, style.css, and runs.json database
        gcs.upload_file(local_index_path, 'index.html', content_type='text/html', make_public=True)
        
        local_css_path = os.path.join(base_dir, 'assets', 'style.css')
        gcs.upload_file(local_css_path, 'assets/style.css', content_type='text/css', make_public=True)
        
        runs_json_str = json.dumps(runs, indent=2)
        gcs.upload_from_string(runs_json_str, 'data/runs.json', content_type='application/json', make_public=True)
        
        print("\nPipeline execution complete. Dashboard, reports, assets, and database updated on GCS.")
    else:
        print("\nPipeline execution complete. No database updates required.")

if __name__ == '__main__':
    main()
