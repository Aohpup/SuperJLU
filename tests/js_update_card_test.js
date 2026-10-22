// 「版本」卡片：版本号不被状态文字覆盖、已是最新提示、失败原因进技术信息。node tests/js_update_card_test.js
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(__dirname+'/../jlu_toolkit/ui_page.py','utf8').split('\n');
const pick=n=>{const i=src.findIndex(l=>l.startsWith(n));if(i<0)throw Error('missing '+n);return src[i]};
const names=['const UPD_TXT=','function updVer(','function updMsg(','function updWhy(','function updRender(','async function updCheck('];
function run(resp,bridge){
 const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{id,hidden:id==='#upd-tech',innerHTML:'',textContent:'',classList:{toggle(){}}});return nodes.get(id)};
 node('#upd-v').textContent='';const toasts=[];
 const ctx=vm.createContext({UPD:null,$:node,esc:s=>String(s??''),toast:(m,bad)=>toasts.push([m,!!bad]),localStorage:{getItem:()=>null},
  document:{querySelector:()=>null},setTimeout,clearTimeout,AbortController,window:{SuperJLU:bridge},SuperJLU:bridge,
  fetch:async()=>{if(resp instanceof Error)throw resp;return{json:async()=>resp}}});
 vm.runInContext(names.map(pick).join('\n')+'\nthis.T={updVer,updCheck,updMsg};',ctx);
 return {T:ctx.T,node,toasts};
}
(async()=>{
 // 已是最新：版本号保留，提示「当前已是最新版本哦！」
 let r=run({ok:true,current:'1.2.0',latest:'1.2.0',has_update:false});
 r.T.updMsg('正在检查…');await r.T.updCheck(true);
 assert.equal(r.node('#upd-v').textContent,'1.2.0');
 assert.match(r.node('#upd-m').innerHTML,/已是最新版本/);
 assert.deepEqual(r.toasts,[['当前已是最新版本哦！',false]]);
 assert.equal(r.node('#upd-tech').hidden,true);
 // 查不到：原因进技术信息，版本号仍在
 r=run({ok:true,current:'1.2.0',has_update:false,unavailable:true,reason:'native-api OSError: x'});
 await r.T.updCheck(true);
 assert.equal(r.node('#upd-v').textContent,'1.2.0');
 assert.equal(r.node('#upd-tech').hidden,false);assert.match(r.node('#upd-why').textContent,/native-api/);
 assert.equal(r.toasts[0][1],true);assert.notEqual(r.toasts[0][0],'当前已是最新版本哦！');
 // 本地接口挂了：用安卓桥的 versionName 兜底，错误类型与「连不上 GitHub」不同
 r=run(new TypeError('Failed to fetch'),{appVersion:()=>'1.2.0'});
 await r.T.updCheck(true);
 assert.equal(r.node('#upd-v').textContent,'1.2.0');
 assert.match(r.node('#upd-why').textContent,/^page TypeError/);
 // 空版本不会把已有版本号清空
 r=run({ok:true,current:'',has_update:false});r.node('#upd-v').textContent='1.2.0';await r.T.updCheck(false);
 assert.equal(r.node('#upd-v').textContent,'1.2.0');
 // 点「检查更新」不得再整体覆盖 #upd-s（旧 bug：清掉 #upd-v 后 updRender 抛错）
 const all=src.join('\n');assert.ok(!all.includes('$("#upd-s").textContent='));assert.ok(!all.includes('s.innerHTML=`当前版本'));
 console.log('js_update_card_test ok');
})().catch(e=>{console.error(e);process.exit(1)});
