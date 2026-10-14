import test from 'node:test';
import assert from 'node:assert/strict';
import { rememberReply, restoreReplies, replyProgress } from '../src/reply-receipts.js';
import { SoftVoiceWorld } from '../src/world.js';

const now = Date.parse('2026-10-14T18:39:13+08:00');
const entry = (seq, patch = {}) => ({ tool: 'pet_say', mod: 'desktop-pet', run: 'r-test', seq, call: `call_${seq}`,
  ts: '2026-10-14T18:38:43+08:00', args: { script: '【开心】这个问题已经回答过了。' }, receipt: '已开始显示,这段约 3 秒。', ...patch });

test('handoff preserves the actual successful answer even before the context split', () => {
  const replies = rememberReply([], entry(1), now);
  assert.match(replyProgress(replies, now), /这个问题已经回答过了/);
  assert.match(replyProgress(replies, now), /不是新的用户请求/);
  assert.match(replyProgress(replies, now), /再次询问/);
  assert.match(replyProgress(replies, now), /不证明音频/);
});
test('failed, missing, expired and future receipts are not reported as delivered', () => {
  for (const patch of [{failed:true},{receipt:''},{ts:'invalid'},{ts:'2026-10-14T18:00:00+08:00'},{ts:'2026-10-14T19:00:00+08:00'}])
    assert.deepEqual(rememberReply([], entry(1,patch),now), []);
});
test('receipt IDs deduplicate; distinct repetitions and a bounded tail remain evidence', () => {
  let replies = rememberReply([],entry(1),now);
  assert.equal(rememberReply(replies,entry(1),now).length,1);
  for(let i=2;i<=5;i++)replies=rememberReply(replies,entry(i),now);
  assert.equal(replies.length,3);assert.match(replies[0].key,/call_3/);
  assert.deepEqual(restoreReplies(JSON.parse(JSON.stringify(replies)),now),replies);
  assert.deepEqual(restoreReplies(replies,now+11*60_000),[]);
});
test('disabled speech still records successful desktop text and failed calls never enter progress', () => {
  const w = new SoftVoiceWorld({cfg:{},dataDir:'.'});
  const current={...entry(1),ts:new Date().toISOString()};
  w.onToolCall(current);assert.equal(w.recentReplies.length,1);assert.equal(w.queue.length,0);
  w.onToolCall({...current,seq:2,failed:true});assert.equal(w.recentReplies.length,1);
  assert.match(w.envPromptVars()['softVoice.recentReplies'],/这个问题已经回答过了/);
});
test('prefix rebuild synchronizes the last tool result without duplicate audio', () => {
  const w = new SoftVoiceWorld({cfg:{},dataDir:'.'});
  w.tailer={poll(){w.onToolCall({...entry(1),ts:new Date().toISOString()})}};
  w.envPromptVars();w.envPromptVars();assert.equal(w.recentReplies.length,1);assert.equal(w.queue.length,0);
});
