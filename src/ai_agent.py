import os
import requests
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def analyze_portfolio(portfolio_data: str, persona: str) -> str:
    prompts = {
        "quant": "당신은 월스트리트 헤지펀드의 수석 퀀트(Quant) 애널리스트입니다. 포트폴리오 데이터를 바탕으로 리스크 관리 및 기계적인 리밸런싱 전략을 4~5문장으로 제시하십시오.",
        "macro": "당신은 글로벌 매크로 헤지펀드의 포트폴리오 매니저입니다. 거시 경제 환경에서 기술주나 특정 섹터가 받을 영향을 탑다운(Top-down) 관점에서 4~5문장으로 제시하십시오.",
        "value": "당신은 정통 딥밸류(Deep Value) 투자자입니다. 기업의 해자(Moat)와 안전마진(Margin of Safety) 관점에서 현재 포지션 유지/매수 의견을 4~5문장으로 제시하십시오.",
        "ten_bagger": "당신은 텐베거(10-Bagger) 발굴 전문가입니다. 포트폴리오 분석과 더불어 메가트렌드 수혜를 입을 새로운 유망 기업을 하나 추천하여 4~5문장으로 제시하십시오."
    }
    
    system_instruction = prompts.get(persona, "당신은 전문적인 금융 AI 애널리스트입니다.")
    user_prompt = f"다음은 오늘 장 마감 후의 내 포트폴리오 데이터야:\n{portfolio_data}\n\n이 데이터를 바탕으로 너의 페르소나에 맞춰 심층 분석 리포트를 작성해줘."
    
    # Gemini API 직접 호출 엔드포인트
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    # API에 보낼 데이터 형식 세팅
    payload = {
        "system_instruction": {
            "parts": {"text": system_instruction}
        },
        "contents": [{
            "parts": [{"text": user_prompt}]
        }]
    }
    
    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload)
        response.raise_for_status() # 통신 에러 발생 시 예외 처리
        result = response.json()
        
        # 응답 JSON에서 텍스트만 추출
        return result["candidates"][0]["content"]["parts"][0]["text"]
        
    except Exception as e:
        print(f"[{persona}] AI 분석 중 오류 발생: {e}")
        return "분석 결과를 불러오지 못했습니다."