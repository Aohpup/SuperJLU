const test=require('node:test'),assert=require('node:assert/strict');
const {boot,page}=require('./helpers');
const config=require('../miniprogram/config'),api=require('../miniprogram/services/api');
const {SmsSchoolClient}=require('../miniprogram/services/school/sms');
const {SchoolHttp}=require('../miniprogram/services/school/http');
const CAS='https://cas.jlu.edu.cn/tpass',IEDU='https://iedu.jlu.edu.cn';
const login='<form id="loginForm" action="/tpass/login?service=https%3A%2F%2Fiedu.jlu.edu.cn%2F"><input name="lt" value="LT-fixture"><input name="execution" value="e1s1"></form>';
function setup(){
 const {storage}=boot('real');config.transport='hybrid';storage.set('superjlu.consent',true);storage.set('superjlu.hybridConsent',true);api.reset();
 wx.base64ToArrayBuffer=s=>Uint8Array.from(Buffer.from(s,'base64')).buffer;
 wx.arrayBufferToBase64=b=>Buffer.from(b).toString('base64');
 return storage;
}
test('hybrid SMS uses cloud CAS and redeems its ticket and queries only on the campus device',async()=>{
 setup();const cloud=[],device=[];let casAuthenticated=false;
 wx.cloud={init(){},async callContainer(o){
  cloud.push(o);
  if(o.path==='/api/wechat/cloud-login')return {statusCode:200,data:{ok:true,token:'opaque',expires_in:7200}};
  assert.equal(o.header.Authorization,'Bearer opaque');
  if(o.path==='/api/cas/close')return {statusCode:200,data:{ok:true}};
  assert.equal(o.path,'/api/cas/request');assert.ok(o.data.url.startsWith(CAS));
  let value={statusCode:200,header:{},cookies:[],flow:'own-cas-flow',data:'',binary:!!o.data.binary};
  if(o.data.url.includes('/code?'))value.data=Buffer.from([255,216,...Array(100).fill(0)]).toString('base64');
  else if(o.data.url.includes('method=isPhone2'))value.data=JSON.stringify({success:true,userinfo:[{ID_NUMBER:'fixture',USER_NAME:'测试'}]});
  else if(o.data.url.includes('method=isPhone')){value.cookies=['mobile_error_info=success; Path=/tpass'];value.data='';}
  else if(o.data.method==='POST'){casAuthenticated=true;value.statusCode=302;value.header.Location=IEDU+'/?ticket=ST-synthetic';}
  else if(casAuthenticated){value.statusCode=302;value.header.Location=(new URL(o.data.url).searchParams.get('service')||IEDU+'/')+'?ticket=ST-synthetic-app';}
  else value.data=login;
  return {statusCode:200,data:{ok:true,...value}};
 }};
 wx.request=o=>{device.push(o);assert.ok(o.url.startsWith(IEDU));o.success({statusCode:200,header:{},cookies:['MOD_AUTH_CAS=academic; Path=/'],data:o.method==='POST'?JSON.stringify({datas:{rows:{rows:[{KCM:'fixture'}]}}}):'<html>campus application</html>'});};
 const c=new SmsSchoolClient();
 try{
  assert.equal((await c.startSms('13800000000')).step,'need_sms_code');
  assert.equal(device.length,0);assert.ok(cloud[1].data.headers.Cookie.includes('last_select_type=mobile_login'));
  await c.sendSms('abcd');assert.equal((await c.verifySms('123456')).step,'success');
  assert.equal(device[0].url,IEDU+'/?ticket=ST-synthetic');assert.equal(device[0].method,'GET');
  await c.enter('wdkb');assert.equal((await c.query('wdkb','modules/example.do',{},'rows')).length,1);
  assert.ok(device.at(-1).header.Cookie.includes('MOD_AUTH_CAS=academic'));
  assert.equal(cloud.filter(o=>o.path==='/api/wechat/cloud-login').length,1);
 }finally{c.clear();await new Promise(r=>setImmediate(r));api.reset();config.transport='http';}
 assert.ok(cloud.some(o=>o.path==='/api/cas/close'&&o.data.flow==='own-cas-flow'));
});
test('hybrid requires renewed cloud consent before transmitting authentication requests',async()=>{
 const storage=setup();storage.delete('superjlu.hybridConsent');let calls=0;
 wx.cloud={init(){},async callContainer(){calls++;throw new Error('must not send');}};
 try{await assert.rejects(new SchoolHttp().request(CAS+'/login'),/同意云端认证/);assert.equal(calls,0);}finally{api.reset();config.transport='http';}
});
test('hybrid cancellation discards late authentication data and closes the orphaned cloud flow',async()=>{
 setup();let deliver;const closed=[];
 wx.cloud={init(){},async callContainer(o){
  if(o.path.endsWith('cloud-login'))return {statusCode:200,data:{token:'t',expires_in:7200}};
  if(o.path==='/api/cas/close'){closed.push(o.data.flow);return {statusCode:200,data:{ok:true}};}
  return new Promise(r=>{deliver=r;});
 }};
 const h=new SchoolHttp();
 try{
  const pending=h.request(CAS+'/login');await new Promise(r=>setImmediate(r));h.clear();
  deliver({statusCode:200,data:{ok:true,statusCode:200,data:login,flow:'late-flow',cookies:['mobile_error_info=success; Path=/tpass']}});
  await assert.rejects(pending,e=>e.code==='LOGIN_CANCELLED');await new Promise(r=>setImmediate(r));
  assert.equal(h.casFlow,'');assert.equal(h.jar.items.length,0);assert.deepEqual(closed,['late-flow']);
 }finally{api.reset();config.transport='http';}
});
test('hybrid login exposes both original password and SMS methods with accurate cloud consent',async()=>{
 setup();const p=page('login');
 try{assert.equal(p.data.hybrid,true);assert.equal(p.data.sms,true);p.setData({phone:'13800000000'});p.passwordLogin();assert.equal(p.data.sms,false);assert.equal(p.data.phone,'');p.setData({password:'sensitive'});p.smsLogin();assert.equal(p.data.password,'');assert.equal(p.data.sms,true);}finally{api.reset();config.transport='http';}
});
test('EMAP source rejection does not repeat CAS authorization or report an expired login',async()=>{
 setup();const c=new SmsSchoolClient();c.finish();let calls=0;
 c.enter=async()=>{throw new Error('source rejection must not trigger another login');};
 c.http.request=async()=>{calls++;return {status:200,url:IEDU+'/',body:JSON.stringify({code:'#E2140100001',msg:'非法的页面跳转.'})};};
 try{
  await assert.rejects(c.query('wdkb','modules/test.do',{},'term'),e=>e.code==='SCHOOL_SOURCE_REJECTED'&&e.message.includes('#E2140100001'));
  assert.equal(calls,1);assert.equal(c.alive(),true);assert.equal(c.lastQueryIssue.serverMessage,'非法的页面跳转.');
 }finally{api.reset();config.transport='http';}
});

test('EMAP entry exchanges for the exact application and initializes the portal before queries',async()=>{
 setup();const c=new SmsSchoolClient(),urls=[];c.finish();
 c.http.request=async(url)=>{urls.push(url);return {status:200,url:IEDU+'/jwapp/sys/wdkb/*default/index.do',body:'<html>application</html>'};};
 try{await c.enter('wdkb');assert.equal(urls.length,2);assert.equal(new URL(urls[0]).searchParams.get('service'),IEDU+'/jwapp/sys/wdkb/*default/index.do');assert.equal(urls[1],IEDU+'/jwapp/sys/emaphome/portal/index.do');}finally{api.reset();config.transport='http';}
});
test('query renews application authorization once and retains only response structure on persistent failure',async()=>{
 setup();const c=new SmsSchoolClient();c.finish();let attempts=0,entries=0;
 c.enter=async()=>{entries++;};
 c.http.request=async()=>({status:200,url:IEDU+'/',body:JSON.stringify(++attempts===1?{code:403,message:'unauthorized'}:{datas:{term:{rows:[{DM:'fixture'}]}}})});
 try{
  assert.equal((await c.query('wdkb','modules/test.do',{},'term')).length,1);assert.equal(entries,1);assert.equal(attempts,2);
  entries=0;attempts=0;c.http.request=async()=>{attempts++;return {status:200,url:IEDU+'/',body:JSON.stringify({code:'UNTRUSTED_REFERER',msg:'请求来源异常，ticket=ST-private 13800000000',message:'private-student-message',student:'private-value'})};};
  await assert.rejects(c.query('wdkb','modules/test.do',{},'term'),e=>e.code==='SCHOOL_FORMAT_CHANGED'&&e.message.includes('wdkb/term'));
  assert.equal(entries,1);assert.equal(attempts,2);assert.equal(JSON.stringify(c.lastQueryIssue).includes('private'),false);
  assert.equal(c.lastQueryIssue.serverCode,'UNTRUSTED_REFERER');assert.ok(c.lastQueryIssue.serverMessage.includes('[数字已隐藏]'));
 }finally{api.reset();config.transport='http';}
});
