from nicegui import ui

# 这行导入会自动执行 views.py 里的 @ui.page('/') 注册
from ui.views import main_page

if __name__ in {"__main__", "__mp_main__"}:
    # 启动服务器
    ui.run(title="搬史机器人 Pro", port=8080, reload=False, show=False)