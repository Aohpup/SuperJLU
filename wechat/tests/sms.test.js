const test=require('node:test'),assert=require('node:assert/strict');
const {SmsSchoolClient}=require('../miniprogram/services/school/sms');
const {strEnc}=require('../miniprogram/services/school/tpass');
const {boot,page,event}=require('./helpers');
const CAS='https://cas.jlu.edu.cn/tpass',IEDU='https://iedu.jlu.edu.cn';
const login='<form id="loginForm" action="/tpass/login?service=https%3A%2F%2Fiedu.jlu.edu.cn%2F"><input name="lt" value="LT-sms"><input name="execution" value="e1s1"></form>';
function network(fn){const calls=[];global.wx={arrayBufferToBase64:b=>Buffer.from(b).toString('base64'),request:o=>{calls.push(o);queueMicrotask(()=>{try{o.success({statusCode:200,header:{},...fn(o,calls.length)});}catch(e){o.fail({errMsg:e.message});}});return {};}};return calls;}
function image(){const a=new Uint8Array(80);a.set([137,80,78,71]);return a.buffer;}

test('SMS flow obtains an image before sending, verifies the code and submits sl=1',async()=>{
 const calls=network((o,n)=>{
  if(n===1){assert.equal(o.header.Cookie,'last_select_type=mobile_login');return {data:login};}
  if(n===2)return {data:image()};
  if(n===3){const u=new URL(o.url);assert.equal(u.searchParams.get('method'),'isPhone');assert.equal(u.searchParams.get('phone'),'13800000000');assert.equal(u.searchParams.get('code'),'ABCD');return {data:image(),cookies:['mobile_error_info=success; Path=/tpass']};}
  if(n===4){assert.equal(new URL(o.url).searchParams.get('phoneCode'),'123456');return {data:JSON.stringify({success:true,userinfo:[{ID_NUMBER:'fixture-account',USER_NAME:'测试'}]})};}
  if(n===5){const f=new URLSearchParams(o.data);assert.equal(o.method,'POST');assert.equal(f.get('sl'),'1');assert.equal(f.get('rsa'),strEnc('fixture-account123456LT-sms'));assert.equal(f.get('code'),'ABCD');assert.equal(f.get('pl'),'6');assert.equal(f.has('phone'),false);assert.equal(f.has('phoneCode'),false);return {statusCode:302,header:{Location:IEDU+'/?ticket=fixture'}};}
  assert.equal(o.header.Cookie,undefined);return {data:'<html>教务门户</html>'};
 });
 const c=new SmsSchoolClient();assert.equal((await c.startSms('13800000000')).step,'need_sms_code');assert.equal(calls.length,2);assert.equal(c.alive(),false);
 assert.equal((await c.sendSms('ABCD')).retry_after,120);await assert.rejects(c.sendSms('ABCD'),e=>e.code==='RATE_LIMIT');
 assert.equal((await c.verifySms('123456')).step,'success');assert.equal(c.alive(),true);assert.equal(c.pending,null);assert.equal(c.captchaCode,'');assert.equal(calls.length,6);
});

test('missing login parameters never cause an SMS to be sent',async()=>{
 const calls=network(()=>({data:'<script>window.location.assign("/tpass/login?wxRedirect=true")</script>'}));
 const c=new SmsSchoolClient();await assert.rejects(c.startSms('13800000000'),e=>e.code==='SCHOOL_WECHAT_WEB_LOGIN'&&e.message.includes('短信验证码'));
 assert.equal(calls.length,1);assert.equal(c.pending,null);await assert.rejects(c.sendSms('ABCD'),e=>e.code==='LOGIN_EXPIRED');
});

test('SMS send requires a fresh success cookie and cooldown survives restarting',async()=>{
 const c=new SmsSchoolClient();c.pending={kind:'sms',phone:'13800000000',accounts:[]};c.started=Date.now();c.http.jar.set('mobile_error_info=success; Path=/tpass',CAS+'/mobilecode');
 network(()=>({data:image()}));await assert.rejects(c.sendSms('ABCD'),e=>e.code==='SCHOOL_SMS_SEND_FAILED');assert.equal(c.sent,false);
 c.clear();c.pending={kind:'sms',phone:'13800000000',accounts:[]};c.started=Date.now();await assert.rejects(c.sendSms('ABCD'),e=>e.code==='RATE_LIMIT');
});

test('multiple SMS accounts require an explicit valid choice, and cancellation erases codes',async()=>{
 const c=new SmsSchoolClient();c.pending={kind:'sms',phone:'13800000000',lt:'LT-sms',execution:'e1s1',post:CAS+'/login',accounts:[]};c.started=Date.now();c.sent=true;c.captchaCode='ABCD';
 const calls=network(()=>({data:{success:true,userinfo:[{ID_NUMBER:'synthetic-account-one',USER_NAME:'甲'},{ID_NUMBER:'synthetic-account-two',USER_NAME:'乙'}]}}));
 const r=await c.verifySms('123456');assert.equal(r.step,'choose_sms_account');assert.equal(calls.length,1);assert.ok(!JSON.stringify(r).includes('synthetic-account'));assert.equal(c.alive(),false);
 await assert.rejects(c.chooseSmsAccount(5),e=>e.code==='INVALID_INPUT');assert.equal(calls.length,1);
 c.cancel();assert.equal(c.pending,null);assert.equal(c.captchaCode,'');await assert.rejects(c.chooseSmsAccount(0),e=>e.code==='LOGIN_EXPIRED');
});

test('bad SMS codes and malformed account results never authenticate',async()=>{
 for(const obj of [{success:false,errcode:'phone_code_error'},{success:'true',userinfo:[{ID_NUMBER:'fixture'}]},{success:true,userinfo:[]},{success:true,userinfo:[{ID_NUMBER:17}]}]){
  const c=new SmsSchoolClient();c.pending={kind:'sms',phone:'13800000000',accounts:[]};c.started=Date.now();c.sent=true;c.captchaCode='ABCD';
  const calls=network(()=>({data:obj}));await assert.rejects(c.verifySms('123456'));assert.equal(c.alive(),false);assert.equal(calls.length,1);assert.equal(c.pending.phoneCode,'');
 }
});

test('SMS page sends no password, waits for consent and presents account selection',async()=>{
 const {storage}=boot('real'),p=page('login'),api=require('../miniprogram/services/api'),old=api.request,calls=[];
 p.setData({direct:true,sms:true,phone:'13800000000'});await p.start();assert.match(p.data.error,/隐私/);
 api.request=async(path,method,body)=>{calls.push({path,body});if(path.endsWith('/start'))return {step:'need_sms_code',captcha:'data:image/png;base64,fixture'};return {step:'choose_sms_account',accounts:[{index:0,label:'测试账号'}]};};
 try{
  p.setData({agreed:true});await p.start();assert.equal(calls[0].path,'/api/login/sms/start');assert.deepEqual(calls[0].body,{phone:'13800000000'});assert.equal(p.data.step,'need_sms_code');
  p.setData({smsCode:'123456'});await p.verify();assert.equal(p.data.step,'choose_sms_account');assert.equal(p.data.smsCode,'');assert.equal(storage.has('phone'),false);assert.equal(storage.get('superjlu.consent'),true);
 }finally{api.request=old;}
});
