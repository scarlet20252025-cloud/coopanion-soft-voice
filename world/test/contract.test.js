// Guards the world 6 contract the way `pnpm check:extension` does for the parts
// that can be verified without a Cortico checkout.
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const meta = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const describe = JSON.parse(readFileSync(join(root, meta.cortico.describe), 'utf8'));

test('manifest declares the current contract with the renamed WebUI fields', () => {
  assert.equal(meta.cortico.api, 6, 'world 6 is the current contract');
  assert.equal(meta.cortico.consoleClient, undefined);
  assert.equal(meta.cortico.consoleStyle, undefined);
  assert.equal(typeof meta.cortico.webUiClient, 'string');
  assert.equal(typeof meta.cortico.webUiStyle, 'string');
  assert.ok(meta.files.includes(meta.cortico.describe), 'files must ship describe.json');
  for (const key of ['webUiClient', 'webUiStyle', 'describe']) {
    assert.ok(existsSync(join(root, meta.cortico[key])), `${key} must exist: ${meta.cortico[key]}`);
  }
});

test('the definition keeps the renamed panels entry point', async () => {
  const { default: definition } = await import('../src/definition.js');
  assert.equal(typeof definition.create, 'function');
  assert.ok(!('console' in definition), 'WorldDefinition must not carry a console() field');
  const world = definition.create({ cfg: { ...definition.defaults() }, dataDir: root, botDir: root,
    persist: () => {}, requestDesktopRestart: null });
  assert.equal(typeof world.webUi, 'function');
  assert.ok(!('console' in world), 'the instance must expose webUi(), not console()');
  assert.ok(Array.isArray(world.webUi('zh').panels));
});

test('describe.json matches the definition and the envPrompt template on disk', async () => {
  const { default: definition } = await import('../src/definition.js');
  assert.deepEqual(describe.tools, [...definition.describe.tools]);
  assert.deepEqual(describe.events, [...definition.describe.events]);
  const world = definition.create({ cfg: { ...definition.defaults() }, dataDir: root, botDir: root,
    persist: () => {}, requestDesktopRestart: null });
  const docs = (world.webUi('zh').promptDocs ?? []).filter((doc) => doc.role === 'envPrompt');
  assert.equal(describe.prompts.length, docs.length);
  for (const [index, doc] of docs.entries()) {
    assert.equal(describe.prompts[index].key, doc.key);
    assert.equal(describe.prompts[index].content, readFileSync(doc.path, 'utf8'),
      'regenerate with `npm run describe` after editing the template');
  }
});

test('every panel the client mounts is declared by the world', async () => {
  const client = (await import(`../${meta.cortico.webUiClient}`)).default;
  const { default: definition } = await import('../src/definition.js');
  const world = definition.create({ cfg: { ...definition.defaults() }, dataDir: root, botDir: root,
    persist: () => {}, requestDesktopRestart: null });
  const declared = new Set(world.webUi('zh').panels.map((panel) => panel.id));
  for (const id of Object.keys(client.panels)) assert.ok(declared.has(id), `undeclared panel: ${id}`);
});
