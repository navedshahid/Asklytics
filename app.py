# app.py
from flask import Flask, jsonify, render_template
from flask_cors import CORS
import time

app = Flask(__name__, template_folder="templates")
CORS(app)

# Register all REST + SSE endpoints (DB config, table select, builder, ask stream)
from compat._bridge import bp as api_bp
app.register_blueprint(api_bp)

@app.get("/health")
def health():
    return jsonify({"status": "ok", "ts": time.time()})

@app.get("/")
def home():
    # Your chat UI (index.html) lives here
    return render_template("index.html")

@app.get("/settings")
def settings_page():
    # Interactive settings page below
    return render_template("settings.html")

if __name__ == "__main__":
    # For dev. Use gunicorn/uvicorn for prod.
    app.run(host="0.0.0.0", port=8080, debug=True)
