import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from src.bot_handlers import start_command, ai_report_command, handle_message

# 환경변수 로드
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

def main():
    print("🤖 텔레그램 봇을 시작합니다...")
    
    if not TELEGRAM_TOKEN:
        print("❌ 오류: .env 파일에 TELEGRAM_TOKEN이 없습니다.")
        return

    # 봇 어플리케이션 빌드
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # 명령어 핸들러 등록
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ai", ai_report_command))
    
    # 일반 텍스트 핸들러 등록 (명령어가 아닌 자연어 처리용)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ 봇이 실행 중입니다. 텔레그램 앱에서 봇에게 메시지를 보내보세요! (종료: Ctrl+C)")
    
    # 봇이 종료되지 않고 계속 메시지를 기다리도록 실행
    app.run_polling()

if __name__ == "__main__":
    main()
