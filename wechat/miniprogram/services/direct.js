const {probe}=require('./school/cas'),{SmsSchoolClient:SchoolClient}=require('./school/sms'),{SchoolData}=require('./school/data'),{failure}=require('./school/http'),store=require('./store');
let client=new SchoolClient(),data=new SchoolData(client),pendingSync=null;
function reset(){client.clear();client=new SchoolClient();data=new SchoolData(client);pendingSync=null;}
async function exclusive(fn) {
  if(client.busy)throw failure('上一个学校请求仍在处理，请稍候','BUSY');
  const current=client;current.busy=true;try{return await fn();}finally{current.busy=false;}
}
async function request(path,method='POST',body={}) {
  if(!wx.getStorageSync('superjlu.consent'))throw failure('请先阅读并同意隐私说明','CONSENT_REQUIRED');
  if(path==='/api/logout'){if(require('../config').transport==='hybrid')await require('./api').cloudRequest('/api/cas/clear');reset();store.clear();return {ok:true};}
  if(path==='/api/login/cancel'){client.cancel();return {ok:true};}
  if(path==='/api/session')return {logged_in:client.alive(),state:client.alive()?'ok':'missing',transport:'direct'};
  if(path==='/api/data'){client.requireLogin();return store.read('real');}
  if(path==='/api/login/start'||path==='/api/login/sms/start')return exclusive(async()=>{
    // Discard the previous account's cached records before a new binding attempt.
    store.clear();if(typeof getApp==='function'){const app=getApp();app.globalData.snapshot=store.empty();app.globalData.schoolLoggedIn=false;}
    data=new SchoolData(client);return path==='/api/login/sms/start'?client.startSms(body.phone):client.start(body.username,body.password);
  });
  if(path==='/api/login/sms/captcha')return exclusive(()=>client.smsCaptcha());
  if(path==='/api/login/sms/send')return exclusive(()=>client.sendSms(body.captcha));
  if(path==='/api/login/sms/verify')return exclusive(()=>client.verifySms(body.sms_code));
  if(path==='/api/login/sms/choose')return exclusive(()=>client.chooseSmsAccount(body.index));
  if(path==='/api/login/captcha')return exclusive(()=>client.captcha());
  if(path==='/api/login/send_code')return exclusive(()=>client.sendCode(body.captcha));
  if(path==='/api/login/verify')return exclusive(()=>client.verify(body.wechat_code));
  if(path==='/api/notices')return exclusive(()=>data.notices(body));
  if(path==='/api/rooms/buildings')return exclusive(()=>data.buildings(body.campus));
  if(path==='/api/rooms')return exclusive(()=>data.rooms(body));
  throw failure('当前直连模式未支持此操作','UNSUPPORTED_OPERATION');
}
function sync(){
  if(!wx.getStorageSync('superjlu.consent'))return Promise.reject(failure('请先阅读并同意隐私说明','CONSENT_REQUIRED'));
  if(!pendingSync){
    const task=exclusive(async()=>{const result=await data.refresh(store.read('real'));store.write('real',result);return result;});
    pendingSync=task;
    task.then(()=>{if(pendingSync===task)pendingSync=null;},()=>{if(pendingSync===task)pendingSync=null;});
  }
  return pendingSync;
}
module.exports={request,sync,reset,probe:()=>probe('mobile_login'),hasSession:()=>client.alive(),diagnostics:()=>client.lastQueryIssue||null};
