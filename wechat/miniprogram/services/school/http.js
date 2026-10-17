// Cookies and tickets stay in memory and are scoped to their school host/path.
const HOSTS=['cas.jlu.edu.cn','iedu.jlu.edu.cn','oa.jlu.edu.cn','csw.jlu.edu.cn','ccst.jlu.edu.cn'];
function failure(message,code='SCHOOL_NETWORK') { const e=new Error(message);e.code=code;return e; }
function parseUrl(url) {
  if(/[\\\x00-\x20]/.test(String(url)))throw failure('学校跳转地址格式异常，已停止请求','UNTRUSTED_REDIRECT');
  const m=/^https:\/\/([a-z0-9.-]+)(?::443)?(\/[^#]*)?(?:#.*)?$/i.exec(url);
  if(!m||!HOSTS.includes(m[1].toLowerCase()))throw failure('学校返回了未支持的跳转地址，已停止请求','UNTRUSTED_REDIRECT');
  const host=m[1].toLowerCase(),path=(m[2]||'/').split('?')[0];return {host,path,origin:'https://'+host};
}
function resolveUrl(location,base) {
  const b=parseUrl(base);let u;
  if(/^https?:\/\//i.test(location))u=location;
  else if(location.startsWith('//'))u='https:'+location;
  else if(location.startsWith('/'))u=b.origin+location;
  else if(location.startsWith('?'))u=b.origin+b.path+location;
  else u=b.origin+b.path.slice(0,b.path.lastIndexOf('/')+1)+location;
  parseUrl(u);
  const m=/^(https:\/\/[^/]+)([^?#]*)([?#].*)?$/.exec(u),segments=[];
  for(const part of m[2].split('/')){if(part==='..')segments.pop();else if(part!=='.')segments.push(part);}
  return m[1]+(segments.join('/')||'/')+(m[3]||'');
}
function form(values) { return Object.keys(values).map(k=>encodeURIComponent(k)+'='+encodeURIComponent(values[k]===undefined?'':values[k])).join('&'); }
function header(headers,name) { const key=Object.keys(headers||{}).find(k=>k.toLowerCase()===name.toLowerCase());return key ? headers[key] : ''; }
class CookieJar {
  constructor(){this.items=[];}
  clear(){this.items=[];}
  set(line,url) {
    const u=parseUrl(url),parts=String(line).split(';'),first=parts.shift(),eq=first.indexOf('=');if(eq<1)return;
    const c={name:first.slice(0,eq).trim(),value:first.slice(eq+1).trim(),domain:u.host,hostOnly:true,path:u.path.slice(0,u.path.lastIndexOf('/'))||'/',expires:Infinity};
    for(const part of parts) {
      const n=part.indexOf('='),k=(n<0?part:part.slice(0,n)).trim().toLowerCase(),v=n<0?'':part.slice(n+1).trim();
      if(k==='domain'){c.domain=v.replace(/^\./,'').toLowerCase();c.hostOnly=false;}
      if(k==='path'&&v.startsWith('/'))c.path=v;
      if(k==='expires'){const n=Date.parse(v);if(Number.isFinite(n))c.expires=n;}
      if(k==='max-age'&&/^-?\d+$/.test(v))c.maxAge=Number(v);
    }
    if(!(u.host===c.domain||u.host.endsWith('.'+c.domain))||!(c.domain==='jlu.edu.cn'||c.domain.endsWith('.jlu.edu.cn')))return;
    if(c.maxAge!==undefined)c.expires=Date.now()+c.maxAge*1000;
    this.items=this.items.filter(x=>!(x.name===c.name&&x.domain===c.domain&&x.path===c.path));
    if(c.expires>Date.now())this.items.push(c);
    if(this.items.length>200)throw failure('学校会话 Cookie 数量异常，请重新登录','COOKIE_LIMIT');
  }
  remove(name,url){const host=parseUrl(url).host;this.items=this.items.filter(c=>!(c.name===name&&(host===c.domain||host.endsWith('.'+c.domain))));}
  value(name,url) {const text=this.forUrl(url),part=text.split('; ').find(v=>v.startsWith(name+'='));return part?part.slice(name.length+1):'';}
  forUrl(url) {
    const u=parseUrl(url);this.items=this.items.filter(c=>c.expires>Date.now());
    return this.items.filter(c=>(c.hostOnly?u.host===c.domain:u.host===c.domain||u.host.endsWith('.'+c.domain))&&(u.path===c.path||u.path.startsWith(c.path.endsWith('/')?c.path:c.path+'/'))).sort((a,b)=>b.path.length-a.path.length).map(c=>c.name+'='+c.value).join('; ');
  }
}
class SchoolHttp {
  constructor(){this.jar=new CookieJar();this.generation=0;this.casFlow='';}
  clear(){
    this.generation++;this.jar.clear();
    const flow=this.casFlow;this.casFlow='';
    if(flow)require('../api').cloudRequest('/api/cas/close','POST',{flow}).catch(()=>{});
  }
  async request(url,options={},hops=0,generation=this.generation) {
    parseUrl(url);if(hops>10)throw failure('学校登录跳转次数过多，请重新登录','REDIRECT_LIMIT');
    const h={'Accept':options.binary?'image/*':'text/html,application/json,*/*',...options.headers};
    for(const k of Object.keys(h))if(/^(referer|cookie|authorization)$/i.test(k))delete h[k];
    const cookie=this.jar.forUrl(url);if(cookie)h.Cookie=cookie;
    let res;
    if(require('../../config').transport==='hybrid'&&parseUrl(url).host==='cas.jlu.edu.cn') {
      const value=await require('../api').cloudRequest('/api/cas/request','POST',{url,method:options.method||'GET',data:options.data||'',headers:h,binary:!!options.binary,flow:this.casFlow});
      if(generation!==this.generation){if(value.flow)require('../api').cloudRequest('/api/cas/close','POST',{flow:value.flow}).catch(()=>{});throw failure('登录已取消，请重新开始','LOGIN_CANCELLED');}
      this.casFlow=value.flow;
      res={...value,data:value.binary?wx.base64ToArrayBuffer(value.data):value.data};
    } else res=await new Promise((resolve,reject)=>{
      let observed={};
      const task=wx.request({url,method:options.method||'GET',data:options.data,header:h,timeout:20000,
        redirect:'manual',dataType:'text',responseType:options.binary?'arraybuffer':'text',enableCache:false,
        success:r=>{
          const merged={...observed,...r.header};
          for(const name of ['set-cookie','location']){
            const value=header(observed,name);
            if(value){for(const k of Object.keys(merged))if(k.toLowerCase()===name)delete merged[k];merged[name]=value;}
          }
          resolve({...r,header:merged});
        },
        fail:e=>{
          const text=String(e.errMsg||'');
          if(/url not in domain list|not.*legal|合法域名/i.test(text))reject(failure('微信尚未认可域名 '+parseUrl(url).host+'。若后台已添加，请在开发者工具「详情 → 域名信息」刷新配置，再重新编译','SCHOOL_DOMAIN_REQUIRED'));
          else if(/proxy|ERR_PROXY_CONNECTION_FAILED|代理/i.test(text))reject(failure('开发者工具无法连接当前代理，请启动代理程序或检查其连接状态，再重新检测校园网','SCHOOL_PROXY'));
          else if(/ssl|certificate|证书/i.test(text))reject(failure('学校 HTTPS 证书校验失败，请检查设备时间和网络','SCHOOL_TLS'));
          else reject(failure('当前设备连接学校超时或失败，请确认已连接校园网并可打开教务系统'));
        }});
      if(task&&typeof task.onHeadersReceived==='function')task.onHeadersReceived(r=>{observed={...observed,...r.header};});
    });
    if(generation!==this.generation)throw failure('登录已取消，请重新开始','LOGIN_CANCELLED');
    const value=header(res.header,'set-cookie');
    let cookies=Array.isArray(value)?value:value?String(value).split(/,(?=\s*[^;,=\s]+\s*=)/):[];
    // Raw Set-Cookie carries Path/Domain/expiry. A normalized SDK cookie array
    // may omit them, so use it only for names absent from the raw headers.
    const rawNames=new Set(cookies.map(c=>String(c).split('=',1)[0].trim()));
    cookies=cookies.concat((res.cookies||[]).filter(c=>!rawNames.has(String(c).split('=',1)[0].trim())));
    cookies.forEach(c=>this.jar.set(c,url));
    if([301,302,303,307,308].includes(res.statusCode)) {
      const location=header(res.header,'location');if(!location)throw failure('当前微信版本未返回学校跳转地址，请更新微信或开发者工具','REDIRECT_UNSUPPORTED');
      const next=resolveUrl(String(location),url),method=options.method||'GET';
      // Never forward password forms or verification codes on a cross-host 307/308.
      if([307,308].includes(res.statusCode)&&method!=='GET'&&parseUrl(next).host!==parseUrl(url).host)throw failure('学校要求跨站转发登录表单，已停止请求','UNTRUSTED_REDIRECT');
      const follow=[301,302,303].includes(res.statusCode)&&method!=='GET'?{binary:options.binary}:options;
      return this.request(next,follow,hops+1,generation);
    }
    return {status:res.statusCode,body:res.data,url,headers:res.header||{}};
  }
}
module.exports={SchoolHttp,CookieJar,parseUrl,resolveUrl,form,header,failure};
