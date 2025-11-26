<h1 align="center">🛡️ Telegram 双向聊天机器人</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  <a href="https://github.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot/stargazers">
    <img src="https://img.shields.io/github/stars/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot.svg?style=social&label=Star" alt="GitHub Stars">
  </a>
</p>

> 一个功能完善、支持 AI 驱动的 Telegram 双向聊天机器人，专为提升用户与管理员之间的沟通效率和安全性而设计。

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
| 🛡️ **内容审查豁免** | 管理员可以为信任用户设置临时或永久豁免，跳过 AI 内容审查，提升沟通效率。 |
| 🔐 **权限控制** | 基于 Telegram ID 的多管理员权限系统，确保只有授权人员才能执行管理操作。 |
| 🤖 **智能自动回复** | 基于知识库的 AI 自动回复功能，在内容审查通过后自动回答用户问题，支持 Markdown 格式，管理员可随时查看自动回复内容。 |
| 🌐 **网络测试工具** | 集成网络测试功能，支持通过远程服务器进行 Ping 测试和路由追踪（NextTrace），支持 ICMP 和 TCP 模式，方便进行网络诊断。 |
| 📰 **RSS 订阅推送** | 在私聊中管理 RSS 列表、关键词和自定义页脚，并按需推送最新条目。 |

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
wget https://raw.githubusercontent.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot/main/.env.example -O .env
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

# Bot每分钟最大处理消息数（每个用户）
MAX_MESSAGES_PER_MINUTE=30

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
docker compose down
docker compose pull
docker compose up -d
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
- `/ping` - 执行 Ping 网络测试（需要授权）。
- `/nexttrace` - 执行路由追踪测试（需要授权）。

#### 管理员命令
- `/block` - 对应话题直接发送永久拉黑用户。
- `/blacklist` - 查看当前的黑名单列表。
- `/stats` - 查看机器人运行统计信息。
- `/view_filtered` - 查看被拦截信息及发送者。
- `/exempt` - 豁免用户内容审查（临时或永久）。
- `/autoreply` - 管理自动回复功能（开启/关闭、管理知识库）。
- `/adduser <user_id>` - 添加网络测试授权用户。
- `/rmuser <user_id>` - 删除网络测试授权用户。
- `/addserver` - 添加网络测试服务器（交互式）。
- `/rmserver` - 删除网络测试服务器。
- `/install_nexttrace` - 在服务器上安装 NextTrace 工具。

### 🤖 自动回复功能

机器人支持基于知识库的智能自动回复功能，可以在内容审查通过后自动回答用户的问题。

#### 功能特点

- **严格基于知识库**：AI 只会根据知识库中的内容回答，不会编造信息
- **内容审查后触发**：自动回复仅在内容审查通过后执行
- **Markdown 格式支持**：自动回复支持 Markdown 格式，提供更好的阅读体验
- **管理员通知**：自动回复内容会同时发送给管理员，方便监控和管理

#### 使用步骤

1. **开启自动回复**
   - 使用 `/autoreply` 命令打开管理菜单
   - 点击"开启自动回复"按钮

2. **添加知识库条目**
   - 方式一：在管理菜单中点击"添加知识条目"
   - 方式二：使用命令 `/autoreply add <标题> <内容>`
   - 示例：`/autoreply add 常见问题 这是问题的答案`

3. **管理知识库**
   - 使用 `/autoreply` 命令进入管理菜单
   - 点击"管理知识库"查看所有条目
   - 可以查看、编辑、删除知识条目

#### 命令说明

- `/autoreply` - 显示自动回复管理菜单
- `/autoreply on` - 开启自动回复
- `/autoreply off` - 关闭自动回复
- `/autoreply add <标题> <内容>` - 添加知识条目
- `/autoreply edit <ID> <标题> <内容>` - 编辑知识条目
- `/autoreply delete <ID>` - 删除知识条目
- `/autoreply list` - 列出所有知识条目

#### 工作流程

1. 用户发送消息
2. 系统进行内容审查（AI 垃圾信息检测）
3. 内容审查通过后，系统检查是否启用自动回复
4. 如果启用，系统根据知识库生成回复
5. 自动回复以 Markdown 格式发送给用户
6. 自动回复内容同时发送给管理员（回复用户消息）

#### 注意事项

- 自动回复仅在知识库中有相关内容时才会触发
- 如果知识库中没有相关内容，系统不会回复，等待管理员手动回复
- 建议定期更新知识库，添加常见问题和答案

### 🛡️ 内容审查豁免功能

机器人支持为信任用户设置内容审查豁免，被豁免的用户可以跳过 AI 内容审查，直接发送消息。

#### 功能特点

- **临时豁免**：支持设置指定小时数的临时豁免，到期后自动恢复审查
- **永久豁免**：支持设置永久豁免，适用于高度信任的用户
- **话题操作**：在用户话题中直接发送命令即可豁免该用户，操作便捷
- **状态查询**：可以随时查看用户的豁免状态和到期时间
- **灵活管理**：支持随时移除豁免，恢复内容审查

#### 使用步骤

1. **在用户话题中豁免用户**（推荐）
   - 进入用户的话题
   - 发送 `/exempt permanent [原因]` 永久豁免
   - 或发送 `/exempt temp <小时数> [原因]` 临时豁免
   - 例如：`/exempt temp 24 临时测试`

2. **通过用户ID豁免**
   - 使用 `/exempt <user_id> permanent [原因]` 永久豁免
   - 或使用 `/exempt <user_id> temp <小时数> [原因]` 临时豁免

3. **查看豁免状态**
   - 在话题中发送 `/exempt` 查看该用户的豁免状态
   - 或使用 `/exempt <user_id>` 查看指定用户的豁免状态

4. **移除豁免**
   - 在话题中发送 `/exempt remove`
   - 或使用 `/exempt <user_id> remove`

#### 命令说明

**在话题中使用：**
- `/exempt` - 查看当前用户的豁免状态
- `/exempt permanent [原因]` - 永久豁免该用户
- `/exempt temp <小时数> [原因]` - 临时豁免该用户（例如：`/exempt temp 24`）
- `/exempt remove` - 移除该用户的豁免

**通过用户ID使用：**
- `/exempt <user_id>` - 查看指定用户的豁免状态
- `/exempt <user_id> permanent [原因]` - 永久豁免指定用户
- `/exempt <user_id> temp <小时数> [原因]` - 临时豁免指定用户
- `/exempt <user_id> remove` - 移除指定用户的豁免

#### 使用示例

```bash
# 在用户话题中永久豁免
/exempt permanent 信任用户，无需审查

# 在用户话题中临时豁免24小时
/exempt temp 24 临时测试

# 通过用户ID永久豁免
/exempt 123456789 permanent 管理员信任

# 移除豁免
/exempt remove
```

#### 工作流程

1. 管理员在用户话题中发送豁免命令
2. 系统记录豁免信息（永久或临时）
3. 用户发送消息时，系统检查豁免状态
4. 如果用户被豁免，跳过 AI 内容审查，直接转发消息
5. 临时豁免到期后，自动恢复内容审查

#### 注意事项

- 豁免功能仅跳过内容审查，其他功能（如速率限制、黑名单检查）仍然有效
- 临时豁免到期后会自动恢复审查，无需手动操作
- 建议谨慎使用永久豁免，仅对高度信任的用户使用
- 可以随时通过 `/exempt remove` 移除豁免

### 🌐 网络测试功能

机器人集成了强大的网络测试功能，支持通过远程服务器进行网络诊断。

#### 功能特点

- **Ping 测试**：通过远程服务器执行 Ping 测试，统计丢包率和延迟信息
- **路由追踪**：使用 NextTrace 工具进行路由追踪，支持 ICMP 和 TCP 模式
- **多服务器支持**：支持配置多个测试服务器，灵活选择测试节点
- **交互式操作**：提供命令式和交互式两种使用模式，操作简单直观
- **权限管理**：管理员自动拥有权限，普通用户需要授权才能使用

#### 使用步骤

1. **配置服务器**（管理员）
   - 使用 `/addserver` 命令添加测试服务器
   - 支持交互式向导，逐步输入服务器信息
   - 或使用命令格式：`/addserver "服务器名称" host port username password`

2. **授权用户**（管理员）
   - 使用 `/adduser <user_id>` 将用户添加到授权列表
   - 管理员自动拥有权限，无需手动添加

3. **执行测试**（授权用户）
   - 使用 `/ping` 命令进行 Ping 测试
   - 使用 `/nexttrace` 命令进行路由追踪
   - 支持命令式（直接提供参数）和交互式（按提示操作）两种模式

#### 命令说明

**用户命令：**
- `/ping [目标] [次数]` - 执行 Ping 测试，例如：`/ping 8.8.8.8 10`
- `/nexttrace [目标]` - 执行路由追踪，例如：`/nexttrace google.com`

**管理员命令：**
- `/adduser <user_id>` - 添加授权用户
- `/rmuser <user_id>` - 删除授权用户
- `/addserver` - 交互式添加服务器
- `/addserver "名称" host port username password` - 快速添加服务器
- `/rmserver` - 删除服务器（显示列表选择）
- `/rmserver "服务器名称"` - 快速删除指定服务器
- `/install_nexttrace` - 在服务器上安装 NextTrace 工具

#### 配置说明

网络测试配置保存在 `data/network_test_config.json` 文件中，首次使用时会自动创建。配置文件格式：

```json
{
  "ADMIN_USERS": [123456789],
  "AUTHORIZED_USERS": [123456789, 987654321],
  "SERVERS": [
    {
      "name": "测试服务器",
      "host": "example.com",
      "port": 22,
      "username": "user",
      "password": "password"
    }
  ]
}
```

**注意：**
- 管理员列表会自动从主配置（`.env` 中的 `ADMIN_IDS`）同步
- 服务器密码以明文形式存储，请妥善保管配置文件
- 建议定期备份配置文件

#### 工作流程

1. 用户发送 `/ping` 或 `/nexttrace` 命令
2. 系统检查用户权限（管理员自动通过）
3. 用户选择测试服务器（如果配置了多个）
4. 用户输入测试目标（交互式模式）
5. 系统通过 SSH 连接到服务器执行测试
6. 返回格式化的测试结果

#### 注意事项

- 首次使用前需要管理员先添加测试服务器
- 普通用户需要管理员授权才能使用网络测试功能
- 路由追踪功能需要服务器上安装 NextTrace 工具（可使用 `/install_nexttrace` 自动安装）

---

### 📰 RSS 订阅功能

本项目已整合高并发 RSS 机器人，可直接在 Telegram 私聊里管理订阅并按关键词过滤更新。

#### 功能特点
- 支持任意数量的 RSS 链接，自动并发轮询，新增条目即时推送
- 为每个订阅源配置关键词、定制页脚和链接预览策略

在 `.env` 中添加 `RSS_CHECK_INTERVAL=300` 控制轮询间隔（秒），建议 ≥ 120

> 提示：初次运行会在 `RSS_DATA_FILE` 指定的位置创建 JSON 文件，文件可备份以迁移订阅数据。
> 管理员也可以随时在 `/panel` → “RSS 功能管理” 中开关功能、查看订阅并执行删除操作。

#### 命令列表（仅限私聊）
- `/rss_add <url>` `/rss_remove <url|ID>` `/rss_list`：管理订阅源
- `/rss_addkeyword <id> <关键词>` `/rss_removekeyword <id> <关键词>` `/rss_listkeywords <id>` `/rss_removeallkeywords <id>`：维护关键词过滤
- `/rss_setfooter [文本]` `/rss_togglepreview`：设置自定义页脚与链接预览
- `/rss_add_user <user_id>` `/rss_rm_user <user_id>`：仅管理员可用，用于维护 RSS 授权用户列表

#### 工作流程
1. 用户通过命令添加订阅源，机器人会在后台解析标题并记录 `last_entry_id`
2. 轮询任务按 `RSS_CHECK_INTERVAL` 间隔并发抓取所有订阅
3. 新条目会按关键词过滤，最多推送 5 条；剩余条目使用摘要提示防止刷屏
4. 消息会附带自定义页脚并遵循是否显示链接预览的设定
5. RSS 命令仅对 `ADMIN_IDS` 以及 `RSS_AUTHORIZED_USER_IDS` 中的用户生效

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