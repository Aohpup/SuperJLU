// Run production helpers, including asynchronous refresh/error behavior.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const page=fs.readFileSync('jlu_toolkit/ui_page.py','utf8');
const lines=page.split('\n');
const prefixes=['function siteHasLoginStatus(','function stBadge(','function serviceTime(',
 'function serviceLink(','function serviceActions(','function serviceHelp(','function serviceResult(','function servicePrimary(','function serviceVpnAlt(','function serviceTip(','function serviceDot(','function renderServiceLinks(',
 'let LINKS_LAST=','async function loadLinks('];
const nodes=new Map();
const $=key=>{if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',disabled:false});return nodes.get(key)};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sample={id:'jwxt',name:'教务',url:'https://iedu.jlu.edu.cn/',campus_only:true,
 vpn_url:'https://vpn.jlu.edu.cn/https/example/',sso_url:'/api/sso/jump?id=jwxt&n=test',
 vpn_sso_url:'/api/sso/jump?id=jwxt&route=webvpn&n=test'};
let requests=0,release,fail=false;
const ctx=vm.createContext({$,esc,Date,Number,URL,navigator:{userAgent:'Desktop'},SITES:{},LINKN:{},
 SST:{missing:['未登录','chip'],unknown:['待验证','chip']},
 LKOK:u=>{try{return new URL(u).protocol==='https:'&&new URL(u).hostname.endsWith('.jlu.edu.cn')}catch(_){return false}},
 api:async()=>{requests++;if(release)await new Promise(resolve=>release=resolve);if(fail)throw Error('离线');return{links:[sample],route:'webvpn'}},
 loadSessions:async()=>({jwxt:{id:'jwxt',state:'ok',checked_at:1792901046}})});
vm.runInContext(lines.filter(l=>prefixes.some(p=>l.startsWith(p))).join('\n'),ctx);
vm.runInContext('const lkA=(url,text,cls)=>LKOK(url)?`<a class="btn ${cls}" href="${esc(url)}">${text}</a>`:"";',ctx);

assert.equal(ctx.serviceTime(1792901046),ctx.serviceTime('1792901046'));
assert.equal(ctx.serviceTime(1792901046000),ctx.serviceTime(1792901046));
assert.match(ctx.serviceTime(1792901046),/2026/);
for(const value of [null,undefined,'','nonsense'])assert.equal(ctx.serviceTime(value),'');
assert.match(ctx.serviceTime('2026-10-25T10:00:00+08:00'),/2026/);
assert.doesNotMatch(ctx.stBadge({id:'jwxt',state:'ok'}),/>已登录|class="done"/);
assert.match(ctx.stBadge({id:'jwxt',state:'ok'}),/登录状态已保存/);
assert.match(ctx.stBadge({id:'vpn',state:'ok'}),/VPN 登录状态已保存/);
for(const id of ['xsxk','lib','ilearn'])for(const state of ['ok','missing','unknown','expired'])assert.equal(ctx.stBadge({id,state}),'');
const desktop=ctx.serviceLink(sample.sso_url,'直接打开','pri');
assert.match(desktop,/target="_blank"/);
ctx.navigator.userAgent='SuperJLU-Android';
const android=ctx.serviceLink(sample.sso_url,'直接打开','pri');
assert.doesNotMatch(android,/target=/); // Local authenticated handoff stays in WebView, then external redirect.
assert.match(android,/href="\/api\/sso\/jump/);
assert.doesNotMatch(android,/superjlu_t|\?t=/);
assert.equal(ctx.serviceLink('javascript:alert(1)','打开','pri'),'');
assert.match(ctx.serviceActions(sample,'webvpn'),/class="btn pri"[^>]*route=webvpn/);
assert.match(ctx.serviceActions({...sample,id:'vpn',vpn_url:null},'direct'),/打开 VPN 网页/);
assert.match(ctx.serviceHelp({vpn_help_url:'/api/sso/jump?id=jwxt&stage=setup'}),/浏览器 VPN 登录说明/);
assert.equal(ctx.serviceHelp({vpn_help_url:'javascript:alert(1)'}),'');
assert.match(ctx.serviceResult({handoff:{state:'network',message:'失败 <script>',checked_at:1792901046}}),/failed.*&lt;script&gt;/);
assert.doesNotMatch(ctx.serviceResult({handoff:{state:'issued',message:'已发起，未确认'}}),/failed/);

(async()=>{
 release=true;
 const a=ctx.loadLinks(),b=ctx.loadLinks();
 assert.equal(requests,1);release();release=null;
 await Promise.all([a,b]);
 assert.match($('#links-b').innerHTML,/class="go"/); assert.match($('#links-b').innerHTML,/\/api\/sso\/jump/); assert.match($('#links-b').innerHTML,/经 WebVPN/);
 assert.doesNotMatch($('#links-b').innerHTML,/1792901046/);
 assert.equal($('#links-refresh').disabled,false);
 await ctx.loadLinks(false);assert.equal(requests,1); // TTL suppresses repeated navigation reads.
 const before=$('#links-b').innerHTML;
 fail=true;await ctx.loadLinks();
 assert.equal($('#links-b').innerHTML,before);
 assert.match($('#links-state').textContent,/读取失败.*保留原显示/);
 assert.equal($('#links-refresh').disabled,false);
 fail=false;await ctx.loadLinks();
 assert.equal(requests,3); // Failed load releases the shared promise and can be retried.
 console.log('Campus services: truthful state, time formats, Android/desktop links, VPN actions and deduplicated refresh passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
