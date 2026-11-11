import io, os, subprocess, sys, tempfile, unittest, wave
from pathlib import Path
from store import Store

class MVPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.s=Store(self.root)
    def tearDown(self): self.tmp.cleanup()
    def test_restart_in_separate_process(self):
        self.s.save_episode(1,'EP01 家','正式剧本','制作中','修改意见')
        self.s.save_task(1,'客厅','S01','镜头制作','AI 视频','已完成','模型 A','通过')
        self.s.upload('../../reference.txt',b'original','参考','剧本',episodes=[1,2],characters=[1])
        code="from store import Store; import sys; s=Store(sys.argv[1]); assert s.rows('SELECT * FROM episodes WHERE id=1')[0]['script']=='正式剧本'; assert s.rows('SELECT * FROM tasks')[0]['completed']; assert len(s.assets(episode=2))==1; assert s.file(s.rows('SELECT * FROM versions')[0]).read_bytes()==b'original'"
        subprocess.run([sys.executable,'-c',code,str(self.root)],check=True)
    def test_script_history_and_immutable_files(self):
        self.s.save_episode(1,'EP01','第一版','制作中','')
        self.s.save_episode(1,'EP01','第二版','待审核','')
        self.assertEqual(self.s.rows('SELECT * FROM script_history ORDER BY id DESC')[0]['content'],'第一版')
        aid=self.s.upload('a.txt',b'one','剧本','剧本')
        self.s.upload('a.txt',b'two','剧本','剧本',asset_id=aid,label='V2')
        self.assertEqual([self.s.file(v).read_bytes() for v in self.s.rows('SELECT * FROM versions')],[b'one',b'two'])
    def test_ui_all_pages_and_media(self):
        from PIL import Image
        from streamlit.testing.v1 import AppTest
        b=io.BytesIO(); Image.new('RGB',(16,16),'green').save(b,format='PNG')
        self.s.upload('test.png',b.getvalue(),'测试图片','正面',characters=[1])
        w=io.BytesIO()
        with wave.open(w,'wb') as f: f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000); f.writeframes(b'\0\0'*800)
        self.s.upload('test.wav',w.getvalue(),'测试音频','配音')
        # Valid H.264 fixture; AppTest checks widget creation, not browser playback.
        self.s.upload('test.mp4',Path('tests/fixtures/preview.mp4').read_bytes(),'测试视频','AI 视频')
        os.environ['TCF_DATA_DIR']=str(self.root)
        at=AppTest.from_file('app.py',default_timeout=20).run()
        self.assertFalse(at.exception)
        for name in ['剧集管理','角色资料库','素材管理','制作进度','制作总览']:
            at.sidebar.radio[0].set_value(name).run(); self.assertFalse(at.exception, str(at.exception))
        self.assertTrue(at.get('imgs')); self.assertTrue(at.get('audio')); self.assertTrue(at.get('video'))
        os.environ.pop('TCF_DATA_DIR',None)

if __name__=='__main__': unittest.main(verbosity=2)
