"""单页应用（内联 CSS/JS，无外部依赖）。"""

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1a4f9c">
<title>JLU Toolkit</title>
<style>
:root{--pri:#1a4f9c;--pri2:#e8effa;--bg:#f4f6fa;--card:#fff;--txt:#1d2433;--sub:#6b7385;--line:#e3e7ef;--ok:#1f9d55;--warn:#d9822b;--bad:#d64545;--r:14px}
@media (prefers-color-scheme:dark){:root{--pri:#7aa7ff;--pri2:#1f2a40;--bg:#0f1218;--card:#181c25;--txt:#e7eaf0;--sub:#9aa3b5;--line:#2a3040}}
*{box-sizing:border-box}html,body{margin:0}
body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--txt);padding-bottom:calc(72px + env(safe-area-inset-bottom))}
header{position:sticky;top:0;z-index:5;background:var(--pri);color:#fff;padding:14px 16px 12px;display:flex;align-items:center;gap:10px}
header h1{font-size:18px;margin:0;flex:1;font-weight:650;letter-spacing:.5px}
header small{opacity:.8;font-size:12px}
.btn{text-decoration:none;display:inline-block;border:0;border-radius:10px;padding:8px 12px;font:inherit;font-size:14px;cursor:pointer;background:var(--pri2);color:var(--pri);font-weight:600}
.btn.pri{background:var(--pri);color:#fff}.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--txt)}
header .btn{background:rgba(255,255,255,.18);color:#fff}
main{max-width:980px;margin:0 auto;padding:12px}
.card{background:var(--card);border-radius:var(--r);padding:14px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.sp{flex:1}
h2{font-size:16px;margin:0 0 10px}.sub{color:var(--sub);font-size:13px}
nav{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);display:flex;padding-bottom:env(safe-area-inset-bottom);z-index:6}
nav button{flex:1;border:0;background:none;padding:9px 0 8px;font:inherit;font-size:12px;color:var(--sub);cursor:pointer}
nav button b{display:block;font-size:19px;line-height:1.2}
nav button.on{color:var(--pri);font-weight:650}
.tab{display:none}.tab.on{display:block}
/* 课表 */
.wk{display:flex;align-items:center;gap:8px}
.wk .n{font-size:18px;font-weight:700;min-width:96px;text-align:center}
.grid{display:grid;grid-template-columns:20px repeat(7,minmax(0,1fr));gap:3px;margin-top:10px}
.card.kb{padding:12px 8px}
.grid .h{font-size:11px;line-height:1.3;color:var(--sub);text-align:center;padding:2px 0}
.grid .h.today{color:var(--pri);font-weight:700}
.grid .p{font-size:11px;color:var(--sub);text-align:center;display:flex;align-items:center;justify-content:center;line-height:1.15}
.grid .p em{font-style:normal;font-size:8.5px;opacity:.8}
@media(min-width:640px){.grid .p em{font-size:10px}}
.off-card h3{font-size:14px;margin:0 0 8px}.ogpa{display:grid;grid-template-columns:repeat(2,1fr);gap:6px 12px}
.ogpa div{display:flex;justify-content:space-between;border-bottom:1px dashed var(--line);padding:4px 0;font-size:13.5px}.ogpa b{color:var(--pri)}
.bar{height:10px;border-radius:99px;background:var(--bg);overflow:hidden;margin:6px 0}.bar i{display:block;height:100%;background:var(--pri);border-radius:99px}
.grp{padding:10px 0;border-bottom:1px solid var(--line)}.grp:last-child{border:0}
.grp .row b{flex:1}.miss{color:var(--bad);font-weight:650;font-size:13px}.done{color:var(--ok);font-weight:650;font-size:13px}
.big{font-size:28px;font-weight:750;color:var(--pri)}
.cell{min-height:46px;border-radius:8px;background:var(--bg)}
.cls{border-radius:7px;padding:3px 3px;font-size:10.5px;line-height:1.3;color:#fff;overflow:hidden;word-break:break-all}
.cls b{display:block;font-size:11px;font-weight:650}
@media(min-width:640px){.grid{grid-template-columns:32px repeat(7,minmax(0,1fr))}.cls{font-size:12.5px;padding:5px 6px}.cls b{font-size:13.5px}.cell{min-height:52px}}
.cls i{font-style:normal;opacity:.9}
.empty{color:var(--sub);text-align:center;padding:30px 0}
/* 成绩 */
.gpa{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center}
.gpa div{background:var(--pri2);border-radius:12px;padding:10px 4px}
.gpa b{display:block;font-size:22px;color:var(--pri)}.gpa span{font-size:12px;color:var(--sub)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:9px 6px;border-bottom:1px solid var(--line);text-align:left}
th{font-size:12px;color:var(--sub);font-weight:600;position:sticky;top:58px;background:var(--card)}
td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.off td{opacity:.42}
.term td{background:var(--pri2);font-size:12px;color:var(--pri);font-weight:650;padding:5px 6px}
input[type=checkbox]{width:18px;height:18px;accent-color:var(--pri)}
select,input[type=text],input[type=date]{font:inherit;padding:7px 9px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--txt)}
.chip{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;background:var(--pri2);color:var(--pri)}
/* 考试 */
.exam{display:flex;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}
.exam:last-child{border:0}
.cd{min-width:74px;text-align:center;border-radius:12px;padding:8px 4px;background:var(--pri2);color:var(--pri)}
.cd b{display:block;font-size:22px;line-height:1.1}.cd span{font-size:11px}
.cd.soon{background:#fdecec;color:var(--bad)}.cd.past{background:var(--bg);color:var(--sub)}
.exam .t{flex:1}.exam .t b{display:block}
#toast{position:fixed;left:50%;bottom:86px;transform:translateX(-50%);background:#222c;color:#fff;padding:9px 16px;border-radius:99px;font-size:14px;display:none;z-index:9;max-width:90vw}
.seg{display:flex;gap:4px;margin-bottom:10px}.seg button{flex:1;padding:8px;border:1px solid var(--line,#ddd);background:transparent;border-radius:8px;color:inherit}.seg button.on{background:var(--acc,#2563eb);color:#fff;border-color:transparent}
.rgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}.rgrid label{display:flex;flex-direction:column;font-size:12px;gap:3px;opacity:.9}.rgrid select,.rgrid input{width:100%;box-sizing:border-box}
.rng{display:flex;align-items:center;gap:4px}.rng input{min-width:0}details#rmore{margin-top:8px}
table.rt{border-collapse:collapse;width:100%;font-size:13px}.rt th,.rt td{padding:6px;border-bottom:1px solid var(--line,#eee);text-align:left;white-space:nowrap}.rt th{cursor:pointer;user-select:none;position:static;top:auto}
details.gc{margin-top:6px}details.gc summary{cursor:pointer;font-size:12px;opacity:.8}
details.tn{border-left:2px solid var(--line,#e5e7eb);padding:4px 0 4px 8px;margin-top:6px}details.tn>summary{cursor:pointer}
</style></head>
<body>
<header><h1>JLU Toolkit <small id="upd"></small></h1>
<button class="btn" id="refresh" title="用已保存会话从教务刷新">⟳ 刷新</button></header>
<main>
<section class="tab on" id="t-kb">
 <div class="card" id="nextexam" hidden></div>
 <div class="card kb">
  <div class="row wk"><button class="btn ghost" id="prev">‹</button><div class="n" id="wkn">第 1 周</div><button class="btn ghost" id="next">›</button><span class="sp"></span><button class="btn" id="today">本周</button></div>
  <div class="grid" id="grid"></div>
 </div>
</section>
<section class="tab" id="t-cj">
 <div class="card"><div class="gpa"><div><b id="g-gpa">-</b><span>自选方案绩点</span></div><div><b id="g-cr">-</b><span>计入学分</span></div><div><b id="g-n">-</b><span>计入课程</span></div></div>
  <p class="sub" style="margin:10px 0 0">按学分加权平均：百分制 60 分记 1.0，每分 +0.1，90 分及以上 4.0；“通过”类不计入。各类官方口径（保研/综测）请勾选课程自行组合。</p></div>
 <div class="card off-card" id="ogpa" hidden></div>
 <div class="card">
  <div class="row"><select id="scheme" style="flex:1"></select><button class="btn pri" id="saveas">保存为方案</button><button class="btn ghost" id="del">删除</button></div>
  <div class="row" style="margin-top:8px"><select id="termf" style="flex:1"><option value="">全部学期</option></select><button class="btn ghost" id="all">全选</button><button class="btn ghost" id="none">清空</button></div><div class="sub" id="dirty" style="margin-top:6px"></div>
 </div>
 <div class="card" style="padding:4px 8px"><table><thead><tr><th style="width:30px"></th><th>课程</th><th class="n" style="text-align:right">学分</th><th class="n" style="text-align:right">成绩</th><th class="n" style="text-align:right">绩点</th></tr></thead><tbody id="gt"></tbody></table></div>
</section>
<section class="tab" id="t-xy"><div id="prog"></div></section>
<section class="tab" id="t-js"><div class="card"><h2>空教室</h2>
 <div class="seg" id="rmode"><button class="on" data-m="date">按日期查询</button><button data-m="week">按周次查询</button></div>
 <div class="rgrid">
  <label>学校校区<select id="rc"><option value="">（点“加载”）</option></select></label>
  <label>教学楼<select id="rb"><option value="">全部</option></select></label>
  <label>教室类型<select id="rt"><option value="">全部</option></select></label>
  <label class="m-date">空闲日期<input type="date" id="rd"></label>
  <label class="m-week" hidden>周次<input id="rw" placeholder="如 6 或 6-8"></label>
  <label class="m-week" hidden>星期<select id="rwd"><option value="1">周一</option><option value="2">周二</option><option value="3">周三</option><option value="4">周四</option><option value="5">周五</option><option value="6">周六</option><option value="7">周日</option></select></label>
  <label>空闲节次<span class="rng"><input type="number" id="rp1" min="1" max="14" value="1">–<input type="number" id="rp2" min="1" max="14" value="2"></span></label>
  <label>上课座位数<span class="rng"><input type="number" id="rs1" min="0" placeholder="不限">–<input type="number" id="rs2" min="0" placeholder="不限"></span></label>
  <label>考试座位数<span class="rng"><input type="number" id="re1" min="0" placeholder="不限">–<input type="number" id="re2" min="0" placeholder="不限"></span></label>
 </div>
 <details id="rmore"><summary>更多条件</summary><div class="rgrid" id="rextra"><p class="sub">加载中…</p></div></details>
 <div class="row" style="margin-top:8px"><button class="btn ghost" id="rcl">加载</button><span style="flex:1"></span><button class="btn pri" id="rq">查询</button></div>
 <p class="sub" id="rinfo" style="margin:8px 0 0">需要已保存会话；结果实时来自教务，自动翻页取全。</p></div>
 <div class="card" id="rres" hidden></div></section>
<section class="tab" id="t-ks"><div class="card"><h2>考试倒计时</h2><div id="exams"></div></div></section>
<section class="tab" id="t-sz">
 <div class="card"><h2>学期</h2><p class="sub" id="calinfo"></p>
  <details><summary class="sub">手动覆盖开学日期（一般不需要）</summary><div class="row" style="margin-top:8px"><input type="date" id="fm"><button class="btn pri" id="savefm">保存覆盖</button><button class="btn ghost" id="clrfm">恢复教务校历</button></div></details></div>
 <div class="card"><h2>导出</h2><p class="sub">导出 iCal 后可导入手机日历，课前 15 分钟提醒。</p><a class="btn pri" id="ics" href="/api/ics" download>导出 iCal (.ics)</a></div>
 <div class="card"><h2>数据与隐私</h2><p class="sub">所有数据保存在本机 <code>~/.config/jlu-toolkit/data/</code>。网页只在 127.0.0.1 上运行，不加载任何外部资源。“刷新”使用终端登录时保存的会话；会话失效时请在终端运行 <code>jlu-toolkit fetch --force-login</code>。</p></div>
</section>
</main>
<nav><button class="on" data-t="kb"><b>▦</b>课表</button><button data-t="cj"><b>◎</b>成绩</button><button data-t="xy"><b>◔</b>学业</button><button data-t="js"><b>⌂</b>教室</button><button data-t="ks"><b>⏱</b>考试</button><button data-t="sz"><b>⚙</b>设置</button></nav>
<div id="toast"></div>
<script>
"use strict";
const $=s=>document.querySelector(s), esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const LEVEL={"优秀":95,"良好":85,"中等":75,"及格":65,"不及格":0,"通过":null,"不通过":0};
const COLORS=["#3b6fd4","#d4573b","#2e9e6a","#9b51e0","#d48a1e","#1f8fa8","#c2416f","#5b6bd6","#6b8e23","#b8572b"];
let D=null, week=1, include=new Set(), current="__all__", dirty=false;
function toast(m){const t=$("#toast");t.textContent=m;t.style.display="block";clearTimeout(t._h);t._h=setTimeout(()=>t.style.display="none",2600)}
function point(s){s=String(s).trim();let v=/^\d+(\.\d+)?$/.test(s)?parseFloat(s):(s in LEVEL?LEVEL[s]:null);if(v===null)return null;return v<60?0:Math.min(4,Math.round((1+(v-60)*.1)*100)/100)}
async function api(path,body){const r=await fetch(path,body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{});const j=await r.json();if(!r.ok||j.ok===false)throw new Error(j.error||r.status);return j}
function weekOf(date){const fm=D.first_monday;if(!fm)return 1;const d0=new Date(fm+"T00:00:00");return Math.floor((date-d0)/864e5/7)+1}
function maxWeek(){return Math.max((D.calendar&&D.calendar.total_weeks)||16,...D.courses.flatMap(c=>c.weeks))}
function color(name){let h=0;for(const ch of name)h=(h*31+ch.charCodeAt(0))>>>0;return COLORS[h%COLORS.length]}
function renderGrid(){
 $("#wkn").textContent=`第 ${week} 周`;
 const g=$("#grid"),days=["一","二","三","四","五","六","日"];let html='<div></div>';
 const fm=D.first_monday, now=new Date();
 days.forEach((d,i)=>{let lab="周"+d,today=false;if(fm){const dd=new Date(fm+"T00:00:00");dd.setDate(dd.getDate()+(week-1)*7+i);lab+=`<br>${dd.getMonth()+1}/${dd.getDate()}`;today=dd.toDateString()===now.toDateString()}html+=`<div class="h${today?" today":""}">${lab}</div>`});
 const cs=D.courses.filter(c=>c.weeks.includes(week));
 const maxP=Math.max(11,...cs.map(c=>c.end));
 for(let p=1;p<=maxP;p++){const pt=(D.periods||{})[p];html+=`<div class="p" style="grid-row:${p+1};grid-column:1;flex-direction:column">${p}${pt?`<em>${pt[0]}</em>`:""}</div>`;for(let d=1;d<=7;d++)html+=`<div class="cell" style="grid-row:${p+1};grid-column:${d+1}"></div>`}
 for(const c of cs)html+=`<div class="cls" style="grid-row:${c.start+1}/${c.end+2};grid-column:${c.weekday+1};background:${color(c.name)}"><b>${esc(c.name)}</b><i>${esc(c.location)}</i></div>`;
 g.innerHTML=html;
 if(!D.courses.length)g.insertAdjacentHTML("afterend",'<p class="empty" id="noc">还没有课表数据，点右上角“刷新”或在终端运行 jlu-toolkit fetch</p>');
}
function schemeOptions(){const s=$("#scheme");s.innerHTML=`<option value="__all__">全部课程</option>`+Object.keys(D.schemes).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join("");s.value=current in D.schemes||current==="__all__"?current:"__all__"}
function applyScheme(name){current=name;include=new Set(name==="__all__"?D.grades.map(g=>g.key):D.schemes[name]);dirty=false;renderGrades()}
function renderGrades(){
 const tf=$("#termf").value;let tot=0,pts=0,n=0;
 for(const g of D.grades){if(!include.has(g.key))continue;const p=point(g.score);if(p===null)continue;tot+=g.credit;pts+=p*g.credit;n++}
 $("#g-gpa").textContent=tot?(pts/tot).toFixed(3):"-";$("#g-cr").textContent=tot||"-";$("#g-n").textContent=n||"-";
 $("#dirty").textContent=dirty?"● 有未保存的修改":"";
 const rows=D.grades.filter(g=>!tf||g.term===tf).slice().sort((a,b)=>b.term.localeCompare(a.term));
 let html="",last=null;
 for(const g of rows){if(g.term!==last){html+=`<tr class="term"><td colspan="5">${esc(g.term||"未知学期")}</td></tr>`;last=g.term}
  const on=include.has(g.key),p=point(g.score);
  html+=`<tr class="${on?"":"off"}"><td><input type="checkbox" data-k="${esc(g.key)}" ${on?"checked":""}></td><td>${esc(g.name)}</td><td class="n">${g.credit}</td><td class="n">${esc(g.score)}</td><td class="n">${p===null?'<span class="chip">不计</span>':p.toFixed(1)}</td></tr>`}
 $("#gt").innerHTML=html||'<tr><td colspan="5" class="empty">还没有成绩数据</td></tr>';
}
function cd(e){if(!e.start)return{cls:"",big:"?",sm:"待定"};const ms=new Date(e.start)-new Date();if(ms<0)return{cls:"past",big:"✓",sm:"已结束"};const d=Math.floor(ms/864e5);if(d>=1)return{cls:d<=3?"soon":"",big:d,sm:"天"};return{cls:"soon",big:Math.ceil(ms/36e5),sm:"小时"}}
function fmtTime(e){if(!e.start)return"时间待定";const s=e.start.replace("T"," ");return s+(e.end?"–"+e.end.slice(11):"")}
function renderExams(){
 const L=D.exams.map(e=>{const c=cd(e);return`<div class="exam"><div class="cd ${c.cls}"><b>${c.big}</b><span>${c.sm}</span></div><div class="t"><b>${esc(e.name)}</b><span class="sub">${esc(fmtTime(e))}<br>${esc(e.location)}${e.seat?" · 座位 "+esc(e.seat):""}${e.kind?" · "+esc(e.kind):""}</span></div></div>`});
 $("#exams").innerHTML=L.join("")||'<p class="empty">暂无考试安排数据（刷新后若教务已发布会显示在这里）</p>';
 const nx=D.exams.find(e=>e.start&&new Date(e.end||e.start)>new Date()),box=$("#nextexam");
 if(nx){const c=cd(nx);box.hidden=false;box.innerHTML=`<div class="exam" style="padding:0"><div class="cd ${c.cls}"><b>${c.big}</b><span>${c.sm}</span></div><div class="t"><span class="sub">下一场考试</span><b>${esc(nx.name)}</b><span class="sub">${esc(fmtTime(nx))} · ${esc(nx.location)}</span></div></div>`}else box.hidden=true;
}
function renderOfficial(){const o=D.official_gpa,box=$("#ogpa");if(o&&o.available===false){box.hidden=false;box.innerHTML=`<h3>教务官方统计</h3><p class="sub" style="margin:0">吉大教务暂未提供「学分绩点统计」接口；成绩里若含教务单科绩点，会显示其学分加权结果。</p>`;return}if(!o||!o.items||!o.items.length){box.hidden=true;return}box.hidden=false;
 box.innerHTML=`<h3>教务官方统计 <span class="chip">只读</span></h3><div class="ogpa">${o.items.map(i=>`<div><span class="sub">${esc(i.label)}</span><b>${esc(i.value)}</b></div>`).join("")}</div><p class="sub" style="margin:8px 0 0">${o.source==="grades_jw_point"?"按教务单科绩点计算":"来自教务「学分绩点统计」"}${o.plan?" · "+esc(o.plan):""}</p>`}
function num(v){return v==null?"-":(Math.round(v*100)/100)}
function officialCard(){const o=D.official_gpa;if(!o||o.source!=="official"||!o.items)return"";return`<div class="card"><h2>教务官方 GPA <span class="chip">只读</span></h2><div class="ogpa">${o.items.map(i=>`<div><span class="sub">${esc(i.label)}</span><b>${esc(i.value)}</b></div>`).join("")}</div></div>`}
let PF={st:"",tm:"",nt:""};
function planCourses(){return(D.plan_courses&&D.plan_courses.courses)||[]}
function pfOk(c){return(!PF.st||c.status===PF.st)&&(!PF.tm||(c.term||"")===PF.tm)&&(!PF.nt||(c.nature||c.category||"")===PF.nt)}
function planFilters(){const cs=planCourses();if(!cs.length)return"";const u=k=>[...new Set(cs.map(k).filter(Boolean))].sort();const sel=(id,l,v,lab)=>`<label>${lab}<select id="${id}"><option value="">全部</option>${l.map(x=>`<option${x===v?" selected":""}>${esc(x)}</option>`).join("")}</select></label>`;
 const n=s=>cs.filter(c=>c.status===s).length;return`<div class="card"><h2>培养方案课程 <span class="sub">${cs.length} 门 · 已修 ${n("已修")} · 在修 ${n("在修")} · 未修 ${n("未修")}</span></h2><div class="rgrid">${sel("pf-st",["已修","在修","未修","未通过"],PF.st,"状态")}${sel("pf-tm",u(c=>c.term),PF.tm,"修读学期")}${sel("pf-nt",u(c=>c.nature||c.category),PF.nt,"课程性质/类别")}</div></div>`}
let PDEPT=false;
function courseRows(cs){PDEPT=planCourses().some(c=>c.dept);const tag={"已修":"done","在修":"chip","未修":"miss","未通过":"miss"};return cs.filter(pfOk).map(c=>`<tr><td><span class="${tag[c.status]||"chip"}">${esc(c.status)}</span></td><td>${esc(c.code)}</td><td>${esc(c.name)}</td><td>${c.credit??""}</td><td>${esc(c.hours||"")}</td><td>${esc(c.nature||c.category||"")}</td><td>${esc(c.exam_type||"")}</td><td>${esc(c.term||"")}</td>${PDEPT?`<td>${esc(c.dept||"")}</td>`:""}<td>${esc(c.score||"")}</td></tr>`).join("")}
function pch(){PDEPT=planCourses().some(c=>c.dept);return`<tr><th>状态</th><th>课程号</th><th>课程名</th><th>学分</th><th>学时</th><th>性质</th><th>考试类型</th><th>修读学期</th>${PDEPT?"<th>开课单位</th>":""}<th>成绩</th></tr>`}
function groupCourses(g){const cs=g.courses||[];if(!cs.length)return"";const rows=courseRows(cs);const k=cs.filter(pfOk).length;return`<details class="gc"${PF.st||PF.tm||PF.nt?" open":""}><summary>课程 ${k}/${cs.length}</summary><div style="overflow-x:auto"><table class="rt"><thead>${pch()}</thead><tbody>${rows||'<tr><td colspan="10" class="sub">无符合筛选的课程</td></tr>'}</tbody></table></div></details>`}
function ungrouped(){const c=D.completion,cs=planCourses();if(!cs.length)return"";const inG=new Set(((c&&c.groups)||[]).flatMap(g=>(g.courses||[]).map(x=>x.code+"|"+x.group_code)));const rest=cs.filter(x=>!inG.has(x.code+"|"+x.group_code));if(!rest.length)return"";return`<div class="card"><h2>${c&&c.groups&&c.groups.length?"未归入课组的课程":"全部课程"} <span class="sub">${rest.filter(pfOk).length} 门</span></h2><div style="overflow-x:auto"><table class="rt"><thead>${pch()}</thead><tbody>${courseRows(rest)}</tbody></table></div></div>`}
function nodeCount(n){return(n.courses||[]).length+(n.children||[]).reduce((s,x)=>s+nodeCount(x),0)}
function treeNode(n,d){const p=n.required?Math.min(100,(n.earned||0)/n.required*100):0;const ok=n.required!=null&&!n.missing;const cs=n.courses||[];const k=cs.filter(pfOk).length;
 const leaf=!(n.children||[]).length;return`<details class="tn"${d<1||(leaf&&cs.length<=3)?" open":""} style="margin-left:${Math.min(d,4)*10}px"><summary><b>${esc(n.name)}</b>${n.nature?` <span class="chip">${esc(n.nature)}</span>`:""} <span class="sub">${num(n.earned)}${n.required!=null?" / "+num(n.required):""} 学分${n.earned_source==="plan_courses"?" (按课程)":""} · ${nodeCount(n)} 门</span> ${ok?'<span class="done">✓</span>':n.missing?`<span class="miss">差 ${num(n.missing)}</span>`:""}</summary>${n.required?`<div class="bar"><i style="width:${p.toFixed(1)}%;${ok?"background:var(--ok)":""}"></i></div>`:""}${cs.length?`<div style="overflow-x:auto"><table class="rt"><thead>${pch()}</thead><tbody>${courseRows(cs)||'<tr><td colspan="10" class="sub">无符合筛选的课程</td></tr>'}</tbody></table></div>`:""}${(n.children||[]).map(ch=>treeNode(ch,d+1)).join("")}</details>`}
function unmatchedCard(c){const u=c.unmatched||[];if(!u.length)return"";const R={substitute:"替代/认定课程（RDKCH/TDKCH）",kzh_not_in_tree:"课组号不在方案课组树中",no_kzh:"无课组号"};const by={};u.forEach(x=>(by[x.unmatched_reason]=by[x.unmatched_reason]||[]).push(x));
 return`<div class="card"><h2>未归组课程 <span class="sub">${u.length} 门</span></h2>${Object.entries(by).map(([r,l])=>`<details><summary>${esc(R[r]||r)} · ${l.length} 门</summary><div style="overflow-x:auto"><table class="rt"><thead>${pch()}</thead><tbody>${courseRows(l)}</tbody></table></div></details>`).join("")}</div>`}
function renderProgress(){const c=D.completion,box=$("#prog");
 if(!c){box.innerHTML=officialCard()+'<div class="card"><p class="empty">还没有学业完成数据，点右上角“刷新”</p></div>';return}
 const pct=c.required?Math.min(100,(c.earned||0)/c.required*100):0;
 let h=officialCard()+`<div class="card"><h2>${esc(c.plan||"培养方案")}</h2><div class="row"><span class="big">${num(c.earned)}</span><span class="sub">/ ${num(c.required)} 学分</span><span class="sp"></span>${c.passed?'<span class="done">✓ 已满足毕业学分</span>':`<span class="miss">还差 ${num(c.missing)} 学分</span>`}</div><div class="bar"><i style="width:${pct.toFixed(1)}%"></i></div><p class="sub" style="margin:0">${c.selected!=null?"已选（含在修）"+num(c.selected)+" 学分 · ":""}${c.calculated_at?"教务计算于 "+esc(c.calculated_at):""}</p></div>`;
 const gs=c.groups||[];
 if(c.tree&&c.tree.length){const st=c.tree_stats||{};h+=planFilters()+`<div class="card"><h2>课组树 <span class="sub">${st.groups||0} 个课组 · 课程已归组 ${st.matched||0}/${st.courses||0}</span></h2>${c.tree.map(n=>treeNode(n,0)).join("")}</div>`+unmatchedCard(c);box.innerHTML=h;return}
 if(gs.length){const todo=gs.filter(g=>!g.passed&&(g.missing||0)>0);
  h+=planFilters()+`<div class="card"><h2>各类课程 <span class="sub">${todo.length?todo.length+" 类未完成":"全部完成"}</span></h2>`+gs.map(g=>{const p=g.required?Math.min(100,(g.earned||0)/g.required*100):0;return`<div class="grp"><div class="row"><b>${esc(g.name)}</b>${g.nature?`<span class="chip">${esc(g.nature)}</span>`:""}</div><div class="bar"><i style="width:${p.toFixed(1)}%;${g.passed?"background:var(--ok)":""}"></i></div><div class="row sub"><span>${num(g.earned)} / ${num(g.required)} 学分${g.courses_done?" · "+g.courses_done+" 门":""}${g.earned_source==="derived"?' <span class="chip">按成绩推算</span>':""}</span><span class="sp"></span>${g.passed||!g.missing?'<span class="done">已完成</span>':`<span class="miss">差 ${num(g.missing)}</span>`}</div>${groupCourses(g)}</div>`}).join("")+`</div>`}
 else h+='<div class="card"><p class="sub">教务未返回分类明细（课组），仅显示总学分。可运行 jlu-toolkit explore 帮助适配。</p></div>';
 if(!gs.length)h+=planFilters();
 box.innerHTML=h+ungrouped()}
document.addEventListener("change",e=>{const id=e.target.id;if(id==="pf-st"||id==="pf-tm"||id==="pf-nt"){PF={st:$("#pf-st").value,tm:$("#pf-tm").value,nt:$("#pf-nt").value};renderProgress()}});
function renderAll(){
 $("#upd").textContent=D.updated?"更新于 "+D.updated.replace("T"," "):"";
 $("#fm").value=D.first_monday||"";
 const terms=[...new Set(D.grades.map(g=>g.term))].sort().reverse();const tf=$("#termf"),keep=tf.value;
 tf.innerHTML='<option value="">全部学期</option>'+terms.map(t=>`<option>${esc(t)}</option>`).join("");tf.value=keep;
 document.getElementById("noc")?.remove();renderGrid();schemeOptions();if(!dirty)applyScheme($("#scheme").value);else renderGrades();renderExams();renderOfficial();renderProgress();
 const cal=D.calendar||{};$("#calinfo").innerHTML=D.first_monday?`第 1 周周一：<b>${esc(D.first_monday)}</b>（${D.first_monday_source==="manual"?"手动覆盖":"来自教务校历"}）${cal.term?" · "+esc(cal.term):""}${cal.total_weeks?" · 共 "+cal.total_weeks+" 周":""} · 今天第 ${weekOf(new Date())} 周`:"尚未读取校历：点右上角“刷新”自动获取开学日期。";
}
async function load(){D=await api("/api/data");week=Math.min(Math.max(1,weekOf(new Date())),maxWeek());renderAll()}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{document.querySelectorAll("nav button,.tab").forEach(x=>x.classList.remove("on"));b.classList.add("on");$("#t-"+b.dataset.t).classList.add("on");scrollTo(0,0)});
$("#prev").onclick=()=>{if(week>1){week--;renderGrid()}};$("#next").onclick=()=>{if(week<maxWeek()){week++;renderGrid()}};
$("#today").onclick=()=>{week=Math.min(Math.max(1,weekOf(new Date())),maxWeek());renderGrid()};
let tx=null;$("#grid").addEventListener("touchstart",e=>tx=e.touches[0].clientX,{passive:true});
$("#grid").addEventListener("touchend",e=>{if(tx===null)return;const dx=e.changedTouches[0].clientX-tx;if(Math.abs(dx)>60)(dx<0?$("#next"):$("#prev")).click();tx=null});
$("#gt").onchange=e=>{const k=e.target.dataset.k;if(!k)return;e.target.checked?include.add(k):include.delete(k);dirty=true;renderGrades()};
$("#scheme").onchange=e=>applyScheme(e.target.value);$("#termf").onchange=renderGrades;
$("#all").onclick=()=>{D.grades.forEach(g=>include.add(g.key));dirty=true;renderGrades()};
$("#none").onclick=()=>{include.clear();dirty=true;renderGrades()};
$("#saveas").onclick=async()=>{const n=prompt("方案名称（如 保研、综测）",current==="__all__"?"":current);if(!n)return;try{D=await api("/api/schemes",{name:n,include:[...include]});current=n.trim();dirty=false;renderAll();toast("已保存方案："+current)}catch(e){toast(e.message)}};
$("#del").onclick=async()=>{if(current==="__all__")return toast("“全部课程”不能删除");if(!confirm("删除方案 "+current+"？"))return;D=await api("/api/schemes/delete",{name:current});current="__all__";dirty=false;renderAll();toast("已删除")};
$("#clrfm").onclick=async()=>{D=await api("/api/settings",{first_monday:""});await load();toast("已恢复为教务校历")};
$("#savefm").onclick=async()=>{try{D=await api("/api/settings",{first_monday:$("#fm").value});await load();toast("已保存")}catch(e){toast(e.message)}};
$("#ics").onclick=e=>{if(!D.first_monday){e.preventDefault();toast("请先刷新以读取校历")}};
$("#refresh").onclick=async()=>{const b=$("#refresh");b.disabled=true;b.textContent="刷新中…";try{const j=await api("/api/refresh",{});D=j;renderAll();const r=j.result,c=k=>r[k]&&r[k].ok?(r[k].count??"✓"):"✗";toast(`课表 ${c("schedule")} · 成绩 ${c("grades")} · 考试 ${c("exams")} · 校历 ${c("calendar")} · 学业 ${c("completion")}`)}catch(e){toast("刷新失败："+e.message)}finally{b.disabled=false;b.textContent="⟳ 刷新"}};
(function(){$("#rd").value=new Date(Date.now()-new Date().getTimezoneOffset()*6e4).toISOString().slice(0,10);$("#rwd").value=String(new Date().getDay()||7)})();
let RM="date",RR=[],RS={k:"name",d:1};
document.querySelectorAll("#rmode button").forEach(b=>b.onclick=()=>{RM=b.dataset.m;document.querySelectorAll("#rmode button").forEach(x=>x.classList.toggle("on",x===b));document.querySelectorAll(".m-date").forEach(e=>e.hidden=RM!=="date");document.querySelectorAll(".m-week").forEach(e=>e.hidden=RM!=="week")});
const opts=(l,all)=>(all?`<option value="">${all}</option>`:"")+l.map(c=>`<option value="${esc(c.code)}">${esc(c.name)}</option>`).join("");
async function loadBuildings(){const c=$("#rc").value;if(!c){$("#rb").innerHTML=opts([],"全部");return}try{const j=await api("/api/rooms/buildings",{campus:c});$("#rb").innerHTML=opts(j.buildings,"全部")}catch(e){toast(e.message)}}
$("#rc").onchange=loadBuildings;
$("#rcl").onclick=async()=>{try{const j=await api("/api/rooms/campuses",{});$("#rc").innerHTML=opts(j.campuses)||'<option value="">未取到校区</option>';await loadBuildings();const t=await api("/api/rooms/types",{});$("#rt").innerHTML=opts(t.types,"全部");const f=await api("/api/rooms/fields",{});$("#rextra").innerHTML=f.fields.map(x=>`<label>${esc(x.caption||x.name)}<input data-f="${esc(x.name)}" placeholder="${esc(x.name)}"></label>`).join("")||'<p class="sub">元数据中没有其它检索字段</p>';toast(`已加载 ${j.campuses.length} 校区 · ${t.types.length} 类型`)}catch(e){toast(e.message)}};
const RCOLS=[["campus","学校校区"],["building","教学楼"],["kind","教室类型"],["name","教室名称"],["free_date","空闲日期"],["free_periods","空闲节次"],["free_time","空闲时间"],["seats","上课座位数"],["exam_seats","考试座位数"]];
function renderRooms(j){const box=$("#rres");box.hidden=false;const n=k=>["seats","exam_seats"].includes(k);const rs=[...RR].sort((a,b)=>{const x=a[RS.k],y=b[RS.k];return RS.d*(n(RS.k)?(+x||0)-(+y||0):String(x).localeCompare(String(y),"zh"))});
 const head=j.mode==="week"?`第${esc(j.weeks)}周 周${"一二三四五六日"[j.weekday-1]}`:`${esc(j.date)} <span class="sub">${j.week>0?"第"+j.week+"周 ":""}周${"一二三四五六日"[j.weekday-1]}</span>`;
 box.innerHTML=`<h2>${head} 第${j.periods[0]}-${j.periods[1]}节 <span class="sub">· ${rs.length} 间</span></h2>`+(rs.length?`<div style="overflow-x:auto"><table class="rt"><thead><tr>${RCOLS.map(([k,l])=>`<th data-k="${k}">${l}${RS.k===k?(RS.d>0?" ▲":" ▼"):""}</th>`).join("")}</tr></thead><tbody>${rs.map(r=>`<tr>${RCOLS.map(([k])=>`<td>${esc(r[k]||"")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`:'<p class="empty">没有符合条件的空教室</p>');
 box.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;RS=RS.k===k?{k,d:-RS.d}:{k,d:1};renderRooms(j)})}
$("#rq").onclick=async()=>{const b=$("#rq");b.disabled=true;b.textContent="查询中…";try{const extra={};document.querySelectorAll("#rextra [data-f]").forEach(i=>{if(i.value.trim())extra[i.dataset.f]=i.value.trim()});
 const j=await api("/api/rooms",{mode:RM,campus:$("#rc").value,building:$("#rb").value,kind:$("#rt").value,date:$("#rd").value,weeks:$("#rw").value,weekday:$("#rwd").value,periods:`${$("#rp1").value}-${$("#rp2").value}`,seat_min:$("#rs1").value,seat_max:$("#rs2").value,exam_min:$("#re1").value,exam_max:$("#re2").value,extra});RR=j.rooms;renderRooms(j)}catch(e){toast("查询失败："+e.message)}finally{b.disabled=false;b.textContent="查询"}};
function fromHash(){const h=new URLSearchParams(location.hash.slice(1));const tab=[...h.keys()][0];const b=document.querySelector(`nav button[data-t="${tab}"]`);if(b)b.click();const s=h.get("scheme");if(s&&D.schemes[s]){$("#scheme").value=s;applyScheme(s)}}
load().then(fromHash).catch(e=>toast("加载失败："+e.message));
</script></body></html>
"""
