import os
import logging
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from data_loader import load_all_data

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

# 서버 시작 시 data/indicators와 data/meta에서 데이터 로드 (메모리 보관)
try:
    df, indicator_catalog, country_catalog = load_all_data()
    logger.info(f"데이터 로드 완료: 지표 {len(indicator_catalog)}개, 국가/엔터티 {len(country_catalog)}개")
except Exception as e:
    logger.error(f"[ERROR] 서버 시작 중 데이터 로드 실패: {e}")
    df, indicator_catalog, country_catalog = None, {}, []

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
    indicators_loaded = len(indicator_catalog) if indicator_catalog else 0
    
    return jsonify({
        "status": "healthy",
        "api_key_set": api_key_set,
        "indicators_loaded": indicators_loaded
    })

@app.route("/catalog")
def catalog():
    """
    지표 사전(코드, 한글명, 단위, 정의, 출처, 연도별 국가 수, 권장 기준연도)과
    국가 목록(국가/집계 구분, 소득 그룹) 반환
    """
    if not indicator_catalog or not country_catalog:
        logger.error("[ERROR] 카탈로그 조회 실패: 로드된 데이터가 없습니다.")
        return jsonify({
            "status": "error",
            "message": "데이터 파일 로드 실패"
        }), 500

    return jsonify({
        "status": "success",
        "indicators": indicator_catalog,
        "countries": country_catalog
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Flask server starting on port {port} (debug={debug})")
    app.run(host="127.0.0.1", port=port, debug=debug)
