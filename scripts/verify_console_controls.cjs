// Browser regression test for the shipped World client. Install Playwright separately.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
  const meta=JSON.parse(fs.readFileSync('world/package.json','utf8'));
  const source=fs.readFileSync(path.join('world',meta.cortico.consoleClient),'utf8');
  const css=fs.readFileSync(path.join('world',meta.cortico.consoleStyle),'utf8');
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'msedge'});
  try {
    const page=await browser.newPage({viewport:{width:1120,height:950}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.setContent('<meta charset="utf-8"><body style="margin:0;background:#12161c;color:#eee;font-family:Segoe UI,Microsoft YaHei,sans-serif"><main id="root" style="padding:24px;max-width:1100px;margin:auto"></main>');
    await page.addStyleTag({content:css});
    await page.evaluate(async source=>{
      const mod=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(source))));
      window.s={phase:'ready',accepting:true,speechEnabled:true,queueLength:0,deviceName:'NVIDIA',selectedDeviceName:'NVIDIA',availableDevices:[],
        selectedVoice:'builtin',voices:[{key:'builtin',name:'已确认音色'}],bubbleSync:{phase:'active'},
        deployment:{state:'connected',installed:true,detail:'启动校验已通过'},
        memory:{freeGiB:4.1,totalGiB:15.2,minimumGiB:2.75,recoveryGiB:3.25,layout:'progressive-kv'},
        values:{deviceName:'NVIDIA',volume:65,playbackMode:'auto',syncBubbles:true,lowPowerMode:true,autoCheckUpdates:true}};
      window.holdScan=true;window.holdSwitch=false;window.failSwitch=false;window.failSave=false;window.staleState=false;
      window.mount=async panel=>{
        window.controller?.abort();window.controller=new AbortController();
        await mod.default.panels[panel||'controls'].mount({root:document.getElementById('root'),signal:window.controller.signal,
          invoke:async(method,args=[])=>{
            if(method==='devices'){
              if(window.holdScan)await new Promise(r=>window.resolveScan=r);
              return {devices:window.s.availableDevices=[{name:'AMD',kind:'integrated'},{name:'NVIDIA',kind:'discrete'}]};
            }
            if(method==='selectDevice'){
              window.s.switchingDevice=true;window.s.deviceChange={state:'loading',startedAt:Date.now(),detail:'正在加载所选设备…'};
              if(window.holdSwitch)await new Promise(r=>window.resolveSwitch=r);
              window.s.switchingDevice=false;
              if(window.failSwitch){window.s.deviceChange={state:'error',detail:'设备切换失败，已恢复原设备配置：driver lost'};throw Error(window.s.deviceChange.detail);}
              window.s.selectedDeviceName=window.s.values.deviceName=args[0];window.s.deviceName=args[0];
              window.s.deviceChange={state:'success',detail:'已选择并保存：'+args[0]+(window.s.speechEnabled?'；语音已重新加载。':'；下次开启语音时使用。')};
            }
            if(method==='save'){
              if(window.failSave)throw Error('模拟磁盘写入失败');
              Object.assign(window.s.values,args[0]);
            }
            const snapshot=structuredClone(window.s);
            if(method==='state'&&window.staleState){window.staleState=false;await new Promise(r=>window.resolveState=r);}
            return snapshot;
          },interval:fn=>{window.tick=fn;},ui:{button:(label,{onClick})=>{const b=document.createElement('button');b.textContent=label;b.onclick=onClick;return b;}}});
      };await window.mount();
    },source);
    const select=page.getByLabel('Vulkan 推理设备',{exact:true});
    await page.waitForFunction(()=>document.querySelector('[aria-label="Vulkan 推理设备"]').value==='NVIDIA');
    assert.match(await page.locator('.device-saved').innerText(),/NVIDIA/); // Before enumeration resolves.
    await page.evaluate(()=>{window.holdScan=false;window.resolveScan();});
    await page.waitForFunction(()=>document.querySelector('[aria-label="Vulkan 推理设备"]').options.length===3);
    await select.selectOption('AMD');await page.evaluate(()=>window.tick());
    assert.equal(await select.inputValue(),'AMD');assert.match(await page.locator('.device-card .field-feedback').innerText(),/待切换/);
    await page.evaluate(()=>window.holdSwitch=true);await page.getByRole('button',{name:'应用设备',exact:true}).click();
    assert.equal(await select.isDisabled(),true);assert.equal(await page.locator('.device-card .startup-progress').isVisible(),true);
    await page.evaluate(()=>window.resolveSwitch());
    await page.waitForFunction(()=>document.querySelector('.device-card .field-feedback').textContent.includes('已选择并保存：AMD'));
    await page.evaluate(async()=>{await window.mount('config');await window.mount();});
    await page.waitForFunction(()=>document.querySelector('[aria-label="Vulkan 推理设备"]').value==='AMD');
    await select.selectOption('NVIDIA');await page.evaluate(()=>{window.failSwitch=true;window.holdSwitch=false;});
    await page.getByRole('button',{name:'应用设备',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.device-card .field-feedback').textContent.includes('driver lost'));
    assert.equal(await select.inputValue(),'AMD');
    await page.evaluate(()=>window.mount());
    await page.waitForFunction(()=>document.querySelector('.device-card .field-feedback').textContent.includes('driver lost'));
    assert.equal(await select.inputValue(),'AMD');
    await page.evaluate(()=>{window.failSwitch=false;window.s.speechEnabled=false;window.s.accepting=false;});
    await select.selectOption('NVIDIA');await page.getByRole('button',{name:'应用设备',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.device-card .field-feedback').textContent.includes('下次开启语音'));
    await page.getByLabel('播放策略',{exact:true}).selectOption('buffered');
    await page.waitForFunction(()=>document.querySelector('.playback-grid').textContent.includes('已保存：播放策略 · 优先连续'));
    await page.evaluate(()=>{window.failSave=true;});await page.getByLabel('播放策略',{exact:true}).selectOption('stream');
    await page.waitForFunction(()=>document.querySelector('.playback-grid').textContent.includes('保存失败'));
    assert.equal(await page.getByLabel('播放策略',{exact:true}).inputValue(),'buffered');
    await page.evaluate(()=>{window.failSave=false;window.staleState=true;void window.tick();});
    await page.getByRole('switch',{name:'气泡同步',exact:true}).click();await page.evaluate(()=>window.resolveState());
    await page.waitForFunction(()=>document.querySelector('[aria-label="气泡同步"]').getAttribute('aria-checked')==='false');
    await page.getByLabel('重复语句缓存',{exact:true}).uncheck();
    await page.waitForFunction(()=>document.querySelector('.playback-grid').textContent.includes('已保存：重复语句缓存 · 已关闭'));
    await page.evaluate(async()=>{window.s.engineVersion='0.5.0';await window.tick();});
    assert.equal(await page.getByLabel('重复语句缓存',{exact:true}).isDisabled(),true);
    assert.match(await page.locator('.cache-option').innerText(),/更新运行包/);
    await page.evaluate(async()=>{window.s.engineVersion='0.5.1';await window.tick();});
    assert.equal(await page.getByLabel('重复语句缓存',{exact:true}).isDisabled(),false);
    const toggle=await page.getByRole('switch',{name:'气泡同步',exact:true}).boundingBox(),title=await page.locator('.feature-title strong').boundingBox();
    assert.ok(toggle.x-title.x-title.width<25,'Bubble toggle must sit beside its label');
    await page.locator('.memory-help summary').click();await page.evaluate(()=>window.tick());
    assert.equal(await page.locator('.memory-help').evaluate(e=>e.open),true);
    await page.evaluate(async()=>{window.s.lastRequestFailure={code:'generation_limit',detail:'上一段朗读达到生成上限，未完整读完；已跳过，后续消息可继续朗读。'};await window.tick();});
    assert.match(await page.locator('.request-warning').innerText(),/未完整读完/);
    assert.equal(await page.locator('.request-warning').isVisible(),true);
    await page.evaluate(async()=>{Object.assign(window.s,{speechEnabled:true,accepting:true,deviceType:'discrete',bubbleSync:{phase:'disabled'},deviceChange:{state:'success',detail:'已选择并保存：NVIDIA；语音已重新加载。'}});await window.mount();});
    await page.waitForFunction(()=>document.querySelector('.device-saved').textContent.includes('NVIDIA'));
    await page.evaluate(async()=>{window.s.updates={stage:'market_only',detail:'npm 扩展有新版，GitHub 更新包尚未同步',available:true,patchAvailable:false,requiresMarketUpdate:true,supported:false,marketplaceVersion:'0.4.5',loadedWorldVersion:'0.4.3',currentWorldVersion:'0.4.3',release:{version:'0.5.2',worldVersion:'0.4.3'}};await window.tick();});
    assert.match(await page.locator('.update-menu').textContent(),/市场扩展有新版/);
    assert.doesNotMatch(await page.locator('.update-menu').textContent(),/已是最新|源码安装/);
    await page.evaluate(async()=>{window.s.updates={stage:'partial',detail:'npm 检查失败',checkComplete:false};await window.tick();});
    assert.match(await page.locator('.update-menu').textContent(),/检查未完成/);
    await page.evaluate(async()=>{window.s.updates={stage:'current',detail:'GitHub 与 npm 均未发现更高版本',loadedWorldVersion:'0.4.6',currentWorldVersion:'0.4.6'};await window.tick();});
    assert.match(await page.locator('.update-menu').textContent(),/磁盘扩展 0.4.6/);
    fs.mkdirSync('.runtime/device-ui-feedback',{recursive:true});
    await page.screenshot({path:'.runtime/device-ui-feedback/dashboard.png',fullPage:true});
    await page.setViewportSize({width:480,height:1000});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Narrow window overflow');
    await page.screenshot({path:'.runtime/device-ui-feedback/narrow.png',fullPage:true});
    assert.equal(await page.getByRole('button',{name:'已部署',exact:true}).isVisible(),true);
    assert.equal(await page.getByRole('button',{name:'已部署',exact:true}).isDisabled(),true);
    assert.equal(await page.getByRole('link',{name:'手动部署指南 ↗',includeHidden:true}).isVisible(),false);
    await page.evaluate(async()=>{window.s.deployment={state:'missing',installed:false,detail:'尚未安装模型'};window.s.deploymentTask={phase:'idle',busy:false};await window.tick();});
    assert.equal(await page.getByRole('button',{name:'一键部署',exact:true}).isEnabled(),true);
    assert.equal(await page.getByRole('link',{name:'手动部署指南 ↗',includeHidden:true}).isVisible(),false);
    await page.evaluate(async()=>{window.s.deploymentTask={phase:'downloading',busy:true,percent:42,detail:'正在下载模型与运行环境',source:'魔搭国内镜像',bytesPerSecond:1048576};await window.tick();});
    assert.equal(await page.getByRole('button',{name:'正在部署…',exact:true}).isDisabled(),true);
    assert.equal(await page.getByLabel('模型部署进度').evaluate(e=>e.value),42);
    await page.evaluate(async()=>{await window.mount('config');await window.mount();});
    assert.equal(await page.getByLabel('模型部署进度').evaluate(e=>e.value),42);
    assert.equal(await page.getByRole('button',{name:'取消下载 / 安装',exact:true}).isVisible(),true);
    await page.evaluate(async()=>{window.s.deploymentTask={phase:'cancelled',busy:false,detail:'已取消，保留续传文件'};await window.tick();});
    assert.equal(await page.getByRole('button',{name:'重试 / 继续下载',exact:true}).isEnabled(),true);
    await page.evaluate(async()=>{window.s.deploymentTask={phase:'error',busy:false,detail:'下载失败，请重试'};await window.tick();});
    assert.equal(await page.getByRole('link',{name:'手动部署指南 ↗'}).isVisible(),true);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({ok:true,world:meta.version,savedBeforeScan:true,pageSwitchPersistence:true,pendingDraftPersistence:true,switchProgress:true,rollbackFeedback:true,saveFailureFeedback:true,stalePollIgnored:true,compactBubbleToggle:true,detailsPersist:true,narrowLayout:true}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
