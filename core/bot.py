import asyncio
import json
import time
import websockets
from nicegui import ui
from core.state import state
from core.utils import add_log, process_message_content, get_avatar_url
from core.api import fetch_group_info, fetch_user_info, execute_merge_forward, execute_single_forward

# [新增] 自动打包互斥锁，防止并发发送冲突
auto_pack_lock = asyncio.Lock()

async def check_and_trigger_auto_pack():
    """自动化检查与触发器"""
    if not state.auto_pack or state.auto_pack_threshold <= 0:
        return
        
    async with auto_pack_lock:
        # 1. 检测媒体库是否达标
        media_items = [i for i in state.pending_list if i['type'] in ['image', 'video']]
        while len(media_items) >= state.auto_pack_threshold:
            state.is_processing = True
            try:
                batch = media_items[:state.auto_pack_threshold]
                add_log(f"[Auto] 媒体满 {state.auto_pack_threshold} 条，全自动打包发车...")
                pack_list = [i['content'] for i in batch]
                msg_ids = [i['raw_msg_id'] for i in batch]
                
                failed_groups = await execute_merge_forward(pack_list, msg_ids)
                if not failed_groups:
                    # 成功后才清理
                    sent_ids = {i['id'] for i in batch}
                    state.pending_list = [i for i in state.pending_list if i['id'] not in sent_ids]
                    state.save_reviews()
                    state.request_ui_refresh()
                    add_log("[Auto] 自动打包完毕并出库")
                else:
                    add_log("[Auto] 打包遇阻，暂停自动发送并保留现场")
                    break # 遇到死图导致失败，跳出循环留给人工处理
            finally:
                state.is_processing = False
            # 刷新列表，看看剩下的够不够再次触发
            media_items = [i for i in state.pending_list if i['type'] in ['image', 'video']]

        # 2. 检测情报局(转发记录)是否达标
        forward_items = [i for i in state.pending_list if i['type'] == 'forward']
        while len(forward_items) >= state.auto_pack_threshold:
            state.is_processing = True
            try:
                batch = forward_items[:state.auto_pack_threshold]
                add_log(f"[Auto] 情报记录满 {state.auto_pack_threshold} 条，自动转发...")
                for item in batch:
                    await execute_single_forward(item['raw_msg_id'])
                
                sent_ids = {i['id'] for i in batch}
                state.pending_list = [i for i in state.pending_list if i['id'] not in sent_ids]
                state.save_reviews()
                state.request_ui_refresh()
                add_log("[Auto] 记录自动转发完毕并出库")
            finally:
                state.is_processing = False
            forward_items = [i for i in state.pending_list if i['type'] == 'forward']

async def check_and_trigger_warnings():
    """检测堆积并发送私聊警告"""
    if not state.swordholder_qq or state.warn_interval_minutes <= 0:
        return
    if time.time() - state.last_warn_time < state.warn_interval_minutes * 60:
        return
        
    media_items = [i for i in state.pending_list if i['type'] in ['image', 'video']]
    forward_items = [i for i in state.pending_list if i['type'] == 'forward']
    
    msgs = []
    if len(media_items) >= state.warn_media_count and state.warn_media_count > 0:
        msgs.append(f"【警告】媒体库已堆积 {len(media_items)} 条，请及时清理防止卡顿裂图！")
    if len(forward_items) >= state.warn_forward_count and state.warn_forward_count > 0:
        msgs.append(f"【警告】情报局已堆积 {len(forward_items)} 条，请及时处理！")
        
    if msgs:
        state.last_warn_time = time.time()
        full_msg = "\n".join(msgs)
        try:
            # 伪造私聊发送 API
            await api_call("send_private_msg", {"user_id": int(state.swordholder_qq), "message": full_msg})
            add_log("[Warn] 已向审核员发送堆积警告")
        except Exception as e:
            pass

async def run_bot(on_status_change=None):
    def update_status(status_str):
        if on_status_change:
            on_status_change(status_str)

    add_log(f"[WS] 正在连接 {state.ws_url} ...")
    
    while state.running:
        try:
            # [新增] 携带 Token 鉴权头
            headers = {}
            if state.ws_token:
                headers["Authorization"] = f"Bearer {state.ws_token}"

            async with websockets.connect(state.ws_url, additional_headers=headers) as websocket:
                state.ws = websocket
                state.connected = True
                
                if state.disconnect_time > 0:
                    add_log("[WS] 重新连接成功，重置断线计时")
                state.disconnect_time = 0.0 
                
                add_log("[WS] 连接成功")
                update_status('connected')
                
                if state.swordholder_qq: 
                    await fetch_user_info(state.swordholder_qq)
                for gid in state.source_groups.union(state.target_groups):
                    await fetch_group_info(gid)

                async for message in websocket:
                    if not state.running: break
                    data = json.loads(message)
                    
                    if 'echo' in data and data['echo'].startswith('req_'):
                        echo = data['echo']
                        if echo in state.api_futures:
                            future = state.api_futures[echo]
                            if not future.done(): future.set_result(data)
                            del state.api_futures[echo]
                        continue

                    resp_data = data.get('data') or {}
                    if data.get('status') == 'ok':
                        if 'group_name' in resp_data:
                            gid = resp_data.get('group_id')
                            if gid:
                                state.group_info_cache[gid] = {
                                    'name': resp_data.get('group_name', str(gid)),
                                    'avatar': get_avatar_url(gid)
                                }
                                state.request_ui_refresh()
                        
                        if 'nickname' in resp_data and 'user_id' in resp_data:
                            uid = resp_data.get('user_id')
                            if uid == state.swordholder_qq:
                                state.user_info_cache[uid] = {
                                    'name': resp_data.get('nickname', str(uid)),
                                    'avatar': get_avatar_url(uid, is_group=False)
                                }
                                state.request_ui_refresh()

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
                                
                                # [新增] 每当有新消息入库，触发一次自动化检查
                                if state.auto_pack:
                                    asyncio.create_task(check_and_trigger_auto_pack())

                                # [新增] 触发警告检查
                                asyncio.create_task(check_and_trigger_warnings())

        except Exception as e:
            add_log(f"[WS] 失去连接: {e}")
            update_status('error')
            
            # [核心修复] 把直接调用 ui.notify 改成放进信箱
            if state.disconnect_time == 0.0:
                state.disconnect_time = time.time()
                state.notify_queue.append(('negative', '❌ 警告：已与 NapCat 失去连接！'))
                
        finally:
            state.connected = False
            
            if state.disconnect_time > 0 and state.auto_clear_minutes > 0:
                offline_duration = (time.time() - state.disconnect_time) / 60
                if offline_duration >= state.auto_clear_minutes:
                    if state.pending_list:
                        add_log(f"[Warn] 断线超过 {state.auto_clear_minutes} 分钟，为防裂图，自动清空待审队列")
                        state.pending_list.clear()
                        state.save_reviews()
                        state.request_ui_refresh()
                        state.disconnect_time = time.time() 

            await asyncio.sleep(3) 
            
    add_log("[WS] 进程已停止")

    update_status('disconnected')
