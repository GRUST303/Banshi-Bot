import json
import os
import asyncio
from typing import Dict, Set, List

CONFIG_FILE = "config.json"
REVIEWS_FILE = "reviews.json"

class BotState:
    def __init__(self):
        self.ws_url = "ws://127.0.0.1:3001"
        self.source_groups: Set[int] = set()
        self.target_groups: Set[int] = set()
        self.swordholder_qq: int = 0
        self.cache_time = 600
        self.app_title: str = "搬史机器人 Pro"
        
        self.connected = False
        self.running = False
        self.ws = None
        
        # 内存队列
        self.pending_list: List[dict] = []
        self.dedup_set: Set[str] = set() # 存hash防重复
        
        # 本地信息缓存
        self.group_info_cache: Dict[int, dict] = {} 
        self.user_info_cache: Dict[int, dict] = {} 
        
        self.ui_needs_refresh = False
        self.api_futures: Dict[str, asyncio.Future] = {} 
        
        self.preview_index: int = -1
        self.is_processing: bool = False # UI防抖

    def load_data(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.ws_url = data.get('ws_url', self.ws_url)
                    self.source_groups = set(data.get('source_groups', []))
                    self.target_groups = set(data.get('target_groups', []))
                    self.swordholder_qq = data.get('swordholder_qq', 0)
                    self.cache_time = data.get('cache_time', self.cache_time)
                    self.app_title = data.get('app_title', "搬史机器人 Pro")
            except Exception as e:
                print(f"[Error] 读配置挂了: {e}")

        if os.path.exists(REVIEWS_FILE):
            try:
                with open(REVIEWS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.pending_list = data.get('list', [])
                    self.dedup_set = set(data.get('dedup', []))
            except Exception as e:
                print(f"[Error] 读本地历史数据失败: {e}")

    def save_config(self):
        data = {
            'ws_url': self.ws_url,
            'source_groups': list(self.source_groups),
            'target_groups': list(self.target_groups),
            'swordholder_qq': self.swordholder_qq,
            'cache_time': self.cache_time,
            'app_title': self.app_title
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except: pass

    def save_reviews(self):
        data = {
            'list': self.pending_list,
            'dedup': list(self.dedup_set)
        }
        try:
            with open(REVIEWS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except: pass

    def request_ui_refresh(self):
        self.ui_needs_refresh = True

# 全局单例
state = BotState()
state.load_data()