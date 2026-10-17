const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {boot,page,event}=require('./helpers');
const {parse}=require('../miniprogram/services/phone-sync');
const bookmark=require('../miniprogram/data/phone-bookmark');
const origin='https://iedu.jlu.edu.cn';
function fixture(){const t=new Date().toISOString();return {version:1,origin,capturedAt:t,data:{courses:[{name:'测试课程',teacher:'测试教师',location:'教一101',weekday:1,start:1,end:2,weeks:[1,2]}],grades:[],exams:[],calendar:{},periods:{},completion:null,updated:t,module_updated:{courses:t},failures:[]}};}
const encode=p=>'SUPERJLU-PHONE-1\n'+JSON.stringify(p);
function browserHarness({badOrigin=false,denyTerm=false,denyGrades=false}={}){
 const all=[],requests=[],alerts=[],copies=[];
 function element(tag){const e={tag,children:[],setAttribute(){},appendChild(v){this.children.push(v);if(v.tag==='iframe')queueMicrotask(()=>v.onload());return v;},remove(){this.removed=true;},focus(){},select(){}};all.push(e);return e;}
 const document={createElement:element,documentElement:element('html'),getElementById:id=>all.find(e=>e.id===id&&!e.removed)};
 const rows={dqxnxq:[{DM:'2026-2027-1'}],cxxszhxqkb:[{KCM:'测试课程',SKXQ:1,KSJC:1,JSJC:2,SKZC:'110',SKJS:'测试教师/123',JASMC:'教一101',XH:'private-student-id'}],
  xscjcx:[{KCM:'测试课程',XF:3,ZCJ:'90',XFJD:4,XNXQDM:'2026-2027-1',XH:'private-student-id'}],cxxsksap:[{KCM:'测试考试',KSSJMS:'2026-10-18 08:00-10:00',XNXQDM:'2026-2027-1'}],
  cxxljc:[{XQKSRQ:'2026-09-01',ZZC:20,ZJXZC:18}],jc:[{DM:1,XXXQ:'01',KSSJ:'08:00',JSSJ:'08:45'}],rxylgpacxcx:[{PJJD:'3.90'}],
  grpyfacx:[{XH:'private-student-id',PYFADM:'private-plan-id',PYFAMC:'测试培养方案'}],cxxsscfa:[{XH:'private-student-id',PYFADM:'private-plan-id',YQXF:150,WCXF:90}],cxscfakz:[{KZM:'必修',YQXF:60,WCXF:30}],cxscfakzkc:[{KCM:'测试课程',KCDM:'code',XF:3,ZCJ:'90'}]};
 const context={document,location:{origin:badOrigin?'https://example.test':origin,pathname:'/jwapp/sys/wdkb/*default/index.do'},navigator:{clipboard:{writeText:async v=>copies.push(v)}},alert:v=>alerts.push(v),URLSearchParams,AbortController,Date,console,setTimeout,clearTimeout,queueMicrotask,
  fetch:async(url,options)=>{requests.push({url,options});const key=url.split('/').pop().slice(0,-3);return {ok:!(denyGrades&&key==='xscjcx'),status:denyGrades&&key==='xscjcx'?401:200,text:async()=>JSON.stringify(denyTerm&&key==='dqxnxq'?{code:'#E2140100001',msg:'非法的页面跳转.'}:{datas:{[key]:{rows:rows[key]||[],totalSize:(rows[key]||[]).length}}})};}};
 return {all,requests,alerts,copies,async run(){await vm.runInNewContext(decodeURIComponent(bookmark.slice('javascript:'.length)).replace(/^void/,''),context);}};
}
test('generated Safari bookmark reads school-only live endpoints and exports selected academic data through a user click',async()=>{
 const h=browserHarness();await h.run();assert.ok(h.requests.length>=10);assert.ok(h.requests.every(r=>r.url.startsWith(origin+'/jwapp/sys/')&&r.options.credentials==='same-origin'&&r.options.referrer.startsWith(origin+'/jwapp/sys/')));
 const area=h.all.find(e=>e.tag==='textarea');assert.ok(area);assert.equal(area.value.includes('private-student-id'),false);assert.equal(area.value.includes('private-plan-id'),false);assert.equal(h.copies.length,0);
 const result=parse(area.value);assert.equal(result.snapshot.courses[0].name,'测试课程');assert.equal(result.snapshot.grades.length,1);assert.equal(result.snapshot.exams.length,1);assert.equal(result.snapshot.calendar.first_monday,'2026-08-31');assert.deepEqual(result.snapshot.failures,[]);
 await h.all.find(e=>e.tag==='button'&&e.textContent.startsWith('复制本次')).onclick();assert.equal(h.copies[0],area.value);
});
test('Safari bookmark refuses other origins and never exports a rejected school response as success',async()=>{
 const other=browserHarness({badOrigin:true});await other.run();assert.equal(other.requests.length,0);assert.equal(other.alerts.length,1);
 const denied=browserHarness({denyTerm:true});await denied.run();assert.equal(denied.all.some(e=>e.tag==='textarea'),false);assert.ok(denied.all.some(e=>String(e.textContent).includes('#E2140100001')));assert.equal(denied.copies.length,0);
});
test('a failed optional browser module is explicitly empty while successful courses remain importable',async()=>{
 const h=browserHarness({denyGrades:true});await h.run();const result=parse(h.all.find(e=>e.tag==='textarea').value);assert.equal(result.snapshot.courses.length,1);assert.equal(result.snapshot.grades.length,0);assert.ok(result.snapshot.failures.includes('grades'));
});
test('phone packet validation rejects stale, oversized, malformed and incomplete snapshots without executing text',()=>{
 const p=fixture();assert.equal(parse(encode(p)).preview.courses,1);
 const stale=structuredClone(p);stale.capturedAt=new Date(Date.now()-31*60000).toISOString();assert.throws(()=>parse(encode(stale)),/30 分钟/);
 const future=structuredClone(p);future.capturedAt=new Date(Date.now()+6*60000).toISOString();assert.throws(()=>parse(encode(future)),/设备时间/);
 assert.throws(()=>parse(bookmark),/完整结果/);assert.throws(()=>parse('SUPERJLU-PHONE-1\n'+'x'.repeat(1024*1024)),/完整结果/);
 const malformed=structuredClone(p);malformed.data.courses[0].weekday=8;assert.throws(()=>parse(encode(malformed)),/数值/);
 const missing=structuredClone(p);missing.data.module_updated={};assert.throws(()=>parse(encode(missing)),/没有成功读取课表/);
 const extra=structuredClone(p);extra.secret='private-token';extra.data.courses[0].student='private-id';assert.equal(JSON.stringify(parse(encode(extra))).includes('private-'),false);
});
test('phone import previews without writes, requires consent and confirmation, then replaces all old account data',async()=>{
 const {app,storage,calls}=boot('real');const p=page('browser-sync'),old={courses:[{name:'old account'}],grades:[{name:'old grade'}],updated:'old'};storage.set('superjlu.cache.real',old);storage.set('superjlu.selection.real',{old:true});
 wx.getClipboardData=o=>o.success({data:encode(fixture())});p.paste();assert.equal(p.data.preview.courses,1);assert.equal(storage.get('superjlu.cache.real').updated,'old');p.apply();assert.match(p.data.error,/同意/);
 p.agree(event({},['local']));p.apply();assert.equal(storage.get('superjlu.cache.real').updated,'old');calls.findLast(c=>c[0]==='modal')[1].success({confirm:true});
 assert.equal(app.globalData.snapshot.courses[0].name,'测试课程');assert.equal(app.globalData.snapshot.grades.length,0);assert.equal(app.globalData.schoolLoggedIn,false);assert.equal(storage.has('superjlu.selection.real'),false);assert.equal(p.packet,null);
 const data=await app.load();assert.equal(data.connectionSource,'phone-browser');await assert.rejects(app.load(true),e=>e.code==='PHONE_BROWSER_REQUIRED');
 p.done();assert.equal(calls.at(-1)[1].url,'/pages/schedule/index');
});
test('reopening imported phone data needs no cloud, CAS session, or automatic clipboard access',async()=>{
 const {app,storage,calls}=boot('real');storage.set('superjlu.cache.real',parse(encode(fixture())).snapshot);const config=require('../miniprogram/config');config.transport='hybrid';
 try{app.onLaunch();assert.equal(app.globalData.directNetworkCheck,undefined);const data=await app.load();assert.equal(data.courses.length,1);const profile=page('profile');profile.onShow();await profile.refresh();assert.equal(calls.at(-1)[1].url,'/pages/browser-sync/index');}finally{config.transport='http';}
});
