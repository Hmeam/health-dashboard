/**
 * Health Insight Dashboard - Vanilla JavaScript Frontend
 * Console log 규격: [PAGE] [CATALOG] [SUGGEST] [RUN] [CHART] [EXPLAIN] [CHAT] [ERROR]
 */

// 전역 상태 관리
const state = {
    indicators: {},
    countries: [],
    currentRunResult: null,
    currentExplainReport: null,
    currentChart: null,
    chatHistory: []
};

// DOM 로드 시 초기화
document.addEventListener("DOMContentLoaded", () => {
    console.log("[PAGE] Health Insight Dashboard 페이지 로드 완료");
    checkHealth();
    loadCatalog();
    initEventListeners();
});

// 1. 서버 헬스체크 및 API 키 상태 확인
async function checkHealth() {
    const serverBadge = document.getElementById("serverStatusBadge");
    const apiBadge = document.getElementById("apiKeyBadge");

    try {
        const res = await fetch("/health");
        const data = await res.json();
        
        if (data.status === "healthy") {
            serverBadge.textContent = "서버: 정상 가동";
            serverBadge.className = "badge badge-success";
        } else {
            serverBadge.textContent = "서버: 비정상";
            serverBadge.className = "badge badge-danger";
        }

        if (data.api_key_set) {
            apiBadge.textContent = "Gemini: API Key 설정됨";
            apiBadge.className = "badge badge-success";
        } else {
            apiBadge.textContent = "Gemini: API Key 미설정";
            apiBadge.className = "badge badge-danger";
        }
        console.log(`[PAGE] 헬스체크 완료: indicators_loaded=${data.indicators_loaded}, api_key_set=${data.api_key_set}`);
    } catch (err) {
        console.error("[ERROR] 헬스체크 통신 오류:", err.message);
        serverBadge.textContent = "서버: 연결 불가";
        serverBadge.className = "badge badge-danger";
        apiBadge.textContent = "Gemini: 확인 불가";
        apiBadge.className = "badge badge-danger";
    }
}

// 2. 지표 카탈로그 로드
async function loadCatalog() {
    try {
        console.log("[CATALOG] /catalog 요청 시작");
        const res = await fetch("/catalog");
        const data = await res.json();

        if (data.status === "success") {
            state.indicators = data.indicators;
            state.countries = data.countries;
            console.log(`[CATALOG] 로드 완료: 지표 ${Object.keys(state.indicators).length}개, 국가 ${state.countries.length}개`);
            renderDynamicParams();
        } else {
            console.error("[ERROR] 카탈로그 로드 실패:", data.message);
        }
    } catch (err) {
        console.error("[ERROR] 카탈로그 요청 통신 오류:", err.message);
    }
}

// 3. 이벤트 리스너 등록
function initEventListeners() {
    // 도구 선택 변경 시 동적 파라미터 렌더링
    document.getElementById("toolSelect").addEventListener("change", () => {
        renderDynamicParams();
    });

    // AI 제안 버튼 클릭
    document.getElementById("suggestBtn").addEventListener("click", handleSuggest);
    document.getElementById("suggestQuestionInput").addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleSuggest();
    });

    // 분석 실행 버튼 클릭
    document.getElementById("runBtn").addEventListener("click", handleRunTool);

    // AI 심층 해석 버튼 클릭
    document.getElementById("explainBtn").addEventListener("click", handleExplain);

    // 후속 질의응답 전송 버튼 클릭
    document.getElementById("sendChatBtn").addEventListener("click", handleChat);
    document.getElementById("chatInput").addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleChat();
    });
}

// 4. 도구별 동적 파라미터 폼 렌더링
function renderDynamicParams() {
    const tool = document.getElementById("toolSelect").value;
    const container = document.getElementById("dynamicParams");
    container.innerHTML = "";

    const indOptions = Object.values(state.indicators).map(ind => 
        `<option value="${ind.indicator_code}">${ind.name_ko} (${ind.indicator_code})</option>`
    ).join("");

    const realCountries = state.countries.filter(c => !c.is_aggregate);
    const countryOptions = realCountries.map(c => 
        `<option value="${c.country_code}" ${c.country_code === 'KOR' ? 'selected' : ''}>${c.country_name} (${c.country_code})</option>`
    ).join("");

    if (tool === "country_profile") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramCountry">대상 국가</label>
                <select id="paramCountry">${countryOptions}</select>
            </div>
            <div class="form-group">
                <label for="paramYear">기준 연도 (미입력 시 지표별 권장연도)</label>
                <input type="text" id="paramYear" placeholder="기본: 각 지표 권장연도" />
            </div>
        `;
    } else if (tool === "efficiency_residual") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramXInd">투입 지표 (X, 비용)</label>
                <select id="paramXInd">
                    <option value="SH.XPD.CHEX.PP.CD" selected>1인당 경상의료비 (PPP 국제달러)</option>
                    <option value="SH.XPD.CHEX.GD.ZS">GDP 대비 경상의료비 (%)</option>
                    <option value="NY.GDP.PCAP.CD">1인당 GDP (현재 미국달러)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramYInd">성과 지표 (Y, 건강)</label>
                <select id="paramYInd">
                    <option value="SP.DYN.LE00.IN" selected>기대수명 (년, 높을수록 좋음)</option>
                    <option value="SP.DYN.IMRT.IN">영아사망률 (출생아 1,000명당, 낮을수록 좋음)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramYear">기준 연도</label>
                <input type="text" id="paramYear" value="2023" />
            </div>
            <div class="form-group">
                <label for="paramPeer">비교 대상 소득 그룹</label>
                <select id="paramPeer">
                    <option value="High income" selected>High income (고소득국 비교)</option>
                    <option value="all">all (전체 국가 비교)</option>
                    <option value="Upper middle income">Upper middle income (상위중간소득국)</option>
                    <option value="Lower middle income">Lower middle income (하위중간소득국)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramHighlight">강조 국가 (쉼표 구분)</label>
                <input type="text" id="paramHighlight" value="KOR, USA" />
            </div>
            <div class="form-group">
                <label for="paramTopN">표시할 상/하위 국가 수</label>
                <input type="number" id="paramTopN" value="10" min="5" max="30" />
            </div>
        `;
    } else if (tool === "robustness_check") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramXInd">기준 투입 지표 (X)</label>
                <select id="paramXInd">
                    <option value="SH.XPD.CHEX.PP.CD" selected>1인당 경상의료비 (PPP 국제달러)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramPeer">비교 소득 그룹 (peer)</label>
                <select id="paramPeer">
                    <option value="High income" selected>High income (고소득국 일관성 검증)</option>
                    <option value="all">all (전체 국가 검증 - 위기국가 착시 주의)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramHighlight">강조 국가 (조건별 순위 추적)</label>
                <input type="text" id="paramHighlight" value="KOR, USA" />
            </div>
        `;
    } else if (tool === "rank_indicator") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramInd">분석 지표</label>
                <select id="paramInd">${indOptions}</select>
            </div>
            <div class="form-group">
                <label for="paramYear">기준 연도 (비워두면 권장연도)</label>
                <input type="text" id="paramYear" placeholder="지표별 권장연도 자동적용" />
            </div>
            <div class="form-group">
                <label for="paramTopN">표시 개수 (N)</label>
                <input type="number" id="paramTopN" value="10" min="5" max="50" />
            </div>
            <div class="form-group">
                <label for="paramOrder">정렬 순서</label>
                <select id="paramOrder">
                    <option value="top" selected>상위 N개국 (우수 국가)</option>
                    <option value="bottom">하위 N개국 (취약 국가)</option>
                    <option value="both">상위 및 하위 동시 비교</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramPeer">소득 그룹 필터</label>
                <select id="paramPeer">
                    <option value="all" selected>전체</option>
                    <option value="High income">High income</option>
                    <option value="Upper middle income">Upper middle income</option>
                    <option value="Lower middle income">Lower middle income</option>
                    <option value="Low income">Low income</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramHighlight">강조 국가 (쉼표 구분)</label>
                <input type="text" id="paramHighlight" value="KOR, USA" />
            </div>
        `;
    } else if (tool === "trend_compare") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramInd">분석 지표</label>
                <select id="paramInd">${indOptions}</select>
            </div>
            <div class="form-group">
                <label for="paramCountries">비교 국가 코드 (쉼표 구분)</label>
                <input type="text" id="paramCountries" value="KOR, USA, JPN, DEU, GBR" />
            </div>
            <div class="form-group">
                <label for="paramStartYear">시작 연도</label>
                <input type="number" id="paramStartYear" value="2010" />
            </div>
            <div class="form-group">
                <label for="paramEndYear">종료 연도</label>
                <input type="number" id="paramEndYear" value="2023" />
            </div>
            <div class="form-group">
                <label for="paramHighlight">강조 국가 (빨간색 굵은선)</label>
                <input type="text" id="paramHighlight" value="KOR" />
            </div>
        `;
    } else if (tool === "scatter_relation") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramXInd">X축 지표</label>
                <select id="paramXInd">${indOptions}</select>
            </div>
            <div class="form-group">
                <label for="paramYInd">Y축 지표</label>
                <select id="paramYInd">${indOptions}</select>
            </div>
            <div class="form-group">
                <label for="paramYear">기준 연도</label>
                <input type="text" id="paramYear" value="2023" />
            </div>
            <div class="form-group">
                <label for="paramXLog">X축 스케일</label>
                <select id="paramXLog">
                    <option value="true" selected>Log10 스케일 (한계효용 반영 및 r_log 산출)</option>
                    <option value="false">일반 선형 스케일 (원값 및 r 산출)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramPeer">소득 그룹 필터</label>
                <select id="paramPeer">
                    <option value="all" selected>전체</option>
                    <option value="High income">High income</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramHighlight">강조 국가</label>
                <input type="text" id="paramHighlight" value="KOR, USA" />
            </div>
        `;
    } else if (tool === "group_summary") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramInd">분석 지표</label>
                <select id="paramInd">${indOptions}</select>
            </div>
            <div class="form-group">
                <label for="paramGroupBy">그룹화 기준</label>
                <select id="paramGroupBy">
                    <option value="income_group" selected>소득 그룹 (income_group)</option>
                    <option value="region">지역/대륙 (region)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="paramYear">기준 연도 (비워두면 권장연도)</label>
                <input type="text" id="paramYear" placeholder="기본 권장연도" />
            </div>
        `;
    } else if (tool === "correlation_with") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramTargetInd">기준 지표 (Target)</label>
                <select id="paramTargetInd">${indOptions}</select>
            </div>
            <div class="form-group">
                <label for="paramYear">기준 연도 (동일 연도 엄격 비교)</label>
                <input type="text" id="paramYear" value="2023" />
            </div>
        `;
    } else if (tool === "data_coverage") {
        container.innerHTML = `
            <div class="form-group">
                <label for="paramInd">특정 지표 (선택 사항)</label>
                <select id="paramInd">
                    <option value="">전체 11개 지표 동시 확인</option>
                    ${indOptions}
                </select>
            </div>
        `;
    }
}

// 5. 파라미터 값 추출
function collectParams(tool) {
    const params = {};
    const parseCommaList = (str) => str ? str.split(",").map(s => s.trim().toUpperCase()).filter(Boolean) : [];

    if (tool === "country_profile") {
        params.country_code = document.getElementById("paramCountry").value;
        const y = document.getElementById("paramYear").value.trim();
        if (y) params.year = parseInt(y, 10);
    } else if (tool === "efficiency_residual") {
        params.x_indicator = document.getElementById("paramXInd").value;
        params.y_indicator = document.getElementById("paramYInd").value;
        params.year = parseInt(document.getElementById("paramYear").value.trim() || 2023, 10);
        params.peer = document.getElementById("paramPeer").value;
        params.highlight = parseCommaList(document.getElementById("paramHighlight").value);
        params.top_n = parseInt(document.getElementById("paramTopN").value || 10, 10);
    } else if (tool === "robustness_check") {
        params.x_indicator = document.getElementById("paramXInd").value;
        params.peer = document.getElementById("paramPeer").value;
        params.highlight = parseCommaList(document.getElementById("paramHighlight").value);
    } else if (tool === "rank_indicator") {
        params.indicator_code = document.getElementById("paramInd").value;
        const y = document.getElementById("paramYear").value.trim();
        if (y) params.year = parseInt(y, 10);
        params.top_n = parseInt(document.getElementById("paramTopN").value || 10, 10);
        params.order = document.getElementById("paramOrder").value;
        params.peer = document.getElementById("paramPeer").value;
        params.highlight = parseCommaList(document.getElementById("paramHighlight").value);
    } else if (tool === "trend_compare") {
        params.indicator_code = document.getElementById("paramInd").value;
        params.country_codes = parseCommaList(document.getElementById("paramCountries").value);
        params.start_year = parseInt(document.getElementById("paramStartYear").value || 2010, 10);
        params.end_year = parseInt(document.getElementById("paramEndYear").value || 2023, 10);
        params.highlight = parseCommaList(document.getElementById("paramHighlight").value);
    } else if (tool === "scatter_relation") {
        params.x_indicator = document.getElementById("paramXInd").value;
        params.y_indicator = document.getElementById("paramYInd").value;
        const y = document.getElementById("paramYear").value.trim();
        if (y) params.year = parseInt(y, 10);
        params.x_log = document.getElementById("paramXLog").value === "true";
        params.peer = document.getElementById("paramPeer").value;
        params.highlight = parseCommaList(document.getElementById("paramHighlight").value);
    } else if (tool === "group_summary") {
        params.indicator_code = document.getElementById("paramInd").value;
        params.group_by = document.getElementById("paramGroupBy").value;
        const y = document.getElementById("paramYear").value.trim();
        if (y) params.year = parseInt(y, 10);
    } else if (tool === "correlation_with") {
        params.target_indicator = document.getElementById("paramTargetInd").value;
        const y = document.getElementById("paramYear").value.trim();
        if (y) params.year = parseInt(y, 10);
    } else if (tool === "data_coverage") {
        const ind = document.getElementById("paramInd").value;
        if (ind) params.indicator_code = ind;
    }

    return params;
}

// 6. Gemini 제안 핸들러 (POST /suggest)
async function handleSuggest() {
    const input = document.getElementById("suggestQuestionInput");
    const question = input.value.trim();
    if (!question) {
        alert("질문을 입력해 주세요.");
        return;
    }

    const loading = document.getElementById("suggestLoading");
    const resultsGrid = document.getElementById("suggestResults");

    loading.classList.remove("hidden");
    resultsGrid.classList.add("hidden");
    resultsGrid.innerHTML = "";

    try {
        console.log(`[SUGGEST] 질문 전송: "${question}"`);
        const res = await fetch("/suggest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question })
        });
        const data = await res.json();

        if (data.status === "success") {
            const suggestions = data.suggestions || [];
            console.log(`[SUGGEST] 제안 수신 완료 (${suggestions.length}개)`);
            
            resultsGrid.innerHTML = suggestions.map((sug, idx) => `
                <div class="suggest-card" onclick="applySuggestion(${idx})">
                    <h4>${idx + 1}. ${sug.title}</h4>
                    <p class="suggest-why">${sug.why}</p>
                    <p class="suggest-caution">⚠️ ${sug.caution}</p>
                </div>
            `).join("");

            // 전역에 현재 제안 목록 임시 보관
            window._lastSuggestions = suggestions;
            resultsGrid.classList.remove("hidden");
        } else {
            console.error("[ERROR] 제안 생성 실패:", data.message);
            alert(`AI 제안 실패: ${data.message}`);
        }
    } catch (err) {
        console.error("[ERROR] /suggest 통신 오류:", err.message);
        alert(`네트워크 오류: ${err.message}`);
    } finally {
        loading.classList.add("hidden");
    }
}

// 제안 카드 클릭 시 폼에 파라미터 자동 적용
window.applySuggestion = function(idx) {
    if (!window._lastSuggestions || !window._lastSuggestions[idx]) return;
    const sug = window._lastSuggestions[idx];
    console.log(`[SUGGEST] 제안 적용: tool=${sug.tool}`, sug.params);

    document.getElementById("toolSelect").value = sug.tool;
    renderDynamicParams();

    // 동적 파라미터 채우기
    setTimeout(() => {
        const p = sug.params || {};
        if (p.indicator_code && document.getElementById("paramInd")) document.getElementById("paramInd").value = p.indicator_code;
        if (p.x_indicator && document.getElementById("paramXInd")) document.getElementById("paramXInd").value = p.x_indicator;
        if (p.y_indicator && document.getElementById("paramYInd")) document.getElementById("paramYInd").value = p.y_indicator;
        if (p.target_indicator && document.getElementById("paramTargetInd")) document.getElementById("paramTargetInd").value = p.target_indicator;
        if (p.country_code && document.getElementById("paramCountry")) document.getElementById("paramCountry").value = p.country_code;
        if (p.country_codes && document.getElementById("paramCountries")) document.getElementById("paramCountries").value = p.country_codes.join(", ");
        if (p.year && document.getElementById("paramYear")) document.getElementById("paramYear").value = p.year;
        if (p.peer && document.getElementById("paramPeer")) document.getElementById("paramPeer").value = p.peer;
        if (p.order && document.getElementById("paramOrder")) document.getElementById("paramOrder").value = p.order;
        if (p.top_n && document.getElementById("paramTopN")) document.getElementById("paramTopN").value = p.top_n;
        if (p.highlight && document.getElementById("paramHighlight")) document.getElementById("paramHighlight").value = p.highlight.join(", ");
        if (p.x_log !== undefined && document.getElementById("paramXLog")) document.getElementById("paramXLog").value = String(p.x_log);

        // 분석 실행 버튼으로 부드럽게 스크롤
        document.getElementById("runBtn").scrollIntoView({ behavior: "smooth" });
    }, 50);
};

// 7. 도구 실행 핸들러 (POST /run)
async function handleRunTool() {
    const tool = document.getElementById("toolSelect").value;
    const params = collectParams(tool);

    console.log(`[RUN] 분석 실행 요청: tool=${tool}`, params);

    const runBtn = document.getElementById("runBtn");
    runBtn.disabled = true;
    runBtn.textContent = "Pandas 계산 중...";

    try {
        const res = await fetch("/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tool, params })
        });
        const data = await res.json();

        if (data.status === "success") {
            const result = data.result;
            state.currentRunResult = result;
            console.log(`[RUN] 계산 완료: 사용국가=${result.used_countries_count}, 제외국가=${result.excluded_countries_count}`);

            // 메타 정보 표시
            renderMetaSection(result);

            // 차트 렌더링
            renderChart(result);

            // 테이블 및 카드 렌더링
            renderResultsTable(result);

            // AI 해석 영역 노출 (이전 보고서는 리셋)
            document.getElementById("explainSection").classList.remove("hidden");
            document.getElementById("explainReportBox").classList.add("hidden");
            document.getElementById("explainReportBox").innerHTML = "";
            state.currentExplainReport = null;

            // 채팅 영역 다시 잠금
            document.getElementById("chatLockNotice").classList.remove("hidden");
            document.getElementById("chatActiveArea").classList.add("hidden");
        } else {
            console.error("[ERROR] /run 계산 실패:", data.message);
            alert(`분석 계산 오류: ${data.message}`);
        }
    } catch (err) {
        console.error("[ERROR] /run 통신 오류:", err.message);
        alert(`네트워크 통신 오류: ${err.message}`);
    } finally {
        runBtn.disabled = false;
        runBtn.textContent = "분석 실행하기 (Pandas 계산)";
    }
}

// 메타 정보 및 통계 주의사항 배너 렌더링
function renderMetaSection(result) {
    const metaSection = document.getElementById("metaInfoSection");
    metaSection.classList.remove("hidden");

    document.getElementById("infoYear").textContent = `기준 연도: ${result.year || '미지정'}`;
    document.getElementById("infoSample").textContent = `분석 대상: ${result.used_countries_count}개국`;
    document.getElementById("infoExcluded").textContent = `제외: ${result.excluded_countries_count}개국`;

    const exBox = document.getElementById("exclusionReasonBox");
    if (result.excluded_reason) {
        exBox.textContent = `ℹ️ 제외 사유: ${result.excluded_reason}`;
        exBox.classList.remove("hidden");
    } else {
        exBox.classList.add("hidden");
    }

    const cautionBox = document.getElementById("cautionBox");
    const cautions = result.cautions || [];
    if (result.warnings && result.warnings.length) {
        cautions.push(...result.warnings);
    }

    if (cautions.length > 0) {
        cautionBox.innerHTML = `<strong>⚠️ 통계적 주의사항:</strong><ul style="margin-left: 20px; margin-top: 6px;">${cautions.map(c => `<li>${c}</li>`).join("")}</ul>`;
        cautionBox.classList.remove("hidden");
    } else {
        cautionBox.classList.add("hidden");
    }
}

// 8. Chart.js 시각화 렌더링
function renderChart(result) {
    const chartSection = document.getElementById("chartSection");
    chartSection.classList.remove("hidden");

    const canvas = document.getElementById("mainChart");
    const ctx = canvas.getContext("2d");

    if (state.currentChart) {
        state.currentChart.destroy();
        state.currentChart = null;
    }

    const chartData = result.chart_data;
    if (!chartData || !chartData.datasets || chartData.datasets.length === 0) {
        console.warn("[CHART] 차트 데이터 없음");
        chartSection.classList.add("hidden");
        return;
    }

    console.log(`[CHART] 차트 생성: type=${chartData.type}, datasets=${chartData.datasets.length}`);

    const config = {
        type: chartData.type || "bar",
        data: {
            labels: chartData.labels,
            datasets: chartData.datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: chartData.indexAxis || "x",
            plugins: {
                legend: {
                    position: "top",
                    labels: { font: { size: 12 } }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const raw = context.raw;
                            if (typeof raw === "object" && raw !== null && raw.country_name) {
                                return `${raw.country_name}: (x=${raw.x}, y=${raw.y})`;
                            }
                            return `${context.dataset.label}: ${context.formattedValue}`;
                        }
                    }
                }
            },
            scales: {}
        }
    };

    // 로그 스케일 처리 (산점도 x_log)
    if (chartData.type === "scatter" && chartData.x_log) {
        config.options.scales.x = {
            type: "logarithmic",
            title: {
                display: true,
                text: `${result.x_indicator?.name_ko || 'X축'} (Log10 스케일)`
            }
        };
        config.options.scales.y = {
            title: {
                display: true,
                text: result.y_indicator?.name_ko || 'Y축'
            }
        };
    }

    state.currentChart = new Chart(ctx, config);
}

// 9. 계산 결과 테이블 렌더링
function renderResultsTable(result) {
    const tableSection = document.getElementById("tableSection");
    tableSection.classList.remove("hidden");

    const cardsGrid = document.getElementById("profileCardsGrid");
    const tableWrapper = document.getElementById("tableWrapper");
    const thead = document.getElementById("resultThead");
    const tbody = document.getElementById("resultTbody");

    cardsGrid.innerHTML = "";
    thead.innerHTML = "";
    tbody.innerHTML = "";

    // Tool 7: country_profile인 경우 카드형 + 테이블 듀얼 렌더링
    if (result.tool === "country_profile") {
        cardsGrid.classList.remove("hidden");
        const list = result.data || [];

        cardsGrid.innerHTML = list.map(item => `
            <div class="profile-card">
                <h4>${item.name_ko}</h4>
                <div class="profile-card-val">${item.value !== null ? item.value.toLocaleString() : '-'} <span style="font-size:0.9rem; font-weight:normal;">${item.unit}</span></div>
                <div class="profile-card-sub">
                    <strong>${item.rank_text || '-'}</strong> (백분위: ${item.percentile !== null ? item.percentile + '%' : '-'})<br>
                    소득그룹 중앙값: ${item.peer_median !== null ? item.peer_median.toLocaleString() : '-'} ${item.unit} 
                    (${item.peer_diff !== null && item.peer_diff > 0 ? '+' : ''}${item.peer_diff !== null ? item.peer_diff : '-'})<br>
                    기준 연도: ${item.year || '-'}년 ${item.is_recommended_year ? '✅' : '⚠️'}
                    ${item.year_fallback_note ? `<br><small style="color:#b45309;">${item.year_fallback_note}</small>` : ''}
                </div>
            </div>
        `).join("");
    } else {
        cardsGrid.classList.add("hidden");
    }

    // 일반 테이블 렌더링
    const dataList = result.data || [];
    if (!dataList || dataList.length === 0) {
        tbody.innerHTML = "<tr><td colspan='10' style='text-align:center;'>표시할 데이터가 없습니다.</td></tr>";
        return;
    }

    // 컬럼 키 추출 (불필요한 내부 raw 필드는 정리)
    const firstRow = dataList[0];
    const excludeKeys = ["is_extra", "is_recommended_year", "year_fallback_note", "note"];
    const colKeys = Object.keys(firstRow).filter(k => !excludeKeys.includes(k));

    thead.innerHTML = `<tr>${colKeys.map(k => `<th>${formatColHeader(k)}</th>`).join("")}</tr>`;

    const highlights = new Set(result.params?.highlight || []);

    tbody.innerHTML = dataList.map(row => {
        const isHl = highlights.has(row.country_code) || row.is_extra;
        return `
            <tr class="${isHl ? 'highlight-row' : ''}">
                ${colKeys.map(k => `<td>${formatCellValue(row[k])}</td>`).join("")}
            </tr>
        `;
    }).join("");
}

function formatColHeader(key) {
    const map = {
        "country_name": "국가명",
        "country_code": "코드",
        "rank": "순위",
        "value": "지표값",
        "x_val": "1인당 의료비",
        "y_val": "실제 기대수명",
        "expected_y": "예상 기대수명",
        "residual": "효율 잔차",
        "year": "연도",
        "name_ko": "지표명",
        "unit": "단위",
        "direction": "방향성",
        "percentile": "백분위(%)",
        "peer_median": "소득군 중앙값",
        "peer_diff": "중앙값 격차",
        "top10_count": "상위10위 횟수",
        "bottom10_count": "하위10위 횟수",
        "consistency_ratio": "일관성 비율",
        "group": "소득/지역 그룹",
        "count": "국가 수",
        "median": "중앙값",
        "mean": "평균값",
        "std": "표준편차",
        "correlation": "상관계수(r)",
        "correlation_log": "로그상관계수(r_log)",
        "common_countries_count": "공통 국가 수(n)",
        "n": "표본수(n)",
        "status": "상태"
    };
    return map[key] || key;
}

function formatCellValue(val) {
    if (val === null || val === undefined) return "-";
    if (typeof val === "number") {
        if (Number.isInteger(val)) return val.toLocaleString();
        return val.toLocaleString(undefined, { maximumFractionDigits: 4 });
    }
    return String(val);
}

// 10. AI 심층 해석 보고서 생성 (POST /explain)
async function handleExplain() {
    if (!state.currentRunResult) {
        alert("먼저 분석을 실행해 주세요.");
        return;
    }

    const explainBtn = document.getElementById("explainBtn");
    const loading = document.getElementById("explainLoading");
    const reportBox = document.getElementById("explainReportBox");

    explainBtn.disabled = true;
    loading.classList.remove("hidden");
    reportBox.classList.add("hidden");

    try {
        console.log(`[EXPLAIN] /explain 요청 시작: tool=${state.currentRunResult.tool}`);
        const res = await fetch("/explain", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ result: state.currentRunResult })
        });
        const data = await res.json();

        if (data.status === "success") {
            const report = data.report;
            state.currentExplainReport = report;
            console.log(`[EXPLAIN] 보고서 수신 완료 (길이: ${report.length}자)`);

            // 경량 마크다운 렌더링
            reportBox.innerHTML = renderSimpleMarkdown(report);
            reportBox.classList.remove("hidden");

            // 후속 질문(채팅) 영역 잠금 해제
            document.getElementById("chatLockNotice").classList.add("hidden");
            document.getElementById("chatActiveArea").classList.remove("hidden");
            document.getElementById("chatSection").scrollIntoView({ behavior: "smooth" });
        } else {
            console.error("[ERROR] /explain 생성 실패:", data.message);
            alert(`해석 보고서 생성 실패: ${data.message}`);
        }
    } catch (err) {
        console.error("[ERROR] /explain 통신 오류:", err.message);
        alert(`네트워크 통신 오류: ${err.message}`);
    } finally {
        explainBtn.disabled = false;
        loading.classList.add("hidden");
    }
}

// 11. AI 후속 대화 핸들러 (POST /chat)
async function handleChat() {
    const chatInput = document.getElementById("chatInput");
    const question = chatInput.value.trim();
    if (!question) return;

    if (!state.currentExplainReport) {
        alert("해석 보고서가 생성된 후에만 질문할 수 있습니다.");
        return;
    }

    const sendBtn = document.getElementById("sendChatBtn");
    const messagesBox = document.getElementById("chatMessages");

    // 사용자 메시지 추가
    appendChatMessage("user", question);
    chatInput.value = "";
    sendBtn.disabled = true;

    try {
        console.log(`[CHAT] 질문 전송: "${question}"`);
        const res = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: question,
                explain_report: state.currentExplainReport,
                run_result: state.currentRunResult,
                chat_history: state.chatHistory
            })
        });
        const data = await res.json();

        if (data.status === "success") {
            const answer = data.answer;
            console.log(`[CHAT] 답변 수신 완료 (길이: ${answer.length}자)`);
            appendChatMessage("ai", answer);

            // 대화 기록 누적
            state.chatHistory.push({ role: "user", content: question });
            state.chatHistory.push({ role: "model", content: answer });
        } else {
            console.error("[ERROR] /chat 오류:", data.message);
            appendChatMessage("ai", `⚠️ 오류가 발생했습니다: ${data.message}`);
        }
    } catch (err) {
        console.error("[ERROR] /chat 통신 오류:", err.message);
        appendChatMessage("ai", `⚠️ 네트워크 오류: ${err.message}`);
    } finally {
        sendBtn.disabled = false;
    }
}

function appendChatMessage(role, text) {
    const box = document.getElementById("chatMessages");
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'ai-bubble'}`;
    bubble.innerHTML = renderSimpleMarkdown(text);
    box.appendChild(bubble);
    box.scrollTop = box.scrollHeight;
}

// 경량 Vanilla 마크다운 파서 (제목, 볼드, 목록, 줄바꿈)
function renderSimpleMarkdown(md) {
    if (!md) return "";
    let html = md
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") // XSS 방지
        .replace(/^### (.*$)/gim, "<h3>$1</h3>")
        .replace(/^## (.*$)/gim, "<h2>$1</h2>")
        .replace(/^# (.*$)/gim, "<h1>$1</h1>")
        .replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>")
        .replace(/\*(.*?)\*/gim, "<em>$1</em>")
        .replace(/^\s*-\s+(.*$)/gim, "<li>$1</li>")
        .replace(/<\/li>\n<li>/gim, "</li><li>")
        .replace(/(<li>.*<\/li>)/gims, "<ul>$1</ul>")
        .replace(/\n\n/gim, "<br><br>");
    return html;
}
