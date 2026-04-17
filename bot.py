import logging
import asyncio
from telegram.ext import Application
from config import config
from handlers import register_handlers
from rss import setup as setup_rss
from database.db_manager import DatabaseManager
from services.telegram_commands import register_bot_commands

async def post_init(app: Application):
    config.BOT_ID = app.bot.id
    config.BOT_USERNAME = app.bot.username
    print(f"Bot ID: {config.BOT_ID} 已设置")
    print(f"Bot Username: {config.BOT_USERNAME} 已设置")
    await register_bot_commands(app)

def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    # Python 3.14 不再为主线程隐式创建事件循环，显式设置可兼容 PTB 的 run_polling。
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    db_manager = DatabaseManager(config.DATABASE_PATH)
    loop.run_until_complete(db_manager.initialize())

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    register_handlers(app)
    setup_rss(app)

    config.validate()

    logging.info("Bot启动中...")
    app.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Bot已停止")
    except Exception as e:
        logging.error(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
