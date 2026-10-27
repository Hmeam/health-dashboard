import math
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger("health_dashboard")

def sanitize_value(val):
    """
    NaN, Infinity 값을 JSON 직렬화 가능한 None 또는 안전한 float로 변환합니다.
    """
    if val is None:
        return None
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (int, np.integer)):
        return int(val)
    return val

def sanitize_records(records):
    """
    딕셔너리 리스트의 모든 결측치/무한대 값을 안전하게 정제합니다.
    """
    cleaned = []
    for row in records:
        cleaned_row = {}
        for k, v in row.items():
            cleaned_row[k] = sanitize_value(v)
        cleaned.append(cleaned_row)
    return cleaned

# ==============================================================================
# Tool 1: data_coverage
# ==============================================================================
def tool_data_coverage(df, indicator_catalog, country_catalog, indicator_code=None, **kwargs):
    """
    지표별 연도별 국가 수, 권장 기준연도 (최대 조사 국가 수의 90% 이상을 채운 가장 최근 연도)
    """
    target_codes = [indicator_code] if indicator_code and indicator_code in indicator_catalog else list(indicator_catalog.keys())
    
    real_countries = [c for c in country_catalog if not c["is_aggregate"]]
    total_real_count = len(real_countries)
    
    coverage_results = []
    for code in target_codes:
        info = indicator_catalog[code]
        rec_year = info["recommended_year"]
        cov = info["year_coverage"]
        rec_cnt = cov.get(rec_year, 0)
        
        # 연도별 국가 수 정렬 (최근 10개년)
        recent_years = sorted(cov.keys(), reverse=True)[:10]
        recent_cov = {y: cov[y] for y in sorted(recent_years)}
        
        coverage_results.append({
            "indicator_code": code,
            "indicator_name": info["indicator_name"],
            "name_ko": info["name_ko"],
            "unit": info["unit"],
            "recommended_year": rec_year,
            "countries_in_recommended_year": rec_cnt,
            "coverage_rate_percent": round((rec_cnt / total_real_count) * 100, 1) if total_real_count else 0,
            "recent_years_coverage": recent_cov
        })
        
    logger.info(f"[TOOL] data_coverage | indicators={len(target_codes)} | total_real_countries={total_real_count}")
    
    return {
        "tool": "data_coverage",
        "params": {"indicator_code": indicator_code},
        "year": "전체 연도 분석",
        "used_countries_count": total_real_count,
        "excluded_countries_count": 0,
        "excluded_reason": "집계 행(World, 지역 등 49개)은 분석 대상에서 제외되었습니다.",
        "warnings": [],
        "cautions": ["조사 주기가 긴 설문/서베이 지표는 연도별 국가 수 편차가 클 수 있습니다."],
        "data": coverage_results,
        "chart_data": {
            "type": "bar",
            "labels": [item["name_ko"] for item in coverage_results],
            "datasets": [{
                "label": "권장 기준연도 수집 국가 수",
                "data": [item["countries_in_recommended_year"] for item in coverage_results],
                "backgroundColor": "rgba(59, 130, 246, 0.7)"
            }]
        }
    }

# ==============================================================================
# Tool 2: rank_indicator
# ==============================================================================
def tool_rank_indicator(df, indicator_catalog, country_catalog, indicator_code, year=None, top_n=10, order="top", highlight=None, peer=None, **kwargs):
    """
    한 지표의 상위/하위 N 순위 (order: top/bottom/both, highlight, 수평 막대)
    - 모든 순위는 같은 값이면 같은 순위로 한다 (rank method='min').
    - highlight가 상위 N 밖이면 실제 순위와 함께 아래에 추가
    """
    if indicator_code not in indicator_catalog:
        raise ValueError(f"유효하지 않은 지표 코드: {indicator_code}")
        
    info = indicator_catalog[indicator_code]
    
    # 기준 연도 자동 채택
    if year is None:
        year = info["recommended_year"]
        year_auto_selected = True
    else:
        year = int(year)
        year_auto_selected = False
        
    # 실제 국가 필터링 (집계 행 제외)
    real_countries = [c for c in country_catalog if not c["is_aggregate"]]
    total_real = len(real_countries)
    
    sub_df = df[(df["indicator_code"] == indicator_code) & (df["year"] == year) & (~df["is_aggregate"])].copy()
    
    # peer (소득 그룹) 필터링 옵션
    if peer and peer != "all":
        sub_df = sub_df[sub_df["income_group"] == peer]
        real_countries = [c for c in real_countries if c.get("income_group") == peer]
        total_real = len(real_countries)
        
    used_count = len(sub_df)
    excluded_count = total_real - used_count
    
    if used_count == 0:
        raise ValueError(f"{year}년에 {info['name_ko']} 데이터가 있는 국가가 없습니다.")
        
    # 지표 방향성 반영
    direction = info.get("direction", "neutral")
    is_lower_better = (direction == "lower_is_better")
    is_neutral = (direction == "neutral")
    
    # 순위 계산: lower_is_better면 낮은 순으로 1위(ascending=True), 그 외에는 높은 순으로 1위(ascending=False)
    sub_df["rank"] = sub_df["value"].rank(method="min", ascending=is_lower_better).astype(int)
    sub_df = sub_df.sort_values(["rank", "country_name"])
    
    highlight_codes = set(highlight) if highlight else set()
    
    # order 처리: top, bottom, both
    top_n = int(top_n)
    if order == "bottom":
        main_df = sub_df.sort_values("rank", ascending=False).head(top_n).sort_values("rank")
    elif order == "both":
        half = max(1, top_n // 2)
        top_part = sub_df.head(half)
        bot_part = sub_df.tail(half)
        main_df = pd.concat([top_part, bot_part]).drop_duplicates(subset=["country_code"]).sort_values("rank")
    else: # top
        main_df = sub_df.head(top_n)
        
    selected_codes = set(main_df["country_code"])
    
    # highlight 처리: 상위 N 밖이면 실제 순위와 함께 아래에 추가
    extra_rows = []
    for code in highlight_codes:
        if code not in selected_codes:
            extra = sub_df[sub_df["country_code"] == code]
            if not extra.empty:
                extra_row = extra.iloc[0].to_dict()
                extra_row["is_extra"] = True
                extra_rows.append(extra_row)
                
    result_rows = []
    for _, r in main_df.iterrows():
        d = r.to_dict()
        d["is_extra"] = False
        result_rows.append(d)
        
    result_rows.extend(extra_rows)
    
    # 차트용 데이터 (수평 막대: Chart.js indexAxis: 'y')
    labels = []
    values = []
    bg_colors = []
    border_colors = []
    
    for r in result_rows:
        c_code = r["country_code"]
        c_name = r["country_name"]
        rk = r["rank"]
        label = f"#{rk} {c_name}"
        if r.get("is_extra"):
            label += " (추가)"
        labels.append(label)
        values.append(sanitize_value(r["value"]))
        
        if c_code in highlight_codes:
            bg_colors.append("rgba(239, 68, 68, 0.85)")  # 빨간색 강조
            border_colors.append("rgba(220, 38, 38, 1)")
        else:
            bg_colors.append("rgba(59, 130, 246, 0.7)")
            border_colors.append("rgba(37, 99, 235, 1)")
            
    warnings = []
    if year_auto_selected:
        warnings.append(f"기준 연도가 지정되지 않아 해당 지표의 권장 기준연도({year}년)가 자동 적용되었습니다.")
    if is_neutral:
        warnings.append(f"{info['name_ko']} 지표는 중립적 지표로, 순위가 높다고 해서 반드시 더 좋거나 우수한 것은 아닙니다.")
        
    direction_note = "낮을수록 좋음 (1위=가장 낮음)" if is_lower_better else ("높을수록 좋다는 뜻은 아님" if is_neutral else "높을수록 좋음 (1위=가장 높음)")
        
    logger.info(f"[TOOL] rank_indicator | indicator={indicator_code} | year={year} | used={used_count} | excluded={excluded_count}")
    
    return {
        "tool": "rank_indicator",
        "params": {
            "indicator_code": indicator_code,
            "year": year,
            "top_n": top_n,
            "order": order,
            "highlight": list(highlight_codes),
            "peer": peer
        },
        "year": year,
        "indicator": {
            "code": indicator_code,
            "name": info["indicator_name"],
            "name_ko": info["name_ko"],
            "unit": info["unit"]
        },
        "used_countries_count": used_count,
        "excluded_countries_count": excluded_count,
        "excluded_reason": f"해당 연도 결측치 {excluded_count}개국, 집계 행(World 등 49개) 제외",
        "warnings": warnings,
        "cautions": ["순위는 절대적인 우열보다는 해당 연도의 상대적 지표 수준을 나타냅니다."],
        "data": sanitize_records(result_rows),
        "chart_data": {
            "type": "bar",
            "indexAxis": "y",
            "labels": labels,
            "datasets": [{
                "label": f"{info['name_ko']} ({info['unit']})",
                "data": values,
                "backgroundColor": bg_colors,
                "borderColor": border_colors,
                "borderWidth": 1
            }]
        }
    }

# ==============================================================================
# Tool 3: trend_compare
# ==============================================================================
def tool_trend_compare(df, indicator_catalog, country_catalog, indicator_code, country_codes, start_year=None, end_year=None, highlight=None, **kwargs):
    """
    선택 국가들의 한 지표 연도별 추이 (start/end 연도, highlight, 선 차트)
    """
    if indicator_code not in indicator_catalog:
        raise ValueError(f"유효하지 않은 지표 코드: {indicator_code}")
        
    if not country_codes:
        raise ValueError("추이를 비교할 국가 코드를 하나 이상 선택해 주세요.")
        
    info = indicator_catalog[indicator_code]
    
    sub_df = df[(df["indicator_code"] == indicator_code) & (df["country_code"].isin(country_codes))].copy()
    
    if sub_df.empty:
        raise ValueError("선택한 국가의 지표 데이터가 존재하지 않습니다.")
        
    min_avail_year = int(sub_df["year"].min())
    max_avail_year = int(sub_df["year"].max())
    
    start_year = int(start_year) if start_year is not None else max(min_avail_year, 2000)
    end_year = int(end_year) if end_year is not None else max_avail_year
    
    if start_year > end_year:
        start_year, end_year = end_year, start_year
        
    sub_df = sub_df[(sub_df["year"] >= start_year) & (sub_df["year"] <= end_year)]
    
    years_range = list(range(start_year, end_year + 1))
    highlight_set = set(highlight) if highlight else set()
    
    # 국가별 시계열 데이터셋 구성
    palette = [
        "rgba(59, 130, 246, 1)",   # Blue
        "rgba(16, 185, 129, 1)",  # Green
        "rgba(245, 158, 11, 1)",  # Amber
        "rgba(139, 92, 246, 1)",  # Purple
        "rgba(236, 72, 153, 1)",  # Pink
        "rgba(20, 184, 166, 1)",  # Teal
        "rgba(249, 115, 22, 1)",  # Orange
    ]
    
    datasets = []
    color_idx = 0
    table_rows = []
    
    # lookup map
    country_name_map = {c["country_code"]: c["country_name"] for c in country_catalog}
    
    for code in country_codes:
        c_df = sub_df[sub_df["country_code"] == code].sort_values("year")
        val_map = dict(zip(c_df["year"], c_df["value"]))
        
        series = [sanitize_value(val_map.get(y)) for y in years_range]
        is_hl = code in highlight_set
        
        color = "rgba(239, 68, 68, 1)" if is_hl else palette[color_idx % len(palette)]
        if not is_hl:
            color_idx += 1
            
        c_name = country_name_map.get(code, code)
        datasets.append({
            "label": f"{c_name} ({code})",
            "data": series,
            "borderColor": color,
            "backgroundColor": color.replace(", 1)", ", 0.1)"),
            "borderWidth": 3 if is_hl else 2,
            "pointRadius": 4 if is_hl else 3,
            "spanGaps": True  # 결측치 구간을 건너뛰고 연결
        })
        
        for y in years_range:
            v = val_map.get(y)
            if v is not None:
                table_rows.append({
                    "country_code": code,
                    "country_name": c_name,
                    "year": y,
                    "value": sanitize_value(v)
                })
                
    used_count = len(country_codes)
    excluded_count = 0
    
    logger.info(f"[TOOL] trend_compare | indicator={indicator_code} | countries={country_codes} | range={start_year}-{end_year}")
    
    return {
        "tool": "trend_compare",
        "params": {
            "indicator_code": indicator_code,
            "country_codes": country_codes,
            "start_year": start_year,
            "end_year": end_year,
            "highlight": list(highlight_set)
        },
        "year": f"{start_year}~{end_year}",
        "indicator": {
            "code": indicator_code,
            "name": info["indicator_name"],
            "name_ko": info["name_ko"],
            "unit": info["unit"]
        },
        "used_countries_count": used_count,
        "excluded_countries_count": excluded_count,
        "excluded_reason": "선택된 비교 대상 국가에 대해서만 시계열 추이를 표시합니다.",
        "warnings": ["특정 연도의 데이터가 비어 있는 경우(결측) 차트 선에 공백이 있을 수 있습니다."],
        "cautions": ["시계열 비교 시 국가별 집계 기준 변경 또는 보고 주기 차이를 감안해야 합니다."],
        "data": sanitize_records(table_rows),
        "chart_data": {
            "type": "line",
            "labels": years_range,
            "datasets": datasets
        }
    }

# ==============================================================================
# Tool 4: scatter_relation
# ==============================================================================
def tool_scatter_relation(df, indicator_catalog, country_catalog, x_indicator, y_indicator, year=None, x_log=False, highlight=None, peer=None, **kwargs):
    """
    두 지표의 같은 연도 산점도 (x 로그 스케일 옵션, 상관계수, highlight)
    - 원값 기준(r)과 x 로그 기준(r_log) 둘 다 계산
    - x_log=True일 때는 r_log를 대표값으로 표기하고 기준 명시
    - 주의사항: 반드시 "상관관계는 인과관계가 아니다" 포함
    """
    if x_indicator not in indicator_catalog or y_indicator not in indicator_catalog:
        raise ValueError("유효하지 않은 x 또는 y 지표 코드입니다.")
        
    x_info = indicator_catalog[x_indicator]
    y_info = indicator_catalog[y_indicator]
    
    if year is None:
        year = y_info["recommended_year"]
        year_auto_selected = True
    else:
        year = int(year)
        year_auto_selected = False
        
    real_countries = [c for c in country_catalog if not c["is_aggregate"]]
    total_real = len(real_countries)
    
    x_df = df[(df["indicator_code"] == x_indicator) & (df["year"] == year) & (~df["is_aggregate"])][["country_code", "country_name", "region", "income_group", "value"]].rename(columns={"value": "x_val"})
    y_df = df[(df["indicator_code"] == y_indicator) & (df["year"] == year) & (~df["is_aggregate"])][["country_code", "value"]].rename(columns={"value": "y_val"})
    
    merged = x_df.merge(y_df, on="country_code").dropna(subset=["x_val", "y_val"])
    
    if peer and peer != "all":
        merged = merged[merged["income_group"] == peer]
        total_real = sum(1 for c in real_countries if c.get("income_group") == peer)
        
    used_count = len(merged)
    excluded_count = total_real - used_count
    
    if used_count < 10:
        raise ValueError("두 지표의 공통 국가가 너무 적음(10개 미만)")
        
    # 1) 원값 기준 피어슨 상관계수 (r)
    corr_raw = float(merged[["x_val", "y_val"]].corr().iloc[0, 1])
    
    # 2) x 로그 변환 기준 피어슨 상관계수 (r_log)
    pos_mask = (merged["x_val"] > 0)
    if pos_mask.sum() >= 10:
        log_x = np.log10(merged.loc[pos_mask, "x_val"].values)
        y_pos = merged.loc[pos_mask, "y_val"].values
        corr_log = float(np.corrcoef(log_x, y_pos)[0, 1])
    else:
        corr_log = corr_raw
        
    effective_corr = corr_log if x_log else corr_raw
    basis_str = "x 로그 기준 (r_log)" if x_log else "원값 기준 (r)"
    
    highlight_set = set(highlight) if highlight else set()
    
    points = []
    hl_points = []
    
    for _, row in merged.iterrows():
        c_code = row["country_code"]
        pt = {
            "x": sanitize_value(row["x_val"]),
            "y": sanitize_value(row["y_val"]),
            "country_code": c_code,
            "country_name": row["country_name"],
            "income_group": row["income_group"],
            "region": row["region"]
        }
        if c_code in highlight_set:
            hl_points.append(pt)
        else:
            points.append(pt)
            
    datasets = [{
        "label": f"전체 국가 ({basis_str} = {effective_corr:.3f})",
        "data": points,
        "backgroundColor": "rgba(59, 130, 246, 0.6)",
        "borderColor": "rgba(37, 99, 235, 1)",
        "pointRadius": 5
    }]
    
    if hl_points:
        datasets.append({
            "label": "강조 국가",
            "data": hl_points,
            "backgroundColor": "rgba(239, 68, 68, 0.9)",
            "borderColor": "rgba(220, 38, 38, 1)",
            "pointRadius": 8
        })
        
    warnings = []
    if year_auto_selected:
        warnings.append(f"기준 연도가 지정되지 않아 기준 연도({year}년)가 자동 적용되었습니다.")
        
    logger.info(f"[TOOL] scatter_relation | x={x_indicator} | y={y_indicator} | year={year} | used={used_count} | r={corr_raw:.3f} | r_log={corr_log:.3f}")
    
    return {
        "tool": "scatter_relation",
        "params": {
            "x_indicator": x_indicator,
            "y_indicator": y_indicator,
            "year": year,
            "x_log": bool(x_log),
            "highlight": list(highlight_set),
            "peer": peer
        },
        "year": year,
        "x_indicator": {"code": x_indicator, "name": x_info["indicator_name"], "name_ko": x_info["name_ko"], "unit": x_info["unit"]},
        "y_indicator": {"code": y_indicator, "name": y_info["indicator_name"], "name_ko": y_info["name_ko"], "unit": y_info["unit"]},
        "correlation": round(effective_corr, 4),
        "correlation_raw": round(corr_raw, 4),
        "correlation_log": round(corr_log, 4),
        "correlation_basis": basis_str,
        "used_countries_count": used_count,
        "excluded_countries_count": excluded_count,
        "excluded_reason": f"두 지표 중 하나라도 결측인 국가 {excluded_count}개국, 집계 행 49개 제외",
        "warnings": warnings,
        "cautions": [
            "상관관계는 인과관계가 아니다.",
            "제3의 교란 변수(소득, 교육, 공중보건 인프라 등)가 두 지표 모두에 영향을 미칠 수 있습니다."
        ],
        "data": sanitize_records(merged.to_dict(orient="records")),
        "chart_data": {
            "type": "scatter",
            "x_log": bool(x_log),
            "datasets": datasets
        }
    }

# ==============================================================================
# Tool 5: efficiency_residual
# ==============================================================================
def tool_efficiency_residual(df, indicator_catalog, country_catalog, x_indicator="SH.XPD.CHEX.PP.CD", y_indicator="SP.DYN.LE00.IN", year=2023, peer="all", highlight=None, top_n=10, **kwargs):
    """
    x 지표 대비 y 지표의 효율 분석
    - x는 log10 변환, numpy.polyfit(deg=1)로 추세선 계산
    - 잔차 = 실제 y − 추세선 예상 y (y가 낮을수록 좋으면 부호 반대)
    - peer 옵션: all / High income / Upper middle income 등
    - 결과: 잔차 상위/하위 10, 산점도 + 추세선, highlight
    """
    if x_indicator not in indicator_catalog or y_indicator not in indicator_catalog:
        raise ValueError("유효하지 않은 지표 코드입니다.")
        
    x_info = indicator_catalog[x_indicator]
    y_info = indicator_catalog[y_indicator]
    
    if year is None:
        year = 2023
    else:
        year = int(year)
        
    real_countries = [c for c in country_catalog if not c["is_aggregate"]]
    total_real = len(real_countries)
    
    x_df = df[(df["indicator_code"] == x_indicator) & (df["year"] == year) & (~df["is_aggregate"])][["country_code", "country_name", "region", "income_group", "value"]].rename(columns={"value": "x_val"})
    y_df = df[(df["indicator_code"] == y_indicator) & (df["year"] == year) & (~df["is_aggregate"])][["country_code", "value"]].rename(columns={"value": "y_val"})
    
    merged = x_df.merge(y_df, on="country_code").dropna(subset=["x_val", "y_val"])
    # 로그 변환을 위해 x > 0 필터링
    merged = merged[merged["x_val"] > 0]
    
    if peer and peer != "all":
        merged = merged[merged["income_group"] == peer].copy()
        total_real = sum(1 for c in real_countries if c.get("income_group") == peer)
        
    used_count = len(merged)
    excluded_count = total_real - used_count
    
    if used_count < 10:
        raise ValueError("분석 대상 국가가 너무 적음(10개 미만)")
        
    # x 로그 변환 및 1차 선형 회귀 추세선 도출
    log_x = np.log10(merged["x_val"].values)
    y_vals = merged["y_val"].values
    
    slope, intercept = np.polyfit(log_x, y_vals, deg=1)
    
    # 예상값 및 잔차 산출
    expected_y = slope * log_x + intercept
    raw_residuals = y_vals - expected_y
    
    # 방향성 처리 (낮을수록 좋은 지표면 실제 y가 예상치보다 낮아야 효율적임)
    is_lower_better = (y_info.get("direction") == "lower_is_better")
    if is_lower_better:
        efficiency_residuals = -raw_residuals
    else:
        efficiency_residuals = raw_residuals
        
    merged["log_x"] = log_x
    merged["expected_y"] = expected_y
    merged["raw_residual"] = raw_residuals
    merged["residual"] = efficiency_residuals
    
    # 순위: 잔차가 클수록 투입 대비 성과(효율)가 우수 (rank method='min')
    merged["rank"] = merged["residual"].rank(method="min", ascending=False).astype(int)
    merged = merged.sort_values("rank")
    
    highlight_set = set(highlight) if highlight else set()
    top_n = int(top_n)
    
    # 상위 N + 하위 N 구성
    top_part = merged.head(top_n)
    bot_part = merged.tail(top_n)
    focus_df = pd.concat([top_part, bot_part]).drop_duplicates(subset=["country_code"]).sort_values("rank")
    
    # highlight 대상 추가
    focus_codes = set(focus_df["country_code"])
    extra_rows = []
    for code in highlight_set:
        if code not in focus_codes:
            extra = merged[merged["country_code"] == code]
            if not extra.empty:
                extra_r = extra.iloc[0].to_dict()
                extra_r["is_extra"] = True
                extra_rows.append(extra_r)
                
    result_table = []
    for _, r in focus_df.iterrows():
        d = r.to_dict()
        d["is_extra"] = False
        result_table.append(d)
    result_table.extend(extra_rows)
    
    # 차트용 데이터: 산점도 점 + 추세선 좌표
    scatter_pts = []
    hl_pts = []
    for _, r in merged.iterrows():
        pt = {
            "x": sanitize_value(r["x_val"]),
            "y": sanitize_value(r["y_val"]),
            "country_code": r["country_code"],
            "country_name": r["country_name"],
            "residual": sanitize_value(r["residual"]),
            "rank": int(r["rank"])
        }
        if r["country_code"] in highlight_set:
            hl_pts.append(pt)
        else:
            scatter_pts.append(pt)
            
    # 추세선 곡선 생성 (로그 스케일 x를 30등분)
    min_x = merged["x_val"].min()
    max_x = merged["x_val"].max()
    line_log_xs = np.linspace(np.log10(min_x), np.log10(max_x), 30)
    line_xs = 10 ** line_log_xs
    line_ys = slope * line_log_xs + intercept
    trend_line_pts = [{"x": sanitize_value(x), "y": sanitize_value(y)} for x, y in zip(line_xs, line_ys)]
    
    chart_datasets = [
        {
            "type": "scatter",
            "label": f"국가별 실제 성과 (총 {used_count}개국)",
            "data": scatter_pts,
            "backgroundColor": "rgba(59, 130, 246, 0.5)",
            "borderColor": "rgba(37, 99, 235, 0.8)",
            "pointRadius": 4
        },
        {
            "type": "line",
            "label": f"예상 추세선 (y = {slope:.2f}*log10(x) + {intercept:.2f})",
            "data": trend_line_pts,
            "borderColor": "rgba(107, 114, 128, 0.9)",
            "borderWidth": 2,
            "borderDash": [5, 5],
            "pointRadius": 0,
            "fill": False
        }
    ]
    if hl_pts:
        chart_datasets.append({
            "type": "scatter",
            "label": "강조 국가",
            "data": hl_pts,
            "backgroundColor": "rgba(239, 68, 68, 0.95)",
            "borderColor": "rgba(220, 38, 38, 1)",
            "pointRadius": 8
        })
        
    logger.info(f"[TOOL] efficiency_residual | year={year} | peer={peer} | used={used_count} | excluded={excluded_count}")
    
    return {
        "tool": "efficiency_residual",
        "params": {
            "x_indicator": x_indicator,
            "y_indicator": y_indicator,
            "year": year,
            "peer": peer,
            "highlight": list(highlight_set),
            "top_n": top_n
        },
        "year": year,
        "x_indicator": {"code": x_indicator, "name": x_info["indicator_name"], "name_ko": x_info["name_ko"], "unit": x_info["unit"]},
        "y_indicator": {"code": y_indicator, "name": y_info["indicator_name"], "name_ko": y_info["name_ko"], "unit": y_info["unit"]},
        "trend_line": {"slope": round(float(slope), 4), "intercept": round(float(intercept), 4)},
        "used_countries_count": used_count,
        "excluded_countries_count": excluded_count,
        "excluded_reason": f"해당 연도 결측치 {excluded_count}개국, 집계 행 49개 제외",
        "warnings": [],
        "cautions": [
            "상관관계는 인과관계가 아니다.",
            "잔차는 의료비 외 요인(소득, 인구 구조, 생활습관 등)도 반영합니다.",
            "전체 국가 비교에서는 위기 국가가 상위에 나올 수 있으니 소득 그룹 비교를 함께 보십시오."
        ],
        "data": sanitize_records(result_table),
        "all_data": sanitize_records(merged.to_dict(orient="records")),
        "chart_data": {
            "type": "scatter",
            "x_log": True,
            "datasets": chart_datasets
        }
    }

# ==============================================================================
# Tool 6: robustness_check
# ==============================================================================
def tool_robustness_check(df, indicator_catalog, country_catalog, x_indicator="SH.XPD.CHEX.PP.CD", peer="High income", highlight=None, **kwargs):
    """
    efficiency_residual을 여러 조건으로 반복해 상위/하위 10위에 든 횟수를 국가별로 집계
    - peer 파라미터 기본값: "High income" (모든 조건을 같은 peer 안에서 실행)
    - 4개 조건: 2019·2021·2023 기대수명, 2023 영아사망률(부호 반대)
    - 상위 10위 진입 횟수 + 하위 10위 진입 횟수 동시 집계
    - highlight 국가(한국, 미국 등)의 조건별 순위 표 제공
    """
    if highlight is None:
        highlight = ["KOR", "USA"]
    highlight_set = set(highlight)
    
    conditions = [
        {"name": "2019년 기대수명", "year": 2019, "y": "SP.DYN.LE00.IN"},
        {"name": "2021년 기대수명", "year": 2021, "y": "SP.DYN.LE00.IN"},
        {"name": "2023년 기대수명", "year": 2023, "y": "SP.DYN.LE00.IN"},
        {"name": "2023년 영아사망률", "year": 2023, "y": "SP.DYN.IMRT.IN"}
    ]
    
    top10_counts = {}
    bottom10_counts = {}
    country_info_map = {}
    country_cond_ranks = {}
    condition_summaries = []
    
    total_conditions = len(conditions)
    
    for cond in conditions:
        res = tool_efficiency_residual(
            df, indicator_catalog, country_catalog,
            x_indicator=x_indicator,
            y_indicator=cond["y"],
            year=cond["year"],
            peer=peer,
            top_n=10
        )
        all_list = res.get("all_data", [])
        total_in_cond = len(all_list)
        
        # 순위 오름차순 정렬
        sorted_by_rank = sorted(all_list, key=lambda x: x["rank"])
        top10 = sorted_by_rank[:10]
        # 하위 10위 (예: 64개국 중 55~64위)
        bottom10 = sorted_by_rank[-10:] if total_in_cond >= 10 else []
        
        top10_codes = {c["country_code"] for c in top10}
        bottom10_codes = {c["country_code"] for c in bottom10}
        
        condition_summaries.append({
            "condition": cond["name"],
            "year": cond["year"],
            "peer": peer,
            "y_indicator": cond["y"],
            "total_countries": total_in_cond,
            "top10": [f"#{c['rank']} {c['country_name']}" for c in top10],
            "bottom10": [f"#{c['rank']} {c['country_name']}" for c in bottom10]
        })
        
        for c in all_list:
            code = c["country_code"]
            if code not in country_info_map:
                country_info_map[code] = {
                    "country_code": code,
                    "country_name": c["country_name"],
                    "income_group": c.get("income_group")
                }
            if code not in country_cond_ranks:
                country_cond_ranks[code] = []
                
            country_cond_ranks[code].append({
                "condition": cond["name"],
                "rank": int(c["rank"]),
                "total_countries": total_in_cond,
                "is_top10": code in top10_codes,
                "is_bottom10": code in bottom10_codes
            })
            
            if code in top10_codes:
                top10_counts[code] = top10_counts.get(code, 0) + 1
            if code in bottom10_codes:
                bottom10_counts[code] = bottom10_counts.get(code, 0) + 1
                
    # 1. 상위 10위 다빈도 국가 목록
    top_consistent = []
    for code, count in sorted(top10_counts.items(), key=lambda x: x[1], reverse=True):
        info = country_info_map[code]
        top_consistent.append({
            "country_code": code,
            "country_name": info["country_name"],
            "income_group": info["income_group"],
            "top10_count": count,
            "bottom10_count": bottom10_counts.get(code, 0),
            "consistency_ratio": round(count / total_conditions, 2)
        })
        
    # 2. 하위 10위 다빈도 국가 목록
    bottom_consistent = []
    for code, count in sorted(bottom10_counts.items(), key=lambda x: x[1], reverse=True):
        info = country_info_map[code]
        bottom_consistent.append({
            "country_code": code,
            "country_name": info["country_name"],
            "income_group": info["income_group"],
            "top10_count": top10_counts.get(code, 0),
            "bottom10_count": count,
            "consistency_ratio": round(count / total_conditions, 2)
        })
        
    # 3. highlight 국가 순위 분석 표
    highlight_table = []
    for code in highlight_set:
        if code in country_info_map:
            info = country_info_map[code]
            ranks_list = country_cond_ranks.get(code, [])
            highlight_table.append({
                "country_code": code,
                "country_name": info["country_name"],
                "income_group": info["income_group"],
                "ranks": [r["rank"] for r in ranks_list],
                "top10_count": top10_counts.get(code, 0),
                "bottom10_count": bottom10_counts.get(code, 0),
                "condition_details": ranks_list
            })
            
    # 차트용 데이터 (상위 일관 국가 막대 차트)
    chart_labels = [f"{item['country_name']} ({item['country_code']})" for item in top_consistent[:10]]
    chart_values = [item["top10_count"] for item in top_consistent[:10]]
    
    logger.info(f"[TOOL] robustness_check | peer={peer} | conditions={total_conditions} | top_consistent={len(top_consistent)}")
    
    return {
        "tool": "robustness_check",
        "params": {
            "x_indicator": x_indicator,
            "peer": peer,
            "conditions_count": total_conditions,
            "highlight": list(highlight_set)
        },
        "year": "2019·2021·2023 교차 검증 (4개 조건)",
        "used_countries_count": len(country_info_map),
        "excluded_countries_count": 0,
        "excluded_reason": f"선택된 소득 그룹({peer}) 내에서 각 조건별 유효 국가를 분석했습니다.",
        "warnings": [],
        "cautions": [
            "인구가 아주 적은 국가(마이크로스테이트 등)가 데이터 특성상 상위에 나타날 수 있습니다.",
            "상관관계는 인과관계가 아니다.",
            "잔차는 의료비 외 요인(소득, 인구 구조, 생활습관 등)도 반영합니다."
        ],
        "data": sanitize_records(top_consistent),
        "top_consistent": sanitize_records(top_consistent),
        "bottom_consistent": sanitize_records(bottom_consistent),
        "highlight_table": sanitize_records(highlight_table),
        "condition_summaries": condition_summaries,
        "chart_data": {
            "type": "bar",
            "labels": chart_labels,
            "datasets": [{
                "label": f"상위 10위 진입 횟수 (총 {total_conditions}회 중)",
                "data": chart_values,
                "backgroundColor": "rgba(16, 185, 129, 0.75)",
                "borderColor": "rgba(5, 150, 105, 1)",
                "borderWidth": 1
            }]
        }
    }

# ==============================================================================
# Tool 7: country_profile
# ==============================================================================
def tool_country_profile(df, indicator_catalog, country_catalog, country_code="KOR", year=None, **kwargs):
    """
    한 국가의 11개 지표 최신값, 그 값의 연도, 세계 순위, 백분위, 같은 소득 그룹 중앙값과 비교 (카드형)
    """
    country_lookup = {c["country_code"]: c for c in country_catalog}
    if country_code not in country_lookup:
        raise ValueError(f"존재하지 않는 국가 코드: {country_code}")
        
    c_info = country_lookup[country_code]
    target_income_group = c_info.get("income_group")
    real_df = df[~df["is_aggregate"]]
    
    indicators_profile = []
    
    for code, info in indicator_catalog.items():
        sub = real_df[(real_df["country_code"] == country_code) & (real_df["indicator_code"] == code)]
        
        direction = info.get("direction", "neutral")
        is_lower_better = (direction == "lower_is_better")
        is_neutral = (direction == "neutral")
        direction_note = "낮을수록 좋음 (1위 = 가장 낮음)" if is_lower_better else ("높을수록 좋다는 뜻은 아님" if is_neutral else "높을수록 좋음")
        
        if sub.empty:
            indicators_profile.append({
                "indicator_code": code,
                "name_ko": info["name_ko"],
                "unit": info["unit"],
                "direction": direction,
                "direction_note": direction_note,
                "value": None,
                "year": None,
                "world_rank": None,
                "world_total": None,
                "rank_text": "데이터 없음",
                "percentile": None,
                "peer_median": None,
                "peer_diff": None,
                "peer_rank": None,
                "peer_total": None,
                "peer_rank_text": "데이터 없음",
                "note": "해당 국가의 데이터가 없습니다."
            })
            continue
            
        # 권장 기준연도 값을 기본 사용 (그 연도에 값이 없을 때만 가장 가까운 과거 연도를 쓰고 연도 표시)
        target_year = int(year) if year is not None else info["recommended_year"]
        c_row = sub[sub["year"] == target_year]
        year_fallback_note = None
        
        if c_row.empty:
            past = sub[sub["year"] <= target_year].sort_values("year")
            if not past.empty:
                c_row = past.iloc[[-1]]
                val_year = int(c_row["year"].iloc[0])
                year_fallback_note = f"권장 기준연도({target_year}년) 결측으로 과거 {val_year}년 데이터 사용"
            else:
                c_row = sub.sort_values("year").iloc[[-1]]
                val_year = int(c_row["year"].iloc[0])
                year_fallback_note = f"권장 기준연도({target_year}년) 결측으로 {val_year}년 데이터 사용"
        else:
            val_year = target_year
            
        val = float(c_row["value"].iloc[0])
        
        # 그 연도에서 전체 실제 국가들 데이터
        y_all = real_df[(real_df["indicator_code"] == code) & (real_df["year"] == val_year)].copy()
        
        # 순위: lower_is_better면 낮은 순으로 1위(ascending=True)
        y_all["rank"] = y_all["value"].rank(method="min", ascending=is_lower_better).astype(int)
        
        c_match = y_all[y_all["country_code"] == country_code]
        w_rank = int(c_match["rank"].iloc[0]) if not c_match.empty else None
        w_total = len(y_all)
        rank_text = f"{w_total}개국 중 {w_rank}위" if w_rank is not None else "순위 없음"
        
        # 상위 백분위 계산 (1위에 가까울수록 100%)
        percentile = round((1 - (w_rank - 1) / w_total) * 100, 1) if w_rank and w_total > 1 else 100.0
        
        # 같은 소득 그룹의 중앙값 및 소득그룹 내 순위
        peer_df = y_all[y_all["income_group"] == target_income_group]
        peer_match = peer_df[peer_df["country_code"] == country_code]
        peer_rank = int(peer_match["rank"].iloc[0]) if not peer_match.empty else None
        peer_total = len(peer_df)
        peer_rank_text = f"{peer_total}개국 중 {peer_rank}위" if peer_rank is not None else "순위 없음"
        
        peer_med = float(peer_df["value"].median()) if not peer_df.empty else None
        peer_diff = round(val - peer_med, 4) if peer_med is not None else None
        
        indicators_profile.append({
            "indicator_code": code,
            "name_ko": info["name_ko"],
            "unit": info["unit"],
            "direction": direction,
            "direction_note": direction_note,
            "value": sanitize_value(val),
            "year": val_year,
            "is_recommended_year": (val_year == info["recommended_year"]),
            "year_fallback_note": year_fallback_note,
            "world_rank": w_rank,
            "world_total": w_total,
            "rank_text": rank_text,
            "percentile": percentile,
            "peer_median": sanitize_value(peer_med),
            "peer_diff": sanitize_value(peer_diff),
            "peer_rank": peer_rank,
            "peer_total": peer_total,
            "peer_rank_text": peer_rank_text,
            "income_group": target_income_group
        })
        
    logger.info(f"[TOOL] country_profile | country={country_code} | income_group={target_income_group}")
    
    return {
        "tool": "country_profile",
        "params": {"country_code": country_code, "year": year},
        "year": "각 지표별 최신 가용 연도",
        "country": {
            "code": country_code,
            "name": c_info["country_name"],
            "region": c_info.get("region"),
            "income_group": target_income_group
        },
        "used_countries_count": 1,
        "excluded_countries_count": 0,
        "excluded_reason": "선택한 대상 국가의 프로필을 생성했습니다.",
        "warnings": ["지표마다 최신 조사 연도가 다를 수 있으므로 각 카드의 기준 연도를 확인하세요."],
        "cautions": [
            "국가 간 단순 비교 시 인구 규모, 지리적 특성, 보건의료 체계 차이를 고려해야 합니다.",
            "소득 그룹 중앙값과의 차이는 해당 소득군 내에서의 상대적 수준을 나타냅니다."
        ],
        "data": sanitize_records(indicators_profile),
        "chart_data": {
            "type": "radar",
            "labels": [item["name_ko"] for item in indicators_profile if item["percentile"] is not None],
            "datasets": [{
                "label": f"{c_info['country_name']} 세계 백분위 (상위 %)",
                "data": [item["percentile"] for item in indicators_profile if item["percentile"] is not None],
                "backgroundColor": "rgba(59, 130, 246, 0.2)",
                "borderColor": "rgba(37, 99, 235, 1)",
                "pointBackgroundColor": "rgba(37, 99, 235, 1)"
            }]
        }
    }

# ==============================================================================
# Tool 8: group_summary
# ==============================================================================
def tool_group_summary(df, indicator_catalog, country_catalog, indicator_code, group_by="income_group", year=None, **kwargs):
    """
    소득 그룹 또는 지역별 지표 중앙값·평균·국가 수 (막대)
    """
    if indicator_code not in indicator_catalog:
        raise ValueError(f"유효하지 않은 지표 코드: {indicator_code}")
        
    if group_by not in ["income_group", "region"]:
        group_by = "income_group"
        
    info = indicator_catalog[indicator_code]
    
    if year is None:
        year = info["recommended_year"]
        year_auto_selected = True
    else:
        year = int(year)
        year_auto_selected = False
        
    sub_df = df[(df["indicator_code"] == indicator_code) & (df["year"] == year) & (~df["is_aggregate"])].copy()
    sub_df = sub_df.dropna(subset=[group_by, "value"])
    
    real_countries = [c for c in country_catalog if not c["is_aggregate"] and c.get(group_by)]
    total_real = len(real_countries)
    used_count = len(sub_df)
    excluded_count = total_real - used_count
    
    if used_count == 0:
        raise ValueError(f"{year}년에 {info['name_ko']} 데이터가 없습니다.")
        
    group_stats = []
    
    # 소득 그룹 표준 순서 정의
    income_order = ["Low income", "Lower middle income", "Upper middle income", "High income"]
    
    for grp_name, g in sub_df.groupby(group_by):
        vals = g["value"]
        group_stats.append({
            "group": grp_name,
            "count": int(len(vals)),
            "median": sanitize_value(float(vals.median())),
            "mean": sanitize_value(float(vals.mean())),
            "std": sanitize_value(float(vals.std())) if len(vals) > 1 else None,
            "min": sanitize_value(float(vals.min())),
            "max": sanitize_value(float(vals.max()))
        })
        
    if group_by == "income_group":
        group_stats.sort(key=lambda x: income_order.index(x["group"]) if x["group"] in income_order else 99)
    else:
        group_stats.sort(key=lambda x: x["median"] if x["median"] is not None else 0, reverse=True)
        
    labels = [g["group"] for g in group_stats]
    medians = [g["median"] for g in group_stats]
    means = [g["mean"] for g in group_stats]
    counts = [g["count"] for g in group_stats]
    
    warnings = []
    if year_auto_selected:
        warnings.append(f"기준 연도가 지정되지 않아 권장 기준연도({year}년)가 적용되었습니다.")
        
    logger.info(f"[TOOL] group_summary | indicator={indicator_code} | group_by={group_by} | year={year} | used={used_count}")
    
    return {
        "tool": "group_summary",
        "params": {
            "indicator_code": indicator_code,
            "group_by": group_by,
            "year": year
        },
        "year": year,
        "indicator": {
            "code": indicator_code,
            "name": info["indicator_name"],
            "name_ko": info["name_ko"],
            "unit": info["unit"]
        },
        "used_countries_count": used_count,
        "excluded_countries_count": excluded_count,
        "excluded_reason": f"해당 연도 결측치 {excluded_count}개국, 집계 행 49개 제외",
        "warnings": warnings,
        "cautions": [
            "그룹 내 국가 간에도 편차가 크므로 평균과 중앙값을 함께 확인하십시오.",
            "그룹별 수집 국가 수의 차이에 유의하십시오."
        ],
        "data": sanitize_records(group_stats),
        "chart_data": {
            "type": "bar",
            "labels": labels,
            "datasets": [
                {
                    "label": f"중앙값 ({info['unit']})",
                    "data": medians,
                    "backgroundColor": "rgba(59, 130, 246, 0.75)",
                    "borderColor": "rgba(37, 99, 235, 1)",
                    "borderWidth": 1
                },
                {
                    "label": f"평균값 ({info['unit']})",
                    "data": means,
                    "backgroundColor": "rgba(16, 185, 129, 0.65)",
                    "borderColor": "rgba(5, 150, 105, 1)",
                    "borderWidth": 1
                }
            ]
        }
    }

# ==============================================================================
# Tool 9: correlation_with
# ==============================================================================
def tool_correlation_with(df, indicator_catalog, country_catalog, target_indicator="SP.DYN.LE00.IN", year=2023, **kwargs):
    """
    한 지표(기본 기대수명)와 나머지 지표들의 같은 연도 상관계수 표 (막대)
    - 주의사항: 반드시 "상관관계는 인과관계가 아니다" 포함
    - 서로 다른 지표 비교 시 반드시 같은 연도만 사용 (기본 2023년)
    """
    if target_indicator not in indicator_catalog:
        raise ValueError(f"유효하지 않은 기준 지표 코드: {target_indicator}")
        
    target_info = indicator_catalog[target_indicator]
    if year is None:
        year = 2023
    else:
        year = int(year)
        
    real_df = df[~df["is_aggregate"]]
    target_sub = real_df[(real_df["indicator_code"] == target_indicator) & (real_df["year"] == year)][["country_code", "value"]].rename(columns={"value": "target_val"})
    
    if target_sub.empty:
        raise ValueError(f"{year}년에 기준 지표({target_info['name_ko']}) 데이터가 없습니다.")
        
    corr_results = []
    
    for code, info in indicator_catalog.items():
        if code == target_indicator:
            continue
            
        x_sub = real_df[(real_df["indicator_code"] == code) & (real_df["year"] == year)][["country_code", "value"]].rename(columns={"value": "x_val"})
        merged = x_sub.merge(target_sub, on="country_code").dropna(subset=["x_val", "target_val"])
        common_count = len(merged)
        
        if common_count < 10:
            corr_results.append({
                "indicator_code": code,
                "name_ko": info["name_ko"],
                "unit": info["unit"],
                "common_countries_count": common_count,
                "correlation": None,
                "correlation_log": None,
                "status": "데이터 부족 (공통 10개국 미만 제외)"
            })
            continue
            
        r_raw = float(merged[["x_val", "target_val"]].corr().iloc[0, 1])
        
        # log 변환 상관계수 (x > 0인 경우)
        pos = merged[merged["x_val"] > 0]
        if len(pos) >= 10:
            r_log = float(np.corrcoef(np.log10(pos["x_val"]), pos["target_val"])[0, 1])
        else:
            r_log = r_raw
            
        is_small_sample = (common_count < 100)
        sample_caution = "국가 수가 적어 다른 지표와 직접 비교하기 어렵다" if is_small_sample else None
            
        corr_results.append({
            "indicator_code": code,
            "name_ko": info["name_ko"],
            "unit": info["unit"],
            "common_countries_count": common_count,
            "n": common_count,
            "correlation": round(r_raw, 4),
            "correlation_log": round(r_log, 4),
            "abs_corr": abs(r_raw),
            "status": "정상 계산",
            "is_small_sample": is_small_sample,
            "sample_caution": sample_caution
        })
        
    # 절댓값 상관계수 높은 순으로 정렬
    valid_corrs = [c for c in corr_results if c["correlation"] is not None]
    valid_corrs.sort(key=lambda x: x["abs_corr"], reverse=True)
    
    invalid_corrs = [c for c in corr_results if c["correlation"] is None]
    sorted_all = valid_corrs + invalid_corrs
    
    # 차트 라벨에 계산 국가 수(n) 표기
    labels = [f"{c['name_ko']} (n={c['n']})" for c in valid_corrs]
    chart_vals = [c["correlation"] for c in valid_corrs]
    bg_colors = [
        "rgba(59, 130, 246, 0.75)" if v >= 0 else "rgba(239, 68, 68, 0.75)"
        for v in chart_vals
    ]
    
    logger.info(f"[TOOL] correlation_with | target={target_indicator} | year={year} | valid_indicators={len(valid_corrs)}")
    
    return {
        "tool": "correlation_with",
        "params": {"target_indicator": target_indicator, "year": year},
        "year": year,
        "target_indicator": {
            "code": target_indicator,
            "name": target_info["indicator_name"],
            "name_ko": target_info["name_ko"],
            "unit": target_info["unit"]
        },
        "used_countries_count": len(target_sub),
        "excluded_countries_count": 0,
        "excluded_reason": "동일 연도 공통 유효 국가가 10개 미만인 지표는 개별 상관계수 산출에서 제외되었습니다.",
        "warnings": ["서로 다른 지표의 관계를 왜곡 없이 파악하기 위해 동일한 기준 연도(2023년) 데이터만 사용했습니다."],
        "cautions": [
            "상관관계는 인과관계가 아니다.",
            "국가 수(n)가 100 미만인 지표(의사 수, 병상 수 등)는 표본 국가 수가 적어 다른 지표와 직접 비교하기 어렵습니다.",
            "상관계수가 높더라도 두 지표 사이에 직접적인 인과성이 성립하지 않을 수 있습니다."
        ],
        "data": sanitize_records(sorted_all),
        "chart_data": {
            "type": "bar",
            "indexAxis": "y",
            "labels": labels,
            "datasets": [{
                "label": f"{target_info['name_ko']}와의 상관계수 (r)",
                "data": chart_vals,
                "backgroundColor": bg_colors,
                "borderWidth": 1
            }]
        }
    }

# ==============================================================================
# TOOL REGISTRY: 전체 9종 도구 등록 카탈로그
# ==============================================================================
TOOL_REGISTRY = {
    "data_coverage": tool_data_coverage,
    "rank_indicator": tool_rank_indicator,
    "trend_compare": tool_trend_compare,
    "scatter_relation": tool_scatter_relation,
    "efficiency_residual": tool_efficiency_residual,
    "robustness_check": tool_robustness_check,
    "country_profile": tool_country_profile,
    "group_summary": tool_group_summary,
    "correlation_with": tool_correlation_with
}

def execute_tool(tool_name, df, indicator_catalog, country_catalog, **params):
    """
    도구 카탈로그에서 도구명을 조회하여 파라미터와 함께 실행하고 검증된 결과를 반환합니다.
    """
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"도구 카탈로그에 없는 도구입니다: '{tool_name}'")
    func = TOOL_REGISTRY[tool_name]
    return func(df, indicator_catalog, country_catalog, **params)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from data_loader import load_all_data
    df, catalog, countries = load_all_data()
    
    print("\n--- Test Tool 7: country_profile (KOR, 권장 기준연도 및 방향성 검증) ---")
    p_res = execute_tool("country_profile", df, catalog, countries, country_code="KOR")
    check_codes = [
        "SP.DYN.LE00.IN",
        "SP.DYN.IMRT.IN",
        "SH.XPD.CHEX.PP.CD",
        "SH.PRV.SMOK",
        "SH.MED.BEDS.ZS",
        "NY.GDP.PCAP.CD"
    ]
    for item in p_res["data"]:
        if item["indicator_code"] in check_codes:
            print(f"[{item['indicator_code']}] {item['name_ko']} {item['year']}년: {item['value']}, {item['rank_text']} (방향: {item['direction']})")
            
    print("\n--- Test Tool 9: correlation_with (2023, n값 및 표본주의 검증) ---")
    c_res = execute_tool("correlation_with", df, catalog, countries, target_indicator="SP.DYN.LE00.IN", year=2023)
    for item in c_res["data"]:
        if item["indicator_code"] in ["SH.MED.PHYS.ZS", "SH.MED.BEDS.ZS", "SH.XPD.CHEX.PP.CD"]:
            print(f"- {item['name_ko']} ({item['indicator_code']}): n={item['n']}, r={item['correlation']}, 주의={item['sample_caution']}")

