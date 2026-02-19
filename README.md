# Telegram 双向聊天机器人 (Rust版)

使用 Rust 完全重构的高性能 Telegram 双向聊天机器人，具备 AI 智能过滤、人机验证、RSS 订阅、网络测试等功能。

## 特性

- **话题群组管理** - 利用 Telegram Forum 功能，为每位用户创建独立对话线程
- **AI 智能筛选** - 集成 Google Gemini API 及 OpenAI (兼容) API
- **人机验证系统** - 新用户首次交互时需通过 AI 生成的验证问题
- **高性能处理** - 基于 tokio 的异步消息队列，轻松应对高并发
- **多媒体支持** - 无缝转发图片、视频、音频、文档等多种媒体格式
- **黑名单管理** - 管理员可轻松拉黑/解封用户
- **内容审查豁免** - 为信任用户设置临时或永久豁免
- **智能自动回复** - 基于知识库的 AI 自动回复功能
- **网络测试工具** - 集成 Ping 测试和路由追踪（NextTrace）
- **RSS 订阅推送** - 在私聊中管理 RSS 列表、关键词和自定义页脚

## 快速开始 (Docker)

1. 克隆项目并切换到 rust-rewrite 分支:
```bash
git clone https://github.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot.git
cd Telegram_Anti-harassment_two-way_chatbot
git checkout rust-rewrite
```

2. 复制配置文件:
```bash
cp .env.example .env
```

3. 编辑 `.env` 文件，填入你的配置

4. 使用 Docker Compose 运行:
```bash
docker-compose up -d
```

## 手动构建

需要 Rust 1.70+ 和 SQLite 开发库。

```bash
# 安装依赖 (Ubuntu/Debian)
sudo apt-get install libsqlite3-dev pkg-config

# 构建
cargo build --release

# 运行
./target/release/tg-anti-harassment-bot
```

## 配置说明

| 变量 | 说明 | 必需 |
|------|------|------|
| BOT_TOKEN | 从 @BotFather 获取的 Bot Token | 是 |
| FORUM_GROUP_ID | 话题群组ID（超级群组） | 是 |
| ADMIN_IDS | 管理员用户ID，逗号分隔 | 是 |
| GEMINI_API_KEY | Google AI Studio API Key | 否 |
| OPENAI_API_KEY | OpenAI API Key | 否 |
| ENABLE_AI_FILTER | 启用AI内容过滤 | 否 (默认: true) |
| VERIFICATION_ENABLED | 启用人机验证 | 否 (默认: true) |
| DATABASE_PATH | 数据库文件路径 | 否 (默认: ./data/bot.db) |
| RSS_ENABLED | 启用RSS功能 | 否 (默认: false) |
| NETWORK_TEST_ENABLED | 启用网络测试 | 否 (默认: false) |

## 命令列表

### 用户命令
- `/start` - 启动机器人
- `/help` - 显示帮助信息
- `/getid` - 获取当前聊天ID

### 管理员命令
- `/panel` - 打开管理面板
- `/block` - 拉黑当前话题用户
- `/unblock [用户ID]` - 解封用户
- `/blacklist` - 查看黑名单
- `/stats` - 查看统计信息
- `/exempt [permanent\|temp 小时] [原因]` - 设置内容审查豁免
- `/autoreply [on\|off\|add\|edit\|delete\|list]` - 管理自动回复
- `/rss [add\|remove\|list] [URL]` - RSS订阅管理
- `/ping [目标]` - Ping测试
- `/traceroute [目标]` - 路由追踪

## 技术栈

- **异步运行时**: Tokio
- **Telegram Bot**: Teloxide
- **数据库**: SQLite + SQLx
- **HTTP客户端**: Reqwest
- **RSS解析**: rss crate

## 与 Python 版的区别

1. **性能**: Rust 版本内存占用更低，CPU 效率更高
2. **类型安全**: 编译期检查避免运行时错误
3. **部署**: 单二进制文件，无需 Python 环境
4. **并发**: 原生异步，无需 GIL 限制

## 许可证

MIT
