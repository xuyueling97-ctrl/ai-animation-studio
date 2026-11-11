"""生成纯合成演示素材。拒绝写入任何非空目录，不读取制作项目。"""
import argparse
import io
import wave
from pathlib import Path
from PIL import Image, ImageDraw
from store import Store

def create_demo(target):
    target=Path(target).resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError('目标目录非空，拒绝覆盖；请选择新的演示目录')
    s=Store(target)
    s.save_episode(1,'EP01 · 演示小屋','【虚构演示】\n场景：几何图形小屋。\n角色 A：今天一起画一扇窗吧。\n角色 B：好呀。','制作中','纯合成数据，与任何真实动画剧本无关。')
    s.execute('UPDATE characters SET description=? WHERE id=1',('演示角色 A：由几何图形组成，无真实角色设计。',))
    for label,color in [('V1','#b3c6ad'),('V2','#789982')]:
        im=Image.new('RGB',(720,360),'#fcf8f2'); draw=ImageDraw.Draw(im)
        for x in [120,360,600]:
            draw.ellipse((x-40,60,x+40,140),fill=color)
            draw.rounded_rectangle((x-52,155,x+52,290),radius=24,fill=color)
        buf=io.BytesIO(); im.save(buf,format='PNG')
        if label=='V1': aid=s.upload('demo-views.png',buf.getvalue(),'几何角色三视图（演示）','正面','演示,合成','演示小屋',[1],[1],label=label)
        else: s.upload('demo-views-v2.png',buf.getvalue(),'几何角色三视图（演示）','正面',asset_id=aid,label=label)
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b'\0\0'*8000)
    music=s.rows("SELECT asset_id FROM music WHERE kind='OP'")[0]['asset_id']
    s.upload('demo-silence.wav',out.getvalue(),'演示静音','音乐',asset_id=music,notes='1 秒静音，仅测试播放器，不是歌曲。')
    s.save_task(1,'演示小屋','001','确认角色参考','正面','已完成','手工绘图','虚构任务')
    s.save_task(1,'演示小屋','002','绘制场景分镜','分镜','制作中','演示工具','待补充景别')
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(Path(__file__).parent/'demo-data'))
    args=parser.parse_args()
    try: print(create_demo(args.output))
    except ValueError as exc: parser.exit(1,str(exc)+'\n')
