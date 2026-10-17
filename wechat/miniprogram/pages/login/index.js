const api=require('../../services/api'),ui=require('../../utils/ui'),config=require('../../config');
Page({
 data:{agreed:false,username:'',password:'',phone:'',smsCode:'',accounts:[],captchaCode:'',wechatCode:'',step:'idle',captcha:'',busy:false,error:'',syncError:'',countdown:0,direct:['direct','hybrid'].includes(config.transport),sms:['direct','hybrid'].includes(config.transport),hybrid:config.transport==='hybrid',endpoint:config.apiBase,network:'',checking:false},
 onShow(){if(this.data.direct&&getApp().globalData.directNetwork)this.setData({network:getApp().globalData.directNetwork.message});},
 async checkNetwork(){
  if(this.data.checking||this.data.busy)return;this.setData({checking:true,network:'正在检查校园网连接…'});
  if(this.data.hybrid){if(!this.data.agreed){this.setData({checking:false,network:'请先阅读并同意下方隐私说明'});return;}wx.setStorageSync('superjlu.consent',true);wx.setStorageSync('superjlu.hybridConsent',true);}
  try{const result=await getApp().checkSchoolNetwork();this.setData({network:result.message});}
  catch(e){this.setData({network:e.message});}finally{this.setData({checking:false});}
 },
 onUnload(){clearInterval(this.timer);if(this.started && this.data.step!=='success')api.request('/api/login/cancel').catch(()=>{});},
 agree(e){this.setData({agreed:e.detail.value.includes('agree')});},
 smsLogin(){if(!this.data.busy)this.setData({sms:true,password:'',error:''});},
 passwordLogin(){if(!this.data.busy)this.setData({sms:false,phone:'',error:''});},
 field(e){this.setData({[e.currentTarget.dataset.field]:e.detail.value});},
 async run(fn){
  if(this.data.busy)return;
  this.setData({busy:true,error:''});
  try{await fn();}catch(e){this.setData({error:e.message});}
  finally{this.setData({busy:false});}
 },
 async start(){
  if(!this.data.agreed)return this.setData({error:'请先阅读并同意隐私说明'});
  if(this.data.sms){if(!/^0?1\d{10}$/.test(this.data.phone.trim()))return this.setData({error:'请填写学校已绑定的手机号'});}
  else if(!this.data.username.trim() || !this.data.password)return this.setData({error:'请填写邮箱前缀和密码'});
  return this.run(async()=>{
   this.started=true;
   wx.setStorageSync('superjlu.consent',true);
   if(this.data.hybrid)wx.setStorageSync('superjlu.hybridConsent',true);
   if(getApp().globalData.mode!=='real')getApp().setMode('real');
   let result;
   try{result=await api.request(this.data.sms?'/api/login/sms/start':'/api/login/start','POST',this.data.sms?{phone:this.data.phone.trim()}:{username:this.data.username,password:this.data.password});}
   finally{this.setData({password:''});}
   this.setData({step:result.step,captcha:result.captcha||''});
   if(result.step==='success')await this.finish();
  });
 },
 async captcha(){return this.run(async()=>{const r=await api.request(this.data.sms?'/api/login/sms/captcha':'/api/login/captcha');this.setData({captcha:r.captcha,captchaCode:'',wechatCode:'',smsCode:'',accounts:[],step:this.data.sms?'need_sms_code':'need_second_factor'});});},
 async send(){
  return this.run(async()=>{
   const r=await api.request(this.data.sms?'/api/login/sms/send':'/api/login/send_code','POST',{captcha:this.data.captchaCode});
   this.setData({step:this.data.sms?'sms_sent':'code_sent',countdown:this.data.sms?(r.retry_after||120):60});
   clearInterval(this.timer);
   this.timer=setInterval(()=>{const next=this.data.countdown-1;this.setData({countdown:Math.max(0,next)});if(next<=0)clearInterval(this.timer);},1000);
  });
 },
 resend(){return ['code_sent','sms_sent'].includes(this.data.step)?this.captcha():this.send();},
 async verify(){return this.run(async()=>{
  let r;try{r=await api.request(this.data.sms?'/api/login/sms/verify':'/api/login/verify','POST',this.data.sms?{sms_code:this.data.smsCode}:{wechat_code:this.data.wechatCode});}
  finally{this.setData({smsCode:'',wechatCode:''});}
  if(this.data.sms&&r.step==='choose_sms_account'){this.setData({step:r.step,accounts:r.accounts});return;}
  if(this.data.sms&&r.step!=='success')throw new Error('学校尚未完成短信登录，请重试');
  await this.finish();
 });},
 async chooseAccount(e){return this.run(async()=>{const r=await api.request('/api/login/sms/choose','POST',{index:Number(e.currentTarget.dataset.index)});this.setData({accounts:[]});if(r.step!=='success')throw new Error('学校尚未完成登录，请重试');await this.finish();});},
 async finish(){
  const session=await api.request('/api/session','GET');
  getApp().globalData.schoolLoggedIn=!!session.logged_in;
  if(!session.logged_in)throw new Error('学校会话已过期，请重新绑定教务');
  let syncError='';try{await getApp().load(true);}catch(e){syncError=e.message;}
  getApp().globalData.lastSyncError=syncError;
  clearInterval(this.timer);this.setData({step:'success',syncError,password:'',phone:'',smsCode:'',accounts:[],wechatCode:'',captchaCode:'',captcha:'',countdown:0});
 },
 async retrySync(){return this.run(async()=>{try{await getApp().load(true);getApp().globalData.lastSyncError='';this.setData({syncError:''});}catch(e){getApp().globalData.lastSyncError=e.message;this.setData({syncError:e.message});throw e;}});},
 restart(){clearInterval(this.timer);this.setData({step:'idle',captcha:'',captchaCode:'',wechatCode:'',smsCode:'',accounts:[],countdown:0,error:''});api.request('/api/login/cancel').catch(()=>{});},
 done(){wx.switchTab({url:'/pages/home/index'});},
 privacy(){wx.navigateTo({url:'/pages/privacy/index'});}
});
