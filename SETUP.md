# moneyMachine — Setup Guide

## Architecture

```
n8n (Score ≥ 8)
  → POST /notify on Flask server
    → Expo Push Notification → your phone
      → App opens, shows job details + AI score
        → You approve / reject
          → POST /bid on Flask server
            → Freelancer API submits bid
```

---

## Step 1 — Install dependencies

```bash
cd moneyMachine
npx expo install expo-notifications expo-device expo-constants
```

---

## Step 2 — Get your Expo Push Token

Run the app on your physical device:
```bash
npx expo start
```

The token prints in the console as:
```
Expo Push Token: ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]
```

---

## Step 3 — Flask server (Render)

Set these environment variables in Render:
```
ANTHROPIC_API_KEY=sk-ant-...
EXPO_PUSH_TOKEN=ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]
FREELANCER_API_TOKEN=...  (optional, for auto-bid)
```

Deploy `server/app.py` to Render.

---

## Step 4 — n8n: replace Telegram Alert with Notify App

After "Pick Best Job", add an HTTP Request node:
- Method: POST
- URL: `https://your-flask-server.onrender.com/notify`
- Body: use the code in `n8n/notify_node.js`

Also update the Claude prompt in "Parse Jobs" to return:
```json
{
  "score": 9,
  "relevant": true,
  "title": "...",
  "link": "...",
  "reason": "...",
  "budget": "$250-750 USD",
  "timeline": "3-7 days",
  "description": "full job description"
}
```

---

## Step 5 — Update FLASK_SERVER in the app

In `app/index.tsx`, line 56:
```ts
const FLASK_SERVER = 'https://your-actual-server.onrender.com';
```

---

## File Structure

```
moneyMachine/
├── app/
│   └── index.tsx          ← Main screen (job details + chat + approve/reject)
├── hooks/
│   └── usePushNotifications.ts  ← Push token registration + listener
├── server/
│   └── app.py             ← Flask server (deploy to Render)
├── n8n/
│   └── notify_node.js     ← n8n code for the Notify App node
└── SETUP.md               ← This file
```
