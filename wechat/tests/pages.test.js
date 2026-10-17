const test=require('node:test'),assert=require('node:assert/strict');
const {boot,page,event}=require('./helpers');
test('all 12 pages initialize with bundled demo data',async()=>{
 boot();
 for(const name of ['home','schedule','grades','campus','profile','exams','rooms','plan','notices','login','privacy','browser-sync']){
  const p=page(name);if(p.onShow)await p.onShow();
  assert.ok(p.data || name==='privacy',name);
  if(p.onUnload)p.onUnload();
 }
});
test('new installs default to real mode with no fabricated user data',()=>{
 const {app,storage}=boot('real');storage.delete('superjlu.mode');app.onLaunch();
 assert.equal(app.globalData.mode,'real');assert.equal(app.globalData.snapshot.courses.length,0);assert.equal(app.globalData.snapshot.grades.length,0);
});
test('week controls, list layout and detail use real page handlers',()=>{
 boot();const p=page('schedule');p.onShow();p.setData({week:1});p.render();
 p.changeWeek(event({delta:-1}));assert.equal(p.data.week,1);
 p.changeWeek(event({delta:1}));assert.equal(p.data.week,2);
 p.layout(event({layout:'list'}));assert.equal(p.data.layout,'list');
 assert.ok(p.data.courses.length);p.detail(event({id:0}));
});
test('search does not change aggregate and selection saves independently',()=>{
 const {storage}=boot();const p=page('grades');p.onShow();const before=p.data.summary.average;
 p.search(event({},'数学'));assert.equal(p.data.summary.average,before);assert.ok(p.data.visible.length<p.grades.length);
 const key=p.data.visible[0].key;p.toggle(event({key}));assert.equal(p.selected[key],false);
 assert.equal(storage.get('superjlu.selection.demo')[key],false);assert.equal(storage.has('superjlu.selection.real'),false);
});
test('import preview does not overwrite official grades or infer GPA',()=>{
 const {storage}=boot();const p=page('grades');p.onShow();const count=p.grades.length;
 storage.set('superjlu.import.demo',[{key:'import1',name:'导入课程',score:'90',credit:3,point:null}]);p.showImport();
 assert.equal(p.data.summary.gpa,'—');assert.equal(p.grades.length,1);
 p.school();assert.equal(p.grades.length,count);assert.equal(p.data.source,'school');
});
test('room demo filters seat capacity, validation retains no bogus real data',async()=>{
 boot();const p=page('rooms');p.onShow();p.seats(event({},'100'));await p.query();assert.equal(p.data.rooms.length,1);assert.equal(p.data.rooms[0].seats,120);
 p.seats(event({},'3000'));await p.query();assert.equal(p.data.busy,false);
});
test('program course status filter operates on bundled rows',()=>{
 boot();const p=page('plan');p.onShow();p.filter(event({filter:'在修'}));assert.ok(p.data.courses.length);assert.ok(p.data.courses.every(c=>c.status==='在修'));
});
test('privacy consent is required before school credentials are submitted',async()=>{
 boot();const p=page('login');await p.start();assert.match(p.data.error,/隐私/);assert.equal(p.started,undefined);
});
test('school login failure clears password and displays error',async()=>{
 const {storage}=boot('real');const p=page('login');p.setData({agreed:true,username:'test',password:'never-store'});
 const api=require('../miniprogram/services/api'),old=api.request;
 api.request=async()=>{throw new Error('network unavailable');};
 try{await p.start();assert.equal(p.data.password,'');assert.equal(p.data.busy,false);assert.match(p.data.error,/network/);assert.equal(storage.get('superjlu.consent'),true);}
 finally{api.request=old;}
});
test('real offline cache remains real and never changes to demo',async()=>{
 const {app}=boot('real');app.globalData.snapshot={courses:[],grades:[],updated:'2026-10-15'};
 const d=await app.load();assert.equal(d.updated,'2026-10-15');assert.equal(app.globalData.mode,'real');assert.equal(app.globalData.offline,true);
});
