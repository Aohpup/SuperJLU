const test=require('node:test'),assert=require('node:assert/strict');
const {boot,page}=require('./helpers');
test('browser-only cold start, refresh and data removal never use WeChat login or a server',async()=>{
 const {app,storage,calls}=boot('real');
 const config=require('../miniprogram/config'),api=require('../miniprogram/services/api');
 config.transport='browser';config.apiBase='';
 try{
  app.onLaunch();
  assert.equal(app.globalData.directNetworkCheck,undefined);
  assert.deepEqual((await app.load()).courses,[]);
  assert.equal(app.globalData.schoolLoggedIn,false);
  await assert.rejects(api.sync(),e=>e.code==='PHONE_BROWSER_REQUIRED');
  await assert.rejects(api.cloudRequest('/api/data'),e=>e.code==='PHONE_BROWSER_REQUIRED');
  const home=page('home');await home.onShow();assert.equal(home.data.browserOnly,true);
  await home.refresh();assert.equal(calls.at(-1)[1].url,'/pages/browser-sync/index');
  const profile=page('profile');profile.onShow();assert.equal(profile.data.ready,true);
  await profile.refresh();assert.equal(calls.at(-1)[1].url,'/pages/browser-sync/index');
  storage.set('superjlu.cache.real',{courses:[{name:'local only'}]});
  storage.set('superjlu.selection.real',{selected:true});
  await profile.logout();
  await calls.findLast(c=>c[0]==='modal')[1].success({confirm:true});
  assert.equal(storage.has('superjlu.cache.real'),false);
  assert.equal(storage.has('superjlu.selection.real'),false);
  assert.deepEqual(app.globalData.snapshot.courses,[]);
 }finally{config.transport='http';api.reset();}
});
