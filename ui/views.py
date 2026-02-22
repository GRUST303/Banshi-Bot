import asyncio
from datetime import datetime
from nicegui import ui
from core.state import state
from core.bot import run_bot
from core.utils import log_subscribers, get_avatar_url
from core.api import (
    execute_direct_media_send, execute_merge_forward,
    execute_single_forward, send_preview_to_reviewer, fetch_user_info, fetch_group_info
)

# 全局组件占位符
log_view = None
status_indicator = None
review_container_left = None
review_container_right = None
badge_media = None
badge_forward = None
groups_s_refreshable = None 
groups_t_refreshable = None
reviewer_panel_refreshable = None 
loading_dialog = None 
global_viewer_dialog = None
global_viewer_content = None

def with_lock(func):
    # 包装器：防止瞎点按钮导致并发冲突
    async def wrapper(*args, **kwargs):
        if state.is_processing:
            ui.notify("后端正在发力，别点太快...", type='warning')
            return
        state.is_processing = True
        if loading_dialog: loading_dialog.open()
        try:
            await func(*args, **kwargs)
        finally:
            state.is_processing = False
            if loading_dialog: loading_dialog.close()
    return wrapper

def open_global_viewer(index: int):
    if index < 0 or index >= len(state.pending_list): return
    state.preview_index = index
    render_global_viewer()
    global_viewer_dialog.open()

def render_global_viewer():
    if state.preview_index < 0 or state.preview_index >= len(state.pending_list): return
    item = state.pending_list[state.preview_index]
    global_viewer_content.clear()
    
    with global_viewer_content:
        ui.label(f"{state.preview_index + 1} / {len(state.pending_list)}").classes('absolute top-4 left-4 text-white font-bold z-50 bg-black/50 px-2 rounded')
        
        if item['type'] == 'image':
            url = item['previews'][0]['url']
            ui.image(url).classes('max-w-full max-h-full object-contain').props('referrerpolicy="no-referrer"')
        elif item['type'] == 'video':
            url = item['previews'][0]['url']
            ui.video(url).classes('w-full max-h-full').props('controls autoplay')
        elif item['type'] == 'forward':
            with ui.column().classes('items-center justify-center h-full text-white gap-4'):
                ui.icon('forum', size='6xl').classes('opacity-80')
                ui.label('聊天记录 (合并转发)').classes('text-3xl font-bold')
                async def send_now():
                    success, msg = await send_preview_to_reviewer(item['raw_msg_id'])
                    ui.notify(msg, type='positive' if success else 'negative')
                ui.button('发送给审核员', on_click=send_now).props('color=blue icon=send')

def switch_preview(direction):
    new_index = state.preview_index + direction
    if new_index < 0: new_index = len(state.pending_list) - 1
    elif new_index >= len(state.pending_list): new_index = 0
    state.preview_index = new_index
    render_global_viewer()

def toggle_all_type(target_type):
    filter_types = ['image', 'video'] if target_type == 'media' else ['forward']
    current_items = [i for i in state.pending_list if i['type'] in filter_types]
    if not current_items: return
    
    all_selected = all(i['selected'] for i in current_items)
    for i in current_items: i['selected'] = not all_selected
    refresh_review_panel()

def delete_selected(target_type):
    filter_types = ['image', 'video'] if target_type == 'media' else ['forward']
    state.pending_list = [i for i in state.pending_list if not (i['selected'] and i['type'] in filter_types)]
    state.save_reviews()
    refresh_review_panel()
    ui.notify(f"清理完毕")

def toggle_select_direct(item, value):
    item['selected'] = value

def refresh_review_panel():
    media_items = [i for i in state.pending_list if i['type'] in ['image', 'video']]
    forward_items = [i for i in state.pending_list if i['type'] == 'forward']
    
    if badge_media: badge_media.text = str(len(media_items))
    if badge_forward: badge_forward.text = str(len(forward_items))

    # 渲染左半区 (图片/视频)
    if review_container_left:
        review_container_left.clear()
        with review_container_left:
            for idx, item in enumerate(state.pending_list):
                if item['type'] not in ['image', 'video']: continue
                
                border_cls = 'border-blue-500 bg-blue-50 dark:bg-blue-900' if item['selected'] else 'border-transparent bg-white dark:bg-gray-800 shadow'
                with ui.card().classes(f'w-full p-0 rounded border-2 transition-all relative aspect-square {border_cls}'):
                    with ui.row().classes('absolute top-1 left-1 z-20'):
                        ui.checkbox(value=item['selected'], on_change=lambda e, i=item: toggle_select_direct(i, e.value)).props('size=sm color=blue keep-color')
                    
                    with ui.row().classes('absolute top-1 right-1 z-20'):
                        icon = 'play_circle' if item['type'] == 'video' else 'zoom_in'
                        ui.button(icon=icon, on_click=lambda _, idx=idx: open_global_viewer(idx)).props('round color=blue dense size=xs shadow stop-propagation')

                    with ui.column().classes('w-full h-full items-center justify-center p-1'):
                        if item['type'] == 'image':
                            ui.image(item['previews'][0]['url']).classes('max-h-full max-w-full rounded').props('referrerpolicy="no-referrer"')
                        else:
                            ui.icon('movie', size='md').classes('opacity-30 dark:text-gray-400')

    # 渲染右半区 (记录)
    if review_container_right:
        review_container_right.clear()
        with review_container_right:
            for idx, item in enumerate(state.pending_list):
                if item['type'] != 'forward': continue
                
                border_cls = 'border-purple-500 bg-purple-50 dark:bg-purple-900' if item['selected'] else 'border-transparent bg-white dark:bg-gray-800 shadow'
                with ui.card().classes(f'w-full p-2 rounded border-2 transition-all relative {border_cls}'):
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.row().classes('items-center gap-2'):
                            ui.checkbox(value=item['selected'], on_change=lambda e, i=item: toggle_select_direct(i, e.value)).props('size=sm color=purple keep-color')
                            with ui.column().classes('gap-0'):
                                ui.label('合并转发记录').classes('text-sm font-bold dark:text-gray-200')
                                ui.label(datetime.fromtimestamp(item['timestamp']).strftime('%H:%M:%S')).classes('text-xs opacity-50 dark:text-gray-400')
                        
                        async def forward_handler(e, i=item):
                            success, msg = await send_preview_to_reviewer(i['raw_msg_id'])
                            ui.notify(msg, type='positive' if success else 'negative')
                            
                        ui.button(icon='send', on_click=forward_handler).props('round color=purple dense size=sm shadow stop-propagation').tooltip('私发给审核员')


@ui.page('/')
def main_page():
    global log_view, status_indicator, review_container_left, review_container_right
    global groups_s_refreshable, groups_t_refreshable, reviewer_panel_refreshable
    global global_viewer_dialog, global_viewer_content, loading_dialog
    global badge_media, badge_forward
    
    dark = ui.dark_mode()
    
    def del_grp(gid, g_type, refresh_func):
        if g_type == 'source': state.source_groups.discard(gid)
        else: state.target_groups.discard(gid)
        state.save_config()
        refresh_func()

    def render_group_item(gid, g_type, refresh_func):
        info = state.group_info_cache.get(gid, {})
        name = info.get('name', str(gid))
        avatar = info.get('avatar', get_avatar_url(gid))
        with ui.row().classes('w-full items-center justify-between bg-gray-50 dark:bg-gray-700 p-2 rounded'):
            with ui.row().classes('items-center gap-2'):
                ui.image(avatar).classes('w-8 h-8 rounded-full').props('referrerpolicy="no-referrer"')
                with ui.column().classes('gap-0'):
                    ui.label(name).classes('text-xs font-bold truncate w-24 dark:text-gray-200')
                    ui.label(str(gid)).classes('text-[10px] opacity-60 dark:text-gray-400')
            ui.icon('close', size='xs').classes('cursor-pointer opacity-50 hover:text-red-500').on('click', lambda: del_grp(gid, g_type, refresh_func))

    # 加载蒙版
    with ui.dialog() as loading_dialog, ui.card().classes('items-center'):
        ui.spinner(size='lg')
        ui.label('请求发送中，去喝口水...').classes('text-sm text-gray-500 mt-2')

    # 画廊
    with ui.dialog() as global_viewer_dialog, ui.card().classes('w-full h-full bg-black flex flex-col justify-center items-center p-0 relative'):
        ui.button(icon='close', on_click=global_viewer_dialog.close).props('flat round color=white').classes('absolute top-4 right-4 z-50')
        global_viewer_content = ui.element('div').classes('w-full h-full flex justify-center items-center')
        ui.button(icon='chevron_left', on_click=lambda: switch_preview(-1)).props('flat round color=white size=xl').classes('absolute left-4 top-1/2 -translate-y-1/2 z-50')
        ui.button(icon='chevron_right', on_click=lambda: switch_preview(1)).props('flat round color=white size=xl').classes('absolute right-4 top-1/2 -translate-y-1/2 z-50')

    def apply_card_theme(card_element):
        card_element.classes('w-full p-4 rounded-xl shadow-lg transition-colors duration-300')
        def update():
            card_element.classes(remove='bg-white text-black bg-gray-800 text-white')
            if dark.value: card_element.classes('bg-gray-800 text-white')
            else: card_element.classes('bg-white text-black')
        dark.on_value_change(update)
        update()
        return card_element

    container = ui.column().classes('w-full h-screen p-6 items-center gap-4 transition-colors duration-300 overflow-hidden')
    def update_bg():
        container.classes(remove='bg-gray-50 bg-gray-900 text-gray-200')
        container.classes('bg-gray-900 text-gray-200' if dark.value else 'bg-gray-50')
    dark.on_value_change(update_bg)
    update_bg()

    with container:
        # 顶栏
        with ui.row().classes('w-full max-w-7xl items-center justify-between flex-shrink-0'):
            with ui.row().classes('items-center gap-3'):
                ui.icon('smart_toy', size='32px').classes('text-blue-500')
                page_title_label = ui.label(state.app_title).classes('text-2xl font-bold dark:text-white')
            with ui.row().classes('items-center gap-4'):
                with ui.row().classes('items-center gap-2'):
                    ui.label('STATUS').classes('text-xs font-bold opacity-60 dark:text-gray-400')
                    status_indicator = ui.element('div').classes('w-3 h-3 rounded-full bg-red-500')
                ui.button(icon='dark_mode', on_click=dark.toggle).props('flat round dense color=grey')

        # 核心网格布局
        with ui.grid(columns=4).classes('w-full max-w-7xl flex-grow gap-6 h-full min-h-0'):
            
            # --- 左栏：控制台 ---
            with ui.column().classes('col-span-1 gap-4 h-full overflow-y-auto no-scrollbar'):
                with apply_card_theme(ui.card()):
                    ui.label('运行控制').classes('text-sm font-bold opacity-60 mb-2 dark:text-gray-400')
                    
                    def on_bot_status(status):
                        if status == 'connected':
                            status_indicator.classes('bg-green-500', remove='bg-red-500 bg-yellow-500')
                        elif status == 'error':
                            status_indicator.classes('bg-yellow-500', remove='bg-green-500 bg-red-500')
                        else:
                            status_indicator.classes('bg-red-500', remove='bg-green-500 bg-yellow-500')

                    async def toggle_run():
                        if not state.running:
                            state.running = True
                            btn_run.props('color=red icon=stop label="断开连接"')
                            asyncio.create_task(run_bot(on_bot_status))
                        else:
                            state.running = False
                            btn_run.props('color=green icon=play_arrow label="开始找史"')
                    btn_run = ui.button('开始找史', on_click=toggle_run).props('color=green icon=play_arrow un-elevated rounded').classes('w-full h-12')

                with apply_card_theme(ui.card()):
                    ui.label('审核员设置').classes('text-lg font-bold mb-2 dark:text-white')
                    @ui.refreshable
                    def render_reviewer_info():
                        global reviewer_panel_refreshable
                        reviewer_panel_refreshable = render_reviewer_info
                        if state.swordholder_qq:
                            info = state.user_info_cache.get(state.swordholder_qq, {})
                            name = info.get('name', '加载中...')
                            avatar = info.get('avatar', get_avatar_url(state.swordholder_qq, False))
                            with ui.row().classes('w-full items-center gap-3 bg-blue-50 dark:bg-blue-900 p-2 rounded mb-2'):
                                ui.image(avatar).classes('w-10 h-10 rounded-full').props('referrerpolicy="no-referrer"')
                                with ui.column().classes('gap-0'):
                                    ui.label(name).classes('text-sm font-bold dark:text-white')
                                    ui.label(str(state.swordholder_qq)).classes('text-xs opacity-60 dark:text-gray-300')
                        else:
                            ui.label('虚位以待').classes('text-xs text-gray-400 mb-2')
                    render_reviewer_info()
                    ui.number(format='%.0f', placeholder='输入QQ号').bind_value(state, 'swordholder_qq').classes('w-full mb-2')
                    async def save_reviewer():
                        state.save_config()
                        if state.swordholder_qq: await fetch_user_info(state.swordholder_qq)
                        render_reviewer_info.refresh()
                        ui.notify('已绑定审核员')
                    ui.button('保存绑定', on_click=save_reviewer).props('outline rounded color=blue w-full')

                with apply_card_theme(ui.card()):
                    ui.label('监听源群').classes('text-sm font-bold text-blue-500')
                    s_in = ui.number(format='%.0f', placeholder='输入群号回车').classes('w-full').props('dense filled')
                    async def add_s(e):
                        if e.sender.value:
                            gid = int(e.sender.value)
                            state.source_groups.add(gid)
                            state.save_config()
                            e.sender.value = None
                            await fetch_group_info(gid) 
                            groups_s.refresh()
                    s_in.on('keydown.enter', add_s)
                    @ui.refreshable
                    def groups_s():
                        global groups_s_refreshable
                        groups_s_refreshable = groups_s 
                        with ui.column().classes('w-full gap-2 mt-2'):
                            for gid in state.source_groups: render_group_item(gid, 'source', groups_s)
                    groups_s()
                    
                    ui.separator().classes('my-4 dark:bg-gray-600')
                    
                    ui.label('分发目标群').classes('text-sm font-bold text-purple-500')
                    t_in = ui.number(format='%.0f', placeholder='输入群号回车').classes('w-full').props('dense filled')
                    async def add_t(e):
                        if e.sender.value:
                            gid = int(e.sender.value)
                            state.target_groups.add(gid)
                            state.save_config()
                            e.sender.value = None
                            await fetch_group_info(gid)
                            groups_t.refresh()
                    t_in.on('keydown.enter', add_t)
                    @ui.refreshable
                    def groups_t():
                        global groups_t_refreshable
                        groups_t_refreshable = groups_t
                        with ui.column().classes('w-full gap-2 mt-2'):
                            for gid in state.target_groups: render_group_item(gid, 'target', groups_t)
                    groups_t()

                with apply_card_theme(ui.card()):
                    ui.label('系统底层').classes('text-sm font-bold opacity-60 mb-2 dark:text-gray-400')
                    ui.input('WebSocket 地址').bind_value(state, 'ws_url').classes('w-full mb-2')
                    ui.button('保存参数', on_click=state.save_config).props('outline rounded color=grey w-full')

            # --- 右栏：业务区 ---
            with ui.column().classes('col-span-3 h-full gap-4 flex flex-col min-h-0'):
                with ui.row().classes('w-full flex-grow gap-4 min-h-0 no-wrap'):
                    
                    # 模块 A：图片视频库
                    with apply_card_theme(ui.card()).classes('flex-1 w-0 h-full flex flex-col p-0 overflow-hidden'):
                        with ui.row().classes('w-full p-3 border-b dark:border-gray-700 justify-between items-center bg-gray-100 dark:bg-gray-800'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('perm_media', size='sm').classes('text-blue-500')
                                ui.label('多媒体库').classes('font-bold dark:text-white')
                                badge_media = ui.badge('0').props('color=blue dense')
                            
                            with ui.row().classes('gap-1'):
                                ui.button('全选', on_click=lambda: toggle_all_type('media')).props('flat dense size=sm')
                                
                                @with_lock
                                async def send_media_direct():
                                    selected = [i for i in state.pending_list if i['selected'] and i['type'] in ['image', 'video']]
                                    if not selected: return
                                    ui.notify(f"开始直发 {len(selected)} 份媒体，有点慢耐心等...", type='info')
                                    for item in selected: await execute_direct_media_send(item['content'])
                                    delete_selected('media')
                                ui.button('硬发', on_click=send_media_direct).props('color=orange icon=send size=sm').tooltip('不打包，直接逐条发送')

                                @with_lock
                                async def send_media_pack():
                                    selected = [i for i in state.pending_list if i['selected'] and i['type'] in ['image', 'video']]
                                    if not selected: return
                                    ui.notify(f"正在打包 {len(selected)} 份媒体...", type='info')
                                    pack_list = [i['content'] for i in selected]
                                    msg_ids = [i['raw_msg_id'] for i in selected]
                                    failed_groups = await execute_merge_forward(pack_list, msg_ids)
                                    if not failed_groups:
                                        delete_selected('media')
                                        ui.notify("打包发送完成", type='positive')
                                    else:
                                        ui.notify(f"部分群未送达，原文件已保留", type='negative')
                                ui.button('打包', on_click=send_media_pack).props('color=blue icon=inventory_2 size=sm').tooltip('整合为一条聊天记录发送')
                                
                                ui.button(icon='delete', on_click=lambda: delete_selected('media')).props('color=red outline size=sm')

                        with ui.scroll_area().classes('flex-grow w-full p-2'):
                            review_container_left = ui.grid(columns=3).classes('w-full gap-2')
                            refresh_review_panel()

                    # 模块 B：聊天记录源
                    with apply_card_theme(ui.card()).classes('flex-1 w-0 h-full flex flex-col p-0 overflow-hidden'):
                        with ui.row().classes('w-full p-3 border-b dark:border-gray-700 justify-between items-center bg-gray-100 dark:bg-gray-800'):
                            with ui.row().classes('items-center gap-2'):
                                ui.icon('forum', size='sm').classes('text-purple-500')
                                ui.label('聊天记录').classes('font-bold dark:text-white')
                                badge_forward = ui.badge('0').props('color=purple dense')
                            
                            with ui.row().classes('gap-1'):
                                ui.button('全选', on_click=lambda: toggle_all_type('forward')).props('flat dense size=sm')
                                
                                @with_lock
                                async def send_forwards():
                                    selected = [i for i in state.pending_list if i['selected'] and i['type'] == 'forward']
                                    if not selected: return
                                    ui.notify(f"准备转发 {len(selected)} 条记录...", type='info')
                                    for item in selected: await execute_single_forward(item['raw_msg_id'])
                                    delete_selected('forward')
                                ui.button('转发', on_click=send_forwards).props('color=green icon=send size=sm')
                                
                                ui.button(icon='delete', on_click=lambda: delete_selected('forward')).props('color=red outline size=sm')

                        with ui.scroll_area().classes('flex-grow w-full p-2'):
                            review_container_right = ui.column().classes('w-full gap-2')
                            refresh_review_panel()

                # 控制台输出日志
                log_card = apply_card_theme(ui.card())
                log_card.classes('w-full h-40 flex-shrink-0')
                with log_card:
                    with ui.row().classes('w-full justify-between items-center mb-1'):
                        ui.label('Console').classes('text-xs font-bold opacity-60 dark:text-gray-400')
                        ui.button('Clean', on_click=lambda: log_view.clear()).props('flat dense size=xs opacity=50 color=grey')
                    log_view = ui.log(max_lines=100).classes('w-full h-full font-mono text-[10px] bg-transparent dark:text-gray-300 leading-tight')
                    
                    def on_log_msg(msg):
                        try: log_view.push(msg)
                        except: pass
                    if on_log_msg not in log_subscribers:
                        log_subscribers.append(on_log_msg)

    # 简易轮询机制刷UI
    def auto_refresh():
        if state.ui_needs_refresh:
            refresh_review_panel()
            if groups_s_refreshable: groups_s_refreshable.refresh()
            if groups_t_refreshable: groups_t_refreshable.refresh()
            if reviewer_panel_refreshable: reviewer_panel_refreshable.refresh()
            state.ui_needs_refresh = False
            

    ui.timer(1.0, auto_refresh)
