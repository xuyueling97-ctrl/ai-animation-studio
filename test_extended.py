import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from store import Store
from backup import export_backup,restore_backup

class ExtendedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.s=Store(self.root/'original')
    def tearDown(self):
        os.environ.pop('TCF_DATA_DIR',None); self.tmp.cleanup()
    def test_music_selection_search_and_links(self):
        aid=self.s.create_music('OP','示例片头曲')
        for label in ['V2.1','V2.2']:
            self.s.upload('song.wav',label.encode(),'示例片头曲','音乐',asset_id=aid,label=label)
        vs=self.s.rows('SELECT * FROM versions')
        for v in vs: self.s.review(v['id'],'已完成','采用','歌词',True)
        self.assertEqual(sum(v['adopted'] for v in self.s.rows('SELECT * FROM versions')),1)
        self.assertEqual(self.s.rows('SELECT * FROM versions WHERE adopted=1')[0]['label'],'V2.2')
        self.s.link_asset(aid,'主题曲','音乐','温暖,家庭','餐桌',[1,8],[1,5])
        self.assertEqual(len(self.s.assets('温暖','音乐',8,5)),1)
        self.assertEqual(len(self.s.assets(episode=2)),0)
    def test_backup_roundtrip_all_history(self):
        aid=self.s.upload('a.txt',b'first','原稿','剧本',episodes=[1],characters=[2])
        self.s.upload('a.txt',b'second','原稿','剧本',asset_id=aid,label='V2')
        self.s.save_episode(1,'EP01','内容','制作中','备忘')
        archive=export_backup(self.s)
        restored=Store(restore_backup(archive,self.root/'restores'))
        self.assertEqual(restored.rows('SELECT * FROM versions'),self.s.rows('SELECT * FROM versions'))
        self.assertEqual(restored.rows('SELECT * FROM episodes'),self.s.rows('SELECT * FROM episodes'))
        self.assertEqual(len(restored.assets(episode=1,character=2)),1)
        for v in restored.rows('SELECT * FROM versions'): self.assertEqual(restored.file(v).read_bytes(),self.s.file(v).read_bytes())
    def test_reject_tamper_and_traversal(self):
        self.s.upload('a.txt',b'original','文件','其他')
        archive=export_backup(self.s)
        for mode in ['tamper','traversal']:
            b=io.BytesIO()
            with zipfile.ZipFile(archive) as src,zipfile.ZipFile(b,'w') as dst:
                for name in src.namelist(): dst.writestr(name,b'bad' if mode=='tamper' and name.startswith('files/') else src.read(name))
                if mode=='traversal': dst.writestr('../escape.txt',b'evil')
            b.seek(0)
            with self.assertRaises(ValueError): restore_backup(b,self.root/'restores')
        self.assertFalse((self.root/'escape.txt').exists())
        self.assertEqual(self.s.file(self.s.rows('SELECT * FROM versions')[0]).read_bytes(),b'original')
    def test_task_reopen(self):
        tid=self.s.save_task(1,'S1','001','任务','分镜','已完成','工具','')
        self.assertTrue(self.s.rows('SELECT * FROM tasks')[0]['completed'])
        self.s.save_task(1,'S1','001','任务','分镜','需要修改','工具','修改',tid)
        self.assertEqual(self.s.rows('SELECT * FROM tasks')[0]['completed'],'')
    def test_ui_edit_and_extended_pages(self):
        from streamlit.testing.v1 import AppTest
        os.environ['TCF_DATA_DIR']=str(self.s.root)
        aid=self.s.create_music('OP','测试音乐')
        for label in ['V1','V2']: self.s.upload('歌词.txt',label.encode(),'测试音乐','音乐',asset_id=aid,label=label)
        at=AppTest.from_file('app.py',default_timeout=20).run()
        at.sidebar.radio[0].set_value('剧集管理').run()
        next(x for x in at.text_area if x.label=='正式剧本').set_value('界面保存测试')
        next(b for b in at.button if b.label=='保存剧集').click().run()
        self.assertEqual(self.s.rows('SELECT script FROM episodes WHERE id=1')[0]['script'],'界面保存测试')
        for name in ['音乐管理','素材管理','备份与恢复']:
            at.sidebar.radio[0].set_value(name).run(); self.assertFalse(at.exception,str(at.exception))
        next(b for b in at.button if b.label=='生成完整备份').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(list((self.s.root/'backups').glob('*.zip')))

if __name__=='__main__': unittest.main(verbosity=2)
