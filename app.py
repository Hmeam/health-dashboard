import os
import logging
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

# .env 환경변수 로드
load_dotenv()

# Backend logging configuration (print 대신 logging 모듈 사용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("health_dashboard")

app = Flask(__name__)
app.config["DEBUG"] = os.getenv("FLASK_DEBUG", "false").lower() == "true"

@app.before_request
def log_request_info():
    logger.info(f"[REQUEST] {request.method} {request.path}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    # API Key는 Frontend에 노출하지 않고 설정 여부(True/False)만 반환
    raw_key = os.getenv("GEMINI_API_KEY", "")
    api_key_set = bool(raw_key and raw_key.strip() and raw_key != "your_gemini_api_key_here")
    
    return jsonify({
        "status": "healthy",
        "api_key_set": api_key_set,
        "indicators_loaded": 0
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Flask server starting on port {port} (debug={debug})")
    app.run(host="127.0.0.1", port=port, debug=debug)
