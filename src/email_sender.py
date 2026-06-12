import os
import requests

class EmailSender:
    def __init__(self, api_key, email_to, email_from=None):
        self.api_key = api_key
        self.email_to = email_to
        self.email_from = email_from or email_to

    def send_notification(self, subject, html_content):
        """Sends an HTML email notification via the Resend HTTP API."""
        if not self.api_key:
            print("Warning: RESEND_API_KEY is not set. Skipping email notification.")
            return False

        print(f"Sending email notification to {self.email_to} via Resend...")
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "from": self.email_from,
            "to": [self.email_to],
            "subject": subject,
            "html": html_content
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code in [200, 202]:
                print("Email notification sent successfully via Resend.")
                return True
            else:
                print(f"Failed to send email. Status code: {response.status_code}. Response: {response.text}")
                return False
        except Exception as e:
            print(f"Error sending email via Resend: {e}")
            return False
