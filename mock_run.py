import os
import sys
import json
import math
import shutil
from datetime import datetime

# Configure environment variables to pass the analyze.py validations
os.environ['STRAVA_CLIENT_ID'] = 'mock_id'
os.environ['STRAVA_CLIENT_SECRET'] = 'mock_secret'
os.environ['STRAVA_REFRESH_TOKEN'] = 'mock_refresh'
os.environ['GCS_BUCKET_NAME'] = 'mock_bucket'
os.environ['EMAIL_TO'] = 'runner@example.com'

# Import local modules
import analyze
import src.strava_client
import src.gcs_uploader
import src.email_sender

# Define Mocks
class MockStravaClient:
    def __init__(self, client_id, client_secret, refresh_token):
        pass

    def get_recent_activities(self, limit=10, after_timestamp=None):
        return [
            {
                "id": 100000001,
                "name": "Tempo Session along the Seine",
                "type": "Run",
                "start_date_local": "2026-06-11T08:30:00Z"
            },
            {
                "id": 100000002,
                "name": "Sleek Glassmorphic Morning Run",
                "type": "Run",
                "start_date_local": "2026-06-12T07:15:00Z"
            }
        ]

    def get_activity_streams(self, activity_id):
        # Generate time-series data
        # Let's simulate a 6km run with some pace variations, heart rate increase, and elevation profile
        num_points = 500
        time_data = [i * 3 for i in range(num_points)] # 25 minutes total
        
        # Latitude & Longitude moving from Paris Notre-Dame
        lat_start, lon_start = 48.853, 2.3499
        latlng_data = [[lat_start + i * 0.00008, lon_start + i * 0.00012] for i in range(num_points)]
        
        # Altitude profile: rolling hills
        altitude_data = [35.0 + 15.0 * math.sin(i / 40.0) + (i * 0.02) for i in range(num_points)]
        
        # Heart rate: warming up, then steady, then a sprint finish
        heartrate_data = []
        for i in range(num_points):
            if i < 100:
                hr = 100 + i * 0.4
            elif i > 450:
                hr = 140 + (i - 450) * 0.8 # Sprint finish
            else:
                hr = 140 + 5.0 * math.sin(i / 10.0)
            heartrate_data.append(int(hr + (i % 3)))
            
        # Cadence: steady 180spm with minor deviations
        cadence_data = [88 + int(2 * math.sin(i / 15.0)) for i in range(num_points)]
        
        # Velocity in m/s: 3.33 m/s = 5:00/km pace.
        # Let's build a positive split or pace drop towards the end to trigger fatigue detection.
        velocity_data = []
        for i in range(num_points):
            if i < 100: # Warm up
                vel = 2.8 + (i * 0.005) # 6:00/km down to 5:00/km
            elif i > 380: # Fading due to fatigue
                vel = 3.3 - ((i - 380) * 0.006) # Slowing down
            else: # Steady pace
                vel = 3.3 + 0.1 * math.sin(i / 20.0)
            velocity_data.append(vel)
            
        return {
            "time": {"data": time_data},
            "latlng": {"data": latlng_data},
            "altitude": {"data": altitude_data},
            "heartrate": {"data": heartrate_data},
            "cadence": {"data": cadence_data},
            "velocity_smooth": {"data": velocity_data}
        }

class MockGCSUploader:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name
        self.mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_gcs')
        os.makedirs(self.mock_dir, exist_ok=True)
        
    def download_as_string(self, blob_name):
        dest_path = os.path.join(self.mock_dir, blob_name.replace('/', os.sep))
        if os.path.exists(dest_path):
            with open(dest_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None

    def upload_from_string(self, content, destination_blob_name, content_type='application/json', make_public=True):
        dest_path = os.path.join(self.mock_dir, destination_blob_name.replace('/', os.sep))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[Mock GCS] Uploaded string content to mock_gcs/{destination_blob_name}")
        return f"file:///{dest_path.replace(os.sep, '/')}"

    def upload_file(self, source_file_path, destination_blob_name, content_type='text/html', make_public=True):
        dest_path = os.path.join(self.mock_dir, destination_blob_name.replace('/', os.sep))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(source_file_path, dest_path)
        print(f"[Mock GCS] Uploaded file from {source_file_path} to mock_gcs/{destination_blob_name}")
        return f"file:///{dest_path.replace(os.sep, '/')}"

class MockEmailSender:
    def __init__(self, api_key, email_to, email_from=None):
        self.mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_gcs')
        os.makedirs(self.mock_dir, exist_ok=True)

    def send_notification(self, subject, html_content):
        dest_path = os.path.join(self.mock_dir, 'email_preview.html')
        with open(dest_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[Mock Email] Email notification simulated. Preview saved to mock_gcs/email_preview.html")
        return True

# Monkeypatch the modules
src.strava_client.StravaClient = MockStravaClient
src.gcs_uploader.GCSUploader = MockGCSUploader
src.email_sender.EmailSender = MockEmailSender
analyze.StravaClient = MockStravaClient
analyze.GCSUploader = MockGCSUploader
analyze.EmailSender = MockEmailSender

if __name__ == '__main__':
    print("Executing Pipeline local simulation with Mock data...")
    # Run the main entry point which will execute with our patched mock clients
    analyze.main()
    
    print("\nLocal mock simulation completed successfully!")
    print(f"To inspect results, open:")
    mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_gcs')
    print(f"  Dashboard: file:///{os.path.join(mock_dir, 'index.html').replace(os.sep, '/')}")
    print(f"  Email Alert: file:///{os.path.join(mock_dir, 'email_preview.html').replace(os.sep, '/')}")
