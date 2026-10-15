const names = {check_memory:'检查内存',validate_model:'正在校验',prepare_voice:'准备音色',prepare_audio:'启动播放器',check_environment:'检查环境',suspending:'正在休眠',sleeping:'低功耗休眠',ready:'就绪',load_model:'正在加载',synthesizing:'正在合成',playing:'正在播放',waiting_memory:'等待内存',disabled:'已关闭',stopped:'已停止',error:'异常',waiting_user:'待配置',idle:'未启动'};
const node = (tag, text, cls) => { const e=document.createElement(tag); if(text!=null)e.textContent=text;if(cls)e.className=cls;return e; };
const card = (title, cls='') => { const e=node('section',null,'card '+cls);if(title)e.append(node('h3',title));return e; };
const fmt = n => Number.isFinite(n) ? Math.round(n).toLocaleString() : '—';
names.buffering='等待连续播放';
const ms = n => `${fmt(n)} ms`;
function fieldFeedback(){const e=node('p',null,'field-feedback');e.setAttribute('role','status');e.setAttribute('aria-live','polite');return e;}
function savedMessage(values={}){
  const labels={volume:'音量',playbackMode:'播放策略',lowPowerMode:'低功耗模式',syncBubbles:'气泡同步',autoCheckUpdates:'自动检查更新',autoDiagnostics:'自动保存诊断',autoSubmitIssues:'自动提交 Issue',cacheRepeated:'重复语句缓存'};
  const modes={auto:'自动',buffered:'优先连续',stream:'优先开口'};
  const pairs=Object.entries(values);
  return pairs.length===1?'已保存：'+(labels[pairs[0][0]]||'设置')+' · '+(typeof pairs[0][1]==='boolean'?(pairs[0][1]?'已开启':'已关闭'):pairs[0][0]==='volume'?pairs[0][1]+'%':modes[pairs[0][1]]||pairs[0][1]):'配置已保存并生效';
}
async function saveField(u,feedback,values,refresh){
  feedback.classList.remove('bad','good');feedback.textContent='正在保存…';
  try{await u.act('save',[values]);feedback.textContent=savedMessage(values);feedback.classList.add('good');return true;}
  catch(e){feedback.textContent='保存失败：'+e.message;feedback.classList.add('bad');return false;}
  finally{await refresh?.();}
}
function makeDeviceControl(ctx,u,onRefresh){
  const element=card('推理设备','device-card'),saved=node('p',null,'device-saved'),actual=node('p',null,'muted'),select=node('select'),feedback=fieldFeedback(),progress=node('div',null,'startup-progress');
  select.setAttribute('aria-label','Vulkan 推理设备');select.disabled=true;progress.hidden=true;
  const buttons=node('div',null,'actions');let latest=null,inventory=[],draft=null,committed=null,detecting=false,applying=false,startedAt=0,error='',scanNote='';
  const label=value=>value||'按安装配置选择';
  function render(s){
    latest=s;if(s.availableDevices?.length)inventory=s.availableDevices;
    const selected=s.selectedDeviceName??s.values?.deviceName??'';
    if(draft===null||draft===committed)draft=selected;committed=selected;
    const desired=draft,devices=new Map([['','按安装配置选择']]);
    for(const d of inventory)devices.set(d.name,d.name+(d.kind==='discrete'?'（独显）':d.kind==='integrated'?'（核显）':''));
    for(const name of [selected,desired])if(name&&!devices.has(name))devices.set(name,name+'（已保存 / 待检测）');
    const signature=JSON.stringify([...devices]);
    if(select.dataset.options!==signature){select.replaceChildren(...[...devices].map(([value,text])=>{const o=node('option',text);o.value=value;return o;}));select.dataset.options=signature;}
    select.value=desired;
    saved.textContent='已保存选择：'+label(selected);
    actual.textContent=s.speechEnabled&&s.accepting&&s.phase!=='sleeping'?'当前运行：'+(s.deviceName||'等待引擎确认'):s.phase==='sleeping'?'模型已休眠 · 下次唤醒使用已保存的设备':'语音未运行 · 下次开启使用已保存的设备';
    const busy=applying||s.switchingDevice,blocked=!!(busy||s.updating||s.speaking||s.queueLength||s.initializing||s.toggling);
    select.disabled=busy;apply.disabled=blocked||detecting||desired===selected;apply.dataset.locked=String(apply.disabled);
    apply.textContent=busy?'正在切换…':desired===selected?'已选择':'应用设备';scan.disabled=detecting||busy;scan.dataset.locked=String(scan.disabled);scan.textContent=detecting?'检测中…':'重新检测';
    progress.hidden=!busy;element.setAttribute('aria-busy',String(busy));feedback.classList.toggle('bad',!!error||s.deviceChange?.state==='error');feedback.classList.toggle('good',!error&&!busy&&desired===selected);
    let message=busy?(s.deviceChange?.detail||'正在切换推理设备…')+' · 已等待 '+Math.max(0,Math.floor((Date.now()-(s.deviceChange?.startedAt||startedAt||Date.now()))/1000))+' 秒':error|| (desired!==selected?'待切换：'+label(desired)+'。点击“应用设备”后生效。':s.deviceChange?.detail||'已选择并保存；切换页面后仍会保留。');
    if(!busy&&scanNote)message+=' '+scanNote;
    if(feedback.textContent!==message)feedback.textContent=message;
  }
  async function detect(){
    if(detecting)return;detecting=true;error='';scanNote='正在检测可用设备…';if(latest)render(latest);
    try{const result=await ctx.invoke('devices');if(ctx.signal.aborted)return;inventory=result.devices||[];scanNote='已检测到 '+inventory.length+' 个设备。';}
    catch(e){error='设备检测失败：'+e.message+'；已保存选择保持不变。';}
    finally{detecting=false;if(!ctx.signal.aborted&&latest)render(latest);}
  }
  const scan=u.button('重新检测',detect);
  const apply=u.button('读取状态…',async()=>{
    if(!latest)return;applying=true;startedAt=Date.now();error='';scanNote='';render(latest);
    try{const result=await u.act('selectDevice',[draft]);draft=result.selectedDeviceName??draft;latest={...latest,...result,values:{...latest.values,deviceName:draft}};}
    catch(e){error=e.message;draft=null;}
    finally{applying=false;await onRefresh();if(!ctx.signal.aborted)render(latest);}
  },'primary');apply.disabled=true;
  select.addEventListener('change',()=>{draft=select.value;error='';scanNote='';if(latest)render(latest);},{signal:ctx.signal});
  buttons.append(apply,scan);element.append(saved,actual,select,buttons,progress,feedback,node('p','空闲时重载语音模型，无需重启桌宠。独显会与游戏共享显存；切换失败会尝试恢复原配置。','muted'));
  let scanned=false;
  return {element,render(s){render(s);if(!scanned){scanned=true;if(!s.availableDevices?.length)void detect();}}};
}
function shell(ctx,title,subtitle) {
  const root=node('div',null,'lva'),heading=node('div',null,'panel-heading'),headingText=node('div');headingText.append(node('div','LIGHTWEIGHT LOCAL VOICE ENGINE','eyebrow'),node('h2',title));heading.append(headingText);root.append(heading,node('p',subtitle,'muted'));
  const content=node('div'),notice=node('p',null,'notice');notice.setAttribute('role','status');root.append(content,notice);ctx.root.replaceChildren(root);
  const state={busy:false,revision:0};
  async function act(method,args=[]) {
    if(state.busy){notice.textContent='上一项操作尚未完成，请稍后再试。';throw new Error(notice.textContent);}
    state.busy=true;state.revision++;notice.textContent=method==='save'?'正在保存设置…':method==='selectDevice'?'正在切换推理设备…':'正在处理…';
    try {const result=await ctx.invoke(method,args);if(!ctx.signal.aborted)notice.textContent=['enable','recover'].includes(method)?'请求已接受，启动结果见播放状态。':method==='save'?savedMessage(args[0]):method==='devices'?`已检测到 ${result.devices?.length??0} 个推理设备`:method==='selectDevice'?(result.deviceChange?.detail||'设备设置已保存'):method==='clearQueue'?'已清空待说队列':method==='test'?'试听已播放完毕':'操作已完成';return result;}
    catch(e){if(!ctx.signal.aborted)notice.textContent=e.message||String(e);throw e;}
    finally{state.busy=false;state.revision++;}
  }
  function button(label,fn,cls='') {
    const b=ctx.ui.button(label,{onClick:async()=>{if(state.busy){notice.textContent='上一项操作尚未完成，请稍后再试。';return;}b.disabled=true;try{await fn();}catch{}finally{if(!ctx.signal.aborted && b.dataset.locked!=='true')b.disabled=false;}}});
    b.classList.add(...cls.split(' ').filter(Boolean));return b;
  }
  function poll(render) {
    let loading=false,again=false;
    const refresh=async()=>{if(ctx.signal.aborted)return;if(loading){again=true;return;}loading=true;const revision=state.revision;try{const s=await ctx.invoke('state');if(!ctx.signal.aborted&&revision===state.revision)render(s);}catch(e){if(!ctx.signal.aborted)notice.textContent='读取失败：'+e.message;}finally{loading=false;if(again){again=false;void refresh();}}};
    void refresh();ctx.interval(refresh,1000);return refresh;
  }
  return {content,notice,state,act,button,poll,heading};
}
function memory(s,c) {
  const m=s.memory;
  if(!c){
    c=card('内存与启动条件','memory-card');
    const field=(tag,key,cls)=>{const e=node(tag,null,cls);e.dataset.memory=key;return e;};
    c.append(field('p','device','memory-device'));
    const figures=node('div',null,'memory-figures');
    for(const [key,label] of [['free','当前可用系统内存'],['required','启动至少需要']]){
      const box=node('div');box.append(node('div',label,'memory-label'),field('div',key,'memory-number'));figures.append(box);
    }
    c.append(figures,field('p','verdict','memory-verdict'));
    const track=node('div',null,'track');track.setAttribute('role','progressbar');track.setAttribute('aria-label','系统内存是否满足语音启动要求');track.dataset.memory='track';track.append(field('div','fill','fill'));c.append(track);
    c.append(field('p','guard','memory-measured'),field('p','measured','memory-measured'),field('p','total','memory-measured'));
    const why=node('details',null,'memory-help');why.append(node('summary','查看占用说明'),field('p','explain','muted'),field('p','peak','muted'),node('p','低功耗模式在空闲时释放模型，下次说话重新加载。启动门槛包含系统余量，不能保证游戏与语音同时运行的性能。','muted'));c.append(why);
  }
  const field=key=>c.querySelector('[data-memory="'+key+'"]');
  field('free').textContent=m.freeGiB.toFixed(1)+' GiB';field('free').setAttribute('aria-label','当前可用系统内存 '+m.freeGiB.toFixed(1)+' GiB');
  field('required').textContent=m.minimumGiB+' GiB';
  field('total').textContent=`系统内存总量 ${m.totalGiB.toFixed(1)} GiB · 上方“可用”是剩余 RAM，不是语音占用或显存。`;
  const enough=m.freeGiB>=m.minimumGiB,loaded=s.workerPid&&s.accepting&&s.phase!=='sleeping';
  c.dataset.memoryReady=String(enough);
  field('fill').style.width=`${Math.max(0,Math.min(100,m.freeGiB/m.minimumGiB*100))}%`;
  field('track').setAttribute('aria-valuemin','0');field('track').setAttribute('aria-valuemax',String(m.minimumGiB));field('track').setAttribute('aria-valuenow',String(Math.min(m.minimumGiB,m.freeGiB)));
  field('guard').textContent=`内存不足后自动重试：可用系统内存达到 ${m.recoveryGiB} GiB`;
  const measured=s.workerPid?s.processMemory:null;
  field('measured').textContent=measured?`语音当前占用的 RAM：${fmt(measured.residentMiB)} MiB（进程物理驻留）`:s.workerPid?'语音当前占用：等待进程实测数据':'语音当前占用：工作进程未运行';
  field('verdict').textContent=loaded?'语音已加载 · 下次加载时重新检查':enough?'满足启动条件':`暂不能启动 · 还差 ${(m.minimumGiB-m.freeGiB).toFixed(2)} GiB 可用内存`;
  const kind=s.deviceType||m.deviceType;
  field('device').textContent=`计算设备：${s.deviceName||m.deviceName||'开启语音后检测'}${kind==='discrete'?'（独显）':kind==='integrated'?'（核显）':''}`;
  field('explain').textContent=`启动至少需要 ${m.minimumGiB} GiB 可用系统内存，包含加载临时空间和系统余量，不代表语音固定占用这么多。${kind==='discrete'?'独显使用自己的显存存放 GPU 权重与缓存，Python、音频和驱动仍需系统内存。':'核显与 CPU 共享系统内存。'}${m.layout==='progressive-kv'?'已启用按需扩展的 FP32 缓存，并采用经实测的独显启动门槛。':m.layout==='text-rows'?'已启用文字词表按需加载；核显启动门槛保留 3 GiB。':''}`;
  field('peak').hidden=!measured;if(measured)field('peak').textContent=`进程提交内存 ${fmt(measured.privateMiB)} MiB · 历史物理驻留峰值 ${fmt(measured.peakResidentMiB)} MiB。提交量不等于当前物理 RAM；这些读数也不能与 GPU 专用/共享显存直接相加。`;
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
    pts.forEach(([x,y,i])=>{const p=item('circle',{cx:x,cy:y,r:3,fill:color});const t=document.createElementNS(ns,'title');t.textContent=`第 ${i+1} 次：${ms(history[i][key])}${history[i].cachedPieces>0?'（包含重复语句缓存）':''}`;p.append(t);});
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
  const checkFeedback=fieldFeedback();autoCheck.addEventListener('change',async()=>{autoCheck.disabled=true;const ok=await saveField(u,checkFeedback,{autoCheckUpdates:autoCheck.checked});if(!ok)autoCheck.checked=!autoCheck.checked;autoCheck.disabled=false;},{signal:ctx.signal});
  updateBox.append(updateVersion,updateDetail,updateProgress,checkUpdate,applyUpdate,restartButton,checkLabel,checkFeedback,node('p','只检查并提示新版；点击更新后自动下载、校验、备份与安装，失败回滚。需要重启时询问，确认即重启，稍后保留待重启提示。','muted'),updateLink);updateMenu.append(updateSummary,updateBox);u.heading.append(updateMenu);
  const deploy=card('模型部署检测','deployment'),deployBadge=node('span','正在检测…','badge'),deployDetail=node('p'),deployHint=node('p','此功能需要安装 Qwen3-TTS 0.6B Base Q8 模型、音频解码模型及本地推理引擎才能发声。','muted'),deployLink=node('a','GitHub 一键部署 / 下载完整安装包 ↗','deploy-link');
  deploy.setAttribute('role','status');deploy.setAttribute('aria-live','polite');deployLink.href='https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/latest';deployLink.target='_blank';deployLink.rel='noopener noreferrer';deploy.append(deployBadge,deployDetail,deployHint,deployLink);
  const hero=card('播放状态','hero'),state=node('span',null,'badge'),detail=node('p',null,'muted');hero.append(state,detail);
  const lastFailure=node('p',null,'request-warning');lastFailure.setAttribute('role','status');lastFailure.hidden=true;hero.append(lastFailure);
  const feedback=node('div',null,'startup-feedback'),stageText=node('p'),progress=node('div',null,'startup-progress');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');progress.setAttribute('role','progressbar');progress.setAttribute('aria-label','语音启动进行中');feedback.hidden=true;feedback.append(stageText,progress);hero.append(feedback);
  let pendingStartAt=0,requestedEnabled=null,stopPending=false,revision=0,latest=null,memoryCard=null;
  const actionButtons={},actions=node('div',null,'actions');let refresh=()=>{};
  const startButton=node('button','读取状态…','primary');startButton.type='button';startButton.disabled=true;
  startButton.addEventListener('click',async()=>{
    if(stopPending||latest?.updating||latest?.switchingDevice){u.notice.textContent='设备切换、更新或停止尚未完成，请稍后再试。';return;}
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
  const volume=card('播放音量'),range=node('input'),output=node('strong');range.type='range';range.min=0;range.max=100;range.step=1;range.setAttribute('aria-label','播放音量');range.addEventListener('input',()=>{output.textContent=range.value+'%';volumeFeedback.textContent='待保存：'+range.value+'%';},{signal:ctx.signal});range.addEventListener('change',async()=>{const previous=latest?.values.volume??65;range.disabled=true;if(!await saveField(u,volumeFeedback,{volume:Number(range.value)})){range.value=previous;output.textContent=previous+'%';}range.disabled=false;await refresh();},{signal:ctx.signal});
  const volumeFeedback=fieldFeedback();volume.append(output,range,volumeFeedback,node('p','0% 跳过后续合成并保留模型。当前播放可点击上方“停止语音”中断并释放模型。','muted'));
  let lowPower=false;
  const power=node('div',null,'power-inline'),powerHint=node('span',null,'muted');
  const powerFeedback=fieldFeedback();const powerButton=u.button('低功耗模式',async()=>{await saveField(u,powerFeedback,{lowPowerMode:!lowPower},()=>refresh());},'power-switch');powerButton.setAttribute('role','switch');powerButton.setAttribute('aria-checked','false');powerButton.setAttribute('aria-label','低功耗模式');
  const powerHelp=node('details',null,'power-help');powerHelp.append(node('summary','说明'),node('p','开启后按配置的空闲时间或内存阈值释放模型，不打断播放；下一句话自动唤醒，首句多一段加载等待。关闭后保持常驻。休眠时间、阈值和是否保留进程在“配置”页调整。','muted'));
  power.append(powerButton,powerHint,powerHelp,powerFeedback);
  let syncBubbles=true;
  const syncOption=node('div',null,'feature-option'),syncCopy=node('div',null,'feature-copy'),syncHint=node('p',null,'muted'),syncTitle=node('div',null,'feature-title'),syncFeedback=fieldFeedback();
  syncOption.setAttribute('aria-label','独立功能：气泡同步');syncHint.id='lva-bubble-sync-hint';syncHint.setAttribute('role','status');
  const syncButton=u.button('读取状态…',async()=>{await saveField(u,syncFeedback,{syncBubbles:!syncBubbles},()=>refresh());},'power-switch');syncButton.setAttribute('role','switch');syncButton.setAttribute('aria-label','气泡同步');syncButton.setAttribute('aria-describedby',syncHint.id);syncButton.disabled=true;
  syncButton.title='首次默认开启，语音就绪后生效。记住你的选择；关闭此功能不会停止语音。';
  syncTitle.append(node('strong','气泡同步'),syncButton);syncCopy.append(syncTitle,syncHint,syncFeedback);syncOption.append(syncCopy);hero.append(syncOption,power);
  const playbackCard=card('播放策略'),playbackSelect=node('select'),playbackHint=node('p',null,'muted');playbackSelect.setAttribute('aria-label','播放策略');
  for(const[value,label]of [['auto','自动（按生成速度判断）'],['buffered','优先连续（整句生成后播）'],['stream','优先开口（可能断续）']]){const option=node('option',label);option.value=value;playbackSelect.append(option);}
  let playbackSaving=false;const playbackFeedback=fieldFeedback();playbackSelect.addEventListener('change',async()=>{const previous=latest?.values.playbackMode||'auto';playbackSaving=true;playbackSelect.disabled=true;try{if(!await saveField(u,playbackFeedback,{playbackMode:playbackSelect.value}))playbackSelect.value=previous;}finally{playbackSaving=false;playbackSelect.disabled=false;await refresh();}},{signal:ctx.signal});playbackCard.append(playbackSelect,playbackFeedback,playbackHint);
  const device=makeDeviceControl(ctx,u,()=>refresh());const deviceCard=device.element;
  const cacheRow=node('label',null,'cache-option'),cacheToggle=node('input'),cacheCopy=node('span','重复语句缓存'),cacheHint=node('small','最多 4 MiB；相同音色和文字直接复用原始音频，休眠时清空。'),cacheFeedback=fieldFeedback();cacheToggle.type='checkbox';cacheToggle.setAttribute('aria-label','重复语句缓存');cacheCopy.append(cacheHint);cacheRow.append(cacheToggle,cacheCopy);playbackCard.append(cacheRow,cacheFeedback);
  cacheToggle.addEventListener('change',async()=>{const previous=latest?.values.cacheRepeated??true;cacheToggle.disabled=true;if(!await saveField(u,cacheFeedback,{cacheRepeated:cacheToggle.checked}))cacheToggle.checked=previous;cacheToggle.disabled=false;await refresh();},{signal:ctx.signal});
  const tuning=node('div',null,'grid resource-grid'),mem=node('div');tuning.append(deviceCard,mem);
  const grid=node('div',null,'grid playback-grid');grid.append(volume,playbackCard);const top=node('div',null,'control-top-grid');top.append(hero,deploy);u.content.append(top,tuning,grid);
  refresh=u.poll(s=>{
    const updates=s.updates||{},stages={idle:'尚未检查',checking:'正在检查',available:'有新版本',current:'已是最新',downloading:'正在下载',validating:'正在校验',backing_up:'正在备份',installing:'正在安装',restoring:'正在恢复旧版本',verifying:'正在验证',installed:'语音引擎已更新',rolled_back:'已回滚',error:'更新失败'};
    updateVersion.textContent=`引擎 ${s.engineVersion||updates.currentVersion||'待检测'} · 扩展 ${updates.loadedWorldVersion||'0.4.2'}`;
    let percentage=null;if(updates.total>0&&['downloading','backing_up','installing','restoring'].includes(updates.stage))percentage=Math.round((updates.stage==='downloading'?updates.received:updates.completed)/updates.total*100);
    updateSummary.textContent=updates.busy?'更新中…':updates.available&&updates.stage!=='installed'?'热更新 · 有新版':'热更新';
    updateDetail.textContent=(stages[updates.stage]||'尚未检查')+(percentage!=null?' '+percentage+'%':'')+(updates.stage==='available'?' v'+updates.release?.version:'')+(updates.error?'：'+updates.error:'')+(updates.requiresFullInstall?'；本次包含原生引擎/模型布局更新，请从发布页运行完整安装包':updates.supported===false?'；当前为源码安装，请用 GitHub 完整包升级':'')+(updates.requiresRestart?'；World 扩展更新待桌宠重启生效':'');
    updateProgress.hidden=!updates.busy;if(percentage==null)updateProgress.removeAttribute('value');else updateProgress.value=percentage;
    if(!autoCheck.disabled)autoCheck.checked=!!(s.values.autoCheckUpdates??true);
    restartButton.hidden=!updates.requiresRestart;restartButton.disabled=!!updates.busy;restartButton.dataset.locked=String(restartButton.disabled);
    const pendingVersion=updates.currentVersion||updates.version||updates.release?.version||'pending';
    if(updates.requiresRestart&&!updates.busy&&!u.state.busy&&restartPrompted!==pendingVersion){restartPrompted=pendingVersion;ctx.memo?.set('restartPromptVersion',pendingVersion);void offerRestart().catch(e=>{u.notice.textContent=e.message;});}
    checkUpdate.disabled=!!updates.busy;checkUpdate.dataset.locked=String(checkUpdate.disabled);applyUpdate.hidden=!updates.available||updates.stage==='installed';applyUpdate.disabled=!!updates.busy||!updates.available||updates.supported!==true||s.speaking||s.queueLength>0||s.initializing;applyUpdate.dataset.locked=String(applyUpdate.disabled);
    if(!playbackSaving&&document.activeElement!==playbackSelect)playbackSelect.value=s.values.playbackMode||'auto';
    const lastMode=s.lastSpeech?.effectivePlaybackMode;playbackHint.textContent='自动模式在生成偏慢或测量不足时先生成整句，等待更久但避免合成欠载；快设备保留流式。'+(lastMode?' 最近实际：'+(lastMode==='buffered'?'整句连续播放':'流式播放'):'');
    device.render(s);
    const version=/^(\d+)\.(\d+)\.(\d+)/.exec(s.engineVersion||''),cacheSupported=!version||Number(version[1])>0||Number(version[2])>5||Number(version[2])===5&&Number(version[3])>=1;
    if(!u.state.busy){cacheToggle.disabled=!cacheSupported;cacheToggle.checked=s.values.cacheRepeated??true;}
    cacheHint.textContent=cacheSupported?'最多 4 MiB；相同音色和文字直接复用原始音频，休眠时清空。':'当前引擎低于 0.5.1，更新运行包后才支持此功能；配置保持。';
    const d=s.deployment||{state:'unknown',detail:'尚未取得模型部署状态'};
    const labels={missing:'未部署 · 无法使用语音',error:'模型连接失败',waiting_memory:'已部署 · 等待内存',connected:'已连接 · 可以发声',loading:'已部署 · 正在连接',sleeping:'已部署 · 低功耗休眠',installed:'已部署 · 尚未连接',unknown:'正在检测模型'};
    deploy.dataset.state=d.state;deployBadge.textContent=labels[d.state]||labels.unknown;deployDetail.textContent=d.detail||'';deploy.classList.toggle('attention',['missing','error','unknown'].includes(d.state));deployLink.classList.toggle('highlight',['missing','error','installed'].includes(d.state));deployLink.textContent=['missing','error'].includes(d.state)?'安装模型 / 部署教程 ↗':'GitHub 部署教程 ↗';deployHint.textContent=d.installed?'Qwen3-TTS 0.6B · Q8 · Vulkan GPU':'需要安装 Qwen3-TTS 0.6B Q8 及本地引擎才能发声。';
    latest=s;const enabled=requestedEnabled??s.speechEnabled;
    lastFailure.hidden=!s.lastRequestFailure;lastFailure.textContent=s.lastRequestFailure?`最近一次朗读异常：${s.lastRequestFailure.detail}`:'';
    syncBubbles=!!s.values.syncBubbles;syncButton.textContent=syncBubbles?'已开启':'已关闭';syncButton.setAttribute('aria-checked',String(syncBubbles));syncButton.disabled=false;
    syncHint.textContent={disabled:'按原版文字计时切换，语音照常播放',voice_off:'已预选 · 开启语音后自动生效（首次默认开启）',muted:'已预选 · 当前静音，气泡按文字计时切换',unavailable:'缺少显示适配桥，请按安装教程接入后重启桌宠',waiting_voice:'已预选 · 等待语音准备完成后自动生效',active:'正在生效 · 等本段语音读完，再切换下一气泡'}[s.bubbleSync?.phase]||'正在读取同步状态';
    const starting=!!(pendingStartAt||enabled&&(s.initializing||s.toggling)),stopping=!!(stopPending||s.toggling&&!s.speechEnabled),ready=s.speechEnabled&&s.accepting&&!['waiting_memory','error','waiting_user','disabled'].includes(s.phase);
    startButton.disabled=stopping||s.switchingDevice||s.updating;startButton.textContent=s.switchingDevice?'设备切换中…':s.updating?'更新中…':stopping?'正在停止…':starting?'加载中 · 点击取消':enabled?'停止语音':'开启语音';startButton.title=starting?'点击取消加载并释放模型':enabled?'停止播放并释放语音模型':'开启本地语音';hero.setAttribute('aria-busy',String(starting||stopping));
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
    const ratios=h.filter(x=>!(x.cachedPieces>0)&&x.seconds>0&&Number.isFinite(x.totalSynthesisMs)).map(x=>x.totalSynthesisMs/(x.seconds*1000));
    grid.append(metric('首次出声',last?ms(last.firstDeviceCallbackMs):'—','最近一条：音频设备首次回调'+(last?.cachedPieces>0?'（包含缓存复用）':'')),metric('平均合成耗时 / 音频时长',ratios.length?(ratios.reduce((a,b)=>a+b,0)/ratios.length).toFixed(2)+'×':'—','低于 1× 表示平均生成快于音频时长；排除包含缓存的记录'),metric('断流 / 设备欠载',last?`${fmt(last.underrunMs)} ms / ${fmt(last.deviceUnderflows)} 次`:'—','最近一条：连续播放监测'));
    const info=card('引擎与诊断'),err=node('p',s.workerError||s.detail||'无异常',s.workerError?'error':'muted');
    const policy=s.nativeSettings?.memoryPolicy==='device-local'?'设备本地显存':s.nativeSettings?.memoryPolicy==='backend-default'?'核显/后端默认分配':'尚未检测';
    const kv=s.nativeSettings;
    const mode={auto:'自动',stream:'流式',buffered:'整句缓冲'};
    info.append(node('p',s.engine),node('p',`实际 GPU：${s.deviceName||'尚未连接'} · 引擎 ${s.engineVersion||'—'}`),node('p',`内存路径：${policy} · 24 kHz 单声道`,'muted'),node('p',`最近加载 / 唤醒 ${ms(s.loadMs)} · 丢弃旧句 ${fmt(s.dropped)}`,'muted'),node('p',last?`最近策略：${mode[last.requestedPlaybackMode]||'—'} → ${mode[last.effectivePlaybackMode]||'—'}；${last.smoothPlayback===true?'播放未检测到欠载':last.smoothPlayback===false?'存在播放欠载':'连续性尚无数据'}。${last.realTimeFactor>=1?'合成慢于实时，不能视为低延迟验收通过。':''}`:'还没有真实播放样本，无法判定性能。','muted'),err);
    const lower=node('div',null,'grid');memoryCard=memory(s,memoryCard);lower.append(memoryCard,info);u.content.replaceChildren(grid,chart(h),lower);
    if(kv?.adaptiveKv&&s.phase==='sleeping')info.append(node('p','推理缓存：模型已休眠释放，下次说话时重新分配。','muted'));
    else if(kv?.adaptiveKv) info.append(node('p',`推理缓存：FP32 · 当前 ${fmt(kv.kvAllocatedMiB)} MiB / ${fmt(kv.kvCapacity)} 个位置 · 按需扩展至 ${fmt(kv.kvContext)}；此数值仅为 Talker KV 缓存，不是模型总显存。`,'muted'));
    const cache=kv?.pcmCache;if(cache)info.append(node('p',`重复语句缓存：命中 ${fmt(cache.hits)} 次 · ${fmt(cache.entries)} 段 · ${(cache.bytes/1048576).toFixed(2)} / ${(cache.maximumBytes/1048576).toFixed(0)} MiB。只减少重复内容的计算，不代表新句推理提速。`,'muted'));
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
  const configFeedback=fieldFeedback();const a=node('div',null,'actions');a.append(u.button('保存配置',async()=>{const values=Object.fromEntries(Object.entries(inputs).map(([k,i])=>[k,i.type==='checkbox'?i.checked:Number(i.value)]));await saveField(u,configFeedback,values);},'primary'));form.append(a,configFeedback);
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
const diagnostics={mount(ctx){
  const u=shell(ctx,'日志与诊断','查看真实的性能与故障报告。采集不会运行额外语音；公开提交由下方开关控制。');
  const options=card('自动报告'),inputs={},progress=node('p','正在读取报告…','notice'),actions=node('div',null,'actions');progress.setAttribute('role','status');
  for(const[key,title,desc]of [
    ['autoDiagnostics','自动记录故障与性能瓶颈','仅保存在本机。连续两次慢于实时或播放欠载才记录性能问题，同类问题每天一份，每天最多三份。'],
    ['autoSubmitIssues','自动提交脱敏 Issue','将版本、硬件/驱动、错误码与必要性能日志提交至 Asryto 的 GitHub 仓库。不含聊天、音频、密钥和个人路径；需要本机已有 GitHub 凭据。未登录或失败则保留 ZIP。']]){
    const row=node('label',null,'row'),text=node('span',title),input=node('input');input.type='checkbox';input.setAttribute('aria-label',title);text.append(node('small',desc));row.append(text,input);const feedback=fieldFeedback();text.append(feedback);options.append(row);inputs[key]=input;
    input.addEventListener('change',async()=>{input.disabled=true;try{feedback.textContent='正在保存…';await u.act('save',[{[key]:input.checked}]);feedback.textContent=savedMessage({[key]:input.checked});feedback.classList.remove('bad');}catch(e){input.checked=!input.checked;feedback.textContent='保存失败：'+e.message;feedback.classList.add('bad');}finally{input.disabled=false;}},{signal:ctx.signal});
  }
  let refresh=()=>{};
  actions.append(u.button('立即生成报告',async()=>{await u.act('collectReport',[0]);await refresh();},'primary'),
    u.button('监测 60 秒',async()=>{await u.act('collectReport',[60]);await refresh();}),
    u.button('刷新列表',async()=>{await u.act('refreshReports');await refresh();}));
  const link=node('a','Asryto · GitHub 问题反馈 ↗');link.href='https://github.com/scarlet20252025-cloud/coopanion-soft-voice/issues';link.target='_blank';link.rel='noopener noreferrer';
  options.append(actions,progress,link);
  const list=card('最近报告'),rows=node('div'),viewer=card('报告详情'),preview=node('pre', '选择一份报告查看。','report-preview');
  viewer.append(preview);list.append(node('p','保留最近 20 份。ZIP 内含设备与性能诊断、关键日志、AI 分析入口和 Issue 草稿。','muted'),rows);
  u.content.append(options,list,viewer);let signature='';
  function renderReports(reports){
    const next=JSON.stringify(reports);if(next===signature)return;signature=next;
    rows.replaceChildren(...reports.map(r=>{
      const item=node('div',null,'report-item'),title=node('strong',r.title),stamp=node('p',new Date(r.atUtc).toLocaleString()+(r.automatic?' · 自动记录':' · 手动采集'),'muted');
      const summary=r.summary||{},readings=node('p',`合成/播放比 ${Number.isFinite(summary.realTimeFactor)?summary.realTimeFactor.toFixed(2)+'×':'未测'} · 断流 ${summary.underrunMs??'未测'} ms · 设备欠载 ${summary.deviceUnderflows??'未测'} 次`,'muted');
      const status=node('p',r.submission?.reason||'仅本地保存','muted'),buttons=node('div',null,'actions');
      buttons.append(u.button('查看报告',async()=>{const d=await u.act('reportDetail',[r.id]);preview.textContent=JSON.stringify({报告:d.report.title,采集时间:d.report.atUtc,...d.snapshot,最近采样:d.sample},null,2)+(d.perf?'\n\n分阶段性能日志\n'+d.perf:'');viewer.scrollIntoView({block:'nearest'});}),
        u.button('导出 ZIP',async()=>{const f=await u.act('exportReport',[r.id]);if(!f)return;const bytes=Uint8Array.from(atob(f.base64),c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'})),a=node('a');a.href=url;a.download=f.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}),
        u.button(r.submission?.submitted?'已提交':'提交 Issue',async()=>{
          const question='向 Asryto 仓库公开提交这份报告的脱敏摘要与性能日志？不包含聊天、音频或个人路径。';
          const yes=ctx.ui.confirm?await ctx.ui.confirm({title:'提交语音问题反馈',body:question}):window.confirm(question);
          if(!yes)return;
          await u.act('submitReport',[r.id,true]);await refresh();}));
      if(r.submission?.submitted){buttons.lastChild.disabled=true;buttons.lastChild.dataset.locked='true';}
      item.append(title,stamp,readings,status,buttons);
      if(r.submission?.url&&/^https:\/\/github\.com\/scarlet20252025-cloud\/coopanion-soft-voice\/issues\/\d+(?:#issuecomment-\d+)?$/.test(r.submission.url)){
        const issue=node('a','查看关联 Issue ↗');issue.href=r.submission.url;issue.target='_blank';issue.rel='noopener noreferrer';item.append(issue);
      }
      return item;
    }));
    if(!reports.length)rows.append(node('p','尚无报告。点击“立即生成报告”，或等待发生语音故障。','empty'));
  }
  refresh=u.poll(s=>{
    for(const[k,input]of Object.entries(inputs))if(document.activeElement!==input)input.checked=!!s.values[k];
    const d=s.diagnostics||{};progress.textContent=(d.detail||'尚未采集报告')+(d.busy&&d.startedAt?' · 已用 '+Math.max(0,Math.floor((Date.now()-d.startedAt)/1000))+' 秒':'');options.setAttribute('aria-busy',String(!!d.busy));
    for(const b of actions.querySelectorAll('button')){b.disabled=!!d.busy;b.dataset.locked=String(!!d.busy);}
    renderReports(d.reports||[]);
  });
  void ctx.invoke('refreshReports').then(refresh).catch(e=>u.notice.textContent=e.message);
}};
export default {panels:{controls,status,config,voices,diagnostics}};
