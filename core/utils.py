import time
import uuid
import os
from typing import Optional, List
from core.state import state

log_subscribers = []

# [修复权限报错] 获取项目根目录的绝对路径，并安全地创建 logs 文件夹
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception as e:
    print(f"[警告] 无法创建日志文件夹: {e}")

def add_log(msg: str):
    timestamp = time.strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    
    try:
        # 使用绝对路径写入日志
        log_file = os.path.join(LOG_DIR, "bot_run.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except: pass

    for sub in log_subscribers:
        try: sub(full_msg)
        except: pass

def get_avatar_url(id_val, is_group=True):
    if is_group:
        return f"https://p.qlogo.cn/gh/{id_val}/{id_val}/100"
    return f"https://q1.qlogo.cn/g?b=qq&nk={id_val}&s=100"

def generate_uuid():
    return str(uuid.uuid4())

def process_message_content(message_chain: List[dict]) -> Optional[dict]:
    if not message_chain: return None
    
    clean_segments = [] 
    previews = []       
    unique_hashes = []  
    msg_type = "unknown" 
    has_text = False
    
    for seg in message_chain:
        stype = seg.get('type')
        data = seg.get('data', {})
        
        if stype == 'text':
            if data.get('text', '').strip(): has_text = True
            
        elif stype == 'image':
            url = data.get('url')
            if url:
                clean_segments.append({"type": "image", "data": {"file": url, "url": url}})
                previews.append({'type': 'image', 'url': url})
                unique_hashes.append(data.get('file') or url)
                if msg_type == "unknown": msg_type = "image"
                elif msg_type != "image": msg_type = "mixed"
            
        elif stype == 'video':
            url = data.get('url')
            file_id = data.get('file') or url 
            if url:
                clean_segments.append({"type": "video", "data": {"file": file_id, "url": url}})
                previews.append({'type': 'video', 'url': url})
                unique_hashes.append(file_id)
                msg_type = "video" 
            
        elif stype in ['forward', 'node']:
            resid = data.get('id') or data.get('file')
            clean_segments.append(seg) 
            previews.append({'type': 'forward', 'id': resid}) 
            unique_hashes.append(resid)
            msg_type = "forward"

    if has_text or not clean_segments: return None

    combined_hash = "".join(str(h) for h in unique_hashes)
    
    # [修复核心] 确保这里用的是 dedup_dict 而不是 dedup_set
    if combined_hash in state.dedup_dict:
        add_log("[去重] 发现重复内容，已丢弃")
        return None
    
    state.dedup_dict[combined_hash] = True
    if len(state.dedup_dict) > state.MAX_DEDUP_SIZE:
        state.dedup_dict.popitem(last=False)
    
    return {
        "id": generate_uuid(),
        "type": msg_type,
        "content": clean_segments, 
        "previews": previews,
        "timestamp": time.time(),
        "selected": False,
        "raw_msg_id": 0 
    }