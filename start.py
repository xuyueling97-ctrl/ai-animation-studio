"""跨平台一键启动；设置保存在项目目录，数据目录不会随工作目录改变。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description='启动 AI 动画制作工作室')
    parser.add_argument('--port',type=int,default=8501)
    parser.add_argument('--address',default='127.0.0.1')
    parser.add_argument('--base-path',default='')
    parser.add_argument('--data-dir')
    args=parser.parse_args()
    config=ROOT/'local-settings.json'
    settings=json.loads(config.read_text('utf-8')) if config.exists() else {}
    if args.data_dir:
        settings['data_dir']=str(Path(args.data_dir).resolve())
        config.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
    if settings.get('data_dir'): os.environ['TCF_DATA_DIR']=settings['data_dir']
    from store import Store
    store=Store()
    print(f'数据保存目录：{store.root}',flush=True)
    print('停止服务：按 Ctrl+C。重启请再次运行启动脚本。',flush=True)
    command=[sys.executable,'-m','streamlit','run',str(ROOT/'app.py'),'--server.port',str(args.port),'--server.address',args.address,'--server.headless','true','--browser.gatherUsageStats','false','--server.maxUploadSize','200']
    if args.base_path: command+=['--server.baseUrlPath',args.base_path.strip('/')]
    subprocess.run(command,cwd=ROOT,check=True)

if __name__=='__main__': main()
