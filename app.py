"""
moneyMachine — Flask server (Render)
Endpoints:
  POST /chat   — proxy to Claude with job context
  POST /bid    — submit bid via Freelancer API (or log approval)
  POST /notify — called by n8n to push job to app (via FCM V1)
"""

import os
import json
import requests
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FREELANCER_TOKEN = os.environ.get("FREELANCER_API_TOKEN", "")
FCM_SERVICE_ACCOUNT = os.environ.get("FCM_SERVICE_ACCOUNT", "")  # JSON string
EXPO_PUSH_TOKEN = os.environ.get("EXPO_PUSH_TOKEN", "")
FCM_TOKEN = os.environ.get("FCM_DEVICE_TOKEN", "")  # Native FCM token


def get_fcm_access_token():
    """Get OAuth2 access token from service account for FCM V1."""
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account

        service_account_info = json.loads(FCM_SERVICE_ACCOUNT)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
    except Exception as e:
        print(f"Error getting FCM access token: {e}")
        return None


def send_fcm_v1(data: dict):
    """Send push notification via FCM V1 API."""
    try:
        service_account_info = json.loads(FCM_SERVICE_ACCOUNT)
        project_id = service_account_info.get("project_id", "")
        access_token = get_fcm_access_token()

        if not access_token:
            return {"error": "Could not get FCM access token"}

        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

        payload = {
            "message": {
                "token": FCM_TOKEN,
                "notification": {
                    "title": f"💰 New Job (Score {data.get('score', '?')}/10)",
                    "body": data.get("title", "New freelance job available"),
                },
                "data": {k: str(v) for k, v in data.items()},
                "android": {
                    "priority": "high",
                    "notification": {
                        "sound": "default",
                        "channel_id": "default"
                    }
                }
            }
        }

        res = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json=payload
        )
        return res.json()
    except Exception as e:
        return {"error": str(e)}


def send_expo_push(data: dict):
    """Send push notification via Expo Push API (fallback)."""
    push_payload = {
        "to": EXPO_PUSH_TOKEN,
        "title": f"💰 New Job (Score {data.get('score', '?')}/10)",
        "body": data.get("title", "New freelance job available"),
        "data": data,
        "sound": "default",
    }
    res = requests.post(
        "https://exp.host/--/api/v2/push/send",
        json=push_payload,
        headers={"Content-Type": "application/json"},
    )
    return res.json()


# ─── Chat proxy ───────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])
    job = data.get("job_context", {})

    system_prompt = f"""You are a freelance advisor helping evaluate and bid on a job.

Job: {job.get('title', '')}
Description: {job.get('description', '')}
Budget: {job.get('budget', 'unknown')}
Score: {job.get('score', '?')}/10
Reason: {job.get('reason', '')}

Answer concisely and practically. Help the freelancer decide whether to bid and how much."""

    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 512,
            "system": system_prompt,
            "messages": messages,
        },
    )
    result = res.json()
    reply = result.get("content", [{}])[0].get("text", "Error from Claude.")
    return jsonify({"reply": reply})


# ─── Bid submission ───────────────────────────────────────────────────────────

@app.route("/bid", methods=["POST"])
def bid():
    data = request.json
    link = data.get("link", "")
    action = data.get("action", "")

    if action != "approve":
        return jsonify({"status": "rejected"})

    print(f"[BID APPROVED] {link}")
    return jsonify({"status": "approved", "link": link})


# ─── Push notification from n8n ───────────────────────────────────────────────

@app.route("/notify", methods=["POST"])
def notify():
    data = request.json

    # Try FCM V1 first, fall back to Expo
    if FCM_SERVICE_ACCOUNT and FCM_TOKEN:
        result = send_fcm_v1(data)
        return jsonify({"status": "sent", "method": "fcm_v1", "result": result})
    elif EXPO_PUSH_TOKEN:
        result = send_expo_push(data)
        return jsonify({"status": "sent", "method": "expo", "result": result})
    else:
        return jsonify({"error": "No push credentials configured"}), 400


# ─── Health check ─────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "moneyMachine server running"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
