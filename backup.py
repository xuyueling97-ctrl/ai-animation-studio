"""一致性 SQLite 快照 + 原文件 + SHA-256；恢复只写新目录。"""
import hashlib
import json
import shutil
import sqlite3
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from store import Store

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def export_backup(store):
    folder=store.root/'backups'; folder.mkdir(exist_ok=True)
    uid=uuid.uuid4().hex
    snapshot=folder/(uid+'.sqlite3')
    target=folder/('claude-family-'+uid+'.zip')
    try:
        with store.connect() as src:
            dst=sqlite3.connect(snapshot)
            try: src.backup(dst)
            finally: dst.close()
        db=sqlite3.connect(snapshot)
        try: rows=db.execute('SELECT v.path,v.sha256 FROM versions v JOIN assets a ON a.id=v.asset_id WHERE a.purged_at IS NULL').fetchall()
        finally: db.close()
        manifest={'format':1,'files':{'studio.sqlite3':digest(snapshot)}}
        with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot,'studio.sqlite3')
            for path,sha in rows:
                p=store.file({'path':path})
                if digest(p)!=sha: raise ValueError('原文件校验失败：'+path)
                z.write(p,path); manifest['files'][path]=sha
            z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
        return target
    except Exception:
        # Only remove this operation's newly-created incomplete archive.
        target.unlink(missing_ok=True)
        raise
    finally: snapshot.unlink(missing_ok=True)

def restore_backup(source, parent):
    parent=Path(parent).resolve(); parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>100000: raise ValueError('备份条目重复或过多')
        if 'manifest.json' not in names or 'studio.sqlite3' not in names: raise ValueError('不是本程序的备份')
        total=sum(i.file_size for i in z.infolist())
        if total>20*1024**3: raise ValueError('解压后超过 20 GB，请分项目恢复')
        if total+256*1024**2>shutil.disk_usage(parent).free: raise ValueError('恢复所需磁盘空间不足')
        for name in names:
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or name.endswith('/'):
                raise ValueError('备份包含不安全路径')
            if name not in ['manifest.json','studio.sqlite3'] and not (len(p.parts)==2 and p.parts[0]=='files'):
                raise ValueError('备份包含未知文件')
        if z.getinfo('manifest.json').file_size>20*1024**2: raise ValueError('清单过大')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('format')!=1 or set(manifest['files'])!=set(names)-{'manifest.json'}: raise ValueError('备份清单不匹配')
        target=parent/('restored-'+uuid.uuid4().hex)
        target.mkdir()
        for name,sha in manifest['files'].items():
            dest=target/name; dest.parent.mkdir(exist_ok=True)
            with z.open(name) as src,dest.open('xb') as dst: shutil.copyfileobj(src,dst)
            if digest(dest)!=sha: raise ValueError('文件校验失败，副本未启用：'+name)
    db=sqlite3.connect(target/'studio.sqlite3')
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('数据库完整性校验失败')
        for table in ['episodes','characters','tasks','assets','versions','asset_episodes','asset_characters','script_history','music']:
            db.execute('SELECT * FROM '+table+' LIMIT 1')
        columns={r[1] for r in db.execute('PRAGMA table_info(assets)')}
        sql='SELECT v.path,v.sha256,v.size FROM versions v JOIN assets a ON a.id=v.asset_id'
        if 'purged_at' in columns: sql+=' WHERE a.purged_at IS NULL'
        for path,sha,size in db.execute(sql):
            if path not in manifest['files'] or manifest['files'][path]!=sha or (target/path).stat().st_size!=size: raise ValueError('数据库与素材清单不匹配')
    finally: db.close()
    Store(target)
    return target

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='大项目备份恢复（无需浏览器上传）')
    p.add_argument('action',choices=['export','restore']); p.add_argument('--archive'); p.add_argument('--data-dir')
    a=p.parse_args(); s=Store(a.data_dir)
    if a.action=='export': print(export_backup(s))
    else:
        if not a.archive: p.error('恢复需要 --archive 备份文件路径')
        print(restore_backup(a.archive,s.root/'restores'))
