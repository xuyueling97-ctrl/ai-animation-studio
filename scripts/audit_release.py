"""检查待提交文件及所有可达 Git 历史。只报告路径/规则，不打印敏感值。"""
import hashlib
from pathlib import PurePosixPath
import re
import subprocess

def git(*args): return subprocess.check_output(['git',*args])

patterns={
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'github-token': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
    'api-token': rb'\bsk-[A-Za-z0-9_-]{24,}',
    'aws-key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'credential-assignment': rb'(?i)(?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*[\x22\x27][A-Za-z0-9_+/=-]{16,}[\x22\x27]',
    'personal-windows-path': rb'(?i)\b[A-Z]:[\\/][A-Za-z0-9_\x20-]+[\\/]',
    'private-unix-path': rb'/(?:home|Users)/[A-Za-z0-9_.-]+/',
}
blocked_dirs={'data','demo-data','private','production','uploads','files','backups','restores','.venv','__pycache__','logs'}
blocked_suffixes={'.db','.sqlite','.sqlite3','.log','.pem','.key','.zip','.docx','.pdf','.xlsx'}
media={'.png','.jpg','.jpeg','.wav','.mp3','.mp4','.m4a','.webp','.gif'}
findings=[]; seen=set(); checked=0

def inspect(path,content,scope):
    global checked
    p=PurePosixPath(path)
    if blocked_dirs.intersection(p.parts) or p.suffix in blocked_suffixes or p.name.startswith('.env') or p.name in {'local-settings.json','secrets.toml','.preservation-baseline.json'}:
        findings.append((scope,path,'private-file'))
    if p.suffix in media and path!='tests/fixtures/preview.mp4' and not (path.startswith('docs/screenshots/') and p.suffix=='.png'):
        findings.append((scope,path,'unreviewed-media'))
    fingerprint=hashlib.sha256(content).digest()
    if fingerprint in seen: return
    seen.add(fingerprint); checked+=1
    if p.suffix in media: return # 合成媒体与截图另行进行人工视觉检查
    for label,pattern in patterns.items():
        if re.search(pattern,content): findings.append((scope,path,label))

paths=git('ls-files','-z').decode().strip('\0').split('\0')
if paths==['']: raise SystemExit('没有已暂存或已跟踪文件，拒绝输出空检查通过')
for path in paths: inspect(path,git('show',':'+path),'index')
revs=git('rev-list','--all').decode().split()
for rev in revs:
    for path in git('ls-tree','-rz','--name-only',rev).decode().strip('\0').split('\0'):
        if path: inspect(path,git('show',rev+':'+path),rev[:8])
for scope,path,label in findings: print(f'{scope}: {path}: {label}')
print(f'Checked {len(paths)} indexed paths, {len(revs)} commits, {checked} unique contents; findings={len(findings)}')
raise SystemExit(bool(findings))
