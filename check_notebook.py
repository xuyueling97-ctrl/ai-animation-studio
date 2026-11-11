"""只读检查；不输出登录 token、不启动隧道、不猜测公网地址。"""
import importlib.util
import json
import os
from pathlib import Path
import socket

print('=== Notebook 启动前检查 ===')
p=Path('/mnt/workspace')
print('持久目录 /mnt/workspace：', '存在且可写' if p.is_dir() and os.access(p,os.W_OK) else '不存在或不可写，请勿继续部署')
print('jupyter-server-proxy：', '已安装（仍需浏览器确认路由启用）' if importlib.util.find_spec('jupyter_server_proxy') else '未检测到')
with socket.socket() as sock:
    print('本机 8501 端口：','已有服务' if sock.connect_ex(('127.0.0.1',8501))==0 else '空闲')
try:
    from jupyter_core.paths import jupyter_runtime_dir
    files=list(Path(jupyter_runtime_dir()).glob('*server-*.json'))
    for f in files:
        try:
            info=json.loads(f.read_text())
            print('Jupyter 服务前缀：',info.get('base_url','/'))
        except (OSError,ValueError): pass
except ImportError: pass
print('下一步：查看平台是否有受登录保护的端口预览入口；或确认 Jupyter 的 proxy/8501/ 路由可用。')
print('检测到包不等于浏览器可以访问；HTTP 页面和 WebSocket 均须验证。详见 README.md。')
