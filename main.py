from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.messaging import MessageChain  # 假设路径是这一种
import asyncio, json, websockets

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
                    text = None

                    if event_type == "join":
                        player = data.get("player")
                        text = f"🎮 玩家 {player} 加入了服务器！"

                    elif event_type == "quit":
                        player = data.get("player")
                        text = f"🚪 玩家 {player} 离开了服务器。"

                    elif event_type == "chat":
                        player = data.get("player")
                        message_text = data.get("message")
                        text = f"💬 {player}: {message_text}"

                    if text is not None:
                        await self.send_to_group(text)

                except Exception as e:
                    logger.error(f"WebSocket 消息解析错误: {e}")

        async with websockets.serve(handler, self.ws_host, self.ws_port):
            await asyncio.Future()

    async def send_to_group(self, text: str):
        target_group = self.config.get("group_id")
        if not target_group:
            logger.warning("未配置 group_id，跳过发送。")
            return

        # 构造 MessageChain
        message_chain = MessageChain.text(text)  # 假设 API 提供 text() 静态方法
        session = target_group  # 如果平台要求 “平台前缀+群号”，需查看文档

        success = await self.context.send_message(session, message_chain)
        if not success:
            logger.error(f"发送群消息失败: 群={target_group}, 文本={text}")
        else:
            logger.info(f"已发送到群 {target_group}: {text}")

    async def terminate(self):
        logger.info("MCQQSync 已停止。")
        if self.server_task:
            self.server_task.cancel()
