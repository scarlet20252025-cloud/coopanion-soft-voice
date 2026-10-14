const TERMINAL=new Set(['done','failed','skipped','cancelled','expired']);
const ENDPOINT='/api/soft-voice/bubble-sync';

/** Optional pet-page adapter. A missing/stopped extension falls back to native timing. */
export function createVoiceBubbleSync({fetchImpl=fetch,now=()=>Date.now(),interval=200}={}) {
  const local=new Map();let enabled=false,timer=null,busy=false,failures=0;
  const apply=s=>{enabled=s.enabled===true;for(const b of s.bubbles||[]){const item=local.get(b.id);if(item)item.state=b.state;}};
  const poll=async()=>{if(busy)return;busy=true;try{const r=await fetchImpl(ENDPOINT,{cache:'no-store'});if(!r.ok)throw Error();apply(await r.json());failures=0;}catch{if(++failures>=3)enabled=false;}finally{busy=false;}};
  const post=(action,id,text)=>{void fetchImpl(ENDPOINT,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action,id,...(text===undefined?{}:{text})})}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(apply).catch(()=>{enabled=false;});};
  const stopIfIdle=()=>{if(!local.size&&timer){clearInterval(timer);timer=null;}};
  return {
    register(id,beats){local.set(id,{at:now(),state:'pending'});post('register',id,beats.map(b=>b.text||'').join(''));if(!timer){timer=setInterval(poll,interval);void poll();}},
    shown(id){post('shown',id);},
    closed(id){post('closed',id);local.delete(id);stopIfIdle();},
    hold(id,lastBeat){
      if(!lastBeat)return undefined;
      const b=local.get(id);if(!b||!enabled)return undefined;
      if(now()-b.at>360000)return false;
      if(TERMINAL.has(b.state))return false;
      // Give the already-written tool receipt a brief chance to reach the tailer.
      if(b.state==='pending'&&now()-b.at>2500)return undefined;
      return true;
    },
    dispose(){if(timer)clearInterval(timer);timer=null;local.clear();enabled=false;},
  };
}
