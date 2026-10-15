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
.btn{border:0;border-radius:10px;padding:8px 12px;font:inherit;font-size:14px;cursor:pointer;background:var(--pri2);color:var(--pri);font-weight:600}
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
.grid .p{font-size:11px;color:var(--sub);text-align:center;display:flex;align-items:center;justify-content:center}
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
 <div class="card"><div class="gpa"><div><b id="g-gpa">-</b><span>当前方案绩点</span></div><div><b id="g-cr">-</b><span>计入学分</span></div><div><b id="g-n">-</b><span>计入课程</span></div></div>
  <p class="sub" style="margin:10px 0 0">按学分加权平均：百分制 60 分记 1.0，每分 +0.1，90 分及以上 4.0；“通过”类不计入。各类官方口径（保研/综测）请勾选课程自行组合。</p></div>
 <div class="card">
  <div class="row"><select id="scheme" style="flex:1"></select><button class="btn pri" id="saveas">保存为方案</button><button class="btn ghost" id="del">删除</button></div>
  <div class="row" style="margin-top:8px"><select id="termf" style="flex:1"><option value="">全部学期</option></select><button class="btn ghost" id="all">全选</button><button class="btn ghost" id="none">清空</button></div><div class="sub" id="dirty" style="margin-top:6px"></div>
 </div>
 <div class="card" style="padding:4px 8px"><table><thead><tr><th style="width:30px"></th><th>课程</th><th class="n" style="text-align:right">学分</th><th class="n" style="text-align:right">成绩</th><th class="n" style="text-align:right">绩点</th></tr></thead><tbody id="gt"></tbody></table></div>
</section>
<section class="tab" id="t-ks"><div class="card"><h2>考试倒计时</h2><div id="exams"></div></div></section>
<section class="tab" id="t-sz">
 <div class="card"><h2>学期设置</h2><div class="row"><label class="sub">第 1 周周一</label><input type="date" id="fm"><button class="btn pri" id="savefm">保存</button></div></div>
 <div class="card"><h2>导出</h2><p class="sub">导出 iCal 后可导入手机日历，课前 15 分钟提醒。</p><a class="btn pri" id="ics" href="/api/ics" download>导出 iCal (.ics)</a></div>
 <div class="card"><h2>数据与隐私</h2><p class="sub">所有数据保存在本机 <code>~/.config/jlu-toolkit/data/</code>。网页只在 127.0.0.1 上运行，不加载任何外部资源。“刷新”使用终端登录时保存的会话；会话失效时请在终端运行 <code>jlu-toolkit fetch --force-login</code>。</p></div>
</section>
</main>
<nav><button class="on" data-t="kb"><b>▦</b>课表</button><button data-t="cj"><b>◎</b>成绩</button><button data-t="ks"><b>⏱</b>考试</button><button data-t="sz"><b>⚙</b>设置</button></nav>
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
function weekOf(date){const fm=D.settings.first_monday;if(!fm)return 1;const d0=new Date(fm+"T00:00:00");return Math.floor((date-d0)/864e5/7)+1}
function maxWeek(){return Math.max(16,...D.courses.flatMap(c=>c.weeks))}
function color(name){let h=0;for(const ch of name)h=(h*31+ch.charCodeAt(0))>>>0;return COLORS[h%COLORS.length]}
function renderGrid(){
 $("#wkn").textContent=`第 ${week} 周`;
 const g=$("#grid"),days=["一","二","三","四","五","六","日"];let html='<div></div>';
 const fm=D.settings.first_monday, now=new Date();
 days.forEach((d,i)=>{let lab="周"+d,today=false;if(fm){const dd=new Date(fm+"T00:00:00");dd.setDate(dd.getDate()+(week-1)*7+i);lab+=`<br>${dd.getMonth()+1}/${dd.getDate()}`;today=dd.toDateString()===now.toDateString()}html+=`<div class="h${today?" today":""}">${lab}</div>`});
 const cs=D.courses.filter(c=>c.weeks.includes(week));
 const maxP=Math.max(11,...cs.map(c=>c.end));
 for(let p=1;p<=maxP;p++){html+=`<div class="p" style="grid-row:${p+1};grid-column:1">${p}</div>`;for(let d=1;d<=7;d++)html+=`<div class="cell" style="grid-row:${p+1};grid-column:${d+1}"></div>`}
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
function renderAll(){
 $("#upd").textContent=D.updated?"更新于 "+D.updated.replace("T"," "):"";
 $("#fm").value=D.settings.first_monday||"";
 const terms=[...new Set(D.grades.map(g=>g.term))].sort().reverse();const tf=$("#termf"),keep=tf.value;
 tf.innerHTML='<option value="">全部学期</option>'+terms.map(t=>`<option>${esc(t)}</option>`).join("");tf.value=keep;
 document.getElementById("noc")?.remove();renderGrid();schemeOptions();if(!dirty)applyScheme($("#scheme").value);else renderGrades();renderExams();
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
$("#savefm").onclick=async()=>{try{D=await api("/api/settings",{first_monday:$("#fm").value});await load();toast("已保存")}catch(e){toast(e.message)}};
$("#ics").onclick=e=>{if(!D.settings.first_monday){e.preventDefault();toast("请先设置第 1 周周一")}};
$("#refresh").onclick=async()=>{const b=$("#refresh");b.disabled=true;b.textContent="刷新中…";try{const j=await api("/api/refresh",{});D=j;renderAll();const r=j.result;toast(`课表 ${r.courses} 门 · 成绩 ${r.grades} 条`+(r.exams!=null?` · 考试 ${r.exams} 场`:""))}catch(e){toast("刷新失败："+e.message)}finally{b.disabled=false;b.textContent="⟳ 刷新"}};
function fromHash(){const h=new URLSearchParams(location.hash.slice(1));const tab=[...h.keys()][0];const b=document.querySelector(`nav button[data-t="${tab}"]`);if(b)b.click();const s=h.get("scheme");if(s&&D.schemes[s]){$("#scheme").value=s;applyScheme(s)}}
load().then(fromHash).catch(e=>toast("加载失败："+e.message));
</script></body></html>
"""
