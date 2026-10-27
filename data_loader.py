import os
import glob
import logging
import pandas as pd

logger = logging.getLogger("health_dashboard")

ENCODINGS = ["utf-8-sig", "utf-8", "cp949"]

# 지표 한글명 및 단위, 방향성 사전
INDICATOR_INFO = {
    "SP.DYN.LE00.IN": {
        "name_ko": "기대수명",
        "unit": "년",
        "direction": "higher_is_better"
    },
    "SP.DYN.IMRT.IN": {
        "name_ko": "영아사망률",
        "unit": "출생아 1,000명당",
        "direction": "lower_is_better"
    },
    "SH.XPD.CHEX.PP.CD": {
        "name_ko": "1인당 경상의료비",
        "unit": "PPP 국제달러",
        "direction": "neutral"
    },
    "SH.XPD.CHEX.GD.ZS": {
        "name_ko": "GDP 대비 경상의료비",
        "unit": "%",
        "direction": "neutral"
    },
    "SH.XPD.OOPC.CH.ZS": {
        "name_ko": "본인부담 의료비 비율",
        "unit": "%",
        "direction": "lower_is_better"
    },
    "SH.MED.PHYS.ZS": {
        "name_ko": "인구 1,000명당 의사 수",
        "unit": "명/1,000명",
        "direction": "higher_is_better"
    },
    "SH.MED.BEDS.ZS": {
        "name_ko": "인구 1,000명당 병상 수",
        "unit": "개/1,000명",
        "direction": "higher_is_better"
    },
    "SH.PRV.SMOK": {
        "name_ko": "성인 흡연율",
        "unit": "%",
        "direction": "lower_is_better"
    },
    "SH.ALC.PCAP.LI": {
        "name_ko": "15세 이상 1인당 알코올 소비량",
        "unit": "순수 알코올 리터",
        "direction": "lower_is_better"
    },
    "NY.GDP.PCAP.CD": {
        "name_ko": "1인당 GDP",
        "unit": "현재 미국달러",
        "direction": "higher_is_better"
    },
    "SP.POP.65UP.TO.ZS": {
        "name_ko": "65세 이상 인구 비율",
        "unit": "%",
        "direction": "neutral"
    }
}

# 메모리 캐시 저장소
_CACHED_DATA = None
_CACHED_CATALOG = None
_CACHED_COUNTRIES = None

def detect_header_and_read(file_path):
    """
    utf-8-sig, utf-8, cp949 순서로 인코딩을 시도하고,
    'Country Name'과 'Country Code'가 포함된 헤더 행을 자동 감지하여 DataFrame으로 로드합니다.
    """
    file_name = os.path.basename(file_path)
    for enc in ENCODINGS:
        try:
            header_line = 0
            with open(file_path, "r", encoding=enc, errors="replace") as f:
                for idx in range(25):
                    line = f.readline()
                    if not line:
                        break
                    if "Country Name" in line and "Country Code" in line:
                        header_line = idx
                        break
            
            df = pd.read_csv(file_path, skiprows=header_line, encoding=enc)
            # Unnamed 열 및 전체가 빈 열 제거
            df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed")]
            df = df.dropna(how="all", axis=1)
            
            logger.info(f"[LOAD] 파일명: {file_name}, 인코딩: {enc}, 건너뛴 줄 수: {header_line}, 행 수: {len(df)}")
            return df, enc, header_line
        except Exception:
            continue
            
    raise ValueError(f"데이터 파일 로드 실패 (지원 인코딩 시도 완료): {file_name}")

def load_country_metadata(meta_dir="data/meta"):
    """
    Metadata_Country_*.csv 파일을 읽어 국가별 Region, IncomeGroup 정보를 반환합니다.
    """
    pattern = os.path.join(meta_dir, "Metadata_Country_*.csv")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError("Metadata_Country 파일을 data/meta에서 찾을 수 없습니다.")
        
    meta_path = files[0]
    df = None
    for enc in ENCODINGS:
        try:
            df = pd.read_csv(meta_path, encoding=enc)
            logger.info(f"[LOAD] 파일명: {os.path.basename(meta_path)}, 인코딩: {enc}, 건너뛴 줄 수: 0, 행 수: {len(df)}")
            break
        except Exception:
            continue
            
    if df is None:
        raise ValueError(f"Metadata_Country 로드 실패: {meta_path}")
        
    df = df.rename(columns={
        "Country Code": "country_code",
        "Region": "region",
        "IncomeGroup": "income_group"
    })
    
    return df[["country_code", "region", "income_group"]]

def load_indicator_metadata(meta_dir="data/meta"):
    """
    Metadata_Indicator_*.csv 11개 파일을 읽어 SOURCE_NOTE, SOURCE_ORGANIZATION을 추출합니다.
    """
    pattern = os.path.join(meta_dir, "Metadata_Indicator_*.csv")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError("Metadata_Indicator 파일을 data/meta에서 찾을 수 없습니다.")
        
    meta_dict = {}
    for fpath in sorted(files):
        for enc in ENCODINGS:
            try:
                df = pd.read_csv(fpath, encoding=enc)
                logger.info(f"[LOAD] 파일명: {os.path.basename(fpath)}, 인코딩: {enc}, 건너뛴 줄 수: 0, 행 수: {len(df)}")
                for _, row in df.iterrows():
                    code = str(row.get("INDICATOR_CODE", "")).strip()
                    if code:
                        meta_dict[code] = {
                            "source_note": str(row.get("SOURCE_NOTE", "")).strip(),
                            "source_org": str(row.get("SOURCE_ORGANIZATION", "")).strip()
                        }
                break
            except Exception:
                continue
                
    return meta_dict

def load_indicator_files(data_dir="data/indicators"):
    """
    data/indicators의 모든 API_*.csv 파일을 읽어
    (raw_melted_df, raw_countries_df)를 반환합니다.
    """
    pattern = os.path.join(data_dir, "API_*.csv")
    files = glob.glob(pattern)
    
    if not files:
        raise FileNotFoundError(f"지표 데이터 파일이 {data_dir} 경로에 없습니다.")
        
    long_dfs = []
    base_countries_df = None
    
    for file_path in sorted(files):
        df, enc, header_line = detect_header_and_read(file_path)
        
        required_cols = ["Country Name", "Country Code", "Indicator Name", "Indicator Code"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"필수 열 누락: '{col}' in {os.path.basename(file_path)}")
                
        if base_countries_df is None:
            # 최초 파일의 266개 국가/엔터티 목록 보존
            base_countries_df = df[["Country Code", "Country Name"]].drop_duplicates().rename(columns={
                "Country Code": "country_code",
                "Country Name": "country_name"
            })
                
        year_cols = [c for c in df.columns if str(c).isdigit()]
        
        melted = pd.melt(
            df,
            id_vars=required_cols,
            value_vars=year_cols,
            var_name="year",
            value_name="value"
        )
        
        melted = melted.rename(columns={
            "Country Code": "country_code",
            "Country Name": "country_name",
            "Indicator Code": "indicator_code",
            "Indicator Name": "indicator_name"
        })
        
        melted["year"] = melted["year"].astype(int)
        melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
        melted = melted.dropna(subset=["value"])
        
        long_dfs.append(melted)
        
    combined_melted = pd.concat(long_dfs, ignore_index=True)
    return combined_melted, base_countries_df

def load_all_data(data_dir="data", force_reload=False):
    """
    지표 CSV 11개와 메타 CSV들을 결합하여
    (combined_df, indicator_catalog, country_catalog) 튜플을 반환합니다.
    """
    global _CACHED_DATA, _CACHED_CATALOG, _CACHED_COUNTRIES
    
    if not force_reload and _CACHED_DATA is not None:
        return _CACHED_DATA, _CACHED_CATALOG, _CACHED_COUNTRIES
        
    ind_dir = os.path.join(data_dir, "indicators")
    meta_dir = os.path.join(data_dir, "meta")
    
    # 1. 지표 데이터 로드 및 266개 국가 기본 마스터 확보
    raw_df, base_countries_df = load_indicator_files(ind_dir)
    
    # 2. 메타데이터 로드
    country_meta = load_country_metadata(meta_dir)
    indicator_meta = load_indicator_metadata(meta_dir)
    
    # 3. 국가 카탈로그 구축 (266개 행: 실제 국가 217개, 집계 행 49개)
    # 집계 행 판별 규칙: Metadata_Country 파일에서 Region이 비어 있거나 메타 파일에 없는 코드
    full_country_df = base_countries_df.merge(country_meta, on="country_code", how="left")
    full_country_df["is_aggregate"] = (
        full_country_df["region"].isna() | 
        (full_country_df["region"].astype(str).str.strip() == "")
    )
    
    country_catalog = []
    for _, row in full_country_df.sort_values("country_name").iterrows():
        country_catalog.append({
            "country_code": row["country_code"],
            "country_name": row["country_name"],
            "region": None if pd.isna(row["region"]) else row["region"],
            "income_group": None if pd.isna(row["income_group"]) else row["income_group"],
            "is_aggregate": bool(row["is_aggregate"])
        })
        
    total_real_countries = sum(1 for c in country_catalog if not c["is_aggregate"])
    total_aggregate_entities = sum(1 for c in country_catalog if c["is_aggregate"])
    
    # 4. Long format 데이터에 국가 메타 및 is_aggregate 결합
    country_lookup = {c["country_code"]: c for c in country_catalog}
    merged_df = raw_df.copy()
    merged_df["region"] = merged_df["country_code"].map(lambda code: country_lookup.get(code, {}).get("region"))
    merged_df["income_group"] = merged_df["country_code"].map(lambda code: country_lookup.get(code, {}).get("income_group"))
    merged_df["is_aggregate"] = merged_df["country_code"].map(lambda code: country_lookup.get(code, {}).get("is_aggregate", True))
    
    # 컬럼 순서 정렬
    merged_df = merged_df[[
        "country_code", "country_name", "region", "income_group",
        "indicator_code", "indicator_name", "year", "value", "is_aggregate"
    ]]
    
    # 5. 지표 카탈로그 구축 (권장 기준연도: 80% 이상 채워진 최근 연도)
    indicator_catalog = {}
    real_df = merged_df[~merged_df["is_aggregate"]]
    
    for ind_code, group in merged_df.groupby("indicator_code"):
        # 실제 국가 데이터만 기준으로 연도별 국가 수 집계
        real_group = real_df[real_df["indicator_code"] == ind_code]
        year_counts = real_group.groupby("year")["country_code"].nunique().to_dict()
        
        # 지표 자체의 최대 국가 수 기준 90% 이상 채워진 가장 최근 연도 산출
        if year_counts:
            max_c = max(year_counts.values())
            threshold = max_c * 0.9
            eligible_years = [y for y, cnt in year_counts.items() if cnt >= threshold]
            if eligible_years:
                rec_year = max(eligible_years)
            else:
                # 동률 또는 대체 시 가장 최근 연도 선택
                max_years = [y for y, cnt in year_counts.items() if cnt == max_c]
                rec_year = max(max_years)
        else:
            rec_year = 2023
            
        custom_info = INDICATOR_INFO.get(ind_code, {})
        meta_info = indicator_meta.get(ind_code, {})
        
        indicator_catalog[ind_code] = {
            "indicator_code": ind_code,
            "indicator_name": group["indicator_name"].iloc[0],
            "name_ko": custom_info.get("name_ko", group["indicator_name"].iloc[0]),
            "unit": custom_info.get("unit", ""),
            "direction": custom_info.get("direction", "neutral"),
            "source_note": meta_info.get("source_note", ""),
            "source_org": meta_info.get("source_org", ""),
            "year_coverage": year_counts,
            "recommended_year": int(rec_year)
        }
        
    total_indicators = len(indicator_catalog)
    total_long_rows = len(merged_df)
    
    # 규격 로그: [MERGE] 지표 수, 국가 수, 집계 행 수, long format 행 수
    logger.info(
        f"[MERGE] 지표 수: {total_indicators}, 국가 수: {total_real_countries}, "
        f"집계 행 수: {total_aggregate_entities}, long format 행 수: {total_long_rows:,}"
    )
    
    _CACHED_DATA = merged_df
    _CACHED_CATALOG = indicator_catalog
    _CACHED_COUNTRIES = country_catalog
    
    return merged_df, indicator_catalog, country_catalog

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("Step 13 data_loader.py 권장 기준연도 검증 실행")
    df, catalog, countries = load_all_data(force_reload=True)
    print("\n--- 권장 기준연도 산출 결과 ---")
    for code, info in catalog.items():
        rec_y = info["recommended_year"]
        cov = info["year_coverage"].get(rec_y, 0)
        print(f"[{code}] {info['name_ko']}: {rec_y}년 ({cov}개국)")
