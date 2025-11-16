# 通过 Watchtower 实现自动更新
1. 下载配置了 Watchtower 的 docker-compose.yml
```bash
wget wget https://raw.githubusercontent.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot/main/watchtower/docker-compose.yml
```
2. 编辑 .env 文件，填入您的配置
```bash
nano .env
```
3. 编辑 docker-compose.yml （非必要）
```
# 只有自定义过容器名，才需进行操作。
nano docker-compose.yml
```

# 通过 Telegram 告知是否完成更新（可选）
启用前，需删除.env配置中“WATCHTOWER_NOTIFICATIONS”和”WATCHTOWER_NOTIFICATION_URL“前面的#注释。

### 如何获取 BOT_TOKEN 和 CHAT_ID？

- BOT_TOKEN  
用 BotFather 创建 bot 后收到的 Token，如：
```json
123456789:ABCDEF_xxxxx-yyyy
```

- CHAT_ID  
在 Bot 的私聊界面发送 /getid ，得到的就是 Chat ID

```json
用户ID: 123456789
```
正确格式：
```json
WATCHTOWER_NOTIFICATION_URL=telegram://123456789:ABCDEF_xxxxx-yyyy@telegram?chats=12345678
```

# 配置解析
> - `WATCHTOWER_NOTIFICATIONS=shoutrrr`: Watchtower 使用 shoutrrr 作为统一通知系统（支持包括telegram在内的等多种渠道）
> - `WATCHTOWER_NOTIFICATION_URL`: 填入 Telegram 钩子
> - `--cleanup`:更新容器镜像并重启容器成功后,自动删除旧镜像
> - `--interval 3600`: 每隔 3600 秒（1 小时）检查一次镜像是否有更新。
> - `TG-Antiharassment-Bot`: 容器名，如果自定义过，记得修改。
> - `max-size`： 单个日志文件最大 10MB
> - `max-file`： 最多保留 3 个日志文件