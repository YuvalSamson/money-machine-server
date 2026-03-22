// ─── n8n: "Notify App" node ───────────────────────────────────────────────────
// Place this node AFTER "Pick Best Job"
// Node type: HTTP Request
// Method: POST
// URL: https://your-flask-server.onrender.com/notify

// Body (JSON):
const job = $input.first().json;

if (job.skipped) {
  return [{ json: { sent: false, reason: 'score too low' } }];
}

return [{
  json: {
    title: job.title,
    link: job.link,
    score: job.score,
    reason: job.reason,
    budget: job.budget || '',
    timeline: job.timeline || '',
    description: job.description || '',
  }
}];

// ─── UPDATED: Pick Best Job node ─────────────────────────────────────────────
// Also extract budget/timeline from description for the app

/*
const items = $input.all();
let best = null;
let bestScore = 0;

for (const item of items) {
  const content = item.json.content?.[0]?.text || '';
  try {
    const clean = content.replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(clean);
    if (parsed.score > bestScore) {
      bestScore = parsed.score;
      best = {
        score: parsed.score,
        reason: parsed.reason,
        title: parsed.title || '',
        link: parsed.link || '',
        description: parsed.description || '',
        budget: parsed.budget || '',
        timeline: parsed.timeline || '',
      };
    }
  } catch(e) {}
}

if (!best) return [{ json: { skipped: true, bestScore: 0 } }];
if (bestScore < 8) return [{ json: { skipped: true, bestScore } }];
return [{ json: best }];
*/

// ─── UPDATED: Claude Score Jobs prompt addition ───────────────────────────────
// Add to the Claude scoring prompt (in Parse Jobs node), after the score JSON:
// "\"budget\": \"extracted budget in USD\", \"timeline\": \"estimated days\", \"description\": \"original description\""
// So the full reply JSON is:
// { score, relevant, title, link, reason, budget, timeline, description }
