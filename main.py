import asyncio
import json
import websockets
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register("astrbot_plugin_mcqqsync", "PISOFT", "接收MCQQSync消息并同步到群聊", "1.0.0")
class MCQQSync(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config
        self.ws_host = self.config.get("ws_host", "0.0.0.0")
        self.ws_port = self.config.get("ws_port", 52778)
        self.server_task = None

    async def initialize(self):
        logger.info(f"MCQQSync 启动 WebSocket 监听 {self.ws_host}:{self.ws_port}")
        self.server_task = asyncio.create_task(self.start_ws_server())

    async def start_ws_server(self):
        async def handler(websocket):
            logger.info("✅ 已连接来自 Minecraft 的 WebSocket")
            async for message in websocket:
                try:
                    data = json.loads(message)
                    event_type = data.get("type")

                    if event_type == "join":
                        player = data.get("player")
                        msg = f"🎮 玩家 {player} 加入了服务器！"
                        await self.send_to_group(msg)

                    elif event_type == "quit":
                        player = data.get("player")
                        msg = f"🚪 玩家 {player} 离开了服务器。"
                        await self.send_to_group(msg)

                    elif event_type == "chat":
                        player = data.get("player")
                        text = data.get("message")
                        msg = f"💬 {player}: {text}"
                        await self.send_to_group(msg)

                    else:
                        logger.warning(f"未知消息类型: {data}")

                except Exception as e:
                    logger.error(f"WebSocket 消息解析错误: {e}")

        async with websockets.serve(handler, self.ws_host, self.ws_port):
            await asyncio.Future()  # 永不结束

    async def send_to_group(self, text: str):
        """发送到目标群聊"""
        target_group = self.config.get("group_id")
        if not target_group:
            logger.warning("未配置 group_id，跳过发送。")
            return
        try:
            await self.context.bot.send_group_message(target_group, text)
            logger.info(f"已发送到群 {target_group}: {text}")
        except Exception as e:
            logger.error(f"发送群消息失败: {e}")

    async def terminate(self):
        logger.info("MCQQSync 已停止。")
        if self.server_task:
            self.server_task.cancel()
