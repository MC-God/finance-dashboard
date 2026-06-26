# 🏦 Private Hedge Fund Cockpit & AI Assistant

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram_Bot-2CA5E0?logo=telegram&logoColor=white)
![Google Sheets API](https://img.shields.io/badge/Google_Sheets_API-34A853?logo=googlesheets&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Gemini_3.5_Flash-8E75B2?logo=googlebard&logoColor=white)

> 개인 투자 자산을 하나의 뷰로 통합하고, 기계적이고 냉철한 AI 어시스턴트의 도움을 받아 **감정을 배제한 데이터 기반의 투자 의사결정**을 내리기 위한 프라이빗 자산 운용 시스템입니다.

## ✨ 주요 기능 (Key Features)

### 🤖 4인 4색 AI 페르소나 리포트
- **Quant (시스템 퀀트):** 베타, 변동성(VIX) 기반의 리스크 방어 로직 제안
- **Macro (글로벌 매크로):** 금리, CPI 등 거시 경제 지표 기반 섹터 비중 조언
- **Value (가치투자):** 실적 펀더멘털 및 잉여현금흐름 기반 버블 경고
- **Ten-Bagger (파괴적 혁신):** 최신 기술 돌파구 서칭 및 텐베거 유망주 추천

### 📱 텔레그램 기반 능동형 어시스턴트
- **자연어 매매 기록:** "테슬라 10주 200달러에 매도해" 입력 시 자연어 판독(NLP) 후 DB 자동 기록 및 실현 손익(PnL) 계산
- **영수증 OCR 판독:** 증권사 보유종목 스크린샷 전송 시 텍스트 파싱 및 시트 일괄 저장
- **능동형 리스크 레이더:** 2시간 주기 실시간 시세 스캔을 통한 익절(+20%) / 손절(-10%) 라인 도달 시 긴급 푸시 알림

### 📊 실시간 대시보드 (Streamlit)
- **자산 성장 타임라인:** 글로벌 매크로 이벤트(FOMC, CPI) 및 내 보유 종목 실적 발표일 오버레이 캘린더
- **ML 섹터 트리맵(Treemap):** 포트폴리오를 AI가 스마트 섹터로 분류하여 시각화 (-30% ~ +30% ROI 컬러 스케일 고정)

### ⚙️ 완전 자동화 파이프라인 (GitHub Actions)
- 한국장(18:00) 및 미국장(06:00) 마감 시점에 맞춰 배치 스크립트 자동 실행
- 시세 오류 발생 시 과거 유효 종가(Close)를 추적하는 3중 방어 로직 탑재

---

## 🏗️ 시스템 아키텍처 (Architecture)

1. **Database:** Google Sheets (`Portfolio`, `History`, `Transaction`, `Realized_PnL`, `AI_Reports`)
2. **Backend Server:** Google Cloud Platform (Ubuntu VM) 24/7 텔레그램 봇 구동
3. **Frontend:** Streamlit Community Cloud
4. **Task Scheduler:** GitHub Actions (Cron 배치 처리)
5. **Data Source:** `yfinance` (미국장), `FinanceDataReader` / Naver API (한국장), `icalendar` (매크로 일정)

---

## 🛠️ 설치 및 실행 방법 (Installation & Setup)

### 1. 저장소 클론 및 패키지 설치
```bash
git clone [https://github.com/USERNAME/finance-dashboard.git](https://github.com/USERNAME/finance-dashboard.git)
cd finance-dashboard
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
