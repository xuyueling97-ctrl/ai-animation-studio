import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from store import Store
from backup import export_backup, restore_backup


class TrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.s=Store(self.root/'project')
        self.aid=self.s.upload('三视图.txt',b'original','三视图','正面',episodes=[1,2],characters=[1,2])
        self.s.upload('三视图 V2.txt',b'history','三视图','正面',asset_id=self.aid,label='V2')
        self.other=self.s.upload('三视图.txt',b'original','重复上传','正面',characters=[1])
        self.before=self.s.rows('SELECT * FROM versions ORDER BY id')
        self.bytes={v['path']:self.s.file(v).read_bytes() for v in self.before}
        self.old_env=os.environ.get('TCF_DATA_DIR')

    def tearDown(self):
        if self.old_env is None: os.environ.pop('TCF_DATA_DIR',None)
        else: os.environ['TCF_DATA_DIR']=self.old_env
        self.tmp.cleanup()

    def test_soft_delete_restore_references_statistics_and_history(self):
        count=len(self.s.assets())
        refs=self.s.references(self.aid)
        self.s.trash_asset(self.aid)
        self.assertEqual(len(self.s.assets()),count-1)
        self.assertEqual(self.s.assets(episode=2),[])
        self.assertEqual([a['id'] for a in self.s.assets(character=1)],[self.other])
        self.assertEqual(self.s.references(self.aid),refs)
        self.assertEqual(self.s.rows('SELECT * FROM versions ORDER BY id'),self.before)
        self.assertEqual([a['id'] for a in self.s.assets(trashed=True)],[self.aid])
        for path,data in self.bytes.items(): self.assertEqual((self.s.root/path).read_bytes(),data)
        self.s.restore_asset(self.aid)
        self.assertEqual(len(self.s.assets()),count)
        self.assertEqual(len(self.s.assets(episode=2)),1)
        self.assertEqual(self.s.references(self.aid),refs)

    def test_duplicate_purge_is_scoped_and_retains_other_history(self):
        self.assertEqual([x['id'] for x in self.s.duplicates(self.aid)],[self.other])
        # 同名但内容不同不会判为重复。
        different=self.s.upload('三视图.txt',b'unique','不同内容','正面')
        self.assertEqual(self.s.duplicates(different),[])
        with self.assertRaises(ValueError): self.s.permanently_delete_asset(self.aid,confirmed=True)
        self.s.trash_asset(self.aid)
        with self.assertRaises(ValueError): self.s.permanently_delete_asset(self.aid)
        self.s.permanently_delete_asset(self.aid,confirmed=True)
        self.assertEqual(self.s.rows('SELECT * FROM versions WHERE asset_id=?',(self.other,)),[self.before[-1]])
        self.assertEqual(self.s.file(self.before[-1]).read_bytes(),b'original')
        for v in self.before[:-1]: self.assertFalse(self.s.file(v).exists())
        self.assertEqual(self.s.rows('PRAGMA integrity_check')[0]['integrity_check'],'ok')
        self.assertEqual(self.s.rows('PRAGMA foreign_key_check'),[])
        with self.assertRaises(ValueError): self.s.restore_asset(self.aid)
        self.assertFalse(self.s.assets(trashed=True))

    def test_restart_in_new_process_for_all_states(self):
        self.s.trash_asset(self.aid)
        code='''from store import Store
import sys
s=Store(sys.argv[1]); aid=int(sys.argv[2])
assert [a['id'] for a in s.assets(trashed=True)]==[aid]
s.restore_asset(aid)
assert len(s.assets(episode=2))==1
s.trash_asset(aid)
s.permanently_delete_asset(aid,confirmed=True)
'''
        subprocess.run([sys.executable,'-c',code,str(self.s.root),str(self.aid)],check=True)
        fresh=Store(self.s.root)
        self.assertFalse(fresh.assets(trashed=True))
        self.assertFalse(fresh.assets(episode=2))
        self.assertEqual(fresh.file(self.before[-1]).read_bytes(),b'original')

    def test_failed_purge_can_resume_after_restart(self):
        self.s.trash_asset(self.aid)
        original=Path.unlink
        counter=[0]
        def fail_second(path,*args,**kwargs):
            counter[0]+=1
            if counter[0]==2: raise PermissionError('文件占用')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_second):
            with self.assertRaises(PermissionError): self.s.permanently_delete_asset(self.aid,confirmed=True)
        restarted=Store(self.s.root)
        self.assertEqual(len(restarted.rows('SELECT * FROM purge_queue')),1)
        with self.assertRaises(ValueError): restarted.restore_asset(self.aid)
        restarted.permanently_delete_asset(self.aid,confirmed=True)
        self.assertFalse(restarted.rows('SELECT * FROM purge_queue'))
        self.assertEqual(restarted.file(self.before[-1]).read_bytes(),b'original')

    def test_reject_outside_path_and_shared_physical_file(self):
        self.s.trash_asset(self.aid)
        for path in ['studio.sqlite3','files/../studio.sqlite3','files/./'+Path(self.before[-1]['path']).name]:
            self.s.execute('UPDATE versions SET path=? WHERE id=?',(path,self.before[0]['id']))
            with self.assertRaises(ValueError): self.s.permanently_delete_asset(self.aid,confirmed=True)
            self.assertTrue(self.s.db.exists())
        self.assertFalse(self.s.rows('SELECT * FROM purge_queue'))

    def test_backup_includes_trash_excludes_purged_files(self):
        self.s.trash_asset(self.aid)
        restored=Store(restore_backup(export_backup(self.s),self.root/'restores'))
        self.assertEqual([a['id'] for a in restored.assets(trashed=True)],[self.aid])
        restored.restore_asset(self.aid)
        self.assertEqual(restored.file(self.before[0]).read_bytes(),b'original')
        self.s.permanently_delete_asset(self.aid,confirmed=True)
        restored2=Store(restore_backup(export_backup(self.s),self.root/'restores'))
        self.assertFalse(restored2.assets(trashed=True))
        self.assertFalse(restored2.assets(episode=2))
        self.assertEqual(restored2.file(self.before[-1]).read_bytes(),b'original')

    def test_legacy_migration_preserves_rows_files_and_is_idempotent(self):
        # 模拟升级前的数据库，删除新列后再启动，旧记录与原文件应保持原样。
        with self.s.connect() as c:
            c.execute('DROP TABLE purge_queue')
            c.execute('ALTER TABLE assets DROP COLUMN deleted_at')
            c.execute('ALTER TABLE assets DROP COLUMN purged_at')
        migrated=Store(self.s.root)
        Store(self.s.root)
        self.assertEqual(migrated.rows('SELECT * FROM versions ORDER BY id'),self.before)
        self.assertEqual(len(migrated.assets(character=1)),2)
        for path,data in self.bytes.items(): self.assertEqual((migrated.root/path).read_bytes(),data)

    def test_deleted_assets_reject_stale_edits(self):
        self.s.trash_asset(self.aid)
        with self.assertRaises(ValueError): self.s.upload('a.txt',b'x','标题','正面',asset_id=self.aid)
        with self.assertRaises(ValueError): self.s.review(self.before[0]['id'],'已完成','','')
        with self.assertRaises(ValueError): self.s.link_asset(self.aid,'新名','正面','','',[],[])
        self.assertEqual(self.s.rows('SELECT * FROM versions ORDER BY id'),self.before)

    def test_ui_confirm_cancel_delete_restore_permanent(self):
        from streamlit.testing.v1 import AppTest
        os.environ['TCF_DATA_DIR']=str(self.s.root)
        at=AppTest.from_file('app.py',default_timeout=20).run()
        at.sidebar.radio[0].set_value('角色资料库').run()
        at.button(key=f'deletechar{self.aid}').click().run()
        self.assertFalse(at.exception)
        texts=' '.join(t.value for t in at.text)
        for expected in ['三视图.txt','三视图 V2.txt','角色 A','角色 B','EP01','EP02']: self.assertIn(expected,texts)
        at.button(key=f'cancel-delete-{self.aid}').click().run()
        self.assertFalse(self.s.assets(trashed=True))
        at.sidebar.radio[0].set_value('素材管理').run()
        at.button(key=f'deleteall{self.aid}').click().run()
        at.button(key=f'confirm-delete-{self.aid}').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(self.s.assets(trashed=True)),1)
        at.sidebar.radio[0].set_value('回收站').run()
        at.button(key=f'restore-{self.aid}').click().run()
        self.assertFalse(self.s.assets(trashed=True))
        self.s.trash_asset(self.aid)
        at.run()
        at.button(key=f'purge-{self.aid}').click().run()
        self.assertTrue(at.button(key=f'confirm-delete-{self.aid}').disabled)
        at.checkbox(key=f'purge-check-{self.aid}').check().run()
        at.button(key=f'confirm-delete-{self.aid}').click().run()
        self.assertFalse(at.exception)
        self.assertFalse(self.s.assets(trashed=True))
        self.assertEqual(self.s.file(self.before[-1]).read_bytes(),b'original')


if __name__=='__main__': unittest.main(verbosity=2)
