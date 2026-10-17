const path=require('node:path');
const root=path.resolve(__dirname,'..');
function boot(mode='demo'){
 require('../miniprogram/config').transport='http';
 require('../miniprogram/config').apiBase='https://api.example.test';
 const storage=new Map([['superjlu.mode',mode]]);
 const calls=[];
 global.wx={
  getStorageSync:k=>storage.get(k),setStorageSync:(k,v)=>storage.set(k,JSON.parse(JSON.stringify(v))),removeStorageSync:k=>storage.delete(k),
  getDeviceInfo:()=>({platform:'devtools'}),showToast:v=>calls.push(['toast',v]),showModal:v=>calls.push(['modal',v]),
  navigateTo:v=>calls.push(['navigate',v]),switchTab:v=>calls.push(['tab',v]),stopPullDownRefresh(){},
  setClipboardData:v=>calls.push(['clipboard',v]),chooseMessageFile:v=>calls.push(['choose',v]),
  login(){throw new Error('Unexpected network login in offline test');},
  request(){throw new Error('Unexpected network request in offline test');}
 };
 let app;
 global.App=x=>{app=x;};
 const file=path.join(root,'miniprogram/app.js');delete require.cache[require.resolve(file)];require(file);
 global.getApp=()=>app;app.onLaunch();
 return {app,storage,calls};
}
function page(name){
 let result;global.Page=x=>{result=x;};
 const file=path.join(root,'miniprogram/pages',name,'index.js');delete require.cache[require.resolve(file)];require(file);
 result.data=structuredClone(result.data);
 result.setData=function(update){Object.assign(this.data,update);};
 return result;
}
const event=(dataset={},value='')=>({currentTarget:{dataset},detail:{value}});
module.exports={boot,page,event,root};
