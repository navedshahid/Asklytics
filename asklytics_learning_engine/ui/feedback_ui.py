from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, render_template_string, request

from ..learning import experience_store as xp
from ..learning.embedder import build_faiss_index


TEMPLATE = """
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>AskLytics Feedback</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
  </head>
  <body class="p-6">
    <div class="max-w-3xl mx-auto">
      <h1 class="text-2xl font-semibold mb-4">AskLytics Feedback</h1>
      <form id="f" class="space-y-3">
        <input id="prompt" class="w-full border p-2 rounded" placeholder="Your prompt" required />
        <textarea id="result" class="w-full border p-2 rounded" rows="4" placeholder="Model result (optional)"></textarea>
        <div class="flex gap-2">
          <button type="button" id="ok" class="px-3 py-2 bg-green-600 text-white rounded">✓ Correct</button>
          <button type="button" id="wrong" class="px-3 py-2 bg-yellow-500 text-black rounded">⚠ Wrong</button>
        </div>
        <div id="corr-wrap" class="hidden">
          <label class="block text-sm text-gray-600">Provide corrected SQL:</label>
          <textarea id="corrected" class="w-full border p-2 rounded" rows="6"></textarea>
          <button type="button" id="submit-correction" class="mt-2 px-3 py-2 bg-blue-600 text-white rounded">Submit Correction</button>
        </div>
        <div id="msg" class="text-sm text-gray-600"></div>
      </form>
    </div>
    <script>
      const okBtn = document.getElementById('ok');
      const wrongBtn = document.getElementById('wrong');
      const corrWrap = document.getElementById('corr-wrap');
      const submitBtn = document.getElementById('submit-correction');
      const msg = document.getElementById('msg');

      okBtn.onclick = async ()=>{
        const prompt = document.getElementById('prompt').value.trim();
        const result = document.getElementById('result').value.trim();
        if(!prompt){ msg.textContent = 'Prompt required.'; return; }
        const r = await fetch('/api/learn/feedback', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ prompt, generated_sql: result, success: true })
        });
        const j = await r.json();
        msg.textContent = j.message || 'Saved.';
      };
      wrongBtn.onclick = ()=>{ corrWrap.classList.remove('hidden'); };
      submitBtn.onclick = async ()=>{
        const prompt = document.getElementById('prompt').value.trim();
        const corrected = document.getElementById('corrected').value.trim();
        if(!prompt || !corrected){ msg.textContent = 'Prompt and corrected SQL required.'; return; }
        const r = await fetch('/api/learn/feedback', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ prompt, validated_sql: corrected, success: true })
        });
        const j = await r.json();
        msg.textContent = j.message || 'Correction saved.';
      };
    </script>
  </body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def home():  # simple inline template to avoid extra files
        return render_template_string(TEMPLATE)

    @app.post("/api/learn/feedback")
    def post_feedback():
        body: Dict[str, Any] = request.get_json(force=True) or {}
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"status": "error", "message": "prompt required"}), 400
        generated_sql = body.get("generated_sql")
        validated_sql = body.get("validated_sql")
        success = bool(body.get("success"))
        feedback = body.get("feedback")
        new_id = xp.save_experience(
            user_prompt=prompt,
            generated_sql=generated_sql,
            validated_sql=validated_sql,
            schema_context=None,
            result_signature=None,
            score=None,
            success=success,
            feedback=feedback,
            provider="feedback",
        )
        # Rebuild index incrementally: embed last entry only
        try:
            text = f"Prompt: {prompt}\nSQL: {validated_sql or generated_sql or ''}"
            build_faiss_index([(new_id, text)])  # builds tiny or extends existing index
        except Exception:
            pass
        return jsonify({"status": "success", "id": new_id, "message": "Feedback stored."}), 200

    return app


if __name__ == "__main__":
    port = int(os.getenv("LEARN_FEEDBACK_PORT", "5055"))
    create_app().run(host="0.0.0.0", port=port, debug=True)

