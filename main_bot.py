import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from src.bot_handlers import start_command, ai_report_command, handle_message, handle_photo, handle_callback_query

# 환경변수 로드 (.env 파일 읽기)
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

def main():
    # 토큰 체크 안전장치 (표준 규격: TELEGRAM_TOKEN)
    if not TELEGRAM_TOKEN:
        print("❌ 시스템 에러: .env 파일에 TELEGRAM_TOKEN이 설정되지 않았습니다.")
        return

    print("📡 [표준 규격] 텔레그램 봇 인프라 구축을 시작합니다...")
    
    # python-telegram-bot 애플리케이션 빌드
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 1. 기본 명령어(/start, /ai) 핸들러 등록
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("ai", ai_report_command))
    
    # 2. 📸 보유현황 스크린샷 이미지 감지 핸들러 등록
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # 3. 🔘 일반계좌/연금계좌 선택 버튼 클릭 피드백 핸들러 등록
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # 4. 일반 텍스트 자연어 입력 처리 핸들러 등록 (명령어 제외)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ 봇이 성공적으로 실행되었습니다. 텔레그램 앱에서 확인해보세요!")
    
    # 봇 가동 및 실시간 모니터링 시작 (Polling)
    application.run_polling()

if __name__ == '__main__':
    main()
