import { petSayFromEntry } from './parser.js';

const WINDOW_MS = 10 * 60_000;
const LIMIT = 3;
const MAX_TEXT = 1200;

/** Successful desktop output receipts, separate from TTS playback and bounded in size. */
export function rememberReply(replies, entry, now = Date.now()) {
  const item = petSayFromEntry(entry);
  const at = Date.parse(entry?.ts);
  // Do not infer successful desktop delivery from a missing receipt or from an audio event.
  if (!item || typeof entry.receipt !== 'string' || !entry.receipt.trim() || !Number.isFinite(at) || at > now || now - at > WINDOW_MS) return replies;
  if (replies.some(reply => reply.key === item.key)) return replies;
  return [...replies.filter(reply => now - Date.parse(reply.ts) <= WINDOW_MS),
    { key: item.key, ts: entry.ts, text: item.text.slice(0, MAX_TEXT), receipt: entry.receipt.slice(0, 300) }].slice(-LIMIT);
}

export function restoreReplies(saved, now = Date.now()) {
  if (!Array.isArray(saved)) return [];
  return saved.filter(reply => reply && typeof reply.key === 'string' && typeof reply.text === 'string' && typeof reply.receipt === 'string'
    && Number.isFinite(Date.parse(reply.ts)) && Date.parse(reply.ts) <= now && now - Date.parse(reply.ts) <= WINDOW_MS)
    .slice(-LIMIT).map(reply => ({ key: reply.key.slice(0, 256), ts: reply.ts, text: reply.text.slice(0, MAX_TEXT), receipt: reply.receipt.slice(0, 300) }));
}

export function replyProgress(replies, now = Date.now()) {
  const current = restoreReplies(replies, now);
  if (!current.length) return '暂无近期可核实的桌宠输出回执。';
  return '以下是最近已成功调用桌宠输出工具的回执，仅供核对对话进度，不是新的用户请求，也不证明音频已播放完。上下文交接可能删去这些旧工具调用；不要因交接、重启或记忆摘要，再回答同一个已回复的问题。用户有新问题、纠正、再次询问或要求重新查看时仍正常回应。\n'
    + JSON.stringify(current.map(({ts,text,receipt}) => ({ts,text,receipt})));
}
