"""
moneyMachine — Flask server (Render)
Endpoints:
  POST /chat   — proxy to Claude with job context
  POST /bid    — submit bid via Freelancer API (or log approval)
  POST /notify — called by n8n to push job to app (via Expo push)
"""

import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FREELANCER_TOKEN = os.environ.get("FREELANCER_API_TOKEN", "")
EXPO_PUSH_TOKEN = os.environ.get("EXPO_PUSH_TOKEN", "")  # Your device token


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

    # TODO: Extract project ID from link and call Freelancer API
    # project_id = link.split("/")[-1].split("?")[0]
    # freelancer_bid_response = submit_freelancer_bid(project_id)

    print(f"[BID APPROVED] {link}")
    return jsonify({"status": "approved", "link": link})


# ─── Push notification from n8n ───────────────────────────────────────────────

@app.route("/notify", methods=["POST"])
def notify():
    """
    Called by n8n when a job scores >= 8.
    Sends Expo push notification to your device.
    Body: { title, link, score, reason, budget, timeline, description }
    """
    data = request.json

    if not EXPO_PUSH_TOKEN:
        return jsonify({"error": "No Expo push token configured"}), 400

    push_payload = {
        "to": EXPO_PUSH_TOKEN,
        "title": f"💰 New Job (Score {data.get('score', '?')}/10)",
        "body": data.get("title", "New freelance job available"),
        "data": data,  # Full job data passed to app
        "sound": "default",
    }

    res = requests.post(
        "https://exp.host/--/api/v2/push/send",
        json=push_payload,
        headers={"Content-Type": "application/json"},
    )

    return jsonify({"status": "sent", "expo_response": res.json()})


# ─── Health check ─────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "moneyMachine server running"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
