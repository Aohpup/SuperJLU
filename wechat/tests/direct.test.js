const test=require('node:test'),assert=require('node:assert/strict');
const {strEnc}=require('../miniprogram/services/school/tpass');
const {CookieJar,SchoolHttp,resolveUrl}=require('../miniprogram/services/school/http');
const {SchoolClient,probe,CAS,IEDU}=require('../miniprogram/services/school/cas');
const {SchoolData,course,grades,calendar,periods}=require('../miniprogram/services/school/data');
const {boot}=require('./helpers');
const image=()=>{const b=new Uint8Array(80);b.set([137,80,78,71]);return b.buffer;};
const login='<form id="loginForm" action="/tpass/login?service=https%3A%2F%2Fiedu.jlu.edu.cn%2F"><input name="lt" value="LT-fixture"><input value="e1s1" name="execution"></form>';
const second='<input name="lt" value="LT-second"><input name="execution" value="e1s2"><input name="WxCode">';
function network(fn){require('../miniprogram/config').transport='direct';const calls=[];global.wx={arrayBufferToBase64:b=>Buffer.from(b).toString('base64'),request:o=>{calls.push(o);queueMicrotask(()=>{try{const r=fn(o,calls.length);o.success({statusCode:200,header:{},...r});}catch(e){o.fail({errMsg:e.message});}});return {onHeadersReceived(){}};}};return calls;}

test('native TPASS encryption matches seven pinned upstream vectors',()=>{
 for(const v of require('./tpass-vectors.json'))assert.equal(strEnc(v.text),v.expected);
});

test('school cookies respect host/path, deletion and parent-domain scope',()=>{
 const jar=new CookieJar();jar.set('session=a; Path=/tpass',CAS+'/login');jar.set('session=deep; Path=/tpass/login',CAS+'/login');
 jar.set('sso=b; Domain=.jlu.edu.cn; Path=/',CAS+'/login');jar.set('evil=c; Domain=edu.cn; Path=/',CAS+'/login');
 assert.equal(jar.forUrl(CAS+'/login'),'session=deep; session=a; sso=b');assert.equal(jar.forUrl(IEDU+'/'),'sso=b');
 assert.equal(jar.forUrl('https://cas.jlu.edu.cn/tpass-other'),'sso=b');
 jar.set('session=; Max-Age=0; Path=/tpass/login',CAS+'/login');assert.equal(jar.value('session',CAS+'/login'),'a');
 jar.remove('session',CAS+'/');assert.equal(jar.value('session',CAS+'/login'),'');
 jar.set('expired=x; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/',CAS+'/login');assert.equal(jar.value('expired',CAS+'/login'),'');
});

test('redirects carry matching cookies, switch POST to GET and normalize relative paths',async()=>{
 assert.equal(resolveUrl('../../info/1/2.htm','https://csw.jlu.edu.cn/index/list/a.htm'),'https://csw.jlu.edu.cn/info/1/2.htm');
 assert.throws(()=>resolveUrl('https://example.com/collect',CAS+'/login'),e=>e.code==='UNTRUSTED_REDIRECT');
 const calls=network((o,n)=>n===1?{statusCode:302,cookies:['cas=only; Path=/'],header:{Location:IEDU+'/?ticket=fixture'}}:{data:'ok'});
 const http=new SchoolHttp();await http.request(CAS+'/login',{method:'POST',data:'rsa=fixture',headers:{Referer:'forbidden',Authorization:'forbidden'}});
 assert.equal(calls.length,2);assert.equal(calls[1].method,'GET');assert.equal(calls[1].data,undefined);assert.equal(calls[1].header.Cookie,undefined);assert.equal(calls[0].header.Referer,undefined);
});

test('cross-host 307 never forwards a login form and cancellation ignores late cookies',async()=>{
 const calls=network(()=>({statusCode:307,header:{location:IEDU+'/'}}));const http=new SchoolHttp();
 await assert.rejects(http.request(CAS+'/login',{method:'POST',data:'rsa=fixture'}),e=>e.code==='UNTRUSTED_REDIRECT');assert.equal(calls.length,1);
 let deliver;wx.request=o=>{deliver=o.success;return {};};const pending=http.request(CAS+'/login');http.clear();deliver({statusCode:200,cookies:['old=late; Path=/'],data:login});
 await assert.rejects(pending,e=>e.code==='LOGIN_CANCELLED');assert.equal(http.jar.forUrl(CAS+'/login'),'');
});
test('raw cookie scope survives a normalized SDK cookie array and empty final headers',async()=>{
 require('../miniprogram/config').transport='direct';let received;
 global.wx={request:o=>{queueMicrotask(()=>{received({header:{'Set-Cookie':'JSESSIONID=fixture; Path=/jwapp; HttpOnly'}});o.success({statusCode:200,header:{'Set-Cookie':''},cookies:['JSESSIONID=fixture'],data:'portal'});});return {onHeadersReceived:cb=>{received=cb;}};}};
 const h=new SchoolHttp();await h.request(IEDU+'/jwapp/sys/emaphome/portal/index.do');
 assert.equal(h.jar.forUrl(IEDU+'/jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do'),'JSESSIONID=fixture');
});

test('password, image captcha and school WeChat code complete the direct CAS flow',async()=>{
 const calls=network((o,n)=>{
  if(n===1){assert.equal(o.header.Cookie,'last_select_type=password_login');return {data:login,cookies:['tpasssessionid=fixture; Path=/tpass']};}
  if(n===2){const f=new URLSearchParams(o.data);assert.equal(f.get('rsa'),strEnc('studenttest-passwordLT-fixture'));assert.equal(f.get('sl'),'0');assert.equal(f.get('execution'),'e1s1');assert.ok(!o.data.includes('test-password'));return {data:second};}
  if(n===3)return {data:image()};
  if(n===4){assert.ok(o.url.includes('/recheckcode?code=ABCD'));return {data:'',cookies:['recheck_mobile_error_info=success; Path=/']};}
  if(n===5){const f=new URLSearchParams(o.data);assert.equal(f.get('WxCode'),'123456');assert.equal(f.get('code'),'ABCD');assert.equal(f.get('lt'),'LT-second');assert.equal(f.get('rsa'),'');return {statusCode:302,header:{location:IEDU+'/?ticket=fixture'}};}
  assert.equal(o.header.Cookie,undefined);return {data:'<html>教务门户</html>',cookies:['_WEU=fixture; Path=/']};
 });
 const c=new SchoolClient(),r=await c.start('student@mails.jlu.edu.cn','test-password');assert.equal(r.step,'need_second_factor');assert.match(r.captcha,/^data:image\/png;base64,/);assert.equal(c.alive(),false);
 await c.sendCode('ABCD');await c.verify('123456');assert.equal(c.alive(),true);assert.equal(c.pending,null);assert.equal(calls.length,6);
 c.clear();assert.equal(c.alive(),false);assert.equal(c.http.jar.items.length,0);
});

test('unexpected CAS pages and unconfirmed send results cannot become authenticated',async()=>{
 network((o,n)=>({data:n===1?login:'<html>maintenance</html>'}));const c=new SchoolClient();await assert.rejects(c.start('student','test-password'),e=>e.code==='SCHOOL_LOGIN_FAILED');assert.equal(c.alive(),false);
 c.pending={lt:'fixture',execution:'e1s2'};c.started=Date.now();c.http.jar.set('recheck_mobile_error_info=success; Path=/',CAS+'/login');
 network(()=>({data:''}));await assert.rejects(c.sendCode('ABCD'),e=>e.code==='SCHOOL_VERIFICATION_FAILED');assert.equal(c.sent,false);
});

test('manual redirect headers are read and domain failures produce actionable text',async()=>{
 let n=0;global.wx={request:o=>{n++;let cb;queueMicrotask(()=>{if(n===1){cb({header:{Location:CAS+'/login'}});o.success({statusCode:302,data:''});}else o.success({statusCode:200,data:login});});return {onHeadersReceived:f=>{cb=f;}};}};
 const r=await new SchoolHttp().request(IEDU+'/');assert.equal(r.url,CAS+'/login');
 wx.request=o=>{o.fail({errMsg:'request:fail url not in domain list'});return {};};await assert.rejects(probe(),e=>e.code==='SCHOOL_DOMAIN_REQUIRED'&&e.message.includes('iedu.jlu.edu.cn')&&e.message.includes('刷新'));
 wx.request=o=>{o.fail({errMsg:'request:fail net::ERR_PROXY_CONNECTION_FAILED'});return {};};await assert.rejects(probe(),e=>e.code==='SCHOOL_PROXY');
});

test('query pagination collects complete personal data and rejects oversized or malformed responses',async()=>{
 const c=new SchoolClient();c.finish();let pages=0;c.http.request=async()=>({status:200,url:IEDU+'/',body:{datas:{rowsKey:{rows:Array.from({length:++pages===1?200:1},(_,i)=>({n:i})),totalSize:201}}}});
 assert.equal((await c.query('cjcx','modules/cjcx/xscjcx.do',{},'rowsKey',true)).length,201);assert.equal(pages,2);
 c.http.request=async()=>({status:200,url:IEDU+'/',body:{datas:{rowsKey:{rows:[],totalSize:2001}}}});await assert.rejects(c.query('x','y',{},'rowsKey',true),e=>e.code==='SCHOOL_DATA_LIMIT');
 c.http.request=async()=>({status:200,url:IEDU+'/',body:'<html>error</html>'});await assert.rejects(c.query('x','y',{},'rowsKey'),e=>e.code==='SCHOOL_FORMAT_CHANGED');
 c.http.request=async()=>({status:200,url:CAS+'/login',body:login});await assert.rejects(c.query('x','y',{},'rowsKey'),e=>e.code==='SCHOOL_SESSION_EXPIRED');assert.equal(c.alive(),false);
});

test('anonymous probe requires a complete password form, not just HTTP 200',async()=>{
 network(()=>({data:login}));assert.equal((await probe()).ok,true);
 for(const html of ['<html>maintenance</html>','<form id="loginForm"></form>']) {
  network(()=>({data:html}));await assert.rejects(probe(),e=>e.code==='SCHOOL_FORMAT_CHANGED');
 }
});

test('WeChat web OAuth is explained without executing scripts or sending a password',async()=>{
 const html='<script>window.location.assign("https://cas.jlu.edu.cn/tpass/login?wxRedirect=true" + encodeURIComponent(window.location.hash));</script>';
 const calls=network(()=>({data:html}));wx.getDeviceInfo=()=>({platform:'devtools'});
 await assert.rejects(probe(),e=>e.code==='SCHOOL_WECHAT_WEB_LOGIN'&&e.message.includes('已选择密码登录'));
 await assert.rejects(new SchoolClient().start('student','test-password'),e=>e.code==='SCHOOL_WECHAT_WEB_LOGIN');
 assert.ok(calls.every(o=>o.method==='GET'&&!o.header['User-Agent']));
 const phone=network(()=>({data:login}));wx.getDeviceInfo=()=>({platform:'ios'});
 assert.equal((await probe()).ok,true);assert.ok(phone.every(o=>!o.header['User-Agent']));
 assert.equal(phone[0].header.Cookie,undefined);assert.equal(phone[1].header.Cookie,'last_select_type=password_login');
 network(()=>({data:html}));wx.getDeviceInfo=()=>({platform:'android'});
 await assert.rejects(probe(),e=>e.code==='SCHOOL_WECHAT_WEB_LOGIN'&&e.message.includes('尚未取得'));
});

test('school mappings retain academic fields without storing raw student identity',()=>{
 const raw={XH:'synthetic-id',KCM:'算法',SKJS:'教师/001',SKXQ:'2',KSJC:'1',JSJC:'2',SKZC:'101',JASMC:'教室',XF:'3',ZCJ:'90',JD:'3.7',XNXQDM:'2026-2027-1'};
 assert.deepEqual(course(raw).weeks,[1,3]);assert.equal(grades([raw])[0].jw_point,3.7);assert.ok(!JSON.stringify([course(raw),grades([raw])]).includes('synthetic-id'));
 assert.equal(calendar({XQKSRQ:'20260901'},'2026-2027-1').first_monday,'2026-08-31');assert.deepEqual(periods([{XXXQ:'01',DM:'1',KSSJ:'0800',JSSJ:'08:45',SFSY:'1'}]),{1:['08:00','08:45']});
});

test('partial school failures preserve the corresponding real cache',async()=>{
 const prior={...require('../miniprogram/services/store').empty(),grades:[{name:'旧真实成绩'}],module_updated:{grades:'old'}};
 const c={requireLogin(){},enter:async()=>{},query:async(app,path)=>{if(path.includes('dqxnxq'))return [{DM:'2026-2027-1'}];if(path.includes('cxxszhxqkb'))return [{KCM:'算法',SKXQ:2,KSJC:1,JSJC:2,SKZC:'1'}];throw new Error('fixture module failure');}};
 const result=await new SchoolData(c).refresh(prior);assert.equal(result.courses[0].name,'算法');assert.deepEqual(result.grades,prior.grades);assert.equal(result.module_updated.grades,'old');assert.ok(result.failures.includes('grades'));assert.ok(result.updated);
});

test('direct API never calls the cloud backend or wx.login and logout clears local cache',async()=>{
 const {storage}=boot('real'),config=require('../miniprogram/config'),api=require('../miniprogram/services/api');config.transport='direct';api.reset();
 try {
  await assert.rejects(api.request('/api/login/start','POST',{username:'student',password:'test-password'}),e=>e.code==='CONSENT_REQUIRED');
  storage.set('superjlu.consent',true);storage.set('superjlu.cache.real',{grades:[{name:'old'}]});
  wx.request=o=>{assert.ok(o.url.startsWith('https://cas.jlu.edu.cn/'));queueMicrotask(()=>o.success({statusCode:200,header:{},data:login}));return {};};
  // Password is rejected by the synthetic login page, while the prior account cache is removed.
  await assert.rejects(api.request('/api/login/start','POST',{username:'student',password:'test-password'}),e=>e.code==='SCHOOL_LOGIN_FAILED');
  assert.equal(storage.has('superjlu.cache.real'),false);assert.equal((await api.request('/api/session','GET')).logged_in,false);
  storage.set('superjlu.cache.real',{courses:[]});await api.request('/api/logout');assert.equal(storage.has('superjlu.cache.real'),false);assert.equal(api.hasSession(),false);
 } finally {api.reset();config.transport='http';}
});

test('authenticated binding stays usable when initial academic sync is temporarily unavailable',async()=>{
 const {app,calls}=boot('real'),p=require('./helpers').page('login'),api=require('../miniprogram/services/api'),original=api.request;
 api.request=async path=>{assert.equal(path,'/api/session');return {logged_in:true};};app.load=async()=>{throw new Error('temporary school outage');};
 try{await p.finish();assert.equal(app.globalData.schoolLoggedIn,true);assert.equal(p.data.step,'success');assert.equal(p.data.syncError,'temporary school outage');assert.equal(app.globalData.lastSyncError,'temporary school outage');}
 finally{api.request=original;}
});

test('a newer network check cannot be overwritten by an older failing check',async()=>{
 const {app}=boot('real'),direct=require('../miniprogram/services/direct'),original=direct.probe,pending=[],config=require('../miniprogram/config');
 direct.probe=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
 try{
  const older=app.checkSchoolNetwork(),newer=app.checkSchoolNetwork();
  pending[1].resolve({ok:true,message:'new connection works'});await newer;
  pending[0].reject(Object.assign(new Error('old domain rejection'),{code:'SCHOOL_DOMAIN_REQUIRED'}));await older;
  assert.equal(app.globalData.directNetwork.ok,true);
  config.transport='direct';const p=require('./helpers').page('home');app.globalData.directNetworkCheck=Promise.resolve({ok:false,message:'stale domain message'});
  await p.onShow();assert.equal(p.data.network,'new connection works');
 }finally{direct.probe=original;config.transport='http';}
});
