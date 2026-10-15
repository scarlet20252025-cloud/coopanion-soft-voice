export const ID = 'soft-voice';
const K = `worlds.${ID}`;

export const DEFAULTS = Object.freeze({ enabled: false, volume: 65, pollMs: 180, maxQueue: 3, maxAgeSec: 45, autoRecover: true, lowPowerMode: false, idleUnloadSec: 300, keepWorker: true, lowMemoryMiB: 1536, syncBubbles: true, playbackMode: 'auto', deviceName: '', autoCheckUpdates:true, autoDiagnostics:true, autoSubmitIssues:false,cacheRepeated:true });
export const CONFIG_GROUP = {
  id: `world:${ID}`, owner: `world:${ID}`,
  schema: { type: 'object', title: '轻量化本地语音引擎', properties: {
    [`${K}.cacheRepeated`]: {type:'boolean',title:'重复语句缓存（最多 4 MiB，休眠时清空）',default:true,'x-hot':true},
    [`${K}.autoDiagnostics`]: {type:'boolean',title:'自动保存故障与连续性能瓶颈报告（仅本地）',default:true,'x-hot':true},
    [`${K}.autoSubmitIssues`]: {type:'boolean',title:'自动提交脱敏 Issue 到 Asryto 仓库（需本机 GitHub 登录）',default:false,'x-hot':true},
    [`${K}.autoCheckUpdates`]: { type:'boolean',title:'自动检查更新（启动后检查，每 24 小时一次）',default:true,'x-hot':true },
    [`${K}.deviceName`]: { type: 'string', title: 'Vulkan 推理设备（空值为自动核显）', default: '', maxLength: 256 },
    [`${K}.playbackMode`]: { type: 'string', title: '播放策略（自动 / 优先连续 / 优先开口）', enum: ['auto','buffered','stream'], default: 'auto', 'x-hot': true },
    [`${K}.syncBubbles`]: { type: 'boolean', title: '气泡同步（默认随语音启用，可单独关闭）', default: true, 'x-hot': true },
    [`${K}.lowPowerMode`]: { type: 'boolean', title: '低功耗模式（空闲或内存紧张时自动休眠）', 'x-hot': true },
    [`${K}.keepWorker`]: { type: 'boolean', title: '休眠时保留工作进程（关闭则完全退出）', 'x-hot': true },
    [`${K}.lowMemoryMiB`]: { type: 'integer', title: '空闲内存低于此值时休眠（MiB，0 关闭）', minimum: 0, maximum: 4096, 'x-hot': true },
    [`${K}.idleUnloadSec`]: { type: 'integer', title: '自动休眠秒数（0 关闭空闲计时，建议 300）', minimum: 0, maximum: 3600, 'x-hot': true },
    [`${K}.volume`]: { type: 'integer', title: '音量（0 为静音，跳过合成）', minimum: 0, maximum: 100, 'x-hot': true },
    [`${K}.maxQueue`]: { type: 'integer', title: '待说队列上限（满时丢弃最旧）', minimum: 1, maximum: 12, 'x-hot': true },
    [`${K}.maxAgeSec`]: { type: 'integer', title: '排队超过多少秒不再朗读', minimum: 5, maximum: 180, 'x-hot': true },
    [`${K}.autoRecover`]: { type: 'boolean', title: '内存恢复后自动重新加载', 'x-hot': true },
    [`${K}.pollMs`]: { type: 'integer', title: '消息检查间隔（毫秒）', minimum: 80, maximum: 2000, 'x-hot': true }
  }}
};

export function volumePercent(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return DEFAULTS.volume;
  return Math.round(Math.max(0, Math.min(100, value)));
}

export function configValues(cfg) {
  return Object.fromEntries(Object.keys(CONFIG_GROUP.schema.properties).map(path => {
    const key = path.slice(K.length + 1);
    return [key, cfg[key] ?? DEFAULTS[key]];
  }));
}

export function validateConfigPatch(values) {
  if (!values || typeof values !== 'object' || Array.isArray(values)) throw new Error('配置必须是对象');
  const patch = {};
  for (const [key, value] of Object.entries(values)) {
    const property = CONFIG_GROUP.schema.properties[`${K}.${key}`];
    if (!property) throw new Error(`未知配置: ${key}`);
    if (property.enum && !property.enum.includes(value)) throw new Error(`${property.title} 的选项无效`);
    if (property.maxLength && (typeof value!=='string' || value.length>property.maxLength)) throw new Error(`${property.title} 的长度无效`);
    if ((property.type === 'integer' && (!Number.isInteger(value))) ||
      (property.type === 'number' && (typeof value !== 'number' || !Number.isFinite(value))) ||
      (property.type === 'boolean' && typeof value !== 'boolean') ||
      (property.type === 'string' && typeof value !== 'string')) throw new Error(`${property.title} 的值无效`);
    if ((property.minimum != null && value < property.minimum) ||
      (property.maximum != null && value > property.maximum)) throw new Error(`${property.title} 超出范围`);
    if (property.multipleOf && Math.abs(value / property.multipleOf - Math.round(value / property.multipleOf)) > 1e-7)
      throw new Error(`${property.title} 的步长必须是 ${property.multipleOf}`);
    patch[key] = value;
  }
  return patch;
}
