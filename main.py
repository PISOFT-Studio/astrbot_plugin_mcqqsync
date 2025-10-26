import asyncio
import json
import websockets
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event import MessageChain, AstrMessageEvent
from astrbot.api.message_components import Plain

@register("astrbot_plugin_mcqqsync", "卡带酱", "接收MCQQSync消息并同步到群聊", "1.0.1")
class MCQQSync(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config or {}
        self.ws_host = self.config.get("ws_host", "0.0.0.0")
        self.ws_port = self.config.get("ws_port", 52778)
        self.provider_id = self.config.get("provider_id", "")
        self.group_id = self.config.get("group_id", "")  # 确保读取
        self.expected_token = self.config.get("expected_token", "")  # 从 config 读取 Token（手动配置）
        self.server_task = None
        self.valid_connections = set()  # 跟踪有效 WS 连接（用 id）

    async def initialize(self):
        if not self.group_id:
            logger.warning("未配置 group_id，插件将无法发送消息。")
        if not self.expected_token:
            logger.warning("未配置 expected_token，安全验证将禁用。")
        logger.info(f"MCQQSync 启动 WebSocket 监听 {self.ws_host}:{self.ws_port}")
        self.server_task = asyncio.create_task(self.start_ws_server())

    async def start_ws_server(self):
        async def handler(websocket, path):
            conn_id = id(websocket)
            logger.info(f"🔌 新连接尝试: {conn_id}")
            valid = False
            try:
                # 等待初始 auth 消息
                auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                auth_data = json.loads(auth_msg)
                if auth_data.get("type") == "auth" and auth_data.get("token") == self.expected_token:
                    valid = True
                    self.valid_connections.add(conn_id)
                    logger.info(f"✅ {conn_id} 通过 Token 认证")
                else:
                    logger.warning(f"❌ {conn_id} 认证失败")
                    await websocket.close(1008, "Invalid token")
                    return
            except asyncio.TimeoutError:
                logger.warning(f"❌ {conn_id} 认证超时")
                await websocket.close(1008, "Auth timeout")
                return
            except Exception as e:
                logger.error(f"❌ {conn_id} 认证错误: {e}")
                await websocket.close(1011, "Auth error")
                return

            if valid:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        token = data.get("token")
                        if token != self.expected_token:
                            logger.warning(f"❌ {conn_id} Token 无效: {token}")
                            continue  # 跳过无效消息

                        await self.process_event(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ {conn_id} JSON 解析错误: {e}")
                    except Exception as e:
                        logger.error(f"❌ {conn_id} 消息处理错误: {e}")

            self.valid_connections.discard(conn_id)
            logger.info(f"🔌 {conn_id} 连接关闭")

        async with websockets.serve(handler, self.ws_host, self.ws_port):
            await asyncio.Future()  # 永不结束

    async def process_event(self, data):
        event_type = data.get("type")
        text = None

        if event_type == "join":
            player = data.get("player", "未知")
            text = f"🎮 玩家 {player} 加入了服务器！"

        elif event_type == "quit":
            player = data.get("player", "未知")
            text = f"🚪 玩家 {player} 离开了服务器。"

        elif event_type == "death":
            player = data.get("player", "未知")
            msg_text = data.get("message", "不明原因")
            text = f"💀 {player} 死亡了: {msg_text}"

        elif event_type == "chat":
            player = data.get("player", "未知")
            msg_text = data.get("message", "")
            text = await self.moderate_chat(player, msg_text)
            if not text:
                return  # 审核失败或违规，跳过

        if text:
            await self.send_to_group(text)

    async def moderate_chat(self, player: str, msg_text: str) -> str:
        if not msg_text:
            return None

        provider = (
            self.context.get_provider_by_id(self.provider_id)
            if self.provider_id
            else self.context.get_using_provider()
        )
        if not provider:
            logger.error("配置文件不正确，提供者未找到")
            return f"💬 {player}: {msg_text}"  # 默认转发

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
                ai_response = resp.completion_text.strip().lower()
                logger.info(f"AI 审核: {ai_response}")
                if ai_response == "true":
                    return f"💬 {player}: 内容违规，不予转发"  # 发送提示
                elif ai_response == "false":
                    return f"💬 {player}: {msg_text}"
                else:
                    logger.warning(f"AI 返回意外: {ai_response}，默认转发")
                    return f"💬 {player}: {msg_text}"
            else:
                logger.error("审核响应格式错误")
                return f"💬 {player}: {msg_text}"  # 默认转发
        except Exception as exc:
            logger.error(f"审核错误: {exc}，默认转发")
            return f"💬 {player}: {msg_text}"

    async def send_to_group(self, text: str):
        if not self.group_id:
            logger.warning("未配置 group_id，跳过发送。")
            return

        try:
            chain = MessageChain([Plain(text=text)])  # 修复：使用 Plain
            success = await self.context.send_message(self.group_id, chain)  # 使用 config group_id
            if success:
                logger.info(f"✅ 已发送到群 {self.group_id}: {text}")
            else:
                logger.error(f"❌ 发送群消息失败: {self.group_id}")
        except Exception as e:
            logger.error(f"发送消息时出错: {e}")

    async def terminate(self):
        logger.info("MCQQSync 已停止。")
        if self.server_task:
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass