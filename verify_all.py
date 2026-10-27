"""
Step 25: Comprehensive Success Criteria Verification Script
"""
import sys
import io

# Ensure UTF-8 output on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import app
import tools
import pandas as pd
import numpy as np

def run_tests():
    print("==================================================")
    print("Health Insight Dashboard: 전체 성공 기준 종합 검증")
    print("==================================================")
    
    df = app.df
    indicator_catalog = app.indicator_catalog
    country_catalog = app.country_catalog
    
    # 1. 데이터 및 엔터티 검증
    assert len(indicator_catalog) == 11, f"지표 수 불일치: {len(indicator_catalog)} != 11"
    assert len(country_catalog) == 266, f"국가/엔터티 수 불일치: {len(country_catalog)} != 266"
    
    real_countries = [c for c in country_catalog if not c['is_aggregate']]
    aggregates = [c for c in country_catalog if c['is_aggregate']]
    assert len(real_countries) == 217, f"실제 국가 수 불일치: {len(real_countries)} != 217"
    assert len(aggregates) == 49, f"집계 그룹 수 불일치: {len(aggregates)} != 49"
    print("[PASS] 1. 데이터셋 및 엔터티 분리 (지표 11개, 실제국가 217개, 집계 49개)")

    # 2. 권장 기준연도 검증
    expected_years = {
        'SP.DYN.LE00.IN': 2024,
        'SP.DYN.IMRT.IN': 2024,
        'SH.XPD.CHEX.PP.CD': 2023,
        'SH.XPD.CHEX.GD.ZS': 2023,
        'SH.XPD.OOPC.CH.ZS': 2023,
        'SH.PRV.SMOK': 2024,
        'SH.ALC.PCAP.LI': 2020,
        'SH.MED.PHYS.ZS': 2018,
        'SH.MED.BEDS.ZS': 2019,
        'SP.POP.65UP.TO.ZS': 2025,
        'NY.GDP.PCAP.CD': 2024
    }
    for code, yr in expected_years.items():
        actual_yr = indicator_catalog[code]['recommended_year']
        assert actual_yr == yr, f"권장연도 불일치 ({code}): {actual_yr} != {yr}"
    print("[PASS] 2. 지표별 권장 기준연도 정확성 검증 (11개 지표 모두 일치)")

    # 3. 2023 주요 수치 검증
    # 기대수명 2023
    le = df[(df['indicator_code']=='SP.DYN.LE00.IN') & (df['year']==2023)]
    kor_le = round(float(le[le['country_code']=='KOR']['value'].iloc[0]), 1)
    jpn_le = round(float(le[le['country_code']=='JPN']['value'].iloc[0]), 1)
    usa_le = round(float(le[le['country_code']=='USA']['value'].iloc[0]), 1)
    assert kor_le == 83.4 and jpn_le == 84.0 and usa_le == 78.4, f"기대수명 불일치: KOR={kor_le}, JPN={jpn_le}, USA={usa_le}"
    
    # 1인당 의료비 PPP 2023
    chex = df[(df['indicator_code']=='SH.XPD.CHEX.PP.CD') & (df['year']==2023)]
    kor_chex = round(float(chex[chex['country_code']=='KOR']['value'].iloc[0]))
    usa_chex = round(float(chex[chex['country_code']=='USA']['value'].iloc[0]))
    assert kor_chex == 4798 and usa_chex == 13473, f"1인당 의료비 불일치: KOR={kor_chex}, USA={usa_chex}"

    # 본인부담 의료비 2023
    oopc = df[(df['indicator_code']=='SH.XPD.OOPC.CH.ZS') & (df['year']==2023)]
    kor_oopc = round(float(oopc[oopc['country_code']=='KOR']['value'].iloc[0]), 1)
    jpn_oopc = round(float(oopc[oopc['country_code']=='JPN']['value'].iloc[0]), 1)
    usa_oopc = round(float(oopc[oopc['country_code']=='USA']['value'].iloc[0]), 1)
    assert kor_oopc == 31.8 and jpn_oopc == 12.2 and usa_oopc == 10.9, f"본인부담금 불일치: KOR={kor_oopc}, JPN={jpn_oopc}, USA={usa_oopc}"
    print("[PASS] 3. 2023 기준 핵심 국가 수치 (기대수명, 의료비, 본인부담률 검증 완료)")

    # 4. 효율성 잔차 및 강건성 검증
    # efficiency_residual (전체)
    res_all = tools.execute_tool("efficiency_residual", df, indicator_catalog, country_catalog, year=2023, peer=None)
    table_all = {r['country_code']: r for r in res_all['all_data']}
    assert round(table_all['KOR']['residual'], 1) == 3.3 and table_all['KOR']['rank'] == 35
    assert round(table_all['USA']['residual'], 1) == -6.2 and table_all['USA']['rank'] == 180

    # efficiency_residual (High income)
    res_high = tools.execute_tool("efficiency_residual", df, indicator_catalog, country_catalog, year=2023, peer="High income")
    table_high = {r['country_code']: r for r in res_high['all_data']}
    assert round(table_high['KOR']['residual'], 1) == 2.8 and table_high['KOR']['rank'] == 12
    assert round(table_high['USA']['residual'], 1) == -7.2 and table_high['USA']['rank'] == 63

    # robustness_check (High income)
    rob = tools.execute_tool("robustness_check", df, indicator_catalog, country_catalog, peer="High income", highlight=["KOR", "USA"])
    top_consistent_codes = [c['country_code'] for c in rob['top_consistent'] if c['top10_count'] == 4]
    bottom_consistent_codes = [c['country_code'] for c in rob['bottom_consistent'] if c['bottom10_count'] == 4]
    assert "SMR" in top_consistent_codes and "ATG" in top_consistent_codes and "ISR" in top_consistent_codes
    assert "USA" in bottom_consistent_codes
    
    hl_map = {c['country_code']: c['ranks'] for c in rob['highlight_table']}
    assert hl_map['KOR'] == [12, 4, 12, 20]
    assert hl_map['USA'] == [62, 63, 63, 60]
    print("[PASS] 4. 효율성 잔차 및 4가지 조건 강건성 분석 수치 일치")

    # 5. 상관분석 및 산점도 검증
    scat = tools.execute_tool("scatter_relation", df, indicator_catalog, country_catalog, x_indicator="SH.XPD.CHEX.PP.CD", y_indicator="SP.DYN.LE00.IN", year=2023, x_log=True)
    assert round(scat['correlation_raw'], 3) == 0.727
    assert round(scat['correlation_log'], 3) == 0.840

    corr = tools.execute_tool("correlation_with", df, indicator_catalog, country_catalog, target_indicator="SP.DYN.LE00.IN", year=2023)
    corr_map = {row['indicator_code']: row for row in corr['data']}
    assert corr_map['SH.MED.PHYS.ZS']['n'] == 58
    assert corr_map['SH.MED.BEDS.ZS']['n'] == 73
    assert corr_map['SH.XPD.CHEX.PP.CD']['n'] == 192
    print("[PASS] 5. 로그 산점도 상관계수 및 다중 상관분석(공통 표본수) 검증 완료")

    # 6. Flask API 엔드포인트 9종 도구 실행 검증
    client = app.app.test_client()
    
    # /health
    h_res = client.get('/health')
    assert h_res.status_code == 200 and h_res.get_json()['status'] == 'healthy'
    
    # /catalog
    c_res = client.get('/catalog')
    assert c_res.status_code == 200 and len(c_res.get_json()['indicators']) == 11

    # 9개 도구 각각 /run 실행
    tool_cases = [
        ("data_coverage", {"indicator_code": "SP.DYN.LE00.IN"}),
        ("rank_indicator", {"indicator_code": "SP.DYN.LE00.IN", "year": 2024, "top_n": 10}),
        ("trend_compare", {"indicator_code": "SP.DYN.LE00.IN", "country_codes": ["KOR", "USA", "JPN"]}),
        ("scatter_relation", {"x_indicator": "SH.XPD.CHEX.PP.CD", "y_indicator": "SP.DYN.LE00.IN", "year": 2023, "x_log": True}),
        ("efficiency_residual", {"year": 2023, "peer": "High income"}),
        ("robustness_check", {"peer": "High income"}),
        ("country_profile", {"country_code": "KOR"}),
        ("group_summary", {"indicator_code": "SP.DYN.LE00.IN", "group_by": "income_group"}),
        ("correlation_with", {"target_indicator": "SP.DYN.LE00.IN", "year": 2023})
    ]

    for tool_name, params in tool_cases:
        r = client.post('/run', json={"tool_name": tool_name, "params": params})
        assert r.status_code == 200, f"/run {tool_name} 실패: {r.status_code}, {r.data}"
        data = r.get_json()
        assert data['status'] == 'success', f"/run {tool_name} 상태 비정상: {data}"
    print("[PASS] 6. Flask 9개 분석 도구 POST /run 엔드포인트 연동 테스트 전체 성공")

    # 7. 프론트엔드 핵심 에셋 존재 확인
    import os
    assert os.path.exists("templates/index.html"), "templates/index.html 누락"
    assert os.path.exists("static/style.css"), "static/style.css 누락"
    assert os.path.exists("static/app.js"), "static/app.js 누락"
    print("[PASS] 7. 프론트엔드 HTML/CSS/JS 에셋 구조 검증 완료")
    
    print("\n==================================================")
    print("전체 7개 검증 카테고리 모두 정상 통과 (ALL TESTS PASSED)")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
