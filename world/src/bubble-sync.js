const textKey = text => String(text || '').replace(/\s+/g, '');
const TERMINAL = new Set(['done','failed','skipped','cancelled','expired']);

/** Correlates bubble IDs with the existing speech queue; never estimates audio duration. */
export class BubbleSpeechSync {
  constructor(enabled, now = () => Date.now()) { this.enabled=enabled;this.now=now;this.jobs=[];this.bubbles=[]; }
  prune() { const cutoff=this.now()-360000;this.jobs=this.jobs.filter(j=>j.at>cutoff).slice(-24);this.bubbles=this.bubbles.filter(b=>b.at>cutoff).slice(-24); }
  pair() {
    for(const b of this.bubbles) {
      if(b.key)continue;
      const j=this.jobs.find(j=>!j.bubbleId&&j.textKey===b.textKey);
      if(j){b.key=j.key;j.bubbleId=b.id;j.displayedAt=b.displayedAt;j.closedAt=b.closedAt;}
    }
  }
  track(item) { this.prune();if(!this.jobs.some(j=>j.key===item.key))this.jobs.push({key:item.key,textKey:textKey(item.text),at:this.now(),state:'queued'});this.pair(); }
  register(id,text) {
    this.prune();if(!this.bubbles.some(b=>b.id===id))this.bubbles.push({id,textKey:textKey(text),at:this.now()});this.pair();return this.snapshot();
  }
  shown(id) { const b=this.bubbles.find(b=>b.id===id);if(b){b.displayedAt=this.now();const j=this.jobs.find(j=>j.key===b.key);if(j)j.displayedAt=b.displayedAt;} }
  closed(id) { const b=this.bubbles.find(b=>b.id===id);if(b){b.closedAt=this.now();const j=this.jobs.find(j=>j.key===b.key);if(j)j.closedAt=b.closedAt;} }
  finish(key,state='done') { const j=this.jobs.find(j=>j.key===key);if(j&&!TERMINAL.has(j.state)){j.state=state;j.audioEndedAt=this.now();} }
  cancelAll() { for(const j of this.jobs)if(!TERMINAL.has(j.state))this.finish(j.key,'cancelled'); }
  async waitUntilShown(key, timeoutMs=12000) {
    const start=this.now();
    while(this.enabled()&&this.now()-start<timeoutMs) {
      const j=this.jobs.find(j=>j.key===key);
      if(!j||j.displayedAt||j.closedAt||TERMINAL.has(j.state))break;
      if(!j.bubbleId&&this.now()-start>500)break;
      await new Promise(resolve=>setTimeout(resolve,80));
    }
    const j=this.jobs.find(j=>j.key===key);if(j&&!TERMINAL.has(j.state)){j.state='playing';j.audioStartedAt=this.now();}
  }
  snapshot() {
    this.prune();this.pair();
    return {enabled:!!this.enabled(),bubbles:this.bubbles.map(b=>{const j=this.jobs.find(j=>j.key===b.key);return {id:b.id,state:j?.state||'pending',at:b.at,displayedAt:b.displayedAt,closedAt:b.closedAt,audioStartedAt:j?.audioStartedAt,audioEndedAt:j?.audioEndedAt};})};
  }
}
