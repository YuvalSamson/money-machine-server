"""
moneyMachine — Flask server (Render)
Endpoints:
  POST /chat        — proxy to Claude with job context
  POST /bid         — submit bid via Freelancer API (or log approval)
  POST /notify      — called by n8n to push job to app (via FCM V1)
  POST /agent/task  — n8n-agent: receive task, run autonomously, report via Telegram
  GET  /agent/workflows — quick list of all n8n workflows
"""

import os
import json
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Env vars ─────────────────────────────────────────────────────────────────
ANTHROPIC_KEY       = os.environ.get("ANTHROPIC_API_KEY", "")
FREELANCER_TOKEN    = os.environ.get("FREELANCER_API_TOKEN", "")
FCM_SERVICE_ACCOUNT = os.environ.get("FCM_SERVICE_ACCOUNT", "")
EXPO_PUSH_TOKEN     = os.environ.get("EXPO_PUSH_TOKEN", "")
FCM_TOKEN           = os.environ.get("FCM_DEVICE_TOKEN", "")
N8N_BASE_URL        = os.environ.get("N8N_BASE_URL", "https://bobdylan.app.n8n.cloud")
N8N_API_KEY         = os.environ.get("N8N_API_KEY", "")
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "6798255669")


# ══════════════════════════════════════════════════════════════════════════════
# EXISTING: FCM / Expo helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_fcm_access_token():
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
                    "notification": {"sound": "default", "channel_id": "default"}
                }
            }
        }
        res = requests.post(
            url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload
        )
        return res.json()
    except Exception as e:
        return {"error": str(e)}


def send_expo_push(data: dict):
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


# ══════════════════════════════════════════════════════════════════════════════
# EXISTING: Chat proxy
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# EXISTING: Bid + Notify
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/bid", methods=["POST"])
def bid():
    data = request.json
    action = data.get("action", "")
    link = data.get("link", "")
    if action != "approve":
        return jsonify({"status": "rejected"})
    print(f"[BID APPROVED] {link}")
    return jsonify({"status": "approved", "link": link})


@app.route("/notify", methods=["POST"])
def notify():
    data = request.json
    if FCM_SERVICE_ACCOUNT and FCM_TOKEN:
        result = send_fcm_v1(data)
        return jsonify({"status": "sent", "method": "fcm_v1", "result": result})
    elif EXPO_PUSH_TOKEN:
        result = send_expo_push(data)
        return jsonify({"status": "sent", "method": "expo", "result": result})
    else:
        return jsonify({"error": "No push credentials configured"}), 400


# ══════════════════════════════════════════════════════════════════════════════
# NEW: n8n-agent
# ══════════════════════════════════════════════════════════════════════════════

def n8n_headers():
    return {
        "X-N8N-API-KEY": N8N_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def n8n_get(path):
    r = requests.get(f"{N8N_BASE_URL}/api/v1{path}", headers=n8n_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

def n8n_post(path, body=None):
    r = requests.post(f"{N8N_BASE_URL}/api/v1{path}", headers=n8n_headers(), json=body or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def n8n_patch(path, body):
    r = requests.patch(f"{N8N_BASE_URL}/api/v1{path}", headers=n8n_headers(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()

def n8n_delete(path):
    r = requests.delete(f"{N8N_BASE_URL}/api/v1{path}", headers=n8n_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

def telegram_send(text, chat_id=None):
    if not TELEGRAM_BOT_TOKEN:
        print(f"[Telegram] {text}")
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        timeout=10
    )

AGENT_TOOLS = [
    {
        "name": "list_workflows",
        "description": "List all n8n workflows. Returns id, name, active status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "active_only": {"type": "boolean", "description": "Return only active workflows."}
            },
            "required": []
        }
    },
    {
        "name": "get_workflow",
        "description": "Get full details of a workflow by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"}
            },
            "required": ["workflow_id"]
        }
    },
    {
        "name": "create_workflow",
        "description": "Create a new n8n workflow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "nodes": {"type": "array"},
                "connections": {"type": "object"},
                "settings": {"type": "object"}
            },
            "required": ["name", "nodes", "connections"]
        }
    },
    {
        "name": "update_workflow",
        "description": "Update an existing workflow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "name": {"type": "string"},
                "nodes": {"type": "array"},
                "connections": {"type": "object"}
            },
            "required": ["workflow_id"]
        }
    },
    {
        "name": "activate_workflow",
        "description": "Activate a workflow.",
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"]
        }
    },
    {
        "name": "deactivate_workflow",
        "description": "Deactivate a workflow.",
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"]
        }
    },
    {
        "name": "delete_workflow",
        "description": "Delete a workflow permanently.",
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"]
        }
    },
    {
        "name": "list_executions",
        "description": "List recent executions, optionally filtered by workflow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": []
        }
    },
    {
        "name": "get_execution",
        "description": "Get details of a specific execution.",
        "input_schema": {
            "type": "object",
            "properties": {"execution_id": {"type": "string"}},
            "required": ["execution_id"]
        }
    },
    {
        "name": "telegram_report",
        "description": "Send a message to the user via Telegram.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"]
        }
    }
]

def execute_agent_tool(tool_name, tool_input):
    try:
        if tool_name == "list_workflows":
            data = n8n_get("/workflows")
            workflows = data.get("data", [])
            if tool_input.get("active_only"):
                workflows = [w for w in workflows if w.get("active")]
            return json.dumps([{"id": w["id"], "name": w["name"], "active": w.get("active", False)} for w in workflows])

        elif tool_name == "get_workflow":
            return json.dumps(n8n_get(f"/workflows/{tool_input['workflow_id']}"))

        elif tool_name == "create_workflow":
            body = {
                "name": tool_input["name"],
                "nodes": tool_input["nodes"],
                "connections": tool_input["connections"],
                "settings": tool_input.get("settings", {"executionOrder": "v1"}),
                "staticData": None
            }
            return json.dumps(n8n_post("/workflows", body))

        elif tool_name == "update_workflow":
            wf_id = tool_input.pop("workflow_id")
            return json.dumps(n8n_patch(f"/workflows/{wf_id}", tool_input))

        elif tool_name == "activate_workflow":
            return json.dumps(n8n_post(f"/workflows/{tool_input['workflow_id']}/activate"))

        elif tool_name == "deactivate_workflow":
            return json.dumps(n8n_post(f"/workflows/{tool_input['workflow_id']}/deactivate"))

        elif tool_name == "delete_workflow":
            return json.dumps(n8n_delete(f"/workflows/{tool_input['workflow_id']}"))

        elif tool_name == "list_executions":
            path = "/executions"
            params = [f"limit={tool_input.get('limit', 20)}"]
            if tool_input.get("workflow_id"):
                params.append(f"workflowId={tool_input['workflow_id']}")
            return json.dumps(n8n_get(path + "?" + "&".join(params)))

        elif tool_name == "get_execution":
            return json.dumps(n8n_get(f"/executions/{tool_input['execution_id']}"))

        elif tool_name == "telegram_report":
            telegram_send(tool_input["message"])
            return json.dumps({"sent": True})

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


AGENT_SYSTEM_PROMPT = """You are n8n-agent, an autonomous AI assistant that manages n8n workflows.
You receive tasks in natural language and execute them via the n8n API.

Your capabilities:
- List, create, update, activate/deactivate, delete workflows
- Check execution status and results
- Report progress and results to the user via Telegram

Workflow:
1. Understand the task
2. Use tools to gather context (list workflows, check executions, etc.)
3. Execute the requested action
4. Verify the result
5. Send a final Telegram report with what was done and the outcome

Always send a Telegram report at the end — even on errors.
Be concise and efficient.
When creating workflows, build complete valid n8n JSON including all required node parameters.
"""

def run_agent(task):
    messages = [{"role": "user", "content": task}]
    telegram_send(f"🤖 *n8n-agent* קיבל משימה:\n`{task}`")

    for _ in range(20):
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-5",
                "max_tokens": 4096,
                "system": AGENT_SYSTEM_PROMPT,
                "tools": AGENT_TOOLS,
                "messages": messages,
            },
            timeout=120
        ).json()

        content = response.get("content", [])
        messages.append({"role": "assistant", "content": content})

        stop_reason = response.get("stop_reason")

        if stop_reason == "end_turn":
            final = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
            return {"status": "done", "result": final}

        if stop_reason == "tool_use":
            tool_results = []
            for block in content:
                if block.get("type") == "tool_use":
                    result = execute_agent_tool(block["name"], block["input"])
                    print(f"[Agent] {block['name']} → {result[:200]}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return {"status": "max_iterations_reached"}


@app.route("/agent/task", methods=["POST"])
def agent_task():
    data = request.get_json(force=True)
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"error": "Missing 'task' field"}), 400

    if data.get("async", False):
        threading.Thread(target=run_agent, args=(task,), daemon=True).start()
        return jsonify({"status": "accepted", "message": "Agent started, results via Telegram"})

    result = run_agent(task)
    return jsonify(result)


@app.route("/agent/workflows", methods=["GET"])
def agent_workflows():
    try:
        return jsonify(n8n_get("/workflows"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# Health check
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "moneyMachine server running"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
