<h1 align="center">🛡️ Telegram 双向聊天机器人</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <a href="https://github.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot/stargazers">
    <img src="https://img.shields.io/github/stars/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot.svg?style=social&label=Star" alt="GitHub Stars">
  </a>
</p>

> 一个功能完善、支持 AI 驱动的 Telegram 双向聊天机器人，专为提升用户与管理员之间的沟通效率和安全性而设计。

<p align="center">
  <strong>如有疑问请联系: <a href="https://t.me/Sanite_Ava_Private_ChatBot">Sanite&Ava</a></strong>
</p>

---

## 📜 目录

- [✨ 核心特性](#-核心特性)
- [🚀 快速开始 (Docker 推荐)](#-快速开始-docker-推荐)
- [🛠️ (可选) 手动部署](#️-可选-手动部署)
- [📖 使用指南](#-使用指南)
- [🔧 配置说明](#-配置说明)
- [🤝 贡献指南](#-贡献指南)
- [📄 许可证](#-许可证)

---

## ✨ 核心特性

| 特性 | 描述 |
| :--- | :--- |
| 💬 **话题群组管理** | 利用 Telegram Forum 功能，为每位用户创建独立对话线程，自动展示用户信息，便于消息追溯与管理。 |
| 🤖 **AI 智能筛选** | 集成 Google Gemini API，可智能识别潜在的垃圾信息或恶意内容，并用于生成多样化的人机验证问题。 |
| 🛡️ **人机验证系统** | 新用户首次交互时需通过 AI 生成的验证问题，有效拦截自动化机器人骚扰。 |
| ⚡ **高性能处理** | 基于 `asyncio` 的异步消息队列和多 Worker 并行处理机制，轻松应对高并发场景，杜绝消息堵塞。 |
| 🖼️ **多媒体支持** | 无缝转发图片、视频、音频、文档等多种媒体格式，并完整保留 Markdown 格式。 |
| ⚫ **黑名单管理** | 管理员可轻松拉黑/解封用户。被拉黑用户将收到友好提示，并可通过 AI 生成的问答挑战进行自助解封。 |
| 🔐 **权限控制** | 基于 Telegram ID 的多管理员权限系统，确保只有授权人员才能执行管理操作。 |

---

## 🚀 快速开始 (Docker 推荐)

> [!TIP]\
> 我们强烈推荐使用 Docker 进行部署，这可以为您免去环境配置的麻烦。

1. 首先，在您的服务器上创建一个目录，用于存放机器人的配置和数据。

```bash
mkdir tg-bot-data
cd tg-bot-data
```

2. 下载 .env.example 配置文件模板，并重命名为 .env

```bash
# wget https://raw.githubusercontent.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot/main/.env.example -O .env
```

3. 编辑 .env 文件，填入您的配置
```bash
nano .env
```

<details>
<summary>📝 点击查看 .env 文件配置示例 (点击展开)</summary>

创建 `.env` 文件后，您可以将以下内容复制进去，并根据注释修改为您自己的配置：

```env
# --- 必需配置 ---

# Telegram Bot配置
# 从 @BotFather 获取您的 Bot Token
BOT_TOKEN=your_bot_token_here

# 您的Telegram话题群组ID
# 将机器人设为群组管理员后，在群组里发送 /getid ，机器人会自动回复群组ID
FORUM_GROUP_ID=-1001234567890

# 管理员ID（您的Telegram用户ID），多个ID用逗号分隔
ADMIN_IDS=123456789,987654321

# --- 可选配置 ---

# Gemini API配置 (如果您需要使用AI相关功能)
# 从 Google AI Studio 获取
GEMINI_API_KEY=your_gemini_api_key_here

# 是否启用AI自动识别垃圾信息和恶意内容
ENABLE_AI_FILTER=true

# AI判断的置信度阈值（0-100），高于此值才会被认为是恶意内容
AI_CONFIDENCE_THRESHOLD=70

# --- 功能开关 ---

# 是否启用新用户人机验证
VERIFICATION_ENABLED=true

# 是否启用黑名单用户自动解封机制
AUTO_UNBLOCK_ENABLED=true

# --- 数据库配置 ---
# 容器内路径，通常不需要修改
DATABASE_PATH=./data/bot.db

# --- 性能配置 ---

# 消息队列处理的worker数量
MAX_WORKERS=5

# 队列中消息的超时时间（秒）
QUEUE_TIMEOUT=30

# --- 验证配置 ---

# 人机验证的超时时间（秒）
VERIFICATION_TIMEOUT=300

# 用户最大尝试验证次数
MAX_VERIFICATION_ATTEMPTS=3

# --- 速率限制 ---
# 通常不需要修改

# Bot每秒最大处理消息数
MAX_MESSAGES_PER_SECOND=30

# Bot每分钟在群组中最大发送消息数
MAX_GROUP_MESSAGES_PER_MINUTE=20

# -- Watchtower 通知钩子（默认禁用，启用需去除配置的#注释） --

# Watchtower 使用 shoutrrr 作为统一通知系统（支持包括 Telegram 在内的等多种渠道）
#WATCHTOWER_NOTIFICATIONS=shoutrrr

# 填入 通知渠道 的钩子（以 Telegram 举例）
#WATCHTOWER_NOTIFICATION_URL=telegram://token@telegram?chats=channel-1[,chat-id-1,...]
```
</details>

--- 
> [!TIP]\
> 配置好 .env 文件，选择 Docker-compose / Docker 部署 Chatbot

### 使用 Docker-Compose

1. 下载 docker-compose.yml:
```bash
wget https://raw.githubusercontent.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot/main/docker-compose.yml
```

2. 使用 Docker Compose 运行:
```bash
docker compose up -d
```

更新容器：
```bash
# 在tg-bot-data目录下，执行以下命令
docker-compose down
docker-compose pull
docker-compose up -d
```

[使用 Watchtower 自动更新本项目](watchtower/README.md)

---
### 使用 Docker Run

```bash
docker run -d \
  --name tg-antiharassment-bot \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  weijiaqaq/tg-antiharassment-bot:latest
```
> **命令解析:**
> - `-d`: 在后台运行容器。
> - `--name tg-antiharassment-bot`: 为容器指定一个名字。
> - `-v $(pwd)/.env:/app/.env`: 将您当前目录下的 `.env` 文件挂载到容器中。
> - `-v $(pwd)/data:/app/data`: 将数据目录挂载出来，确保持久化存储。
> - `--restart unless-stopped`: 容器退出时自动重启，保证服务高可用。
> - `weijiaqaq/tg-antiharassment-bot:latest`: 指定要运行的 Docker Hub 镜像。

---

## 🛠️ (可选) 手动部署

<details>
<summary>👨‍💻 点击查看手动部署指南 (点击展开)</summary>

如果您不想使用 Docker，也可以通过以下步骤手动部署。

#### 1. 克隆项目

```bash
git clone https://github.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot.git
cd Telegram_Anti-harassment_two-way_chatbot
```

#### 2. 安装依赖

```bash
# 建议创建并激活虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 3. 配置环境变量

复制 `.env.example` 文件为 `.env`，并填入您的配置。详细配置项请参考 Docker 部署部分的示例。

```bash
# 复制配置模板
cp .env.example .env

# 编辑.env文件
nano .env
```

#### 4. 运行Bot

```bash
python bot.py
```
</details>

---

## 📖 使用指南

### 🔑 获取必要信息

1.  **Bot Token**: 在 Telegram 中与 [@BotFather](https://t.me/BotFather) 对话，使用 `/newbot` 命令创建机器人即可获得。
2.  **话题群组 ID**: 创建一个超级群组 (Supergroup)，在设置中启用“话题”(Topics) 功能。然后将您的机器人添加为该群组的管理员。在群组中发送/getid，机器人会自动回复包含群组 ID 的信息。
3.  **Gemini API 密钥** (可选): 访问 [Google AI Studio](https://aistudio.google.com/api-keys) 创建并复制您的 API 密钥。

### 📜 命令列表

#### 用户命令
- `/start` - 启动机器人，显示欢迎信息。
- `/getid` - 显示当前用户/群组ID。
- `/help` - 显示帮助信息。

#### 管理员命令
- `/block` - 对应话题直接发送永久拉黑用户。
- `/blacklist` - 查看当前的黑名单列表。
- `/stats` - 查看机器人运行统计信息。
- `/view_filtered` - 查看被拦截信息及发送者。

---

## 🔧 配置说明

所有配置项均通过 `.env` 文件进行管理。详细的变量说明请参考 [快速开始](#-快速开始-docker-推荐) 部分的 `.env` 文件示例。

---

## 🤝 贡献指南

欢迎任何形式的贡献！如果您有好的想法或发现了 Bug，请随时提交 Pull Request 或创建 Issue。

## 📄 许可证

本项目采用 [MIT 许可协议](LICENSE)。

## 🙏 致谢

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - 优秀的 Telegram Bot 框架。
- [Google Gemini](https://ai.google.dev/) - 提供强大的 AI 能力。

---

<p align="center">
  如果这个项目对你有帮助，请给个 Star ⭐️
</p>
<p align="center">
  <a href="https://www.star-history.com/#Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot&type=date&legend=bottom-right">
    <img src="https://api.star-history.com/svg?repos=Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot&type=date&legend=bottom-right" alt="Star History Chart">
  </a>
</p>