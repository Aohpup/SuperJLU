const {SchoolHttp,parseUrl,resolveUrl,form,header,failure}=require('./http');
const {strEnc}=require('./tpass');
const CAS='https://cas.jlu.edu.cn/tpass',IEDU='https://iedu.jlu.edu.cn';
const loginUrl=service=>CAS+'/login?service='+encodeURIComponent(service||IEDU+'/');
function decode(s) {return String(s||'').replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;|&apos;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>');}
function attr(tag,name) {const m=new RegExp('\\b'+name+'\\s*=\\s*([\"\'])([\\s\\S]*?)\\1','i').exec(tag);return m?decode(m[2]):'';}
function fields(html) {const out={};for(const m of String(html||'').matchAll(/<input\b[^>]*>/gi)){const n=attr(m[0],'name')||attr(m[0],'id');if(n)out[n]=attr(m[0],'value');}return out;}
const second=html=>/name\s*=\s*["']WxCode["']|二次认证|recheckcode|获取微信验证码/i.test(String(html));
const loginPage=html=>/<form\b[^>]*\bid\s*=\s*["']loginForm["']/i.test(String(html));
function loginFields(page,mode='密码') {
  const f=fields(page.body);
  if(page.status===200&&loginPage(page.body)&&f.lt)return f;
  if(/window\.location\.assign\s*\(/i.test(String(page.body))&&/\bwxRedirect=/i.test(String(page.body))) {
    throw failure('已选择'+mode+'登录，但学校在当前微信环境中仍返回网页授权跳转，尚未取得登录参数','SCHOOL_WECHAT_WEB_LOGIN');
  }
  throw failure('学校未返回完整的登录参数，请重新检测校园网连接','SCHOOL_FORMAT_CHANGED');
}
function errorText(html) {const m=/id=["'](?:errormsghide|errormsg)["'][^>]*>([\s\S]*?)<\//i.exec(String(html));return m?decode(m[1].replace(/<[^>]*>/g,'')).trim().slice(0,120):'';}
class SchoolClient {
  constructor(){this.http=new SchoolHttp();this.logged=false;this.expires=0;this.pending=null;this.busy=false;this.started=0;this.sent=false;this.lastSend=0;}
  alive(){return this.logged&&Date.now()<this.expires;}
  clear(){this.http.clear();this.logged=false;this.expires=0;this.pending=null;this.sent=false;this.captchaCode='';this.started=0;this.lastSend=0;}
  cancel(){this.pending=null;this.sent=false;this.captchaCode='';if(!this.alive())this.http.clear();}
  need(){if(!this.pending||Date.now()-this.started>600000)throw failure('登录流程已过期，请重新输入账号密码','LOGIN_EXPIRED');}
  async start(username,password) {
    this.clear();username=String(username||'').trim().replace(/@(?:mails\.|mail\.)?jlu\.edu\.cn$/i,'');password=String(password||'').trim();
    if(!username||!password||username.length>100||password.length>256)throw failure('请填写正确的邮箱前缀和密码','INVALID_INPUT');
    this.started=Date.now();
    // Same preference written by the school's #password_login click handler.
    // It selects the web tab only; it does not bypass the school's OAuth routing.
    this.http.jar.set('last_select_type=password_login; Path=/tpass',CAS+'/login');
    const page=await this.http.request(loginUrl());if(page.status!==200)throw failure('学校认证页面暂不可用，请稍后重试');
    const f=loginFields(page);
    const tag=/<form\b[^>]*\bid=["']loginForm["'][^>]*>/i.exec(String(page.body));
    const action=tag&&attr(tag[0],'action'),post=action?resolveUrl(action,page.url):loginUrl();
    if(parseUrl(post).host!=='cas.jlu.edu.cn'||parseUrl(post).path!=='/tpass/login')throw failure('学校登录表单地址异常，已停止提交','UNTRUSTED_REDIRECT');
    const body={rsa:strEnc(username+password+f.lt),ul:username.length,pl:password.length,sl:'0',lt:f.lt,execution:f.execution||'e1s1',_eventId:'submit'};
    for(const k of Object.keys(f).filter(k=>/^remember/i.test(k)).slice(0,2))body[k]=f[k]&&!/^(false|0)$/.test(f[k])?f[k]:'true';
    password='';username='';
    const r=await this.http.request(post,{method:'POST',data:form(body),headers:{'Content-Type':'application/x-www-form-urlencoded','Origin':'https://cas.jlu.edu.cn'}});
    if(second(r.body)) {
      const p=fields(r.body);this.pending={lt:p.lt||f.lt,execution:p.execution||'e1s2'};
      return this.captcha();
    }
    if(r.status===200&&parseUrl(r.url).host==='iedu.jlu.edu.cn'&&!loginPage(r.body))return this.finish();
    this.clear();throw failure(errorText(r.body)||'学校未完成登录，请核对邮箱前缀和密码','SCHOOL_LOGIN_FAILED');
  }
  async captcha() {
    this.need();this.sent=false;this.captchaCode='';
    const r=await this.http.request(CAS+'/code?'+Date.now(),{binary:true});
    const b=r.body instanceof ArrayBuffer?new Uint8Array(r.body):new Uint8Array(0);
    const jpeg=b[0]===255&&b[1]===216,png=b[0]===137&&b[1]===80&&b[2]===78&&b[3]===71;
    if(r.status!==200||b.length<50||(!jpeg&&!png))throw failure('图形验证码未返回有效图片，请重试','CAPTCHA_IMAGE_FAILED');
    return {step:'need_second_factor',captcha:'data:image/'+(png?'png':'jpeg')+';base64,'+wx.arrayBufferToBase64(r.body)};
  }
  async sendCode(code) {
    this.need();code=String(code||'').trim();if(!code||code.length>20)throw failure('请填写图形验证码','INVALID_INPUT');
    if(Date.now()-this.lastSend<60000)throw failure('请等待一分钟后再发送验证码','RATE_LIMIT');
    this.http.jar.set('recheck_djsendtime='+(Date.now()+120000)+'; Path=/',CAS+'/');
    this.http.jar.remove('recheck_mobile_error_info',CAS+'/recheckcode');
    const r=await this.http.request(CAS+'/recheckcode?code='+encodeURIComponent(code)+'&t='+Date.now(),{headers:{'X-Requested-With':'XMLHttpRequest'}});
    const info=this.http.jar.value('recheck_mobile_error_info',CAS+'/recheckcode');
    if(r.status!==200||info!=='success')throw failure(({img_code_error:'图形验证码错误，请换一张重试',get_times_more:'学校要求稍后再发送验证码',get_session_error:'学校会话已过期，请重新输入账号密码'})[info]||'学校未确认验证码发送成功，请重试','SCHOOL_VERIFICATION_FAILED');
    this.sent=true;this.captchaCode=code;this.lastSend=Date.now();return {step:'code_sent'};
  }
  async verify(code) {
    this.need();code=String(code||'').trim();if(!this.sent||!code||code.length>20)throw failure('请先发送并填写学校微信验证码','INVALID_INPUT');
    const p=this.pending,values={rsa:'',ul:'',pl:'',sl:'',lt:p.lt,execution:p.execution,_eventId:'submit',code:this.captchaCode,WxCode:code,not_exit_number:'',service_id:''};
    const r=await this.http.request(loginUrl(),{method:'POST',data:form(values),headers:{'Content-Type':'application/x-www-form-urlencoded','Origin':'https://cas.jlu.edu.cn'}});
    if(r.status===200&&parseUrl(r.url).host==='iedu.jlu.edu.cn'&&!loginPage(r.body))return this.finish();
    const f=fields(r.body);if(f.lt)p.lt=f.lt;if(f.execution)p.execution=f.execution;
    throw failure(errorText(r.body)||'学校验证码错误或已过期，请重试','SCHOOL_VERIFICATION_FAILED');
  }
  finish(){this.logged=true;this.expires=Date.now()+7200000;this.pending=null;this.captchaCode='';this.sent=false;return {step:'success'};}
  async enter(app) {
    this.requireLogin();
    const index=IEDU+'/jwapp/sys/'+app+'/*default/index.do';
    // The portal's login ticket does not activate every EMAP application.
    // Exchange for this exact service with the cloud CAS session, then redeem
    // on the campus device. Match upstream's additional portal bootstrap.
    const r=await this.http.request(require('../../config').transport==='hybrid'?loginUrl(index):index);
    if(parseUrl(r.url).host==='cas.jlu.edu.cn'||loginPage(r.body)) {this.logged=false;throw failure('学校会话已过期，请重新绑定教务','SCHOOL_SESSION_EXPIRED');}
    if(r.status!==200||parseUrl(r.url).host!=='iedu.jlu.edu.cn')throw failure('学校应用暂不可用，请稍后重试','SCHOOL_APP_UNAVAILABLE');
    try{await this.http.request(IEDU+'/jwapp/sys/emaphome/portal/index.do');}catch(e){if(['LOGIN_CANCELLED','UNTRUSTED_REDIRECT'].includes(e.code))throw e;}
  }
  requireLogin(){if(!this.alive()){this.logged=false;throw failure('请先绑定教务账号；重启小程序后需要重新认证','SCHOOL_SESSION_EXPIRED');}}
  async query(app,relative,values={},key='',paged=false,renewed=false) {
    this.requireLogin();let rows=[],total=null;
    for(let page=1;page<=20;page++) {
      const data=paged?{...values,pageSize:'200',pageNumber:String(page)}:values;
      const r=await this.http.request(IEDU+'/jwapp/sys/'+app+'/'+relative,{method:'POST',data:form(data),headers:{'Accept':'application/json, text/javascript, */*; q=0.01','Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Origin':IEDU}});
      if(parseUrl(r.url).host==='cas.jlu.edu.cn'||loginPage(r.body)){this.logged=false;throw failure('学校会话已过期，请重新绑定教务','SCHOOL_SESSION_EXPIRED');}
      if([401,403].includes(r.status)&&!renewed&&require('../../config').transport==='hybrid'){await this.enter(app);return this.query(app,relative,values,key,paged,true);}
      if(r.status!==200)throw failure('学校查询接口返回 HTTP '+r.status+'（'+app+'/'+key+'）','SCHOOL_QUERY_FAILED');
      let obj;try{obj=typeof r.body==='string'?JSON.parse(r.body):r.body;}catch(e){throw failure('学校查询接口返回格式已变化','SCHOOL_FORMAT_CHANGED');}
      const block=obj&&obj.datas&&obj.datas[key];
      if(!block||!Array.isArray(block.rows)){
        const sourceRejected=String(obj&&obj.code)==='#E2140100001';
        if(!sourceRejected&&!renewed&&require('../../config').transport==='hybrid'){await this.enter(app);return this.query(app,relative,values,key,paged,true);}
        const keys=v=>v&&typeof v==='object'?Object.keys(v).slice(0,12).map(k=>/^[A-Za-z_][A-Za-z0-9_]{0,40}$/.test(k)?k:'other'):[];
        const code=obj&&[-1,0,1,200,401,403,500,'-1','0','1','200','401','403','500'].includes(obj.code)?obj.code:'other';
        const clean=v=>['string','number','boolean'].includes(typeof v)?String(v).slice(0,240).replace(/(?:ticket|token|password|secret)=[^\s&]+/gi,'credential=[已隐藏]').replace(/\b\d{8,}\b/g,'[数字已隐藏]'):'';
        this.lastQueryIssue={app,key,status:r.status,code,serverCode:clean(obj&&obj.code),serverMessage:clean(obj&&obj.msg),jsonKeys:keys(obj),dataKeys:keys(obj&&obj.datas),blockKeys:keys(block),hasAppCookie:!!this.http.jar.value('_WEU',IEDU+'/jwapp/sys/'+app+'/'),hasPortalCookie:!!this.http.jar.value('MOD_AUTH_CAS',IEDU+'/')};
        console.warn('[SuperJLU 查询诊断]',this.lastQueryIssue);
        if(sourceRejected)throw failure('学校拒绝当前小程序的查询来源（#E2140100001），手机实时同步尚未接通。此错误不需要重新输入账号或验证码','SCHOOL_SOURCE_REJECTED');
        throw failure('学校查询未通过（'+app+'/'+key+'，HTTP '+r.status+'，code='+(this.lastQueryIssue.serverCode||code)+'）：'+(this.lastQueryIssue.serverMessage||'未返回预期数据')+'。可在「我的」复制连接诊断','SCHOOL_FORMAT_CHANGED');
      }
      if(block.rows.length>2000||Number(block.totalSize)>2000)throw failure('查询结果范围异常，已停止读取','SCHOOL_DATA_LIMIT');
      rows=rows.concat(block.rows);if(rows.length>2000)throw failure('查询结果范围异常，已停止读取','SCHOOL_DATA_LIMIT');
      total=block.totalSize===null||block.totalSize===undefined?null:Number(block.totalSize);
      if(!paged||block.rows.length===0||(Number.isFinite(total)&&total>0&&rows.length>=total)||block.rows.length<200)break;
      if(page===20)throw failure('查询分页未结束，已停止读取','SCHOOL_DATA_LIMIT');
    }
    return rows;
  }
}
async function probe(mode='password_login') {
  const http=new SchoolHttp(),results=[];
  http.jar.set('last_select_type='+mode+'; Path=/tpass',CAS+'/login');
  try {
    for(const url of [IEDU+'/',loginUrl()]) {
      const r=await http.request(url);loginFields(r,mode==='mobile_login'?'短信验证码':'密码');
      results.push({host:parseUrl(url).host,status:r.status,reachable:true});
    }
    const hybrid=require('../../config').transport==='hybrid';
    return {ok:true,message:hybrid?'校园网与云端认证已连通，可以开始验证码登录':mode==='mobile_login'?'校园网直连正常，可以开始短信验证码登录':'校园网直连正常，可以填写学校账号进行绑定',results};
  } finally {http.clear();}
}
module.exports={SchoolClient,probe,fields,attr,decode,second,loginPage,loginFields,CAS,IEDU};
