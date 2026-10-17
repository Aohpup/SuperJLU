const test=require('node:test'),assert=require('node:assert/strict');
const {boot}=require('./helpers');
test('simultaneous API requests share one wx.login and never return session_key',async()=>{
 const {storage}=boot('real');storage.set('superjlu.consent',true);
 const api=require('../miniprogram/services/api');api.reset();let count=0;
 wx.login=({success})=>{count++;success({code:'wx-code'});};
 wx.request=({url,success,header})=>{
  if(url.endsWith('/api/wechat/login'))success({statusCode:200,data:{ok:true,token:'opaque',expires_in:7200}});
  else {assert.equal(header.Authorization,'Bearer opaque');success({statusCode:200,data:{ok:true,courses:[]}});}
 };
 await Promise.all([api.request('/api/data','GET'),api.request('/api/session','GET')]);assert.equal(count,1);api.reset();
});
test('school expiry is not retried as a wx login',async()=>{
 const {storage}=boot('real');storage.set('superjlu.consent',true);const api=require('../miniprogram/services/api');api.reset();
 let logins=0,requests=0;wx.login=({success})=>{logins++;success({code:'wx-code'});};
 wx.request=({url,success})=>{if(url.endsWith('/api/wechat/login'))success({statusCode:200,data:{ok:true,token:'t',expires_in:7200}});else{requests++;success({statusCode:401,data:{ok:false,error:'expired',code:'SCHOOL_SESSION_EXPIRED'}});}};
 await assert.rejects(api.request('/api/refresh'),e=>e.code==='SCHOOL_SESSION_EXPIRED');assert.equal(logins,1);assert.equal(requests,1);api.reset();
});
test('HTTP loopback is rejected on a physical phone',async()=>{
 const config=require('../miniprogram/config'),previous=config.apiBase;
 const {storage}=boot('real');config.apiBase='http://127.0.0.1:8787';storage.set('superjlu.consent',true);const api=require('../miniprogram/services/api');api.reset();
 wx.getDeviceInfo=()=>({platform:'ios'});wx.login=({success})=>success({code:'wx-code'});
 try{await assert.rejects(api.request('/api/data'),/手机运行需要/);}finally{api.reset();config.apiBase=previous;}
});
test('native CloudRun transport uses platform identity without wx.login',async()=>{
 const {storage}=boot('real');storage.set('superjlu.consent',true);
 const config=require('../miniprogram/config'),api=require('../miniprogram/services/api');config.transport='cloudrun';config.cloudEnv='test-environment';config.cloudService='test-service';api.reset();
 const paths=[];wx.cloud={init(){},callContainer:async options=>{paths.push(options.path);assert.equal(options.config.env,'test-environment');assert.equal(options.header['X-WX-SERVICE'],'test-service');return {statusCode:200,data:options.path.endsWith('cloud-login')?{ok:true,token:'opaque-cloud-token',expires_in:7200}:{ok:true,courses:[]}};}};
 try{await api.request('/api/data','GET');assert.deepEqual(paths,['/api/wechat/cloud-login','/api/data']);}finally{config.transport='http';config.cloudEnv='';config.cloudService='';api.reset();}
});
