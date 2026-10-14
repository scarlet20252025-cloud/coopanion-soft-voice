"""Optional, reversible pet-page hooks for the standalone voice extension (official 0.1.4)."""
import argparse
import json
from pathlib import Path
import shutil

MARKER = 'SOFT_VOICE_BUBBLE_BRIDGE'
HOOKS = [
    ("const host = window.petHost || null;", "const host = window.petHost || null;\n// SOFT_VOICE_BUBBLE_BRIDGE: all synchronization logic is in the extension client.\nlet voiceBubbleSync = null;\nvoid import('./soft-voice-bubble-sync.js').then(({ createVoiceBubbleSync }) => { voiceBubbleSync = createVoiceBubbleSync(); }).catch(() => {});"),
    ("case 'say': dropAsks();", "case 'say': voiceBubbleSync?.register(m.id, m.beats); dropAsks();"),
    ("function closeBubble() {", "function closeBubble() {\n  if (item?.kind === 'say') voiceBubbleSync?.closed(item.id);"),
    ("if (it.beatDone && T < it.holdUntil) return;", "if (it.beatDone) {\n        const synced = voiceBubbleSync?.hold(it.id, it.i === it.beats.length - 1);\n        if (synced === true || (synced !== false && T < it.holdUntil)) return;\n      }"),
    ("if (b.text) { openBubble('say', '<p class=\"b-text\"></p>'); sfx.pop(); }", "if (b.text) { openBubble('say', '<p class=\"b-text\"></p>'); if (it.i === 0) voiceBubbleSync?.shown(it.id); sfx.pop(); }"),
]

def patched(source):
    if MARKER in source:
        return source
    result = source
    for before, after in HOOKS:
        if result.count(before) != 1:
            raise ValueError('Pet page changed; cannot safely apply bubble hook: ' + before[:60])
        result = result.replace(before, after, 1)
    return result

def install_bridge(package, restore=False):
    package = Path(package).resolve()
    if json.loads((package / 'package.json').read_text(encoding='utf-8-sig'))['version'] != '0.1.4':
        raise ValueError('This bridge is verified for cortico-world-desktop-pet 0.1.4 only')
    page = package / 'web' / 'pet-app.js'
    backup = page.with_name('pet-app.js.soft-voice-original')
    current = page.read_text(encoding='utf-8')
    if restore:
        original = backup.read_text(encoding='utf-8')
        if current != patched(original):
            raise ValueError('Pet page has unrelated edits; restoration would overwrite them')
        page.write_text(original, encoding='utf-8')
    else:
        result = patched(current)
        if MARKER not in current and not backup.exists():
            shutil.copy2(page, backup)
        client = Path(__file__).with_name('bubble-client.js')
        shutil.copy2(client, package / 'web' / 'soft-voice-bubble-sync.js')
        page.write_text(result, encoding='utf-8')
    return page

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--desktop-pet', required=True)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print('Bubble bridge ready:', install_bridge(args.desktop_pet, args.restore))
