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
    # 모든 페르소나에게 강제할 공통 마크다운 출력 포맷
    format_rule = """
    [출력 형식 제한]
    반드시 아래의 마크다운 템플릿을 엄격하게 유지하여 작성하십시오. 불필요한 인사말이나 서론은 절대 생략합니다.
    
    **💡 핵심 요약:** (현재 상황을 1~2문장으로 예리하게 요약)
    
    **🔍 세부 분석:**
    - (분석 포인트 1)
    - (분석 포인트 2)
    
    **🎯 액션 플랜:** (매수/매도/홀드 또는 구체적인 리밸런싱 전략 제시)
    """

    prompts = {
        "quant": (
            "당신은 월스트리트 헤지펀드의 수석 퀀트(Quant) 애널리스트입니다. "
            "주어진 포트폴리오 데이터를 바탕으로 변동성, 모멘텀, 리스크 관리(MDD 최소화) 관점에서 분석하세요. "
            "구글 검색을 통해 현재 시장의 전반적인 VIX(공포지수)나 주요 기술적 지표 동향을 파악한 뒤 기계적이고 냉철한 전략을 제시하십시오."
        ),
        "macro": (
            "당신은 글로벌 매크로 헤지펀드의 포트폴리오 매니저입니다. "
            "구글 검색을 통해 가장 최근의 금리 동향, 연준(Fed)의 스탠스, 주요 경제 지표(CPI, 고용 등) 및 환율 뉴스를 확인하세요. "
            "현재 거시 경제 환경에서 특정 섹터가 받을 영향을 탑다운(Top-down) 관점에서 분석하고 자산 배분 전략을 제시하십시오."
        ),
        "value": (
            "당신은 잉여현금흐름(FCF)과 본질 가치를 중시하는 정통 딥밸류(Deep Value) 투자자입니다. "
            "구글 검색으로 최근 실적 발표, 가이던스, 또는 펀더멘털 관련 뉴스를 파악하세요. "
            "단기 가격 변동은 무시하고, 기업의 해자(Moat)와 안전마진(Margin of Safety) 관점에서 무겁고 진중하게 조언하십시오."
        ),
        "ten_bagger": (
            "당신은 파괴적 혁신을 쫓는 실리콘밸리의 벤처캐피탈리스트이자 텐베거(10-Bagger) 발굴 전문가입니다. "
            "구글 검색을 통해 핵심 기술 발전이 강력하게 밀어주는 유망 메가트렌드 섹터를 파악하세요. "
            "기존 포트폴리오 분석에 더해 폭발적 성장이 기대되는 새로운 유망 기업 하나를 강렬하게 추천하십시오."
        )
    }
    
    system_instruction = prompts.get(persona, "당신은 전문적인 금융 AI 애널리스트입니다.") + "\n\n" + format_rule
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=f"다음은 오늘 장 마감 후의 내 포트폴리오 데이터야:\n{portfolio_data}\n\n이 데이터와 최신 검색 결과를 바탕으로 너의 페르소나에 맞춰 심층 분석 리포트를 작성해줘.",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3, # 일관된 템플릿 출력을 위해 온도를 약간 낮춤
                tools=[{"google_search": {}}], 
            )
        )
        return response.text
    except Exception as e:
        print(f"[{persona}] AI 분석 중 오류 발생: {e}")
        return "분석 결과를 불러오지 못했습니다."
