// Use Cortico's launcher contract and Coopanion's existing graceful SIGTERM handler.
// No Electron patch, forced exit, guessed executable path or external launcher.
export function restartRequest(dataDir,{
 loadBoot=()=>import('cortico/boot.ts'),
 hosted=()=>process.env.ELECTRON_RUN_AS_NODE==='1'&&process.connected===true&&process.listenerCount('SIGTERM')>0,
 signal=()=>process.emit('SIGTERM'), // Windows kill(SIGTERM) can terminate abruptly; invoke the registered handler.
 schedule=fn=>{setTimeout(fn,500).unref();},
}={}){
 return async()=>{
  if(!hosted())throw Error('当前宿主不支持直接重启，请正常退出并重新打开桌宠；更新文件已保留。');
  const boot=await loadBoot();
  if(!boot.isSupervised())throw Error('未检测到自动拉起的启动器，请从桌宠托盘重启；更新文件已保留。');
  boot.requestRestart(dataDir);
  schedule(signal); // Let the confirmed panel request return before graceful shutdown.
  return {requested:true,detail:'已请求重启，正在保存并关闭当前桌宠进程，启动器随后重新加载。'};
 };
}
