import { spawn } from 'node:child_process';
import { StringDecoder } from 'node:string_decoder';

export function pythonJson(p,module,args=[],onProgress=null) {
  return new Promise((resolve,reject)=>{
    const child=spawn(p.python,['-m',module,...args],{windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',PYTHONUNBUFFERED:'1'}});
    const decoder=new StringDecoder('utf8');let text='',tail='',last=null,settled=false;
    const fail=error=>{if(settled)return;settled=true;clearTimeout(timer);reject(error);};
    const timer=setTimeout(()=>{child.kill();fail(new Error('语音辅助操作超时；未完成的更新会在下次尝试时回滚。'));},180000);
    child.stdout.on('data',bytes=>{
      text+=decoder.write(bytes);
      const lines=text.split(/\r?\n/);text=lines.pop()||'';
      for(const line of lines){try{last=JSON.parse(line.replace(/^@@UPDATE@@/,''));onProgress?.(last);}catch{}}
      if(text.length>65536){child.kill();fail(new Error('语音辅助响应过大'));}
    });
    child.stderr.on('data',bytes=>{tail=(tail+bytes.toString('utf8')).slice(-3000);});
    child.once('error',fail);
    child.once('close',code=>{if(settled)return;settled=true;clearTimeout(timer);if(code!==0)reject(new Error(last?.detail||tail||`语音辅助进程退出 (${code})`));else if(!last)reject(new Error('语音辅助进程没有返回结果'));else resolve(last);});
  });
}
