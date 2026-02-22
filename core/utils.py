import time
import uuid
from typing import Optional, List
from core.state import state

# 日志订阅器，解耦前端和后端
log_subscribers = []

def add_log(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    for sub in log_subscribers:
        try:
            sub(full_msg)
        except: pass

def get_avatar_url(id_val, is_group=True):
    if is_group:
        return f"https://p.qlogo.cn/gh/{id_val}/{id_val}/100"
    return f"https://q1.qlogo.cn/g?b=qq&nk={id_val}&s=100"

def generate_uuid():
    return str(uuid.uuid4())

def process_message_content(message_chain: List[dict]) -> Optional[dict]:
    # 过滤空消息
    if not message_chain: return None
    
    clean_segments = [] 
    previews = []       
    unique_hashes = []  
    msg_type = "unknown" 
    has_text = False
    
    # 遍历消息段
    for seg in message_chain:
        stype = seg.get('type')
        data = seg.get('data', {})
        
        if stype == 'text':
            if data.get('text', '').strip(): has_text = True
            
        elif stype == 'image':
            url = data.get('url')
            if url:
                # 给file也塞url，OneBot的坑
                clean_segments.append({"type": "image", "data": {"file": url, "url": url}})
                previews.append({'type': 'image', 'url': url})
                unique_hashes.append(data.get('file') or url)
                if msg_type == "unknown": msg_type = "image"
                elif msg_type != "image": msg_type = "mixed"
            
        elif stype == 'video':
            url = data.get('url')
            if url:
                clean_segments.append({"type": "video", "data": {"file": url, "url": url}})
                previews.append({'type': 'video', 'url': url})
                unique_hashes.append(data.get('file') or url)
                msg_type = "video" 
            
        elif stype in ['forward', 'node']:
            resid = data.get('id') or data.get('file')
            clean_segments.append(seg) 
            previews.append({'type': 'forward', 'id': resid}) 
            unique_hashes.append(resid)
            msg_type = "forward"

    # 过滤纯文本信息
    if has_text or not clean_segments: return None

    # 去重
    combined_hash = "".join(str(h) for h in unique_hashes)
    if combined_hash in state.dedup_set:
        add_log("[去重] 发现重复内容，已丢弃")
        return None
    
    state.dedup_set.add(combined_hash)
    
    return {
        "id": generate_uuid(),
        "type": msg_type,
        "content": clean_segments, 
        "previews": previews,
        "timestamp": time.time(),
        "selected": False,
        "raw_msg_id": 0 # 留空给外部填
    }