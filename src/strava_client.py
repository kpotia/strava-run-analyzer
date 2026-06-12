import requests
import time

class StravaClient:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expires_at = 0

    def _refresh_access_token(self):
        """Refreshes the access token using the refresh token if expired."""
        if self.access_token and time.time() < self.token_expires_at - 60:
            return self.access_token

        print("Refreshing Strava access token...")
        url = 'https://www.strava.com/oauth/token'
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        res_json = response.json()
        
        self.access_token = res_json['access_token']
        self.token_expires_at = res_json['expires_at']
        if 'refresh_token' in res_json:
            self.refresh_token = res_json['refresh_token']
            
        return self.access_token

    def get_headers(self):
        token = self._refresh_access_token()
        return {'Authorization': f'Bearer {token}'}

    def get_recent_activities(self, limit=10, after_timestamp=None):
        """
        Fetches recent athlete activities.
        limit: Number of activities to fetch.
        after_timestamp: Epoch timestamp to filter activities after.
        """
        url = 'https://www.strava.com/api/v3/athlete/activities'
        headers = self.get_headers()
        params = {'per_page': limit}
        if after_timestamp:
            params['after'] = int(after_timestamp)
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_activity_streams(self, activity_id):
        """
        Fetches raw stream data for an activity.
        Returns a dictionary keyed by type (e.g. latlng, altitude, etc.)
        """
        types = ['time', 'latlng', 'distance', 'altitude', 'heartrate', 'cadence', 'velocity_smooth']
        url = f'https://www.strava.com/api/v3/activities/{activity_id}/streams'
        headers = self.get_headers()
        params = {
            'keys': ','.join(types),
            'key_by_type': 'true'
        }
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
