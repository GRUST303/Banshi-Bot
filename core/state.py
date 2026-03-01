import json
import os
import asyncio
from typing import Dict, Set, List
from collections import OrderedDict

CONFIG_FILE = "config.json"
REVIEWS_FILE = "reviews.json"

class BotState:
    def __init__(self):
        self.ws_url = "ws://127.0.0.1:3001"
        self.ws_token: str = "" 
        self.source_groups: Set[int] = set()
        self.target_groups: Set[int] = set()
        self.swordholder_qq: int = 0
        self.cache_time = 600
        self.app_title: str = "搬史机器人 Pro"
        
        self.auto_clear_minutes: int = 30
        self.auto_pack: bool = False
        self.auto_pack_threshold: int = 10
        
        #堆积警告机制
        self.warn_media_count: int = 50
        self.warn_forward_count: int = 20
        self.warn_interval_minutes: int = 30
        self.last_warn_time: float = 0.0

        # [新增] 分页控制
        self.media_page: int = 1
        self.media_page_max: int = 1
        self.forward_page: int = 1
        self.forward_page_max: int = 1
        
        self.connected = False
        self.running = False
        self.ws = None
        
        self.pending_list: List[dict] = []
        self.dedup_dict: OrderedDict = OrderedDict() 
        self.MAX_DEDUP_SIZE = 2000 
        
        self.group_info_cache: Dict[int, dict] = {} 
        self.user_info_cache: Dict[int, dict] = {} 
        
        self.ui_needs_refresh = False
        self.api_futures: Dict[str, asyncio.Future] = {} 
        
        self.preview_index: int = -1
        self.is_processing: bool = False 
        self.disconnect_time: float = 0.0 
        
        # [新增] 专门给后台任务给前端发通知的信箱
        self.notify_queue: List[tuple] = [] 

    def load_data(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.ws_url = data.get('ws_url', self.ws_url)
                    self.ws_token = data.get('ws_token', "")
                    self.source_groups = set(data.get('source_groups', []))
                    self.target_groups = set(data.get('target_groups', []))
                    self.swordholder_qq = data.get('swordholder_qq', 0)
                    self.cache_time = data.get('cache_time', self.cache_time)
                    self.app_title = data.get('app_title', "搬史机器人 Pro")
                    self.auto_clear_minutes = data.get('auto_clear_minutes', 30)
                    self.auto_pack = data.get('auto_pack', False)
                    self.auto_pack_threshold = data.get('auto_pack_threshold', 10)
                    self.warn_media_count = data.get('warn_media_count', 50)
                    self.warn_forward_count = data.get('warn_forward_count', 20)
                    self.warn_interval_minutes = data.get('warn_interval_minutes', 30)
            except Exception as e:
                print(f"[Error] 读配置挂了: {e}")

        if os.path.exists(REVIEWS_FILE):
            try:
                with open(REVIEWS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.pending_list = data.get('list', [])
                    saved_dedups = data.get('dedup', [])
                    for d in saved_dedups:
                        self.dedup_dict[d] = True
                        if len(self.dedup_dict) > self.MAX_DEDUP_SIZE:
                            self.dedup_dict.popitem(last=False)
            except Exception as e:
                print(f"[Error] 读本地历史数据失败: {e}")

    def save_config(self):
        data = {
            'ws_url': self.ws_url,
            'ws_token': self.ws_token,
            'source_groups': list(self.source_groups),
            'target_groups': list(self.target_groups),
            'swordholder_qq': self.swordholder_qq,
            'cache_time': self.cache_time,
            'app_title': self.app_title,
            'auto_clear_minutes': self.auto_clear_minutes,
            'auto_pack': self.auto_pack,
            'auto_pack_threshold': self.auto_pack_threshold,
            'warn_media_count': self.warn_media_count,
            'warn_forward_count': self.warn_forward_count,
            'warn_interval_minutes': self.warn_interval_minutes
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except: pass

    def save_reviews(self):
        data = {
            'list': self.pending_list,
            'dedup': list(self.dedup_dict.keys())
        }
        try:
            with open(REVIEWS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except: pass

    def request_ui_refresh(self):
        self.ui_needs_refresh = True

state = BotState()

state.load_data()


