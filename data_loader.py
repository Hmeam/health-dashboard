import os
import glob
import logging
import pandas as pd

logger = logging.getLogger("health_dashboard")

ENCODINGS = ["utf-8-sig", "utf-8", "cp949"]

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
        except Exception as e:
            continue
            
    raise ValueError(f"데이터 파일 로드 실패 (지원 인코딩 시도 완료): {file_name}")

def load_indicator_files(data_dir="data/indicators"):
    """
    data/indicators의 모든 API_*.csv 파일을 읽어 각 파일을 long format으로 변환하고
    하나의 DataFrame으로 결합합니다.
    """
    pattern = os.path.join(data_dir, "API_*.csv")
    files = glob.glob(pattern)
    
    if not files:
        raise FileNotFoundError(f"지표 데이터 파일이 {data_dir} 경로에 없습니다.")
        
    long_dfs = []
    
    for file_path in sorted(files):
        df, enc, header_line = detect_header_and_read(file_path)
        
        # 필수 열 확인
        required_cols = ["Country Name", "Country Code", "Indicator Name", "Indicator Code"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"필수 열 누락: '{col}' in {os.path.basename(file_path)}")
                
        # 연도 열 식별 (숫자로만 이루어진 4자리 열)
        year_cols = [c for c in df.columns if str(c).isdigit()]
        
        melted = pd.melt(
            df,
            id_vars=required_cols,
            value_vars=year_cols,
            var_name="year",
            value_name="value"
        )
        
        # 표준 컬럼명으로 소문자 통일
        melted = melted.rename(columns={
            "Country Code": "country_code",
            "Country Name": "country_name",
            "Indicator Code": "indicator_code",
            "Indicator Name": "indicator_name"
        })
        
        melted["year"] = melted["year"].astype(int)
        melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
        
        # 빈칸은 0으로 채우지 않고 제외 (NaN 제거)
        melted = melted.dropna(subset=["value"])
        
        long_dfs.append(melted)
        
    combined_df = pd.concat(long_dfs, ignore_index=True)
    return combined_df

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("Step 12 data_loader.py 테스트 실행 시작")
    df = load_indicator_files()
    logger.info(f"총 Long Format 데이터 행 수: {len(df):,}")
    logger.info(f"고유 지표 수: {df['indicator_code'].nunique()}개")
    logger.info(f"고유 국가/엔터티 수: {df['country_code'].nunique()}개")
