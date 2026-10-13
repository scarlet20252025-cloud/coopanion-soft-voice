/** Turn a desktop-pet pet_say script into TTS text without action markers. */
export function speechText(script) {
  if (typeof script !== 'string') return '';
  return script
    .replace(/【[^】]*】/g, '')
    .replace(/<[^<>\r\n]*>|＜[^＜＞\r\n]*＞/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\s*\n\s*/g, ' ')
    .trim();
}

export function petSayFromEntry(entry) {
  if (!entry || typeof entry !== 'object') return null;
  if (entry.tool !== 'pet_say' || entry.failed === true) return null;
  if (entry.mod && entry.mod !== 'desktop-pet') return null;
  const script = entry.args && typeof entry.args === 'object' ? entry.args.script : null;
  const text = speechText(script);
  if (!text) return null;
  if (typeof entry.run !== 'string' || !Number.isSafeInteger(entry.seq) || entry.seq < 1) return null;
  return {
    key: JSON.stringify([entry.run, entry.seq, entry.call ?? '']),
    run: entry.run,
    seq: entry.seq,
    text,
    script: String(script)
  };
}
