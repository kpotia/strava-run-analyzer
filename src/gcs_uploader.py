import os
import json
import base64
from google.cloud import storage
from google.oauth2 import service_account

class GCSUploader:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name
        self.client = self._init_client()
        self.bucket = self.client.bucket(self.bucket_name)

    def _init_client(self):
        """Initializes the GCP Storage Client using credentials or environment defaults."""
        gcs_key = os.environ.get('GCS_SERVICE_ACCOUNT_KEY')
        if gcs_key:
            try:
                # Try decoding base64 first
                decoded = base64.b64decode(gcs_key).decode('utf-8')
                info = json.loads(decoded)
                print("Authenticated to GCP using base64-encoded GCS_SERVICE_ACCOUNT_KEY.")
            except Exception:
                try:
                    # Fallback to direct JSON string
                    info = json.loads(gcs_key)
                    print("Authenticated to GCP using raw JSON GCS_SERVICE_ACCOUNT_KEY.")
                except Exception as e:
                    print(f"Error parsing GCS_SERVICE_ACCOUNT_KEY, falling back to default authentication: {e}")
                    return storage.Client()
            
            credentials = service_account.Credentials.from_service_account_info(info)
            return storage.Client(credentials=credentials)
        else:
            print("No GCS_SERVICE_ACCOUNT_KEY found. Authenticating to GCP using default credentials (local / IAM role).")
            return storage.Client()

    def download_as_string(self, blob_name):
        """Downloads a blob directly as a string. Returns None if the blob does not exist."""
        blob = self.bucket.blob(blob_name)
        if not blob.exists():
            print(f"Blob '{blob_name}' does not exist in bucket '{self.bucket_name}'.")
            return None
        return blob.download_as_text()

    def upload_from_string(self, content, destination_blob_name, content_type='application/json', make_public=True):
        """Uploads a string directly to GCS."""
        print(f"Uploading content to gs://{self.bucket_name}/{destination_blob_name}...")
        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_string(content, content_type=content_type)
        if make_public:
            try:
                blob.make_public()
            except Exception as e:
                print(f"Warning: Could not make gs://{self.bucket_name}/{destination_blob_name} public: {e}")
        return blob.public_url

    def upload_file(self, source_file_path, destination_blob_name, content_type='text/html', make_public=True):
        """Uploads a local file to GCS."""
        print(f"Uploading {source_file_path} to gs://{self.bucket_name}/{destination_blob_name}...")
        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_path, content_type=content_type)
        if make_public:
            try:
                blob.make_public()
            except Exception as e:
                print(f"Warning: Could not make gs://{self.bucket_name}/{destination_blob_name} public: {e}")
        return blob.public_url
