import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 최신 Gemini 클라이언트 초기화
client = genai.Client(api_key=GEMINI_API_KEY)

def analyze_portfolio(portfolio_data: str, persona: str) -> str:
    """
    포트폴리오 데이터를 바탕으로 3가지 페르소나에 맞춘 분석 의견을 생성합니다.
    """
    # 페르소나별 시스템 프롬프트 정의
    prompts = {
        "quant": (
            "당신은 데이터와 통계를 맹신하는 냉철한 퀀트 투자자입니다. "
            "주어진 포트폴리오의 수익률, 변동성, 종목 비중의 리스크를 수치 기반으로 분석하고, "
            "기계적인 비중 조절(리밸런싱) 조언을 3~4문장으로 짧게 제공하세요."
        ),
        "macro": (
            "당신은 글로벌 경제 흐름을 꿰뚫어보는 거시경제 전문가입니다. "
            "주어진 데이터를 바탕으로 현재 시장 상황(특히 AI 인프라 등 기술주 및 매크로 환경)을 진단하고, "
            "어떤 섹터로 자금을 이동시켜야 할지 탑다운(Top-down) 관점의 조언을 3~4문장으로 제공하세요."
        ),
        "value": (
            "당신은 기업의 본질 가치를 믿는 워런 버핏 같은 가치투자자입니다. "
            "단기적인 수익률 변동에 흔들리지 말고, 장기적 관점에서 기업의 펀더멘털을 믿고 "
            "뚝심 있게 홀딩하거나 저가 매수할 기회가 있는지 3~4문장으로 조언하세요."
        )
    }
    
    system_instruction = prompts.get(persona, "당신은 훌륭한 금융 AI 어시스턴트입니다.")
    
    try:
        # Gemini 3.5 Flash 모델 호출
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=f"다음은 오늘 장 마감 후의 내 포트폴리오 데이터야:\n{portfolio_data}\n\n이 데이터를 바탕으로 너의 페르소나에 맞춰 조언을 해줘.",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7, # 0에 가까울수록 일관성, 1에 가까울수록 창의성
            )
        )
        return response.text
    except Exception as e:
        print(f"[{persona}] AI 분석 중 오류 발생: {e}")
        return "분석 결과를 불러오지 못했습니다."

# --- 테스트 실행 블록 ---
if __name__ == "__main__":
    # Phase 1에서 수집한 데이터라고 가정 (가짜 데이터)
    sample_portfolio = """
    Ticker: NVDA | Shares: 10 | Avg_Price: 120.0 | Current_Price: 125.0 | 1D_Return: +4.1%
    Ticker: SOXX | Shares: 5 | Avg_Price: 200.0 | Current_Price: 198.0 | 1D_Return: -1.0%
    """
    
    print("🤖 [Quant 의견]\n" + analyze_portfolio(sample_portfolio, "quant") + "\n")
    print("🌍 [Macro 의견]\n" + analyze_portfolio(sample_portfolio, "macro") + "\n")
    print("📈 [Value 의견]\n" + analyze_portfolio(sample_portfolio, "value") + "\n")
