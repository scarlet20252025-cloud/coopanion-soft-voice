// Mirrors `pnpm describe:extension` for this package: tools and events come from
// the WorldDefinition, and role=envPrompt templates are read from disk verbatim.
// The framework compares its own regenerated copy with this file, so both must
// come from the same sources.
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import definition from '../src/definition.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const scratch = join(tmpdir(), 'soft-voice-describe-mount');
const world = definition.create({
  cfg: { ...definition.defaults() },
  dataDir: scratch,
  botDir: scratch,
  persist: () => {},
  requestDesktopRestart: null
});
const docs = (world.webUi?.('zh')?.promptDocs ?? []).filter((doc) => doc.role === 'envPrompt');
const prompts = docs.map(({ key, title, role, path }) => ({
  key, title, ...(role ? { role } : {}), content: readFileSync(path, 'utf8')
}));
const file = {
  tools: [...definition.describe.tools],
  events: [...definition.describe.events],
  ...(prompts.length ? { prompts } : {})
};
writeFileSync(join(root, 'describe.json'), `${JSON.stringify(file, null, 2)}\n`, 'utf8');
console.log(`describe.json written: ${file.tools.length} tools, ${file.events.length} events, ${prompts.length} prompts`);
