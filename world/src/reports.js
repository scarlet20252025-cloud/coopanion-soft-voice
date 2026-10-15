import { pythonJson } from './helpers.js';
import { readFileSync } from 'node:fs';

const WORLD_VERSION=JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8')).version;

const CODES=new Set(['worker_error','worker_exit','startup_timeout','speech_timeout','protocol_error','memory_guard','slow_synthesis','playback_underflow']);

// Runs outside the audio path; a report must never fail or pause speech.
export class VoiceReports {
  constructor(runtime,cfg,log) {
    this.runtime=runtime;this.cfg=cfg;this.log=log;this.running=null;this.rows=[];
    this.state={phase:'idle',detail:'尚未采集报告',reports:[],retention:20};
    this.seen=new Map();this.perf=[];this.nextAutomatic=0;
  }
  status(){return {...this.state,busy:!!this.running};}
  async call(action,args=[]) {
    const p=this.runtime.profile();
    return pythonJson(p,'coopanion_soft_voice.reports',
      ['--runtime',p.runtime,'--data-dir',this.runtime.root,'--world-version',WORLD_VERSION,action,...args],null,8*1024*1024);
  }
  async refresh(){try{const result=await this.call('list');this.state={...this.state,...result};return this.status();}catch(error){this.state.phase='error';this.state.detail='无法读取报告；旧版运行包请先从模型部署入口升级完整安装包。';throw error;}}
  async run(action,args=[],automatic=false) {
    if(this.running)throw new Error('正在处理上一份诊断报告，请稍等');
    this.state.phase=action==='submit'?'submitting':'collecting';
    this.state.startedAt=Date.now();
    this.state.detail=action==='submit'?'正在去重并提交脱敏 Issue…':args.includes('60')?'监测中（60 秒），可以正常使用语音…':'正在收集设备与语音指标…';
    this.running=(async()=>{
      const result=await this.call(action,args);
      if(action==='collect'&&result.report&&automatic&&this.cfg.autoSubmitIssues&&result.report.code!=='memory_guard') {
        this.state.phase='submitting';this.state.detail='报告已保存，正在提交脱敏 Issue…';
        await this.call('submit',['--id',result.report.id,'--authorized','--automatic']);
      }
      await this.refresh();
      this.state.phase='ready';
      const submitted=this.state.reports.find(r=>r.id===result.report?.id)?.submission;
      this.state.detail=result.skipped?result.reason||'相同问题已记录，未重复提交':
        action==='submit'||automatic&&this.cfg.autoSubmitIssues?submitted?.reason||'报告已保存':'报告已保存，可查看或导出 ZIP';
      return this.status();
    })().catch(error=>{
      this.state.phase='error';this.state.detail='报告操作未完成，可重试。若使用旧版运行包，请先从模型部署入口升级完整安装包。';
      this.log?.warn('语音诊断操作失败：'+error.name);throw error;
    }).finally(()=>{this.running=null;});
    return this.running;
  }
  observe(event,now=Date.now()) {
    if(!this.cfg.autoDiagnostics)return;
    let code=event.code;
    if(event.type==='playback') {
      const seconds=Number(event.seconds),rtf=Number(event.realTimeFactor ?? (seconds>0?event.totalSynthesisMs/(seconds*1000):NaN));
      if(!(seconds>=3))return;
      this.perf.push({slow:Number.isFinite(rtf)&&rtf>1.25,underflow:event.underrunMs>250||event.deviceUnderflows>=2});
      if(this.perf.length>2)this.perf.shift();
      if(this.perf.length<2)return;
      code=this.perf.every(p=>p.underflow)?'playback_underflow':this.perf.every(p=>p.slow)?'slow_synthesis':null;
    }
    if(!CODES.has(code)||this.running||now<this.nextAutomatic||now-(this.seen.get(code)||0)<86400000)return;
    this.seen.set(code,now);this.nextAutomatic=now+3600000;
    void this.run('collect',['--code',code,'--automatic'],true).catch(()=>{});
  }
}
