import os
import requests

class EmailSender:
    def __init__(self, api_key, email_to, email_from=None):
        self.api_key = api_key
        self.email_to = email_to
        # Default to EMAIL_TO if EMAIL_FROM is not specified (assists with Single Sender Verification)
        self.email_from = email_from or email_to

    def send_notification(self, subject, html_content):
        """Sends an HTML email notification via the SendGrid HTTP API."""
        if not self.api_key:
            print("Warning: SENDGRID_API_KEY is not set. Skipping email notification.")
            return False

        print(f"Sending email notification to {self.email_to} from {self.email_from}...")
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "personalizations": [{
                "to": [{"email": self.email_to}]
            }],
            "from": {
                "email": self.email_from,
                "name": "Strava Run Analyzer"
            },
            "subject": subject,
            "content": [{
                "type": "text/html",
                "value": html_content
            }]
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code in [200, 201, 202]:
                print("Email notification sent successfully.")
                return True
            else:
                print(f"Failed to send email. Status code: {response.status_code}. Response: {response.text}")
                return False
        except Exception as e:
            print(f"Error sending email via SendGrid: {e}")
            return False
