import os
import re
import json
import logging
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from google import genai
from google.genai import types
from data_loader import load_all_data
from tools import execute_tool, TOOL_REGISTRY

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

@app.route("/run", methods=["POST"])
def run_tool():
    """
    선택된 도구를 Pandas로 실행, 계산 결과 + 차트 데이터 반환
    """
    if df is None or not indicator_catalog or not country_catalog:
        logger.error("[ERROR] 도구 실행 실패: 데이터가 로드되지 않았습니다.")
        return jsonify({
            "status": "error",
            "message": "데이터 파일 로드 실패"
        }), 500

    data = request.get_json(silent=True) or {}
    tool_name = data.get("tool") or data.get("tool_name")
    params = data.get("params") or {}
    
    # params가 비어있고 data 최상위에 인자가 있는 경우 지원
    if not params:
        params = {k: v for k, v in data.items() if k not in ["tool", "tool_name"]}
        
    if not tool_name:
        logger.error("[ERROR] 실행할 도구 미지정")
        return jsonify({
            "status": "error",
            "message": "실행할 도구가 지정되지 않았습니다."
        }), 400
        
    if tool_name not in TOOL_REGISTRY:
        logger.error(f"[ERROR] 도구 목록에 없는 도구: '{tool_name}'")
        return jsonify({
            "status": "error",
            "message": f"도구 목록에 없는 도구입니다: '{tool_name}'"
        }), 400

    try:
        result = execute_tool(tool_name, df, indicator_catalog, country_catalog, **params)
        logger.info(f"[RESPONSE] 도구 실행 완료: {tool_name} (결과 행 수: {len(result.get('data', []))})")
        return jsonify({
            "status": "success",
            "result": result
        })
    except ValueError as ve:
        logger.error(f"[ERROR] 도구 실행 검증 오류: {ve}")
        return jsonify({
            "status": "error",
            "message": str(ve)
        }), 400
    except Exception as e:
        logger.error(f"[ERROR] 도구 실행 중 예외 발생: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"도구 실행 중 오류가 발생했습니다: {str(e)}"
        }), 500

def parse_json_safely(raw_text):
    """
    JSON 파싱 실패 시 코드블록 제거, 끝 쉼표 제거 후 1회 재시도
    """
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except Exception:
        # 끝 쉼표 제거 정규식 적용 후 1회 재시도
        text_fixed = re.sub(r',\s*([\]}])', r'\1', text)
        return json.loads(text_fixed)

@app.route("/suggest", methods=["POST"])
def suggest():
    """
    사용자 질문과 지표 사전 요약을 Gemini에 전달, 도구 카탈로그 중 분석 제안 JSON 수신
    """
    raw_key = os.getenv("GEMINI_API_KEY", "")
    if not raw_key or raw_key.strip() == "" or raw_key == "your_gemini_api_key_here":
        logger.error("[ERROR] API Key 미설정")
        return jsonify({
            "status": "error",
            "message": "API Key 미설정: .env 파일에 GEMINI_API_KEY를 설정해 주세요."
        }), 400

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({
            "status": "error",
            "message": "질문 내용을 입력해 주세요."
        }), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # 지표 사전 요약 (코드, 한글명, 단위, 권장 기준연도, 방향성)
    catalog_summary = []
    for code, info in indicator_catalog.items():
        catalog_summary.append({
            "code": code,
            "name_ko": info["name_ko"],
            "unit": info["unit"],
            "recommended_year": info["recommended_year"],
            "direction": info["direction"]
        })
        
    tool_descriptions = [
        {"tool": "rank_indicator", "desc": "한 지표의 상위/하위 N 순위", "params": {"indicator_code": "str", "year": "int(optional)", "top_n": "int", "order": "top/bottom/both", "highlight": "list[str](optional)", "peer": "all/High income(optional)"}},
        {"tool": "trend_compare", "desc": "선택 국가들의 한 지표 연도별 추이 비교 (선 차트)", "params": {"indicator_code": "str", "country_codes": "list[str]", "start_year": "int", "end_year": "int", "highlight": "list[str]"}},
        {"tool": "scatter_relation", "desc": "두 지표의 같은 연도 산점도 및 상관계수(r, r_log)", "params": {"x_indicator": "str", "y_indicator": "str", "year": "int(optional)", "x_log": "bool", "highlight": "list[str]", "peer": "all/High income"}},
        {"tool": "efficiency_residual", "desc": "x(의료비) 대비 y(기대수명/영아사망률) 효율 잔차 분석", "params": {"x_indicator": "str", "y_indicator": "str", "year": "int(기본2023)", "peer": "all/High income", "highlight": "list[str]", "top_n": "int"}},
        {"tool": "robustness_check", "desc": "효율 분석 4개 조건(2019/2021/2023 기대수명, 2023 영아사망률) 교차 검증", "params": {"x_indicator": "str", "peer": "High income(기본)", "highlight": "list[str]"}},
        {"tool": "country_profile", "desc": "한 국가의 11개 지표 권장연도 수치, 순위, 백분위, 소득군 중앙값 비교", "params": {"country_code": "str(예: KOR)"}},
        {"tool": "group_summary", "desc": "소득 그룹 또는 지역별 지표 중앙값·평균 통계 (막대)", "params": {"indicator_code": "str", "group_by": "income_group/region", "year": "int(optional)"}},
        {"tool": "correlation_with", "desc": "기준 지표(기대수명)와 타 지표들의 동일 연도 상관계수 순위 표", "params": {"target_indicator": "str(기본 SP.DYN.LE00.IN)", "year": "int(기본2023)"}}
    ]

    prompt = f"""
당신은 보건·경제 데이터 분석 전문가입니다.
사용자의 질문을 해결하기 위해 도구 카탈로그에서 실행할 수 있는 최적의 분석 3~5개를 제안해 주세요.

[사용자 질문]
"{question}"

[사용 가능한 지표 목록]
{json.dumps(catalog_summary, ensure_ascii=False, indent=2)}

[도구 카탈로그]
{json.dumps(tool_descriptions, ensure_ascii=False, indent=2)}

[규칙]
1. 도구 카탈로그에 명시된 도구명(tool)과 지표 코드(code)만 사용해야 합니다.
2. 각 제안은 반드시 다음 키를 포함하는 JSON 객체여야 합니다:
   - "title": 분석 제목 (한국어)
   - "tool": 도구명 (카탈로그 내 이름)
   - "params": 도구 실행에 필요한 파라미터 객체
   - "why": 이 분석을 추천하는 이유 (사용자 질문과 연결)
   - "caution": 통계/해석 시 주의해야 할 점 (인과관계 주의 등)
3. 3개 이상 5개 이하의 제안을 담은 JSON 배열 또는 {{"suggestions": [...]}} 형태로만 응답하세요.
"""
    try:
        logger.info(f"[AI] Gemini suggest 요청 시작 (모델: {model_name})")
        client = genai.Client(api_key=raw_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        raw_text = response.text or "{}"
        logger.info(f"[AI] Gemini 응답 수신 완료 (길이: {len(raw_text)}자)")
        
        parsed = parse_json_safely(raw_text)
        if isinstance(parsed, dict) and "suggestions" in parsed:
            raw_suggestions = parsed["suggestions"]
        elif isinstance(parsed, list):
            raw_suggestions = parsed
        else:
            raw_suggestions = []
            
        # 서버 측 안전 검증: 카탈로그에 없는 도구, 사전에 없는 지표, 없는 국가 제거
        valid_suggestions = []
        country_set = {c["country_code"] for c in country_catalog}
        
        for item in raw_suggestions:
            tool = item.get("tool")
            if tool not in TOOL_REGISTRY:
                continue
            params = item.get("params") or {}
            
            # 지표 검증
            ind_keys = ["indicator_code", "x_indicator", "y_indicator", "target_indicator"]
            invalid_ind = any(k in params and params[k] not in indicator_catalog for k in ind_keys)
            if invalid_ind:
                continue
                
            # 국가 코드 검증
            if "country_code" in params and params["country_code"] not in country_set:
                continue
            if "country_codes" in params:
                params["country_codes"] = [c for c in params["country_codes"] if c in country_set]
                if not params["country_codes"]:
                    continue
            if "highlight" in params:
                params["highlight"] = [c for c in params["highlight"] if c in country_set]
                
            valid_suggestions.append({
                "title": item.get("title", f"{tool} 분석"),
                "tool": tool,
                "params": params,
                "why": item.get("why", "질문과 관련된 분석입니다."),
                "caution": item.get("caution", "상관관계는 인과관계가 아닙니다.")
            })
            
        if not valid_suggestions:
            # 안전 기본 제안 제공
            valid_suggestions = [
                {
                    "title": "한국 국가 건강·경제 프로필",
                    "tool": "country_profile",
                    "params": {"country_code": "KOR"},
                    "why": "한국의 11개 주요 지표 수준과 소득군 내 위치를 종합 조망합니다.",
                    "caution": "지표별 조사 연도 차이에 유의하십시오."
                },
                {
                    "title": "의료비 대비 기대수명 효율 분석",
                    "tool": "efficiency_residual",
                    "params": {"x_indicator": "SH.XPD.CHEX.PP.CD", "y_indicator": "SP.DYN.LE00.IN", "peer": "High income", "highlight": ["KOR"]},
                    "why": "의료비 지출 규모 대비 기대수명 달성 성과(잔차)를 평가합니다.",
                    "caution": "상관관계는 인과관계가 아니며 다양한 외부 요인이 잔차에 포함됩니다."
                }
            ]

        logger.info(f"[RESPONSE] /suggest 완료 (제안 수: {len(valid_suggestions)})")
        return jsonify({
            "status": "success",
            "suggestions": valid_suggestions
        })
        
    except json.JSONDecodeError as je:
        logger.error(f"[ERROR] JSON 파싱 실패: {je}")
        return jsonify({
            "status": "error",
            "message": "JSON 파싱 실패: Gemini 응답을 JSON 데이터로 변환하지 못했습니다."
        }), 500
    except Exception as e:
        err_str = str(e).lower()
        logger.error(f"[ERROR] Gemini 호출 실패: {e}")
        if "api_key_invalid" in err_str or "unauthenticated" in err_str or "401" in err_str or "403" in err_str:
            return jsonify({"status": "error", "message": "API 인증 실패: 유효한 GEMINI_API_KEY인지 확인해 주세요."}), 401
        elif "timeout" in err_str or "deadline" in err_str:
            return jsonify({"status": "error", "message": "API Timeout: Gemini 응답 시간이 초과되었습니다."}), 504
        elif "connection" in err_str or "network" in err_str:
            return jsonify({"status": "error", "message": "네트워크 오류: Gemini API 서버에 연결할 수 없습니다."}), 503
        else:
            return jsonify({"status": "error", "message": f"Gemini 분석 제안 오류: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Flask server starting on port {port} (debug={debug})")
    app.run(host="127.0.0.1", port=port, debug=debug)
