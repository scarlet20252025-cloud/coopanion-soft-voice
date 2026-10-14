const names = {check_memory:'检查内存',validate_model:'正在校验',prepare_voice:'准备音色',prepare_audio:'启动播放器',check_environment:'检查环境',suspending:'正在休眠',sleeping:'低功耗休眠',ready:'就绪',load_model:'正在加载',synthesizing:'正在合成',playing:'正在播放',waiting_memory:'等待内存',disabled:'已关闭',stopped:'已停止',error:'异常',waiting_user:'待配置',idle:'未启动'};
const node = (tag, text, cls) => { const e=document.createElement(tag); if(text!=null)e.textContent=text;if(cls)e.className=cls;return e; };
const card = (title, cls='') => { const e=node('section',null,'card '+cls);if(title)e.append(node('h3',title));return e; };
const fmt = n => Number.isFinite(n) ? Math.round(n).toLocaleString() : '—';
names.buffering='等待连续播放';
const ms = n => `${fmt(n)} ms`;
function shell(ctx,title,subtitle) {
  const root=node('div',null,'lva'),heading=node('div',null,'panel-heading'),headingText=node('div');headingText.append(node('div','LIGHTWEIGHT LOCAL VOICE ENGINE','eyebrow'),node('h2',title));heading.append(headingText);root.append(heading,node('p',subtitle,'muted'));
  const content=node('div'),notice=node('p',null,'notice');notice.setAttribute('role','status');root.append(content,notice);ctx.root.replaceChildren(root);
  const state={busy:false};
  async function act(method,args=[]) {
    if(state.busy)return;state.busy=true;notice.textContent='正在处理…';
    try {const result=await ctx.invoke(method,args);if(!ctx.signal.aborted)notice.textContent=['enable','recover'].includes(method)?'请求已接受，启动结果见播放状态。':'操作已完成';return result;}
    catch(e){if(!ctx.signal.aborted)notice.textContent=e.message||String(e);throw e;}
    finally{state.busy=false;}
  }
  function button(label,fn,cls='') {
    const b=ctx.ui.button(label,{onClick:async()=>{if(state.busy)return;b.disabled=true;try{await fn();}catch{}finally{if(!ctx.signal.aborted && b.dataset.locked!=='true')b.disabled=false;}}});
    b.classList.add(...cls.split(' ').filter(Boolean));return b;
  }
  function poll(render) {
    let loading=false;
    const refresh=async()=>{if(loading||ctx.signal.aborted)return;loading=true;try{const s=await ctx.invoke('state');if(!ctx.signal.aborted)render(s);}catch(e){if(!ctx.signal.aborted)notice.textContent='读取失败：'+e.message;}finally{loading=false;}};
    void refresh();ctx.interval(refresh,1000);return refresh;
  }
  return {content,notice,state,act,button,poll,heading};
}
function memory(s,c) {
  const m=s.memory;
  if(!c){
    c=card('系统内存与启动保护');
    const field=(tag,key,cls)=>{const e=node(tag,null,cls);e.dataset.memory=key;return e;};
    c.append(field('div','free','stat'),field('p','total','muted'));
    const track=node('div',null,'track');track.append(field('div','fill','fill'));
    for(let i=0;i<3;i++)track.append(field('span','marker'+i,'marker'));c.append(track);
    c.append(field('p','guard','warn'),field('p','measured','memory-measured'),field('p','verdict','muted'));
    const why=node('details',null,'memory-help');why.append(node('summary','为什么仍需要这些内存？'),field('p','explain','muted'),field('p','peak','muted'),node('p','低功耗模式在空闲时释放模型，下一句话仍要重新加载；它不能减少正在合成时的模型需求。启动保护线不是游戏同时运行的性能保证。','muted'));c.append(why);
  }
  const field=key=>c.querySelector('[data-memory="'+key+'"]');
  field('free').textContent=m.freeGiB.toFixed(1)+' GiB';field('total').textContent=`当前空闲 / 系统总量 ${m.totalGiB.toFixed(1)} GiB`;
  field('fill').style.width=`${Math.min(100,m.freeGiB/m.totalGiB*100)}%`;
  [m.minimumGiB,m.recoveryGiB,s.values.lowPowerMode&&s.values.lowMemoryMiB>0?s.values.lowMemoryMiB/1024:null].forEach((n,i)=>{const e=field('marker'+i);e.hidden=n==null;if(n!=null){e.style.left=n/m.totalGiB*100+'%';e.title=n+' GiB';}});
  field('guard').textContent=`加载 / 唤醒前至少 ${m.minimumGiB} GiB 空闲 · 自动恢复需 ${m.recoveryGiB} GiB`;
  const measured=s.workerPid?s.processMemory:null;
  field('measured').textContent=measured?`语音进程专用 ${fmt(measured.privateMiB)} MiB · 驻留 ${fmt(measured.residentMiB)} MiB`:'语音进程占用：尚无当前实测数据';
  field('verdict').textContent=s.workerPid&&s.accepting&&s.phase!=='sleeping'?'模型已加载，启动保护线仅在重新加载时检查。':m.freeGiB<m.minimumGiB?'可用内存不足，保留文字回复。':'达到启动保护线。';
  field('explain').textContent=`这里的 ${m.minimumGiB} GiB 是加载前系统需要剩余的内存，包含模型、推理缓存、加载临时空间和系统余量。它不是模型固定占用。${m.layout==='text-rows'?'已启用文字词表按需加载，避免完整词表常驻核显。':m.layout==='compact'?'已识别固定音色精简模型，当前显示的是精简布局经实测校准后的加载保护线。':'当前运行时使用常规保护线。'}`;
  field('peak').hidden=!measured;if(measured)field('peak').textContent=`本进程历史驻留峰值 ${fmt(measured.peakResidentMiB)} MiB。进程计数未单列核显共享内存，不能与系统空闲量直接相减。`;
  return c;
}
function metric(title,value,hint){const c=card(title);c.append(node('div',value,'stat'),node('p',hint,'muted'));return c;}
function chart(history) {
  const c=card('最近 30 次语音 · 首次出声延迟');
  if(!history.length){c.append(node('div','尚无数据。完成一次试听或聊天朗读后显示真实曲线。','empty'));return c;}
  const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 760 235');svg.setAttribute('role','img');svg.setAttribute('aria-label','首次音频设备回调及含排队延迟曲线，单位毫秒');
  function item(tag,attrs,text){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(text)e.textContent=text;svg.append(e);return e;}
  const max=Math.max(1000,...history.flatMap(x=>[x.firstDeviceCallbackMs,x.totalStartMs]).filter(Number.isFinite))*1.15;
  for(let i=0;i<4;i++){const y=15+i*60;item('line',{x1:55,y1:y,x2:742,y2:y,stroke:'var(--lv-border,#384052)' });item('text',{x:2,y:y+5,fill:'var(--lv-muted,#aeb9d0)' ,'font-size':12},String(Math.round(max*(1-i/3))));}
  for(const [key,color] of [['firstDeviceCallbackMs','#9faeff'],['totalStartMs','#71d9b1']]){
    const pts=history.flatMap((h,i)=>Number.isFinite(h[key])?[[55+i*(687/Math.max(1,history.length-1)),195-Math.min(max,h[key])/max*180,i]]:[]);
    item('polyline',{points:pts.map(([x,y])=>[x,y].join(',')).join(' '),fill:'none',stroke:color,'stroke-width':2.5});
    pts.forEach(([x,y,i])=>{const p=item('circle',{cx:x,cy:y,r:3,fill:color});const t=document.createElementNS(ns,'title');t.textContent=`第 ${i+1} 次：${ms(history[i][key])}`;p.append(t);});
  }
  item('text',{x:55,y:224,fill:'var(--lv-muted,#aeb9d0)' ,'font-size':12},'较早');item('text',{x:710,y:224,fill:'var(--lv-muted,#aeb9d0)' ,'font-size':12},'最近');c.append(svg);
  c.append(node('p','● 紫色：首次设备回调　● 绿色：含排队总延迟','legend'),node('p','毫秒，越低越快。计时从语音任务接收开始，不含聊天模型思考或系统扬声器的额外延迟；切换音色时清空旧曲线。','chart-caption'));return c;
}
const controls={mount(ctx){
  const u=shell(ctx,'语音控制','日常开关与播放控制。音色管理、诊断图表和高级设置分别位于其他页签。');
  const updateMenu=node('details',null,'update-menu'),updateSummary=node('summary','热更新'),updateBox=node('div',null,'update-box'),updateVersion=node('p'),updateDetail=node('p','按需检查 GitHub 更新，不依赖扩展市场。','muted'),updateProgress=node('progress');updateProgress.max=100;updateProgress.hidden=true;updateProgress.setAttribute('aria-label','当前更新阶段进度');
  const checkUpdate=u.button('检查更新',async()=>{await u.act('checkUpdate');await refresh();});
  const applyUpdate=u.button('下载并热更新',async()=>{await u.act('applyUpdate');await refresh();},'primary');applyUpdate.disabled=true;applyUpdate.hidden=true;
  let restartPrompted=ctx.memo?.get('restartPromptVersion','')||'';
  async function offerRestart(){
    if(!ctx.ui.confirm){u.notice.textContent='扩展更新待重启；请正常退出并重新打开桌宠。';return;}
    const yes=await ctx.ui.confirm({title:'更新完成，需要重启桌宠',body:'确认后保存并重启，会中断当前语音和桌宠对话。取消或稍后将继续运行当前版本，更新文件保留。'});
    if(ctx.signal.aborted)return;
    if(yes)await u.act('restartDesktop',[true]);else u.notice.textContent='已保留待重启状态，方便时点击“重启桌宠”。';
  }
  const restartButton=u.button('重启桌宠',offerRestart);restartButton.hidden=true;
  const updateLink=node('a','GitHub 发布页 ↗');updateLink.href='https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/latest';updateLink.target='_blank';updateLink.rel='noopener noreferrer';
  const autoCheck=node('input');autoCheck.type='checkbox';
  const checkLabel=node('label',' 自动检查（每 24 小时）');checkLabel.prepend(autoCheck);checkLabel.style.display='block';
  autoCheck.setAttribute('aria-label','自动检查更新');
  autoCheck.addEventListener('change',()=>{void u.act('save',[{autoCheckUpdates:autoCheck.checked}]).catch(()=>{});},{signal:ctx.signal});
  updateBox.append(updateVersion,updateDetail,updateProgress,checkUpdate,applyUpdate,restartButton,checkLabel,node('p','只检查并提示新版；点击更新后自动下载、校验、备份与安装，失败回滚。需要重启时询问，确认即重启，稍后保留待重启提示。','muted'),updateLink);updateMenu.append(updateSummary,updateBox);u.heading.append(updateMenu);
  const deploy=card('模型部署检测','deployment'),deployBadge=node('span','正在检测…','badge'),deployDetail=node('p'),deployHint=node('p','此功能需要安装 Qwen3-TTS 0.6B Base Q8 模型、音频解码模型及本地推理引擎才能发声。','muted'),deployLink=node('a','GitHub 一键部署 / 下载完整安装包 ↗','deploy-link');
  deploy.setAttribute('role','status');deploy.setAttribute('aria-live','polite');deployLink.href='https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/latest';deployLink.target='_blank';deployLink.rel='noopener noreferrer';deploy.append(deployBadge,deployDetail,deployHint,deployLink);
  const hero=card('播放状态','hero'),state=node('span',null,'badge'),detail=node('p',null,'muted');hero.append(state,detail);
  const feedback=node('div',null,'startup-feedback'),stageText=node('p'),progress=node('div',null,'startup-progress');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');progress.setAttribute('role','progressbar');progress.setAttribute('aria-label','语音启动进行中');feedback.hidden=true;feedback.append(stageText,progress);hero.append(feedback);
  let pendingStartAt=0,requestedEnabled=null,stopPending=false,revision=0,latest=null,memoryCard=null;
  const actionButtons={},actions=node('div',null,'actions');let refresh=()=>{};
  const startButton=node('button','读取状态…','primary');startButton.type='button';startButton.disabled=true;
  startButton.addEventListener('click',async()=>{
    if(stopPending||latest?.updating||latest?.switchingDevice)return;
    const want=!(requestedEnabled??latest?.speechEnabled??false),seq=++revision;requestedEnabled=want;
    feedback.hidden=false;progress.hidden=false;feedback.classList.remove('bad','good');
    if(want){pendingStartAt=Date.now();stageText.textContent='正在请求启动语音…';startButton.textContent='加载中 · 点击取消';}
    else{stopPending=true;stageText.textContent='正在停止并释放语音模型…';startButton.textContent='正在停止…';startButton.disabled=true;}
    try{await ctx.invoke(want?'enable':'disable');}
    catch(e){stageText.textContent='操作失败：'+e.message;feedback.classList.add('bad');progress.hidden=true;u.notice.textContent=e.message;}
    finally{if(seq===revision){requestedEnabled=null;pendingStartAt=0;stopPending=false;}await refresh();}
    },{signal:ctx.signal});actions.append(startButton);
  for(const [label,method]of [['试听一句','test'],['重试恢复','recover'],['清空待说队列','clearQueue']]){
    const b=u.button(label,async()=>{await u.act(method);await refresh();});actionButtons[method]=b;if(method==="recover")b.hidden=true;if(method==="test")b.disabled=true;actions.append(b);
  }hero.append(actions);
  const volume=card('播放音量'),range=node('input'),output=node('strong');range.type='range';range.min=0;range.max=100;range.step=1;range.setAttribute('aria-label','播放音量');range.addEventListener('input',()=>output.textContent=range.value+'%',{signal:ctx.signal});range.addEventListener('change',()=>{void u.act('save',[{volume:Number(range.value)}]).catch(()=>{});},{signal:ctx.signal});
  volume.append(output,range,node('p','0% 跳过后续合成并保留模型。当前播放可点击上方“停止语音”中断并释放模型。','muted'));
  let lowPower=false;
  const power=node('div',null,'power-inline'),powerHint=node('span',null,'muted');
  const powerButton=u.button('低功耗模式',async()=>{await u.act('save',[{lowPowerMode:!lowPower}]);await refresh();},'power-switch');powerButton.setAttribute('role','switch');powerButton.setAttribute('aria-checked','false');powerButton.setAttribute('aria-label','低功耗模式');
  const powerHelp=node('details',null,'power-help');powerHelp.append(node('summary','说明'),node('p','开启后按配置的空闲时间或内存阈值释放模型，不打断播放；下一句话自动唤醒，首句多一段加载等待。关闭后保持常驻。休眠时间、阈值和是否保留进程在“配置”页调整。','muted'));
  power.append(powerButton,powerHint,powerHelp);hero.append(power);
  let syncBubbles=true;
  const syncOption=card(null,'feature-option'),syncCopy=node('div',null,'feature-copy'),syncHint=node('p',null,'muted');
  syncOption.setAttribute('aria-label','独立功能：气泡同步');syncHint.id='lva-bubble-sync-hint';syncHint.setAttribute('role','status');
  syncCopy.append(node('strong','气泡同步'),syncHint);
  const syncButton=u.button('读取状态…',async()=>{await u.act('save',[{syncBubbles:!syncBubbles}]);await refresh();},'power-switch');syncButton.setAttribute('role','switch');syncButton.setAttribute('aria-label','气泡同步');syncButton.setAttribute('aria-describedby',syncHint.id);syncButton.disabled=true;
  syncButton.title='首次默认开启，语音就绪后生效。记住你的选择；关闭此功能不会停止语音。';
  syncOption.append(syncCopy,syncButton);
  const playbackCard=card('播放策略'),playbackSelect=node('select'),playbackHint=node('p',null,'muted');playbackSelect.setAttribute('aria-label','播放策略');
  for(const[value,label]of [['auto','自动（按生成速度判断）'],['buffered','优先连续（整句生成后播）'],['stream','优先开口（可能断续）']]){const option=node('option',label);option.value=value;playbackSelect.append(option);}
  playbackSelect.addEventListener('change',()=>{void u.act('save',[{playbackMode:playbackSelect.value}]).catch(()=>{});},{signal:ctx.signal});playbackCard.append(playbackSelect,playbackHint);
  const deviceCard=card('推理设备'),deviceSelect=node('select'),deviceDetail=node('p',null,'muted'),automatic=node('option','默认安装设备（通常为核显）');automatic.value='';deviceSelect.append(automatic);deviceSelect.setAttribute('aria-label','Vulkan 推理设备');let deviceLoaded=false;
  const scanDevices=u.button('检测设备',async()=>{const result=await u.act('devices');if(!result)return;const chosen=latest?.values.deviceName||'';deviceSelect.replaceChildren(automatic);for(const d of result.devices){const option=node('option',`${d.kind==='discrete'?'独显':'核显'} · ${d.name}`);option.value=d.name;deviceSelect.append(option);}deviceSelect.value=chosen;deviceLoaded=true;await refresh();});
  const switchDevice=u.button('切换设备',async()=>{await u.act('selectDevice',[deviceSelect.value]);await refresh();});switchDevice.disabled=true;deviceCard.append(deviceDetail,deviceSelect,scanDevices,switchDevice,node('p','空闲时重载语音模型，不重启桌宠。独显与游戏共享显存；选择失败会恢复原设备配置。','muted'));
  const tuning=node('div',null,'grid');tuning.append(playbackCard,deviceCard);
  const grid=node('div',null,'grid'),mem=node('div');grid.append(volume,mem);const top=node('div',null,'control-top-grid');top.append(hero,deploy);u.content.append(top,tuning,syncOption,grid);
  refresh=u.poll(s=>{
    const updates=s.updates||{},stages={idle:'尚未检查',checking:'正在检查',available:'有新版本',current:'已是最新',downloading:'正在下载',validating:'正在校验',backing_up:'正在备份',installing:'正在安装',restoring:'正在恢复旧版本',verifying:'正在验证',installed:'语音引擎已更新',rolled_back:'已回滚',error:'更新失败'};
    updateVersion.textContent=`引擎 ${s.engineVersion||updates.currentVersion||'待检测'} · 扩展 ${updates.loadedWorldVersion||'0.4.0'}`;
    let percentage=null;if(updates.total>0&&['downloading','backing_up','installing','restoring'].includes(updates.stage))percentage=Math.round((updates.stage==='downloading'?updates.received:updates.completed)/updates.total*100);
    updateSummary.textContent=updates.busy?'更新中…':updates.available&&updates.stage!=='installed'?'热更新 · 有新版':'热更新';
    updateDetail.textContent=(stages[updates.stage]||'尚未检查')+(percentage!=null?' '+percentage+'%':'')+(updates.stage==='available'?' v'+updates.release?.version:'')+(updates.error?'：'+updates.error:'')+(updates.supported===false?'；当前为源码安装，请用 GitHub 完整包升级':'')+(updates.requiresRestart?'；World 扩展更新待桌宠重启生效':'');
    updateProgress.hidden=!updates.busy;if(percentage==null)updateProgress.removeAttribute('value');else updateProgress.value=percentage;
    autoCheck.checked=!!(s.values.autoCheckUpdates??true);
    restartButton.hidden=!updates.requiresRestart;restartButton.disabled=!!updates.busy;restartButton.dataset.locked=String(restartButton.disabled);
    const pendingVersion=updates.currentVersion||updates.version||updates.release?.version||'pending';
    if(updates.requiresRestart&&!updates.busy&&!u.state.busy&&restartPrompted!==pendingVersion){restartPrompted=pendingVersion;ctx.memo?.set('restartPromptVersion',pendingVersion);void offerRestart().catch(e=>{u.notice.textContent=e.message;});}
    checkUpdate.disabled=!!updates.busy;checkUpdate.dataset.locked=String(checkUpdate.disabled);applyUpdate.hidden=!updates.available||updates.stage==='installed';applyUpdate.disabled=!!updates.busy||!updates.available||updates.supported!==true||s.speaking||s.queueLength>0||s.initializing;applyUpdate.dataset.locked=String(applyUpdate.disabled);
    if(document.activeElement!==playbackSelect)playbackSelect.value=s.values.playbackMode||'auto';
    const lastMode=s.lastSpeech?.effectivePlaybackMode;playbackHint.textContent='自动模式在生成偏慢或测量不足时先生成整句，等待更久但避免合成欠载；快设备保留流式。'+(lastMode?' 最近实际：'+(lastMode==='buffered'?'整句连续播放':'流式播放'):'');
    deviceDetail.textContent=s.switchingDevice?'正在切换并加载模型…':'选择：'+(s.values.deviceName||'默认安装设备')+(s.workerPid&&s.deviceName?' · 实际：'+s.deviceName:'');switchDevice.disabled=!deviceLoaded||s.speaking||s.queueLength>0||s.initializing||s.switchingDevice||s.updating;switchDevice.dataset.locked=String(switchDevice.disabled);deviceSelect.disabled=s.switchingDevice||s.updating;
    const d=s.deployment||{state:'unknown',detail:'尚未取得模型部署状态'};
    const labels={missing:'未部署 · 无法使用语音',error:'模型连接失败',waiting_memory:'已部署 · 等待内存',connected:'已连接 · 可以发声',loading:'已部署 · 正在连接',sleeping:'已部署 · 低功耗休眠',installed:'已部署 · 尚未连接',unknown:'正在检测模型'};
    deploy.dataset.state=d.state;deployBadge.textContent=labels[d.state]||labels.unknown;deployDetail.textContent=d.detail||'';deploy.classList.toggle('attention',['missing','error','unknown'].includes(d.state));deployLink.classList.toggle('highlight',['missing','error','installed'].includes(d.state));deployLink.textContent=['missing','error'].includes(d.state)?'安装模型 / 部署教程 ↗':'GitHub 部署教程 ↗';deployHint.textContent=d.installed?'Qwen3-TTS 0.6B · Q8 · Vulkan GPU':'需要安装 Qwen3-TTS 0.6B Q8 及本地引擎才能发声。';
    latest=s;const enabled=requestedEnabled??s.speechEnabled;
    syncBubbles=!!s.values.syncBubbles;syncButton.textContent=syncBubbles?'已开启':'已关闭';syncButton.setAttribute('aria-checked',String(syncBubbles));syncButton.disabled=false;
    syncHint.textContent={disabled:'按原版文字计时切换，语音照常播放',voice_off:'已预选 · 开启语音后自动生效（首次默认开启）',muted:'已预选 · 当前静音，气泡按文字计时切换',unavailable:'缺少显示适配桥，请按安装教程接入后重启桌宠',waiting_voice:'已预选 · 等待语音准备完成后自动生效',active:'正在生效 · 等本段语音读完，再切换下一气泡'}[s.bubbleSync?.phase]||'正在读取同步状态';
    const starting=!!(pendingStartAt||enabled&&(s.initializing||s.toggling)),stopping=!!(stopPending||s.toggling&&!s.speechEnabled),ready=s.speechEnabled&&s.accepting&&!['waiting_memory','error','waiting_user','disabled'].includes(s.phase);
    startButton.disabled=stopping;startButton.textContent=stopping?'正在停止…':starting?'加载中 · 点击取消':enabled?'停止语音':'开启语音';startButton.title=starting?'点击取消加载并释放模型':enabled?'停止播放并释放语音模型':'开启本地语音';hero.setAttribute('aria-busy',String(starting||stopping));
    for(const [key,disabled] of [['test',!ready||starting||stopping||s.speaking||s.queueLength>0||s.values.volume===0],['recover',starting||stopping]]){actionButtons[key].disabled=!!disabled;actionButtons[key].dataset.locked=String(!!disabled);}
    actionButtons.recover.hidden=stopping||!['error','waiting_memory','waiting_user'].includes(s.phase);
    feedback.classList.toggle('bad',!stopping&&['error','waiting_memory','waiting_user'].includes(s.phase));feedback.classList.toggle('good',s.phase==='ready'&&ready);feedback.hidden=!starting&&!stopping&&!ready&&!['error','waiting_memory','waiting_user'].includes(s.phase);progress.hidden=!starting&&!stopping;progress.setAttribute('aria-label',stopping?'语音正在停止':'语音启动进行中');
    if(starting){const elapsed=Math.max(0,Math.floor((Date.now()-(s.loadingSince||pendingStartAt||Date.now()))/1000));stageText.textContent=`${s.detail||'正在启动语音'} · 已等待 ${elapsed} 秒`;progress.setAttribute('aria-valuetext',stageText.textContent);}
    else stageText.textContent=stopping?'正在停止并释放语音模型…':s.phase==='ready'&&ready?`语音已开启，可以发声${s.loadMs!=null?' · 最近加载 '+(s.loadMs/1000).toFixed(1)+' 秒':''}`:s.phase==='sleeping'?'已开启，正在低功耗休眠；下一句话自动唤醒。':s.detail||'已关闭';
    lowPower=!!s.values.lowPowerMode;powerButton.setAttribute('aria-checked',String(lowPower));powerButton.textContent=`低功耗模式 ${lowPower?'开':'关'}`;powerHint.textContent=lowPower?'空闲休眠 · 下次说话自动唤醒':'模型保持常驻';state.textContent=stopping?'正在停止':starting?'正在开启':names[s.phase]||s.phase;detail.textContent=`${s.voices.find(v=>v.key===s.selectedVoice)?.name||s.selectedVoice} · 排队 ${s.queueLength} 句 · ${s.speechEnabled?'已开启':'已关闭'}`;if(document.activeElement!==range){range.value=s.values.volume;output.textContent=s.values.volume+'%';}memoryCard=memory(s,memoryCard);if(!mem.firstChild)mem.append(memoryCard);
  });
}};
const status={mount(ctx){
  let memoryCard=null;
  const u=shell(ctx,'运行状态','真实语音指标与内存门槛。没有样本时不估算性能，不填充演示数据。');
  u.poll(s=>{
    const h=s.history||[],last=h.at(-1),grid=node('div',null,'grid');
    const ratios=h.filter(x=>x.seconds>0&&Number.isFinite(x.totalSynthesisMs)).map(x=>x.totalSynthesisMs/(x.seconds*1000));
    grid.append(metric('首次出声',last?ms(last.firstDeviceCallbackMs):'—','最近一条：音频设备首次回调'),metric('平均合成耗时 / 音频时长',ratios.length?(ratios.reduce((a,b)=>a+b,0)/ratios.length).toFixed(2)+'×':'—','低于 1× 表示平均生成快于音频时长'),metric('断流 / 设备欠载',last?`${fmt(last.underrunMs)} ms / ${fmt(last.deviceUnderflows)} 次`:'—','最近一条：连续播放监测'));
    const info=card('引擎与诊断'),err=node('p',s.workerError||s.detail||'无异常',s.workerError?'error':'muted');
    const policy=s.nativeSettings?.memoryPolicy==='device-local'?'设备本地显存':s.nativeSettings?.memoryPolicy==='backend-default'?'核显/后端默认分配':'尚未检测';
    const mode={auto:'自动',stream:'流式',buffered:'整句缓冲'};
    info.append(node('p',s.engine),node('p',`实际 GPU：${s.deviceName||'尚未连接'} · 引擎 ${s.engineVersion||'—'}`),node('p',`内存路径：${policy} · 24 kHz 单声道`,'muted'),node('p',`最近加载 / 唤醒 ${ms(s.loadMs)} · 丢弃旧句 ${fmt(s.dropped)}`,'muted'),node('p',last?`最近策略：${mode[last.requestedPlaybackMode]||'—'} → ${mode[last.effectivePlaybackMode]||'—'}；${last.smoothPlayback===true?'播放未检测到欠载':last.smoothPlayback===false?'存在播放欠载':'连续性尚无数据'}。${last.realTimeFactor>=1?'合成慢于实时，不能视为低延迟验收通过。':''}`:'还没有真实播放样本，无法判定性能。','muted'),err);
    const lower=node('div',null,'grid');memoryCard=memory(s,memoryCard);lower.append(memoryCard,info);u.content.replaceChildren(grid,chart(h),lower);
  });
}};
const config={mount(ctx){
  const u=shell(ctx,'配置','管理排队与资源恢复策略。保存后生效；不会改变参考音色或采样参数。');
  const form=card('消息与资源策略'),inputs={};
  for(const[key,title,desc,min,max]of [['lowPowerMode','低功耗模式','开启后按下方条件自动休眠，下一句话自动唤醒；关闭后模型常驻。加载内存保护始终有效。'],['keepWorker','休眠时保留工作进程','保留进程和播放器，释放模型；关闭则深度休眠并完全退出进程。低占用模式仍占数百 MiB，不保证唤醒更快。'],['lowMemoryMiB','内存保护阈值（MiB）','0 关闭。空闲内存低于此值且没有播放/排队时提前休眠；建议 1536。加载要求以“内存与启动要求”卡片为准。',0,4096],['idleUnloadSec','自动休眠（秒）','0 关闭空闲计时；建议 300。空闲到时休眠，不打断播放，下一句话自动唤醒。',0,3600],['maxQueue','队列容量','达到上限时丢弃最旧的待说句，保留最近内容。',1,12],['maxAgeSec','待说有效期（秒）','开始合成前检查；超过时限不再补读。',5,180],['pollMs','消息检查间隔（毫秒）','默认 180。调低只影响取消息速度，不能加快模型计算。',80,2000],['autoRecover','内存恢复后自动重试','只在内存不足导致的加载失败后生效；达到自动恢复门槛后，每分钟最多一次。']]){
    const row=node('label',null,'row'),text=node('span',title),input=node('input');text.append(node('small',desc));input.type=min==null?'checkbox':'number';if(min!=null){input.min=min;input.max=max;input.step=1;}input.setAttribute('aria-label',title);row.append(text,input);form.append(row);inputs[key]=input;
  }
  function powerFields(){for(const k of ['keepWorker','lowMemoryMiB','idleUnloadSec']) inputs[k].disabled=!inputs.lowPowerMode.checked;}
  inputs.lowPowerMode.addEventListener('change',powerFields,{signal:ctx.signal});
  const a=node('div',null,'actions');a.append(u.button('保存配置',async()=>{const values=Object.fromEntries(Object.entries(inputs).map(([k,i])=>[k,i.type==='checkbox'?i.checked:Number(i.value)]));await u.act('save',[values]);},'primary'));form.append(a);
  const fixed=card('音色稳定性');fixed.append(node('p','原速 1.0 · 种子 44 · 固定参考音色特征'),node('p','这些参数不作为普通设置开放，避免出现保存无效、意外变声或不完整输出。音色切换请到“音色库”。','muted'));
  u.content.append(form,fixed);void ctx.invoke('state').then(s=>{if(ctx.signal.aborted)return;for(const[k,i]of Object.entries(inputs)){if(i.type==='checkbox')i.checked=s.values[k];else i.value=s.values[k];}powerFields();}).catch(e=>u.notice.textContent=e.message);
}};
const voices={mount(ctx){
  const u=shell(ctx,'音色库','音色作为独立 ZIP 数据包导入。导入不会自动替换当前声音，选择后重新加载生效。');
  const catalog=node('div',null,'grid'),upload=card('导入音色包'),file=node('input');file.type='file';file.accept='.zip,application/zip';file.setAttribute('aria-label','选择 ZIP 音色包');
  upload.append(node('p','ZIP 根目录：voice.json + reference.wav。最多 2 MiB；参考音频为 3–15 秒、24 kHz、单声道 PCM16。','muted'),file);
  let refresh=()=>{};
  upload.append(u.button('校验并导入 ZIP',async()=>{
    const f=file.files?.[0];if(!f){u.notice.textContent='请先选择 ZIP 文件';return;}if(f.size>2*1024*1024){u.notice.textContent='文件超过 2 MiB';return;}
    const base64=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(new Error('文件读取失败'));r.readAsDataURL(f);});
    const result=await u.act('import',[base64]);if(result)u.notice.textContent=`已导入“${result.name}”。选择该音色后才会生效。`;file.value='';await refresh();
  },'primary'));
  const help=card('制作与分享'),link=node('a','音色制作教程 ↗');link.href='https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/VOICE_PACKS.md';link.target='_blank';link.rel='noopener noreferrer';help.append(link,node('p','教程包含音频准备、转写、打包命令、试听检查与常见错误。ZIP 只包含音频和说明，不包含模型或可执行脚本。','muted'));
  u.content.append(catalog,upload,help);
  refresh=u.poll(s=>{catalog.replaceChildren(...s.voices.map(v=>{const c=card(v.name,'voice '+(v.key===s.selectedVoice?'selected':!v.available?'pending':''));c.append(node('span',v.key===s.selectedVoice?'使用中':v.available?'可用':'待更新','badge'),node('p',v.description,'muted'));if(v.available&&v.key!==s.selectedVoice)c.append(u.button('使用此音色',async()=>{await u.act('select',[v.key]);await refresh();}));if(!v.available)c.append(node('p','后续更新将提供更多默认音色。','muted'));return c;}));});
}};
export default {panels:{controls,status,config,voices}};
