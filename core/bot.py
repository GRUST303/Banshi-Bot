import asyncio
import json
import websockets
from core.state import state
from core.utils import add_log, process_message_content, get_avatar_url
from core.api import fetch_group_info, fetch_user_info

async def run_bot(on_status_change=None):
    def update_status(status_str):
        if on_status_change:
            on_status_change(status_str)

    add_log(f"[WS] 正在连接 {state.ws_url} ...")
    
    while state.running:
        try:
            async with websockets.connect(state.ws_url) as websocket:
                state.ws = websocket
                state.connected = True
                add_log("[WS] 连接成功")
                update_status('connected')
                
                # 上线刷基础信息
                if state.swordholder_qq: 
                    await fetch_user_info(state.swordholder_qq)
                for gid in state.source_groups.union(state.target_groups):
                    await fetch_group_info(gid)

                async for message in websocket:
                    if not state.running: break
                    data = json.loads(message)
                    
                    # 拦截API回调
                    if 'echo' in data and data['echo'].startswith('req_'):
                        echo = data['echo']
                        if echo in state.api_futures:
                            future = state.api_futures[echo]
                            if not future.done(): future.set_result(data)
                            del state.api_futures[echo]
                        continue

                    # 处理事件推送
                    resp_data = data.get('data') or {}
                    if data.get('status') == 'ok':
                        # 群名片刷新
                        if 'group_name' in resp_data:
                            gid = resp_data.get('group_id')
                            if gid:
                                state.group_info_cache[gid] = {
                                    'name': resp_data.get('group_name', str(gid)),
                                    'avatar': get_avatar_url(gid)
                                }
                                state.request_ui_refresh()
                        
                        # 个人名片刷新
                        if 'nickname' in resp_data and 'user_id' in resp_data:
                            uid = resp_data.get('user_id')
                            if uid == state.swordholder_qq:
                                state.user_info_cache[uid] = {
                                    'name': resp_data.get('nickname', str(uid)),
                                    'avatar': get_avatar_url(uid, is_group=False)
                                }
                                state.request_ui_refresh()

                    # 群消息捕获
                    if data.get('post_type') == 'message' and data.get('message_type') == 'group':
                        gid = data.get('group_id')
                        if gid in state.source_groups:
                            item = process_message_content(data.get('message', []))
                            if item:
                                item['raw_msg_id'] = data.get('message_id')
                                state.pending_list.append(item)
                                state.save_reviews()
                                add_log(f"[bot] 捕获新数据入库: {item['type']}")
                                state.request_ui_refresh()

        except Exception as e:
            add_log(f"[WS] 断开连接: {e}")
            update_status('error')
        finally:
            state.connected = False
            await asyncio.sleep(3) # 死循环防洪
            
    add_log("[WS] 进程已停止")
    update_status('disconnected')