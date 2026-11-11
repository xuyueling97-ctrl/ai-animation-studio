from pathlib import Path
import difflib
import json
import mimetypes
import streamlit as st
from store import Store, STATUSES, CATEGORIES, EXTENSIONS, now

st.set_page_config(page_title='AI 动画制作工作室',page_icon='🏡',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp {background:#fcf8f2;color:#39372f} h1,h2,h3 {color:#455d50}
[data-testid="stSidebar"] {background:#efe9dd} div[data-testid="stMetric"] {background:#f1ecdf;border-radius:14px;padding:18px}
.stButton>button {border-radius:9px} .block-container {padding-top:2rem;max-width:1350px}
[data-testid="stMetric"] * {color:#39372f !important}
[data-testid="stFileUploaderDropzoneInstructions"] {display:none}
[data-testid="stFileUploaderDropzone"]::before {content:'拖入文件，或点击选择';font-size:14px}
[data-testid="stFileUploaderDropzone"] button {font-size:0}
[data-testid="stFileUploaderDropzone"] button::after {content:'选择文件';font-size:14px}
[data-testid="stAppDeployButton"] {display:none}
</style>''',unsafe_allow_html=True)
s=Store()
episodes=s.rows('SELECT * FROM episodes ORDER BY id')
characters=s.rows('SELECT * FROM characters ORDER BY id')
enames={e['id']:e['title'] for e in episodes}
cnames={c['id']:c['name'] for c in characters}

def preview(v, key):
    p=s.file(v)
    if not p.exists(): st.error('原文件缺失，请从备份恢复。'); return
    ext=p.suffix.lower()
    try:
        if ext in ['.png','.jpg','.jpeg','.webp','.gif']: st.image(str(p),width='stretch')
        elif ext in ['.mp3','.wav','.m4a','.ogg','.flac']: st.audio(str(p),format=mimetypes.guess_type(p)[0] or 'audio/mp4')
        elif ext in ['.mp4','.webm']: st.video(str(p),format='video/'+ext[1:])
        elif ext in ['.txt','.md','.csv','.srt']: st.code(p.read_text(encoding='utf-8-sig',errors='replace')[:100000],language=None)
        else: st.caption('此文档可下载后使用本机阅读器查看。')
    except Exception:
        st.warning('文件无法预览，请下载检查格式；原始文件已保留。')
    with p.open('rb') as f: st.download_button('下载原文件',f,file_name=v['filename'],key='dl'+key)
    st.caption(f"{v['label']} · {v['filename']} · {v['size']/1024:.1f} KB · {v['created']}")

def uploader(key, episode=None, character=None):
    with st.expander('＋ 上传新素材'):
        with st.form('upload'+key,clear_on_submit=True):
            title=st.text_input('素材名称')
            cat=st.selectbox('分类',CATEGORIES)
            tags=st.text_input('标签（逗号分隔）')
            scene=st.text_input('场景编号或名称')
            eps=st.multiselect('关联剧集',list(enames),default=[episode] if episode else [],format_func=enames.get)
            chars=st.multiselect('关联角色',list(cnames),default=[character] if character else [],format_func=cnames.get)
            f=st.file_uploader('选择文件（每个不超过 200 MB）',type=EXTENSIONS)
            if st.form_submit_button('保存素材'):
                if f:
                    try: s.upload(f.name,f.getvalue(),title or f.name,cat,tags,scene,eps,chars); st.success('已保存原文件与关联信息')
                    except (ValueError,OSError) as e: st.error(str(e))
                else: st.warning('请先选择文件')

def dismiss_delete():
    st.session_state.pop('pending_delete',None)

@st.dialog('确认删除素材',width='medium',on_dismiss=dismiss_delete)
def delete_dialog(aid, permanent=False):
    rows=s.rows('SELECT * FROM assets WHERE id=?',(aid,))
    if not rows: st.warning('素材不存在，请刷新'); return
    a=rows[0]
    st.text(f"素材 #{aid}：{a['title']}")
    versions=s.rows('SELECT * FROM versions WHERE asset_id=? ORDER BY id',(aid,))
    st.text('涉及文件（全部历史版本）：')
    for v in versions: st.text(f"{v['label']} · {v['filename']}")
    if not versions: st.caption('此条目尚未上传文件。')
    refs=s.references(aid)
    st.text('关联角色：'+('、'.join(r['name'] for r in refs['characters']) or '无'))
    st.text('关联剧集：'+('、'.join(r['title'] for r in refs['episodes']) or '无'))
    if refs['characters'] or refs['episodes']:
        st.warning('这是整条素材的操作，会同时影响以上所有角色和剧集中的显示。若只想取消某处引用，请取消并到“资料与关联”修改。')
    duplicates=s.duplicates(aid)
    if duplicates:
        st.info('检测到内容相同的其他素材（不会被删除）：'+ '；'.join(f"#{d['id']} {d['title']}" for d in duplicates))
    if permanent:
        st.error('永久删除会清除上述全部版本的原文件，无法从回收站恢复。其他素材、剧本历史和已有备份不会被删除。')
        checked=st.checkbox('我确认永久删除此素材及其全部版本原文件',key=f'purge-check-{aid}')
        label='确认永久删除'
    else:
        st.info('移入回收站后从正常列表和统计中隐藏，原文件、历史版本和引用关系均保留，可随时恢复。')
        checked=True
        label='确认移入回收站'
    if st.button('取消',key=f'cancel-delete-{aid}'):
        dismiss_delete(); st.rerun()
    if st.button(label,disabled=not checked,key=f'confirm-delete-{aid}'):
        try:
            if permanent: s.permanently_delete_asset(aid,confirmed=True)
            else: s.trash_asset(aid)
            st.session_state['asset_notice']='已永久删除原文件' if permanent else '素材已移入回收站，可在回收站恢复'
            dismiss_delete()
            st.rerun()
        except (ValueError,OSError) as e:
            st.error(str(e)+'。如文件清理未完成，可到回收站重试。')

def gallery(items,key):
    if not items: st.info('这里还没有素材。上传第一份素材，开始制作吧。')
    for a in items:
        with st.expander(f"{a['title']} · {a['category']} · {a['tags']}"):
            versions=s.rows('SELECT * FROM versions WHERE asset_id=? ORDER BY id DESC',(a['id'],))
            prefix=f"{key}{a['id']}"
            if st.button('删除',key='delete'+prefix): st.session_state['pending_delete']=(a['id'],False)
            duplicates=s.duplicates(a['id'])
            if duplicates:
                st.caption('内容重复：'+'；'.join(f"#{d['id']} {d['title']}"+('（回收站）' if d['deleted_at'] else '') for d in duplicates)+'。每条素材独立保存，请核对引用和版本后再删除。')
            tabs=st.tabs(['预览与审阅','新增版本','版本比较','资料与关联'])
            with tabs[0]:
                if not versions: st.info('尚未上传版本，请到“新增版本”上传。')
                else:
                    v=st.selectbox('查看版本',versions,format_func=lambda x:f"{'★ ' if x['adopted'] else ''}{x['label']} · {x['status']} · {x['filename']}",key=f"v{prefix}")
                    preview(v,f"{prefix}{v['id']}")
                    with st.form('review'+prefix+str(v['id'])):
                        status=st.selectbox('审阅状态',STATUSES,index=STATUSES.index(v['status']))
                        notes=st.text_area('版本说明 / 审阅意见',v['notes'])
                        lyrics=st.text_area('该版本歌词 / 文本说明',v['lyrics'])
                        adopted=st.checkbox('标记为最终采用版本（同一素材仅保留一个）',bool(v['adopted']))
                        if st.form_submit_button('保存审阅'): s.review(v['id'],status,notes,lyrics,adopted); st.rerun()
            with tabs[1]:
                with st.form('version'+prefix,clear_on_submit=True):
                    label=st.text_input('版本名称（如 V2.1）',f'V{len(versions)+1}')
                    note=st.text_area('本版变化')
                    f=st.file_uploader('上传新版本，历史原文件始终保留',type=EXTENSIONS,key='vf'+prefix)
                    if st.form_submit_button('添加版本'):
                        if f:
                            try: s.upload(f.name,f.getvalue(),a['title'],a['category'],asset_id=a['id'],label=label,notes=note); st.rerun()
                            except (ValueError,OSError) as e: st.error(str(e))
                        else: st.warning('请选择文件')
            with tabs[2]:
                if len(versions)<2: st.caption('上传两个版本后即可并排比较。')
                else:
                    left,right=st.columns(2)
                    x=left.selectbox('版本 A',versions,index=1,format_func=lambda v:f"#{v['id']} {v['label']}",key='ca'+prefix)
                    y=right.selectbox('版本 B',versions,format_func=lambda v:f"#{v['id']} {v['label']}",key='cb'+prefix)
                    with left: preview(x,'compareA'+prefix); st.write(x['notes'])
                    with right: preview(y,'compareB'+prefix); st.write(y['notes'])
                    st.caption('原文件内容相同' if x['sha256']==y['sha256'] else '原文件内容不同；音视频支持分别试听/播放，不自动同步。')
                    if x['lyrics'] or y['lyrics']:
                        diff='\n'.join(difflib.unified_diff(x['lyrics'].splitlines(),y['lyrics'].splitlines(),fromfile=x['label'],tofile=y['label'],lineterm=''))
                        st.code(diff or '歌词相同',language='diff')
            with tabs[3]:
                with st.form('links'+prefix):
                    title=st.text_input('素材标题',a['title']); cat=st.selectbox('素材分类',CATEGORIES,index=CATEGORIES.index(a['category']))
                    tags=st.text_input('素材标签',a['tags']); scene=st.text_input('素材场景',a['scene'])
                    eps=st.multiselect('引用剧集',list(enames),default=[r['episode_id'] for r in s.rows('SELECT * FROM asset_episodes WHERE asset_id=?',(a['id'],))],format_func=enames.get)
                    chars=st.multiselect('引用角色',list(cnames),default=[r['character_id'] for r in s.rows('SELECT * FROM asset_characters WHERE asset_id=?',(a['id'],))],format_func=cnames.get)
                    if st.form_submit_button('保存资料与引用'):
                        try: s.link_asset(a['id'],title,cat,tags,scene,eps,chars); st.rerun()
                        except ValueError as e: st.error(str(e))

def task_editor(eid=None):
    rows=s.rows('SELECT * FROM tasks WHERE episode_id=? ORDER BY id DESC',(eid,)) if eid else s.rows('SELECT * FROM tasks ORDER BY id DESC')
    choice=st.selectbox('新建或编辑任务',[None]+[r['id'] for r in rows],format_func=lambda x:'＋ 新建任务' if x is None else next(f"#{r['id']} {r['title']} · {r['status']}" for r in rows if r['id']==x))
    r=next((r for r in rows if r['id']==choice),{})
    with st.form(f'task{eid}{choice}'):
        ep=st.selectbox('所属剧集',[None]+list(enames),index=([None]+list(enames)).index(r.get('episode_id',eid)),format_func=lambda x:enames.get(x,'全季 / OP / ED'))
        title=st.text_input('任务名称',r.get('title',''))
        c1,c2=st.columns(2)
        scene=c1.text_input('场景',r.get('scene','')); shot=c2.text_input('镜头编号',r.get('shot',''))
        stage=st.selectbox('制作环节',CATEGORIES,index=CATEGORIES.index(r.get('stage','分镜')))
        status=st.selectbox('当前状态',STATUSES,index=STATUSES.index(r.get('status','未开始')))
        tool=st.text_input('使用的模型或工具',r.get('tool',''))
        notes=st.text_area('修改意见 / 待办细节',r.get('notes',''))
        if st.form_submit_button('保存任务'):
            try: s.save_task(ep,scene,shot,title,stage,status,tool,notes,choice); st.rerun()
            except ValueError as e: st.error(str(e))
    for t in rows:
        st.write(f"**{t['title']}** · {t['status']} · {t['scene']} / {t['shot']}")
        st.caption(f"工具：{t['tool'] or '未填写'}　完成：{t['completed'] or '尚未完成'}　{t['notes']}")

st.sidebar.title('🏡 动画制作工作室')
st.sidebar.caption('第一季 · 动画制作管理中心')
st.sidebar.caption('v'+(Path(__file__).parent/'VERSION').read_text().strip())
page=st.sidebar.radio('工作台',['制作总览','剧集管理','角色资料库','素材管理','音乐管理','制作进度','回收站','备份与恢复'])
if st.sidebar.checkbox('显示本机数据目录',value=False):
    st.sidebar.caption(f'持久化目录：{s.root}')
st.title(page)
if notice:=st.session_state.pop('asset_notice',None): st.success(notice)
if page=='制作总览':
    st.caption('让每一个镜头，都有家的温度。')
    cols=st.columns(3)
    cols[0].metric('已完成剧集',f"{sum(e['status']=='已完成' for e in episodes)} / 8")
    cols[1].metric('素材条目',len(s.assets()))
    cols[2].metric('待完成任务',s.rows("SELECT count(*) n FROM tasks WHERE status!='已完成'")[0]['n'])
    st.subheader('第一季制作进度')
    for e in episodes:
        tasks=s.rows('SELECT status FROM tasks WHERE episode_id=?',(e['id'],))
        done=sum(t['status']=='已完成' for t in tasks)
        st.write(f"**{e['title']}**　{e['status']}　·　已完成任务 {done}/{len(tasks)}")
        st.progress(done/len(tasks) if tasks else 0)
    st.subheader('当前待办')
    for t in s.rows("SELECT * FROM tasks WHERE status!='已完成' ORDER BY updated DESC LIMIT 10"):
        st.write(f"{enames.get(t['episode_id'],'全季')} · {t['title']} · {t['status']}")
    st.subheader('音乐制作')
    tracks=s.rows('SELECT m.* FROM music m JOIN assets a ON a.id=m.asset_id WHERE a.deleted_at IS NULL AND a.purged_at IS NULL')
    if not tracks: st.caption('尚未建立音乐项目，请在音乐管理中创建 OP《示例片头曲》与 ED《示例片尾曲》。')
    for track in tracks:
        vs=s.rows('SELECT * FROM versions WHERE asset_id=? ORDER BY adopted DESC,id DESC',(track['asset_id'],))
        st.write(f"{track['kind']} · {track['title']} · {vs[0]['status'] if vs else '未开始'}"+(' · ★ 已选定版本' if vs and vs[0]['adopted'] else ''))
    stats=s.rows('SELECT category AS 分类,count(*) AS 数量 FROM assets WHERE deleted_at IS NULL AND purged_at IS NULL GROUP BY category')
    if stats: st.subheader('素材分类统计'); st.dataframe(stats,hide_index=True,width='stretch')
    st.subheader('最近更新的素材'); gallery(s.assets()[:5],'recent')
elif page=='剧集管理':
    eid=st.selectbox('选择剧集',list(enames),format_func=enames.get)
    e=next(e for e in episodes if e['id']==eid)
    tabs=st.tabs(['剧本与状态','场景与分镜 / 制作任务','关联素材'])
    with tabs[0]:
        with st.form(f'ep{eid}'):
            title=st.text_input('剧集名称',e['title']); status=st.selectbox('制作状态',STATUSES,index=STATUSES.index(e['status']))
            script=st.text_area('正式剧本',e['script'],height=400)
            notes=st.text_area('制作说明',e['notes'])
            if st.form_submit_button('保存剧集'): s.save_episode(eid,title,script,status,notes); st.rerun()
        with st.expander('剧本历史（每次修改自动留存）'):
            for h in s.rows('SELECT * FROM script_history WHERE episode_id=? ORDER BY id DESC',(eid,)):
                st.text(h['created']); st.code(h['content'],language=None)
    with tabs[1]: task_editor(eid)
    with tabs[2]: uploader('ep',episode=eid); gallery(s.assets(episode=eid),'ep')
elif page=='角色资料库':
    cid=st.selectbox('选择角色',list(cnames),format_func=cnames.get)
    c=next(c for c in characters if c['id']==cid)
    with st.form(f'char{cid}'):
        desc=st.text_area('角色设定说明',c['description'],height=200)
        if st.form_submit_button('保存设定'): s.execute('UPDATE characters SET description=?,updated=? WHERE id=?',(desc,now(),cid)); st.success('已保存')
    uploader('char',character=cid); gallery(s.assets(character=cid),'char')
elif page=='素材管理':
    uploader('all')
    q=st.text_input('搜索素材名称、标签或场景')
    cols=st.columns(3)
    cat=cols[0].selectbox('分类筛选',[None]+CATEGORIES,format_func=lambda x:x or '全部分类')
    ep=cols[1].selectbox('剧集筛选',[None]+list(enames),format_func=lambda x:enames.get(x,'全部剧集'))
    ch=cols[2].selectbox('角色筛选',[None]+list(cnames),format_func=lambda x:cnames.get(x,'全部角色'))
    items=s.assets(q,cat,ep,ch)
    st.caption(f'共 {len(items)} 项素材')
    page_num=st.number_input('页码（每页 10 项）',min_value=1,max_value=max(1,(len(items)+9)//10),value=1)
    gallery(items[(page_num-1)*10:page_num*10],'all')
elif page=='音乐管理':
    st.caption('每首音乐独立保存版本、歌词、审阅意见和最终选择。')
    with st.form('newmusic',clear_on_submit=True):
        kind=st.selectbox('音乐类型',['OP','ED','背景音乐'])
        title=st.text_input('音乐名称',placeholder='示例片头曲 / 示例片尾曲')
        if st.form_submit_button('建立音乐项目'):
            try: s.create_music(kind,title); st.rerun()
            except ValueError as e: st.error(str(e))
    music=s.rows('SELECT a.* FROM assets a JOIN music m ON m.asset_id=a.id WHERE a.deleted_at IS NULL AND a.purged_at IS NULL ORDER BY a.updated DESC')
    gallery(music,'music')
elif page=='制作进度': task_editor()
elif page=='回收站':
    st.caption('删除的素材暂存在这里；恢复会重新显示原有角色和剧集引用。不会自动清空回收站。')
    items=s.assets(trashed=True)
    st.write(f'回收站共 {len(items)} 项素材')
    for a in items:
        with st.expander(f"#{a['id']} {a['title']} · 删除于 {a['deleted_at']}"):
            for v in s.rows('SELECT * FROM versions WHERE asset_id=? ORDER BY id',(a['id'],)):
                st.text(f"{v['label']} · {v['filename']}")
            refs=s.references(a['id'])
            st.text('原关联角色：'+('、'.join(r['name'] for r in refs['characters']) or '无'))
            st.text('原关联剧集：'+('、'.join(r['title'] for r in refs['episodes']) or '无'))
            if st.button('恢复素材',key=f"restore-{a['id']}"):
                try:
                    s.restore_asset(a['id']); st.session_state['asset_notice']='素材及原有引用已恢复'; st.rerun()
                except ValueError as e: st.error(str(e))
            if st.button('永久删除',key=f"purge-{a['id']}"): st.session_state['pending_delete']=(a['id'],True)
    pending=s.rows('SELECT DISTINCT a.* FROM assets a JOIN purge_queue q ON q.asset_id=a.id')
    if pending:
        st.warning('以下素材已确认永久删除，但因文件占用或服务中断尚未清理完毕，不能恢复。请释放文件占用后重试。')
        for a in pending:
            st.text(f"#{a['id']} {a['title']}")
            if st.button('重试永久删除',key=f"retry-{a['id']}"): st.session_state['pending_delete']=(a['id'],True)
elif page=='备份与恢复':
    from backup import export_backup,restore_backup
    st.info('备份包含数据库与所有历史素材。恢复写入独立副本，不覆盖当前项目。')
    st.write(f'当前数据目录：{s.root}')
    if st.button('生成完整备份'):
        try:
            with st.spinner('正在校验素材并生成备份…'): st.session_state['backup_path']=str(export_backup(s))
            st.success('备份已保存到数据目录的 backups 文件夹')
        except Exception as e: st.error('备份失败：'+str(e))
    bp=st.session_state.get('backup_path')
    if bp and Path(bp).exists():
        st.code(bp,language=None)
        if Path(bp).stat().st_size<=200*1024**2:
            with open(bp,'rb') as f: st.download_button('下载备份到电脑',f,file_name=Path(bp).name)
        else: st.info('备份超过 200 MB，请用 Notebook 文件面板下载此 ZIP，避免浏览器内存不足。')
    restore=st.file_uploader('选择本应用导出的 ZIP（最多 200 MB；更大文件请用命令行）',type=['zip'])
    if st.button('校验并恢复为独立副本',disabled=restore is None):
        try:
            with st.spinner('正在校验和恢复…'): target=restore_backup(restore,s.root/'restores')
            st.session_state['restored_path']=str(target)
            st.success('副本恢复完成，当前项目仍保持原样')
        except Exception as e: st.error('恢复失败，原项目未变更：'+str(e))
    rp=st.session_state.get('restored_path')
    if rp:
        st.code(rp,language=None)
        st.caption('启用后请停止服务并重新运行启动脚本。该选择会被记住，旧目录仍保留。')
        confirm=st.checkbox('我确认下次启动使用以上恢复副本')
        if st.button('设为下次启动的项目',disabled=not confirm):
            (Path(__file__).parent/'local-settings.json').write_text(json.dumps({'data_dir':rp},ensure_ascii=False,indent=2),encoding='utf-8')
            st.success('已设置。请在终端按 Ctrl+C，然后重新运行启动脚本。')

if pending:=st.session_state.get('pending_delete'):
    delete_dialog(*pending)
