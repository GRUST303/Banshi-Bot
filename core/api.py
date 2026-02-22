import asyncio
import json
import time
import random
from typing import List, Tuple
from core.state import state
from core.utils import add_log

async def api_call(action, params, wait=False, timeout=15):
    # 底层API调用，封装了发包和异步等待响应的逻辑
    if not state.ws or not state.connected: return None
    
    if not wait:
        try: await state.ws.send(json.dumps({"action": action, "params": params}))
        except: pass
        return None

    echo = f"req_{int(time.time()*100000)}"
    future = asyncio.get_running_loop().create_future()
    state.api_futures[echo] = future
    try:
        await state.ws.send(json.dumps({"action": action, "params": params, "echo": echo}))
        return await asyncio.wait_for(future, timeout)
    except Exception as e:
        add_log(f"[API] 请求超时或报错: {e}")
        if echo in state.api_futures: del state.api_futures[echo]
        return None

async def fetch_group_info(gid):
    await api_call("get_group_info", {"group_id": int(gid), "no_cache": True}, wait=False)

async def fetch_user_info(uid):
    await api_call("get_stranger_info", {"user_id": int(uid), "no_cache": True}, wait=False)


async def execute_merge_forward(content_list: List[List[dict]], msg_ids: List[int]) -> List[int]:
    # 打包逻辑
    if not state.target_groups: return []
    failed_groups = []
    
    # 策略1：自定义节点克隆
    nodes_l1 = [{"type": "node", "data": {"name": state.app_title, "uin": "10000", "content": f"📅 {time.strftime('%Y-%m-%d')} 精选"}}]
    for segments in content_list:
        nodes_l1.append({"type": "node", "data": {"name": state.app_title, "uin": "10000", "content": segments}})

    # 策略2：单纯引用原始ID
    nodes_l2 = [{"type": "node", "data": {"id": str(mid)}} for mid in msg_ids] if msg_ids else []

    for gid in state.target_groups:
        success = False
        gid_int = int(gid)
        
        try:
            res = await api_call("send_group_forward_msg", {"group_id": gid_int, "messages": nodes_l1}, wait=True)
            if res and res.get('status') == 'ok':
                add_log(f"[Send] 伪造打包发送成功 -> 群{gid}")
                success = True
        except Exception as e:
            add_log(f"[Warn] L1发送失败 ({e})，尝试降级L2")
        
        # 降级重试
        if not success and nodes_l2:
            try:
                res = await api_call("send_group_forward_msg", {"group_id": gid_int, "messages": nodes_l2}, wait=True)
                if res and res.get('status') == 'ok':
                    add_log(f"[Send] 引用打包成功 -> 群{gid}")
                    success = True
            except Exception as e:
                add_log(f"[Error] L2也失败了: {e}")

        if not success:
            failed_groups.append(gid)
            add_log(f"[Error] 群{gid} 彻底发送失败，状态保留")
        
        await asyncio.sleep(2.0) # 防风控休眠

    return failed_groups

async def execute_direct_media_send(segments: List[dict]):
    # 单条加随机延迟
    for gid in state.target_groups:
        try:
            await api_call("send_group_msg", {"group_id": int(gid), "message": segments})
            add_log(f"[Send] 直发媒体 -> 群{gid}")
            await asyncio.sleep(random.uniform(2.0, 3.5)) 
        except Exception as e:
            add_log(f"[Error] 直发失败 群{gid}: {e}")

async def execute_single_forward(msg_id):
    # 原样转发聊天记录
    for gid in state.target_groups:
        try:
            await api_call("forward_group_single_msg", {"group_id": int(gid), "message_id": str(msg_id)})
            add_log(f"[Send] 记录转发 -> 群{gid}")
            await asyncio.sleep(1.0)
        except Exception as e:
            add_log(f"[Error] 记录转发失败 群{gid}: {e}")

async def send_preview_to_reviewer(raw_msg_id) -> Tuple[bool, str]:
    if not state.swordholder_qq:
        return False, "请先设置审核员QQ"
    try:
        target_qq = int(state.swordholder_qq)
        await api_call("forward_friend_single_msg", {"user_id": target_qq, "message_id": str(raw_msg_id)})
        return True, f"已私聊推送给 ({target_qq})"
    except Exception as e:
        add_log(f"[Error] 私聊推送失败: {e}")
        return False, "发送异常，看日志"