import asyncio
import json
import websockets
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event import MessageChain, AstrMessageEvent

from astrbot.api.message_components import Plain


@register("astrbot_plugin_mcqqsync", "PISOFT", "接收MCQQSync消息并同步到群聊", "1.0.0")
class MCQQSync(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        # self.asconfig = asconfig
        # self.provider_id = asconfig.get("provider_id", "")


        self.config = config
        self.ws_host = self.config.get("ws_host", "0.0.0.0")
        self.ws_port = self.config.get("ws_port", 52778)
        self.provider_id = self.config.get("provider_id", "")
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
                        msg_text = data.get("message")
                        provider = (
                            self.context.get_provider_by_id(self.provider_id)
                            if self.provider_id
                            else self.context.get_using_provider()
                        )

                        if not provider:
                            logger.error("配置文件不看的吗……")
                            return

                        try:
                            resp = await provider.text_chat(
                                prompt=msg_text,
                                session_id=None,
                                contexts=[],
                                image_urls=[],
                                func_tool=None,
                                system_prompt="你是个判断内容是否违规的机器人，只回答True与False，True代表违规，False为不违规",
                            )
                            if resp.role == "assistant":
                                if resp.completion_text == "False":
                                    logger.info("AI:"+resp.completion_text)
                                    text = f"💬 {player}: {msg_text}"
                                elif resp.completion_text == "True":
                                    logger.info("AI:"+resp.completion_text)
                                    text = f"💬 {player}: 内容违规 不予转发"
                                else:
                                    logger.info("AI:"+resp.completion_text)
                                    text = None
                            else:
                                logger.error("判断失败")
                        except Exception as exc:
                            logger.error(f"error: {exc}")


                    if text:
                        await self.send_to_group(text)

                except Exception as e:
                    logger.error(f"WebSocket 消息解析错误: {e}")

        async with websockets.serve(handler, self.ws_host, self.ws_port):
            await asyncio.Future()  # 永不结束

    async def send_to_group(self, text: str):
        group_id = self.config.get("group_id")
        if not group_id:
            logger.warning("未配置 group_id，跳过发送。")
            return

        try:
            chain = MessageChain().message(text)  # 或用 Plain，视版本决定
            # 如果 MessageChain().message(...) 不可用：
            # chain = [ Plain(text=text) ]

            # success = await self.context.send_message(group_id, chain)

            success = await self.context.send_message("default:GroupMessage:819691704", chain)
            if success:
                logger.info(f"✅ 已发送到群 {group_id}: {text}")
            else:
                logger.error(f"❌ 发送群消息失败: {group_id}")
        except Exception as e:
            logger.error(f"发送消息时出错: {e}")

    async def terminate(self):
        logger.info("MCQQSync 已停止。")
        if self.server_task:
            self.server_task.cancel()
