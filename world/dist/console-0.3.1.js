const names = {suspending:'正在休眠',sleeping:'低功耗休眠',ready:'就绪',load_model:'正在加载',synthesizing:'正在合成',playing:'正在播放',waiting_memory:'等待内存',disabled:'已关闭',stopped:'已停止',error:'异常',waiting_user:'待配置',idle:'未启动'};
const node = (tag, text, cls) => { const e=document.createElement(tag); if(text!=null)e.textContent=text;if(cls)e.className=cls;return e; };
const card = (title, cls='') => { const e=node('section',null,'card '+cls);if(title)e.append(node('h3',title));return e; };
const fmt = n => Number.isFinite(n) ? Math.round(n).toLocaleString() : '—';
const ms = n => `${fmt(n)} ms`;
function shell(ctx,title,subtitle) {
  const root=node('div',null,'lva');root.append(node('div','LOCAL VOICE ASSISTANT','eyebrow'),node('h2',title),node('p',subtitle,'muted'));
  const content=node('div'),notice=node('p',null,'notice');notice.setAttribute('role','status');root.append(content,notice);ctx.root.replaceChildren(root);
  const state={busy:false};
  async function act(method,args=[]) {
    if(state.busy)return;state.busy=true;notice.textContent='正在处理…';
    try {const result=await ctx.invoke(method,args);if(!ctx.signal.aborted)notice.textContent='操作已完成';return result;}
    catch(e){if(!ctx.signal.aborted)notice.textContent=e.message||String(e);throw e;}
    finally{state.busy=false;}
  }
  function button(label,fn,cls='') {
    const b=ctx.ui.button(label,{onClick:async()=>{if(state.busy)return;b.disabled=true;try{await fn();}catch{}finally{if(!ctx.signal.aborted)b.disabled=false;}}});
    b.classList.add(...cls.split(' ').filter(Boolean));return b;
  }
  function poll(render) {
    let loading=false;
    const refresh=async()=>{if(loading||state.busy||ctx.signal.aborted)return;loading=true;try{const s=await ctx.invoke('state');if(!ctx.signal.aborted)render(s);}catch(e){if(!ctx.signal.aborted)notice.textContent='读取失败：'+e.message;}finally{loading=false;}};
    void refresh();ctx.interval(refresh,2000);return refresh;
  }
  return {content,notice,state,act,button,poll};
}
function memory(s) {
  const m=s.memory,c=card('内存与启动要求');
  c.append(node('div',`${m.freeGiB.toFixed(1)} GiB`,'stat'),node('p',`当前空闲 / 系统总量 ${m.totalGiB.toFixed(1)} GiB`,'muted'));
  const track=node('div',null,'track'),fill=node('div',null,'fill');fill.style.width=`${Math.min(100,m.freeGiB/m.totalGiB*100)}%`;track.append(fill);
  for(const n of [m.minimumGiB,m.recoveryGiB,...(s.values.lowPowerMode&&s.values.lowMemoryMiB>0?[s.values.lowMemoryMiB/1024]:[])]){const line=node('span',null,'marker');line.style.left=`${n/m.totalGiB*100}%`;line.title=`${n} GiB`;track.append(line);}c.append(track);
  c.append(node('p',`加载 / 唤醒前至少 ${m.minimumGiB} GiB 空闲 · 自动恢复需 ${m.recoveryGiB} GiB`,'warn'));
  c.append(node('p',s.values.lowPowerMode?`低功耗模式已开启 · 空闲 ${s.values.idleUnloadSec || 0} 秒 / 可用内存低于 ${s.values.lowMemoryMiB || 0} MiB 时休眠（0 表示该条件关闭）。下一句自动唤醒，需要额外加载时间。`:'低功耗模式已关闭：模型就绪后保持常驻，不因空闲或内存阈值自动休眠。','muted'));
  c.append(node('p',s.workerPid&&s.accepting&&s.phase!=='sleeping'?'模型已加载。此时空闲低于 4 GiB 不代表运行不达标；关闭后再次加载仍需检查。':m.freeGiB<m.minimumGiB?'目前不足加载门槛，将保留文字回复。请释放内存后恢复。':'达到加载门槛；这不代表游戏负载下的性能保证。','muted'));
  return c;
}
function metric(title,value,hint){const c=card(title);c.append(node('div',value,'stat'),node('p',hint,'muted'));return c;}
function chart(history) {
  const c=card('最近 30 次语音 · 首次出声延迟');
  if(!history.length){c.append(node('div','尚无数据。完成一次试听或聊天朗读后显示真实曲线。','empty'));return c;}
  const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 760 235');svg.setAttribute('role','img');svg.setAttribute('aria-label','首次音频设备回调及含排队延迟曲线，单位毫秒');
  function item(tag,attrs,text){const e=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(text)e.textContent=text;svg.append(e);return e;}
  const max=Math.max(1000,...history.flatMap(x=>[x.firstDeviceCallbackMs||0,x.totalStartMs||0]))*1.15;
  for(let i=0;i<4;i++){const y=15+i*60;item('line',{x1:55,y1:y,x2:742,y2:y,stroke:'var(--border)' });item('text',{x:2,y:y+5,fill:'var(--muted-foreground)' ,'font-size':12},String(Math.round(max*(1-i/3))));}
  for(const [key,color] of [['firstDeviceCallbackMs','#9faeff'],['totalStartMs','#71d9b1']]){
    const pts=history.map((h,i)=>[55+i*(687/Math.max(1,history.length-1)),195-Math.min(max,h[key]||0)/max*180]);
    item('polyline',{points:pts.map(p=>p.join(',')).join(' '),fill:'none',stroke:color,'stroke-width':2.5});
    pts.forEach(([x,y],i)=>{const p=item('circle',{cx:x,cy:y,r:3,fill:color});const t=document.createElementNS(ns,'title');t.textContent=`第 ${i+1} 次：${ms(history[i][key])}`;p.append(t);});
  }
  item('text',{x:55,y:224,fill:'var(--muted-foreground)' ,'font-size':12},'较早');item('text',{x:710,y:224,fill:'var(--muted-foreground)' ,'font-size':12},'最近');c.append(svg);
  c.append(node('p','● 紫色：首次设备回调　● 绿色：含排队总延迟','legend'),node('p','毫秒，越低越快。计时从语音任务接收开始，不含聊天模型思考或系统扬声器的额外延迟；切换音色时清空旧曲线。','chart-caption'));return c;
}
const controls={mount(ctx){
  const u=shell(ctx,'语音控制','日常开关与播放控制。音色管理、诊断图表和高级设置分别位于其他页签。');
  const hero=card('播放状态','hero'),state=node('span',null,'badge'),detail=node('p',null,'muted');hero.append(state,detail);
  const actions=node('div',null,'actions');let refresh=()=>{};
  for(const [label,method,args,cls]of [['开启语音','enable',[],'primary'],['试听一句','test',[],''],['恢复语音','recover',[],''],['立即停止 / 释放内存','disable',[],'danger'],['清空待说队列','clearQueue',[],'']])actions.append(u.button(label,async()=>{await u.act(method,args);await refresh();},cls));hero.append(actions);
  const volume=card('播放音量'),range=node('input'),output=node('strong');range.type='range';range.min=0;range.max=100;range.step=1;range.setAttribute('aria-label','播放音量');range.addEventListener('input',()=>output.textContent=range.value+'%',{signal:ctx.signal});range.addEventListener('change',()=>{void u.act('save',[{volume:Number(range.value)}]).catch(()=>{});},{signal:ctx.signal});
  volume.append(output,range,node('p','0% 跳过后续合成并保留模型。当前正在播放的声音请用“立即停止”中断。','muted'));
  const power=card('低功耗模式'),powerInput=node('input'),powerLabel=node('label','自动休眠');powerInput.type='checkbox';powerInput.setAttribute('aria-label','低功耗模式');powerLabel.prepend(powerInput);
  powerInput.addEventListener('change',()=>{void u.act('save',[{lowPowerMode:powerInput.checked}]).then(()=>refresh()).catch(()=>refresh());},{signal:ctx.signal});
  power.append(powerLabel,node('p','开启后，空闲到时或可用内存低于设置值时释放模型并休眠，不打断当前播放。下一句话自动唤醒，首句需要额外等待。关闭后保持常驻，仍保留加载内存保护。这里只控制语音引擎，不调整电脑电源计划。','muted'));
  const grid=node('div',null,'grid'),mem=node('div');grid.append(volume,mem);u.content.append(hero,power,grid);
  refresh=u.poll(s=>{powerInput.checked=!!s.values.lowPowerMode;state.textContent=names[s.phase]||s.phase;detail.textContent=`${s.voices.find(v=>v.key===s.selectedVoice)?.name||s.selectedVoice} · 排队 ${s.queueLength} 句 · ${s.speechEnabled?'已开启':'已关闭'}`;if(document.activeElement!==range){range.value=s.values.volume;output.textContent=s.values.volume+'%';}mem.replaceChildren(memory(s));});
}};
const status={mount(ctx){
  const u=shell(ctx,'运行状态','真实语音指标与内存门槛。没有样本时不估算性能，不填充演示数据。');
  u.poll(s=>{
    const h=s.history||[],last=h.at(-1),grid=node('div',null,'grid');
    const ratios=h.filter(x=>x.seconds>0&&Number.isFinite(x.totalSynthesisMs)).map(x=>x.totalSynthesisMs/(x.seconds*1000));
    grid.append(metric('首次出声',last?ms(last.firstDeviceCallbackMs):'—','最近一条：音频设备首次回调'),metric('平均合成耗时 / 音频时长',ratios.length?(ratios.reduce((a,b)=>a+b,0)/ratios.length).toFixed(2)+'×':'—','低于 1× 表示平均生成快于音频时长'),metric('断流 / 设备欠载',last?`${fmt(last.underrunMs)} ms / ${fmt(last.deviceUnderflows)} 次`:'—','最近一条：连续播放监测'));
    const info=card('引擎与诊断'),err=node('p',s.workerError||s.detail||'无异常',s.workerError?'error':'muted');
    info.append(node('p',s.engine),node('p',`24 kHz 单声道 · 最近加载 / 唤醒 ${ms(s.loadMs)} · 丢弃旧句 ${s.dropped}`,'muted'),err);
    const lower=node('div',null,'grid');lower.append(memory(s),info);u.content.replaceChildren(grid,chart(h),lower);
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
