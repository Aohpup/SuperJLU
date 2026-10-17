// Matches CAS login10.js mobilecode/isPhone/isPhone2 and loginBtnTrue.
// No SMS is sent until the user enters the image challenge and taps Send.
const {SchoolClient,loginFields,loginPage,attr,CAS,IEDU}=require('./cas');
const {parseUrl,resolveUrl,form,failure}=require('./http');
const {strEnc}=require('./tpass');
const endpoint=CAS+'/mobilecode';
const messages={user_not_exist:'该手机号未绑定学校账号，请先在学校统一认证中绑定密保手机',error1:'验证码获取过于频繁，请在 10 分钟后重试',error2:'已达到学校短信发送次数限制，请稍后再试',img_code_error:'图形验证码错误，请更换图片后重试',mobile_reg_error:'手机号格式错误',phone_code_error:'短信验证码错误，请重新输入',phone_code_expire:'短信验证码已过期，请重新获取'};
class SmsSchoolClient extends SchoolClient {
 constructor(){super();this.lastSmsSend=0;}
 smsPending(){this.need();if(this.pending.kind!=='sms')throw failure('请重新开始短信登录','LOGIN_EXPIRED');return this.pending;}
 async startSms(phone){
  phone=String(phone||'').trim();if(!/^0?1\d{10}$/.test(phone))throw failure('请输入学校已绑定的手机号','INVALID_INPUT');
  this.clear();this.started=Date.now();
  this.http.jar.set('last_select_type=mobile_login; Path=/tpass',CAS+'/login');
  const page=await this.http.request(CAS+'/login?service='+encodeURIComponent(IEDU+'/'));
  const f=loginFields(page,'短信验证码');
  const tag=/<form\b[^>]*\bid\s*=\s*["']loginForm["'][^>]*>/i.exec(String(page.body));
  const action=tag&&attr(tag[0],'action'),post=action?resolveUrl(action,page.url):page.url;
  if(parseUrl(post).host!=='cas.jlu.edu.cn'||parseUrl(post).path!=='/tpass/login')throw failure('学校登录表单地址异常，已停止提交','UNTRUSTED_REDIRECT');
  this.pending={kind:'sms',phone,lt:f.lt,execution:f.execution||'e1s1',post,accounts:[],phoneCode:''};
  return this.smsCaptcha();
 }
 async smsCaptcha(){
  const p=this.smsPending();p.accounts=[];p.phoneCode='';
  const r=await super.captcha();return {...r,step:'need_sms_code'};
 }
 async sendSms(captcha){
  const p=this.smsPending();captcha=String(captcha||'').trim();
  if(!captcha||captcha.length>20)throw failure('请填写图形验证码','INVALID_INPUT');
  if(this.lastSmsSend&&Date.now()-this.lastSmsSend<120000)throw failure('请等待两分钟后再发送短信验证码','RATE_LIMIT');
  this.sent=false;p.accounts=[];p.phoneCode='';
  // Retain the cooldown even if the response is lost, to avoid duplicate SMS.
  this.lastSmsSend=Date.now();
  this.http.jar.remove('mobile_error_info',endpoint);
  const r=await this.http.request(endpoint+'?'+form({phone:p.phone,code:captcha,method:'isPhone',t:Date.now()}),{binary:true});
  const status=this.http.jar.value('mobile_error_info',endpoint);
  if(r.status!==200||status!=='success')throw failure(messages[status]||'学校未确认短信发送成功，请稍后重试','SCHOOL_SMS_SEND_FAILED');
  this.sent=true;this.captchaCode=captcha;return {step:'sms_sent',retry_after:120};
 }
 async verifySms(code){
  const p=this.smsPending();code=String(code||'').trim();
  if(!this.sent||!/^\d{6}$/.test(code))throw failure('请先发送并填写 6 位短信验证码','INVALID_INPUT');
  p.accounts=[];p.phoneCode='';
  const r=await this.http.request(endpoint+'?'+form({phone:p.phone,phoneCode:code,code:this.captchaCode,method:'isPhone2',t:Date.now()}),{headers:{'X-Requested-With':'XMLHttpRequest'}});
  let obj;try{obj=typeof r.body==='string'?JSON.parse(r.body):r.body;}catch(e){throw failure('学校短信校验返回格式异常，请重试','SCHOOL_FORMAT_CHANGED');}
  if(r.status!==200||!obj||obj.success!==true)throw failure(messages[obj&&obj.errcode]||'学校未确认短信验证成功','SCHOOL_SMS_VERIFY_FAILED');
  const list=obj.userinfo;
  if(!Array.isArray(list)||!list.length||list.length>20||list.some(a=>!a||typeof a.ID_NUMBER!=='string'||!a.ID_NUMBER.trim()||a.ID_NUMBER.length>100))throw failure('学校未返回可登录的账号，请稍后重试','SCHOOL_FORMAT_CHANGED');
  p.accounts=list.map(a=>({id:a.ID_NUMBER,name:String(a.USER_NAME||'').slice(0,40)}));p.phoneCode=code;
  if(p.accounts.length===1)return this.chooseSmsAccount(0);
  return {step:'choose_sms_account',accounts:p.accounts.map((a,index)=>({index,label:(a.id.length>4?a.id.slice(0,2)+'•••'+a.id.slice(-2):a.id)+(a.name?' · '+a.name:'')}))};
 }
 async chooseSmsAccount(index){
  const p=this.smsPending();
  if(!Number.isInteger(index)||!p.accounts[index]||!p.phoneCode)throw failure('请选择本次短信验证返回的学校账号','INVALID_INPUT');
  const id=p.accounts[index].id,code=p.phoneCode;
  const values={rsa:strEnc(id+code+p.lt),ul:id.length,pl:code.length,sl:'1',lt:p.lt,execution:p.execution,_eventId:'submit',code:this.captchaCode};
  p.accounts=[];p.phoneCode='';this.sent=false;
  this.http.jar.set('is_mobile=true; Path=/tpass',CAS+'/login');
  try{
   const r=await this.http.request(p.post,{method:'POST',data:form(values),headers:{'Content-Type':'application/x-www-form-urlencoded','Origin':'https://cas.jlu.edu.cn'}});
   if(r.status===200&&parseUrl(r.url).host==='iedu.jlu.edu.cn'&&!loginPage(r.body)&&!/wxRedirect=|window\.location\.assign/i.test(String(r.body)))return this.finish();
   throw failure('短信已验证，但学校尚未完成教务登录，请重新开始','SCHOOL_LOGIN_FAILED');
  }catch(e){this.clear();throw e;}
 }
}
module.exports={SmsSchoolClient};
