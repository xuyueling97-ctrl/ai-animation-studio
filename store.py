"""本地数据层。原文件只追加；回收站与明确确认的定向清理。"""
import hashlib
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone, timedelta

STATUSES = ['未开始', '制作中', '待审核', '需要修改', '已完成']
CATEGORIES = ['剧本', '分镜', '立绘', '正面', '侧面', '背面', '表情', '服装配饰', '背景', '配音', '音效', 'AI 视频', '后期', '成片', '音乐', '其他']
EXTENSIONS = ['png','jpg','jpeg','webp','gif','mp4','webm','mp3','wav','m4a','ogg','flac','pdf','txt','md','doc','docx','xls','xlsx','csv','ppt','pptx','srt']

def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

def default_root():
    return Path(os.environ.get('TCF_DATA_DIR', '/mnt/workspace/ai-animation-studio-data' if os.name != 'nt' else str(Path(__file__).parent / 'data'))).resolve()

class Store:
    def __init__(self, root=None):
        self.root = Path(root or default_root()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'files').mkdir(exist_ok=True)
        self.db = self.root / 'studio.sqlite3'
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS episodes(id INTEGER PRIMARY KEY, title TEXT NOT NULL, script TEXT DEFAULT '', status TEXT DEFAULT '未开始', notes TEXT DEFAULT '', updated TEXT);
            CREATE TABLE IF NOT EXISTS characters(id INTEGER PRIMARY KEY, name TEXT UNIQUE, description TEXT DEFAULT '', updated TEXT);
            CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, episode_id INTEGER REFERENCES episodes(id), scene TEXT DEFAULT '', shot TEXT DEFAULT '', title TEXT NOT NULL, stage TEXT, status TEXT DEFAULT '未开始', tool TEXT DEFAULT '', notes TEXT DEFAULT '', completed TEXT DEFAULT '', updated TEXT);
            CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT, tags TEXT, scene TEXT, updated TEXT);
            CREATE TABLE IF NOT EXISTS asset_episodes(asset_id INTEGER REFERENCES assets(id), episode_id INTEGER REFERENCES episodes(id), PRIMARY KEY(asset_id,episode_id));
            CREATE TABLE IF NOT EXISTS asset_characters(asset_id INTEGER REFERENCES assets(id), character_id INTEGER REFERENCES characters(id), PRIMARY KEY(asset_id,character_id));
            CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY, asset_id INTEGER REFERENCES assets(id), label TEXT, filename TEXT, path TEXT UNIQUE, sha256 TEXT, size INTEGER, notes TEXT DEFAULT '', status TEXT DEFAULT '未开始', adopted INTEGER DEFAULT 0, created TEXT);
            CREATE TABLE IF NOT EXISTS script_history(id INTEGER PRIMARY KEY, episode_id INTEGER REFERENCES episodes(id), content TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS music(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, lyrics TEXT DEFAULT '', asset_id INTEGER UNIQUE REFERENCES assets(id));
            ''')
            for n in range(1,9):
                c.execute('INSERT OR IGNORE INTO episodes(id,title,updated) VALUES(?,?,?)', (n, f'EP{n:02d}', now()))
            for n,name in enumerate(['角色 A','角色 B','角色 C','角色 D','角色 E'],1):
                c.execute('INSERT OR IGNORE INTO characters(id,name,updated) VALUES(?,?,?)', (n,name,now()))
            if 'lyrics' not in [r[1] for r in c.execute('PRAGMA table_info(versions)')]:
                c.execute("ALTER TABLE versions ADD COLUMN lyrics TEXT DEFAULT ''")
            columns={r[1] for r in c.execute('PRAGMA table_info(assets)')}
            for column in ('deleted_at','purged_at'):
                if column not in columns:
                    c.execute(f'ALTER TABLE assets ADD COLUMN {column} TEXT')
            c.execute('CREATE TABLE IF NOT EXISTS purge_queue(asset_id INTEGER REFERENCES assets(id), path TEXT PRIMARY KEY)')
            for kind,title in [('OP','示例片头曲'),('ED','示例片尾曲')]:
                if not c.execute('SELECT id FROM music WHERE kind=? AND title=?',(kind,title)).fetchone():
                    aid=c.execute("INSERT INTO assets(title,category,tags,scene,updated) VALUES(?,'音乐',?,'',?)",(title,kind,now())).lastrowid
                    c.execute('INSERT INTO music(kind,title,asset_id) VALUES(?,?,?)',(kind,title,aid))

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:
                yield c
        finally:
            c.close()

    def rows(self, sql, args=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql,args)]

    def execute(self, sql, args=()):
        with self.connect() as c:
            return c.execute(sql,args).lastrowid

    def save_episode(self, eid, title, script, status, notes):
        if status not in STATUSES: raise ValueError('状态无效')
        with self.connect() as c:
            old=c.execute('SELECT script FROM episodes WHERE id=?',(eid,)).fetchone()
            if old['script'] != script:
                c.execute('INSERT INTO script_history(episode_id,content,created) VALUES(?,?,?)',(eid,old['script'],now()))
            c.execute('UPDATE episodes SET title=?,script=?,status=?,notes=?,updated=? WHERE id=?',(title,script,status,notes,now(),eid))

    def save_task(self, eid, scene, shot, title, stage, status, tool, notes, tid=None):
        if not title.strip(): raise ValueError('请填写任务名称')
        if status not in STATUSES: raise ValueError('状态无效')
        completed = now() if status=='已完成' else ''
        if tid:
            old=self.rows('SELECT completed FROM tasks WHERE id=?',(tid,))[0]
            if status=='已完成' and old['completed']: completed=old['completed']
        values=(eid,scene,shot,title,stage,status,tool,notes,completed,now())
        if tid:
            self.execute('UPDATE tasks SET episode_id=?,scene=?,shot=?,title=?,stage=?,status=?,tool=?,notes=?,completed=?,updated=? WHERE id=?',values+(tid,))
        else:
            return self.execute('INSERT INTO tasks(episode_id,scene,shot,title,stage,status,tool,notes,completed,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',values)

    def upload(self, filename, data, title, category, tags='', scene='', episodes=(), characters=(), asset_id=None, label='V1', notes=''):
        filename=filename.replace('\\','/').split('/')[-1]
        ext=Path(filename).suffix.lower().lstrip('.')
        if ext not in EXTENSIONS: raise ValueError('不支持此文件格式')
        if not data: raise ValueError('不能上传空文件')
        if len(data)>200*1024*1024: raise ValueError('单个文件最大 200 MB')
        if not title.strip() or not label.strip(): raise ValueError('标题和版本号不能为空')
        if asset_id is not None:
            with self.connect() as c: self._active(c,asset_id)
        rel='files/'+uuid.uuid4().hex+'.'+ext
        # 独占创建，文件名不受上传路径控制，永不覆盖。
        with (self.root / rel).open('xb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        with self.connect() as c:
            if asset_id is not None: self._active(c,asset_id)
            if asset_id is None:
                asset_id=c.execute('INSERT INTO assets(title,category,tags,scene,updated) VALUES(?,?,?,?,?)',(title,category,tags,scene,now())).lastrowid
                c.executemany('INSERT INTO asset_episodes VALUES(?,?)',[(asset_id,e) for e in episodes])
                c.executemany('INSERT INTO asset_characters VALUES(?,?)',[(asset_id,e) for e in characters])
            c.execute('INSERT INTO versions(asset_id,label,filename,path,sha256,size,notes,created) VALUES(?,?,?,?,?,?,?,?)',(asset_id,label,filename,rel,hashlib.sha256(data).hexdigest(),len(data),notes,now()))
            c.execute('UPDATE assets SET updated=? WHERE id=?',(now(),asset_id))
        return asset_id

    def file(self, version):
        path=(self.root / version['path']).resolve()
        if not path.is_relative_to(self.root / 'files'): raise ValueError('素材路径无效')
        return path

    def review(self, vid, status, notes, lyrics, adopted=False):
        if status not in STATUSES: raise ValueError('状态无效')
        with self.connect() as c:
            aid=c.execute('SELECT asset_id FROM versions WHERE id=?',(vid,)).fetchone()[0]
            self._active(c,aid)
            if adopted: c.execute('UPDATE versions SET adopted=0 WHERE asset_id=?',(aid,))
            c.execute('UPDATE versions SET status=?,notes=?,lyrics=?,adopted=? WHERE id=?',(status,notes,lyrics,int(adopted),vid))
            c.execute('UPDATE assets SET updated=? WHERE id=?',(now(),aid))

    def link_asset(self, aid, title, category, tags, scene, episodes, characters):
        if not title.strip(): raise ValueError('素材名称不能为空')
        with self.connect() as c:
            self._active(c,aid)
            c.execute('UPDATE assets SET title=?,category=?,tags=?,scene=?,updated=? WHERE id=?',(title,category,tags,scene,now(),aid))
            c.execute('DELETE FROM asset_episodes WHERE asset_id=?',(aid,))
            c.execute('DELETE FROM asset_characters WHERE asset_id=?',(aid,))
            c.executemany('INSERT INTO asset_episodes VALUES(?,?)',[(aid,e) for e in episodes])
            c.executemany('INSERT INTO asset_characters VALUES(?,?)',[(aid,e) for e in characters])

    def create_music(self, kind, title):
        if not title.strip(): raise ValueError('请填写音乐名称')
        with self.connect() as c:
            aid=c.execute("INSERT INTO assets(title,category,tags,scene,updated) VALUES(?,'音乐',?,'',?)",(title,kind,now())).lastrowid
            c.execute('INSERT INTO music(kind,title,asset_id) VALUES(?,?,?)',(kind,title,aid))
        return aid

    def assets(self, query='', category=None, episode=None, character=None, trashed=False):
        sql='SELECT a.* FROM assets a WHERE a.purged_at IS NULL AND a.deleted_at IS '+('NOT NULL' if trashed else 'NULL')+' AND (a.title LIKE ? OR a.tags LIKE ? OR a.scene LIKE ?)'
        args=['%'+query+'%']*3
        if category: sql+=' AND a.category=?'; args.append(category)
        if episode: sql+=' AND EXISTS(SELECT 1 FROM asset_episodes e WHERE e.asset_id=a.id AND e.episode_id=?)'; args.append(episode)
        if character: sql+=' AND EXISTS(SELECT 1 FROM asset_characters e WHERE e.asset_id=a.id AND e.character_id=?)'; args.append(character)
        return self.rows(sql+' ORDER BY a.updated DESC,a.id DESC',args)

    @staticmethod
    def _active(c, aid):
        row=c.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
        if not row or row['deleted_at'] or row['purged_at']:
            raise ValueError('素材不在使用中，请刷新页面或先从回收站恢复')
        return row

    def references(self, aid):
        return {
            'characters': self.rows('SELECT c.id,c.name FROM characters c JOIN asset_characters r ON r.character_id=c.id WHERE r.asset_id=? ORDER BY c.id',(aid,)),
            'episodes': self.rows('SELECT e.id,e.title FROM episodes e JOIN asset_episodes r ON r.episode_id=e.id WHERE r.asset_id=? ORDER BY e.id',(aid,)),
        }

    def duplicates(self, aid):
        # 比较内容哈希，不按文件名删除或合并，重复上传始终是独立条目。
        return self.rows('''SELECT DISTINCT a.id,a.title,a.deleted_at FROM assets a
            JOIN versions v ON v.asset_id=a.id WHERE a.id!=? AND a.purged_at IS NULL
            AND v.sha256 IN (SELECT sha256 FROM versions WHERE asset_id=?) ORDER BY a.id''',(aid,aid))

    def trash_asset(self, aid):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._active(c,aid)
            c.execute('UPDATE assets SET deleted_at=? WHERE id=?',(now(),aid))

    def restore_asset(self, aid):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
            if not row or not row['deleted_at'] or row['purged_at']:
                raise ValueError('只能恢复回收站中的素材；永久删除不可恢复')
            c.execute('UPDATE assets SET deleted_at=NULL WHERE id=?',(aid,))

    def _purge_path(self, c, aid, path):
        p=self.file({'path':path})
        if p.parent != (self.root/'files').resolve() or p.is_dir():
            raise ValueError('拒绝删除非原始素材文件')
        # 防御异常数据库中的别名路径；不同条目绝不按名称或哈希批量删除。
        for row in c.execute('SELECT path FROM versions WHERE asset_id!=?',(aid,)):
            if (self.root/row['path']).resolve()==p:
                raise ValueError('此物理文件仍被其他素材引用，已拒绝永久删除')
        return p

    def permanently_delete_asset(self, aid, *, confirmed=False):
        if not confirmed: raise ValueError('永久删除需要再次明确确认')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
            if not row or not row['deleted_at']: raise ValueError('请先将素材移入回收站')
            if not row['purged_at']:
                paths=[v['path'] for v in c.execute('SELECT path FROM versions WHERE asset_id=?',(aid,))]
                for path in paths: self._purge_path(c,aid,path)
                c.executemany('INSERT INTO purge_queue(asset_id,path) VALUES(?,?)',[(aid,p) for p in paths])
                c.execute('UPDATE assets SET purged_at=? WHERE id=?',(now(),aid))
        # 持久化清理队列先提交，再逐个定向删除。失败/断电可重试，绝不恢复成可用的残缺素材。
        for job in self.rows('SELECT path FROM purge_queue WHERE asset_id=?',(aid,)):
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                p=self._purge_path(c,aid,job['path'])
                p.unlink(missing_ok=True)
                c.execute('DELETE FROM purge_queue WHERE asset_id=? AND path=?',(aid,job['path']))
        # 保留历史版本元数据与引用作为审计记录；常规查询和备份不包含已清除的文件。
