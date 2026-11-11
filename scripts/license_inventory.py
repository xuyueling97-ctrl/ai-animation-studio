"""从当前安装环境导出依赖声明和许可证原文；不收集路径、用户名或环境变量。"""
from importlib.metadata import distributions
from pathlib import Path
import json
import re

root=Path(__file__).resolve().parents[1]
target=root/'docs'/'third-party-licenses'
target.mkdir(parents=True,exist_ok=True)
rows=[]
for d in sorted(distributions(),key=lambda x:x.metadata['Name'].lower()):
    m=d.metadata; name=m['Name']
    if name.lower() in {'pip','setuptools','wheel'}: continue
    expr=m.get('License-Expression')
    if not expr:
        expr='; '.join(x.removeprefix('License :: ') for x in m.get_all('Classifier',[]) if x.startswith('License ::'))
    if not expr: expr=(m.get('License','').splitlines() or ['未声明'])[0]
    notices=[]
    for f in d.files or []:
        if re.search(r'(?i)(license|copying|notice)',Path(str(f)).name) and '.dist-info/' in str(f).replace('\\','/'):
            p=d.locate_file(f)
            if p.is_file(): notices.append('=== '+str(f).split('.dist-info/')[-1]+' ===\n'+p.read_text('utf-8',errors='replace'))
    safe=re.sub(r'[^A-Za-z0-9_.-]','_',name)
    if notices: (target/(safe+'.txt')).write_text('\n\n'.join(notices),encoding='utf-8')
    available=(target/(safe+'.txt')).exists()
    rows.append({'name':name,'version':d.version,'declared_license':expr,'notice_file':('third-party-licenses/'+safe+'.txt') if available else None})
(root/'docs'/'dependency-licenses.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['# 依赖许可证清单','','来自 v0.1.0 的 Python 3.11 Windows 干净安装环境。以下为包元数据声明，不等于所有二进制内嵌组件许可证。原文保留于相邻目录。','','| 包 | 版本 | 声明 | 原文 |','| --- | --- | --- | --- |']
for r in rows:
    link=f"[许可证]({r['notice_file']})" if r['notice_file'] else '安装包未附文本，请核对上游'
    lines.append(f"| {r['name']} | {r['version']} | {r['declared_license'].replace('|','/')} | {link} |")
(root/'docs'/'DEPENDENCIES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Dependency packages:',len(rows),'without notice:',[r['name'] for r in rows if not r['notice_file']])
