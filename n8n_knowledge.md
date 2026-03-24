# n8n Agent Knowledge Base

## Error Handling

- A workflow CANNOT handle its own errors in n8n — this is a hard platform limitation.
- The correct pattern requires TWO separate workflows:
  1. **Error Handler Workflow** — contains only: Error Trigger → notification node (Telegram/Slack)
  2. **Main Workflow** — in Settings → "Error Workflow" → set to the Error Handler Workflow ID
- When the main workflow fails, n8n automatically triggers the Error Handler Workflow.
- Error Trigger only fires in production (published + active). It does NOT fire during manual test runs.
- Always publish AND activate the Error Handler Workflow before linking it.

## Workflow Activation

- A workflow must be both **Published** and **Active** to run on triggers (Schedule, Webhook, etc.)
- Manual trigger ("Execute workflow from Manual Trigger") works without being active.
- Error Trigger only fires when the workflow that errors is Active in production.

## Publishing

- Use POST /api/v1/workflows/{id}/activate to activate a workflow via API.
- A workflow with unconnected nodes cannot be published — all nodes must be connected.

## Telegram Notifications

- Bot token: 8600850753:AAFiCwvMtBA6cqo_G-bM75a-l17PafTbcDk
- Chat ID: 6798255669
- API endpoint: https://api.telegram.org/bot{TOKEN}/sendMessage
- Body: { "chat_id": "6798255669", "text": "..." }
- n8n expressions in text field use {{ }} syntax — e.g. {{ $json.workflow.name }}

## Error Trigger Data Fields

When Error Trigger fires, these fields are available in $json:
- $json.workflow.name — name of the failed workflow
- $json.execution.lastNodeExecuted — name of the node that failed
- $json.execution.error.message — error message
- $json.execution.error.stack — stack trace
- $json.execution.url — link to the execution in n8n UI
- $json.execution.id — execution ID

## Useful Test URLs

- https://httpbin.org/status/429 — returns 429 Rate Limit error (reliable)
- https://httpbin.org/status/500 — returns 500 Server Error (reliable)
- https://httpstat.us/500 — unreliable, often offline

## API Notes

- n8n Cloud API base: https://bobdylan.app.n8n.cloud/api/v1
- To update workflow settings (e.g. errorWorkflow): PATCH /workflows/{id} with settings object
- errorWorkflow field goes inside "settings": { "errorWorkflow": "WORKFLOW_ID" }
- Always verify workflow exists before linking it as error handler
