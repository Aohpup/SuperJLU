// Field mappings and read-only endpoints ported from the pinned SuperJLU modules (MIT).
const academic=require('../../utils/academic'),{failure,resolveUrl,parseUrl}=require('./http'),{decode,attr}=require('./cas');
const s=v=>v===null||v===undefined?'':String(v).trim().replace(/^(-?\d+)\.0$/,'$1');
const number=v=>s(v)!==''&&Number.isFinite(Number(v))?Number(v):null;
const pick=(r,keys)=>{for(const k of keys)if(s(r[k]))return s(r[k]);return '';};
const passed=v=>/^(通过|合格|已修|已完成|是|true|1)$/.test(s(v))||academic.score(v)!==null&&academic.score(v)>=60;
function course(r){
  const name=s(r.KCM),weekday=Number(r.SKXQ),start=Number(r.KSJC),end=Number(r.JSJC),weeks=[];
  [...s(r.SKZC)].forEach((x,i)=>{if(x==='1')weeks.push(i+1);});
  if(!name||!weeks.length||!Number.isInteger(weekday)||weekday<1||weekday>7||!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end>20)return null;
  return {name,teacher:[...new Set(s(r.SKJS).split(',').map(x=>x.split('/')[0].trim()).filter(Boolean))].join(','),location:s(r.JASMC)||'待定',weekday,start,end,weeks};
}
function grades(rows) {
  const count={};return rows.map(r=>{
    const name=s(r.KCM),credit=number(r.XF),score=pick(r,['ZCJ','XSZCJMC','DJCJMC']);if(!name||credit===null||credit<=0||!score)return null;
    const term=s(r.XNXQDM),nature=pick(r,['KCXZDM_DISPLAY','KCXZMC','KCXZ_DISPLAY','KCXZ'])||'未标注',signature=JSON.stringify([term,name,nature]);
    count[signature]=(count[signature]||0)+1;
    const raw=pick(r,['XFJD','JD','CJJD','KCJD']),jp=number(raw),point=jp===null?academic.point(score):jp;
    return {name,credit,score,term,nature,jw_point:jp,point,point_source:jp===null?'estimated':'reported',numeric_score:academic.score(score),key:JSON.stringify([term,name,nature,count[signature]])};
  }).filter(Boolean);
}
function date(v) {let m=/(\d{4})[-/.年]?(\d{2})[-/.月]?(\d{2})/.exec(s(v));if(!m)return '';const d=m[1]+'-'+m[2]+'-'+m[3];return academic.date(d)?d:'';}
function time(v) {const m=/^(\d{1,2}):?(\d{2})(?::\d{2})?$/.exec(s(v));return m&&+m[1]<24&&+m[2]<60?m[1].padStart(2,'0')+':'+m[2]:'';}
function calendar(r,term) {
  const start=date(r.XQKSRQ),d=academic.date(start);if(!d)throw failure('学校校历缺少有效开始日期','SCHOOL_FORMAT_CHANGED');
  d.setDate(d.getDate()-((d.getDay()+6)%7));return {term,start_date:start,first_monday:academic.iso(d),total_weeks:Number(r.ZZC)||0,teaching_weeks:Number(r.ZJXZC)||0};
}
function periods(rows) {
  const useful=rows.filter(r=>!['0','否','false'].includes(s(r.SFSY))),counts={};useful.forEach(r=>{const c=s(r.XXXQ);counts[c]=(counts[c]||0)+1;});
  const campus=Object.keys(counts).sort((a,b)=>counts[b]-counts[a])[0],out={};
  for(const r of useful.filter(r=>s(r.XXXQ)===campus)){const i=Number(r.DM||r.PX||s(r.MC).replace(/\D/g,'')),a=time(r.KSSJ),b=time(r.JSSJ);if(i&&a&&b&&!out[i])out[i]=[a,b];}return out;
}
function exam(r) {
  const name=s(r.KCM);if(!name)return null;
  const m=/(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*(\d{1,2}):(\d{2})\s*[-~至到]\s*(\d{1,2}):(\d{2})/.exec(s(r.KSSJMS));
  let start='',end='';if(m){const d=m[1]+'-'+m[2].padStart(2,'0')+'-'+m[3].padStart(2,'0');start=d+'T'+m[4].padStart(2,'0')+':'+m[5];end=d+'T'+m[6].padStart(2,'0')+':'+m[7];}
  else {const d=date(r.KSRQ);if(d)start=d+'T00:00';}
  return {name,start,end,location:s(r.JASMC)||'待定',seat:s(r.ZWH),kind:s(r.KSMC),term:s(r.XNXQDM)};
}
function completion(summary,plan,rows) {
  const required=number(summary.YQXF)===null?number(plan.ZSYQXF):number(summary.YQXF),earned=number(summary.WCXF)===null?number(plan.YWCXF):number(summary.WCXF);
  return {plan:s(summary.PYFAMC)||s(plan.PYFAMC),required,earned,groups:rows.map(g=>{
    const required=number(g.YQXF),earned=number(g.WCXF);return {name:s(g.KZM)||s(g.KCXZDM_DISPLAY)||'未命名课组',required,earned,passed:passed(g.SFTG),missing:required!==null&&earned!==null?Math.max(0,required-earned):null};
  })};
}
function planCourses(rows,gs,cs) {
  const done={};gs.forEach(g=>{if(!done[g.name]||passed(g.score))done[g.name]=g;});const current=new Set(cs.map(c=>c.name)),seen=new Set();
  return rows.map(r=>{
    const name=pick(r,['KCM','KCMC']),code=pick(r,['KCH','KCDM']),group=pick(r,['KZM','KZMC']),key=code+'|'+name+'|'+group;
    if(!name||seen.has(key))return null;seen.add(key);
    const g=done[name],score=pick(r,['ZCJ','CJ','XSZCJMC','ZZCJ','ZSCJ'])||(g&&g.score)||'',raw=pick(r,['XDZTDM_DISPLAY','XDZT_DISPLAY','SFTG_DISPLAY','WCZT','TGZT','SFTG']);
    const status=score?(passed(score)?'已修':'未通过'):passed(raw)?'已修':/在修|修读中/.test(raw)||s(r.SFXK)==='1'||current.has(name)?'在修':'未修';
    return {name,code,credit:number(r.XF||r.KCXF),group,nature:pick(r,['KCXZDM_DISPLAY','KCXZ_DISPLAY','KCXZDM','KCXZ']),term:pick(r,['XNXQDM','JYXDXQ','XDXQ','KKXQ'])||(g&&g.term)||'',score,status};
  }).filter(Boolean);
}
class SchoolData {
  constructor(client){this.client=client;this.context={};this.roomMeta=null;}
  async refresh(previous) {
    const c=this.client;c.requireLogin();const data=JSON.parse(JSON.stringify(previous)),failures=[],updated={...data.module_updated};let successes=0;
    const step=async(key,fn)=>{try{data[key]=await fn();updated[key]=new Date().toISOString();successes++;}catch(e){if(['SCHOOL_SESSION_EXPIRED','LOGIN_CANCELLED','SCHOOL_DATA_LIMIT','UNTRUSTED_REDIRECT'].includes(e.code))throw e;failures.push(key);}};
    await c.enter('wdkb');
    const terms=await c.query('wdkb','modules/jshkcb/dqxnxq.do',{},'dqxnxq');
    const term=terms[0]&&s(terms[0].DM);if(!term)throw failure('学校未返回当前学期，请稍后重试','SCHOOL_FORMAT_CHANGED');
    await step('courses',async()=> (await c.query('wdkb','modules/xskcb/cxxszhxqkb.do',{XNXQDM:term},'cxxszhxqkb')).map(course).filter(Boolean));
    await step('grades',async()=>{
      await c.enter('cjcx');const querySetting=JSON.stringify([{name:'SFYX',caption:'是否有效',linkOpt:'AND',builderList:'cbl_m_List',builder:'m_value_equal',value:'1',value_display:'是'},{name:'SHOWMAXCJ',caption:'显示最高成绩',linkOpt:'AND',builderList:'cbl_m_List',builder:'m_value_equal',value:'0',value_display:'否'}]);
      let rows=await c.query('cjcx','modules/cjcx/xscjcx.do',{querySetting,'*order':'-XNXQDM,-KCH,-KXH'},'xscjcx',true);
      if(!rows.length)rows=await c.query('cjcx','modules/cjcx/xscjcx.do',{querySetting:'[]','*order':'-XNXQDM,-KCH,-KXH'},'xscjcx',true);return grades(rows);
    });
    await step('exams',async()=>{
      await c.enter('studentWdksapApp');let rows;
      try{rows=await c.query('studentWdksapApp','WdksapController/cxxsksap.do',{requestParamStr:JSON.stringify({XNXQDM:term,'*order':'-KSRQ,-KSSJMS'})},'cxxsksap');}
      catch(e){if(['SCHOOL_SESSION_EXPIRED','LOGIN_CANCELLED','SCHOOL_DATA_LIMIT','UNTRUSTED_REDIRECT'].includes(e.code))throw e;rows=await c.query('studentWdksapApp','modules/wdksap/wdksap.do',{XNXQDM:term},'wdksap');}return rows.map(exam).filter(Boolean);
    });
    await c.enter('wdkb');
    await step('calendar',async()=>{const bits=term.split('-'),xq=bits.pop(),r=await c.query('wdkb','modules/xskcb/cxxljc.do',{XN:bits.join('-'),XQ:xq},'cxxljc');return calendar(r[0]||{},term);});
    await step('periods',async()=>{const p=periods(await c.query('wdkb','modules/jshkcb/jc.do',{},'jc'));if(!Object.keys(p).length)throw failure('学校未返回节次时间');return p;});
    await step('official_gpa',async()=>{
      await c.enter('cjcx');const rows=await c.query('cjcx','modules*cjcx/rxylgpacx/rxylgpacxcx.do',{pageSize:'10',pageNumber:'1'},'rxylgpacxcx');
      const r=rows[0]||{},labels={ZGCJGPA:'官方GPA（最高成绩）',PJJD:'平均绩点',JQPJF:'加权平均分',GPA:'官方GPA',PPJDCX:'平均学分绩点（初修）',PPJDZG:'平均学分绩点（最高）'};
      const items=Object.keys(labels).filter(k=>s(r[k])).map(k=>({label:labels[k],value:s(r[k])}));if(!items.length)throw failure('学校未提供官方汇总绩点');return {items};
    });
    let plan={},summary={};
    await step('completion',async()=>{
      await c.enter('xsfacx');const p=await c.query('xsfacx','modules/pyfacxepg/grpyfacx.do',{},'grpyfacx');plan=p[0]||{};
      await c.enter('xywccx');const r=await c.query('xywccx','modules/xywccx/cxxsscfa.do',{SCLBDM:'04','*order':'-CZSJ'},'cxxsscfa');summary=r[0]||{};
      const context={XH:s(summary.XH||plan.XH),PYFADM:s(summary.PYFADM||plan.PYFADM),BYNJDM:s(summary.BYNJDM)||'-',SCLBDM:s(summary.SCLBDM)||'04'};
      this.context=context;let groups=[];if(context.XH&&context.PYFADM)groups=await c.query('xywccx','modules/xywccx/cxscfakz.do',context,'cxscfakz');
      if(!Object.keys(summary).length&&!Object.keys(plan).length)throw failure('学校未提供学业完成数据');return completion(summary,plan,groups);
    });
    await step('plan_courses',async()=>{
      if(!this.context.XH||!this.context.PYFADM)throw failure('学校未提供个人培养方案参数');
      await c.enter('xywccx');const rows=await c.query('xywccx','modules/xywccx/cxscfakzkc.do',this.context,'cxscfakzkc',true);return {courses:planCourses(rows,data.grades||[],data.courses||[])};
    });
    if(!successes)throw failure('本次未能同步任何模块，请稍后重试');
    return {...data,updated:new Date().toISOString(),failures,module_updated:updated,first_monday:(data.calendar||{}).first_monday||''};
  }
  async notices(body) {
    const routes={'csw-xytz':['https://csw.jlu.edu.cn/index/xytz_.htm','软件学院'],'ccst-xytz':['https://ccst.jlu.edu.cn/xwzx/xytz.htm','计算机学院'],'179577':['https://oa.jlu.edu.cn/defaultroot/PortalInformation!jldxList.action?channelId=179577&startPage=1','校内通知']};
    const target=routes[body.category];if(!target)throw failure('未知通知来源','INVALID_INPUT');
    const r=await this.client.http.request(target[0]);if(r.status!==200)throw failure('学校通知暂时无法访问');
    const html=String(r.body),items=[],seen=new Set();
    const blocks=body.category==='179577'?[html]:html.match(/<li\b[^>]*>[\s\S]*?<\/li>/gi)||[];
    for(const block of blocks)for(const m of block.matchAll(/<a\b([^>]+)>([\s\S]*?)<\/a>/gi)) {
      const href=attr(m[1],'href');if(!(/info\/\d+\/\d+\.htm/.test(href)||/PortalInformation!getInformation.action\?/.test(href)))continue;
      let url;try{url=resolveUrl(href,target[0]);}catch(e){continue;}if(parseUrl(url).host!==parseUrl(target[0]).host||seen.has(url))continue;
      const title=decode(attr(m[1],'title')||m[2].replace(/<[^>]*>/g,'')).trim();if(!title||body.keyword&&!title.includes(body.keyword))continue;
      const d=/(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})/.exec(block);seen.add(url);items.push({id:url,title,url,dept:target[1],time:body.category==='179577'?'':d?d[1]+'-'+d[2].padStart(2,'0')+'-'+d[3].padStart(2,'0'):''});
    }
    return {items:items.slice(0,50),hint:items.length?'':'未取得通知条目，学校页面可能需要单独登录或已调整结构'};
  }
  async roomMetadata() {
    if(this.roomMeta)return this.roomMeta;const c=this.client;await c.enter('kxjas');
    const r=await c.http.request('https://iedu.jlu.edu.cn/jwapp/sys/kxjas/modules/kxjscx.do?*json=1');
    if(r.status!==200)throw failure('空教室查询元数据暂不可用');let obj;try{obj=typeof r.body==='string'?JSON.parse(r.body):r.body;}catch(e){throw failure('空教室查询参数需要适配学校当前版本','SCHOOL_FORMAT_CHANGED');}
    const controls=[];const walk=v=>{if(!v||typeof v!=='object')return;if(Array.isArray(v))return v.forEach(walk);if(typeof v.name==='string'&&/^[A-Z][A-Z0-9_]{1,30}$/.test(v.name))controls.push(v);Object.values(v).forEach(walk);};walk(obj);
    if(!controls.length)throw failure('未取得空教室查询参数，已停止查询','SCHOOL_FORMAT_CHANGED');this.roomMeta=controls;return controls;
  }
  async buildings(campus) {
    const meta=await this.roomMetadata(),control=meta.find(x=>/教学楼|楼宇|建筑物/.test(s(x.caption))),url=control&&(control.url||control.dict);
    if(!url||typeof url!=='string')return {buildings:[]};
    const base='https://iedu.jlu.edu.cn/jwapp/sys/kxjas/modules/kxjscx.do',target=resolveUrl(url,base);
    if(parseUrl(target).host!=='iedu.jlu.edu.cn'||!/\.do(?:\?|$)/.test(target))throw failure('教学楼字典地址异常');
    const r=await this.client.http.request(target+(target.includes('?')?'&':'?')+'XXXQDM='+encodeURIComponent(campus));
    let obj;try{obj=typeof r.body==='string'?JSON.parse(r.body):r.body;}catch(e){return {buildings:[]};}
    const rows=Array.isArray(obj)?obj:obj&&Array.isArray(obj.rows)?obj.rows:[];return {buildings:rows.slice(0,300).map(r=>({code:s(r.id||r.DM),name:s(r.name||r.MC)})).filter(r=>r.code&&r.name)};
  }
  async rooms(body) {
    if(!/^(01|02|03|04|05|06)$/.test(s(body.campus))||!academic.date(body.date)||!/^\d{1,2}(?:-\d{1,2})?$/.test(body.periods))throw failure('请选择有效的校区、日期和节次','INVALID_INPUT');
    const [a,b]=body.periods.split('-').map(Number),end=b||a;if(a<1||a>end||end>14)throw failure('节次必须在 1–14 之间','INVALID_INPUT');
    const minimum=Number(body.seat_min)||0;if(!Number.isInteger(minimum)||minimum<0||minimum>2000)throw failure('座位数应为 0–2000 的整数','INVALID_INPUT');
    const meta=await this.roomMetadata(),names=new Set(meta.map(x=>x.name)),choose=(keys)=>keys.find(k=>names.has(k));
    const camp=choose(['XXXQDM','XXXQ','XQDM']),day=choose(['KXRQ','RQ','CXRQ']),period=choose(['JC','JCDM','KSJC']);
    if(!camp||!day||!period)throw failure('学校空教室参数与当前版本不同，已停止查询','SCHOOL_FORMAT_CHANGED');
    const values={[camp]:body.campus,[day]:body.date,[period]:Array.from({length:end-a+1},(_,i)=>a+i).join(',')};
    const building=choose(['JXLDM','JZWDM','LH']);if(body.building&&building)values[building]=body.building;
    const querySetting=Object.keys(values).map(name=>({name,value:values[name],linkOpt:'AND',builder:'equal'}));
    values.querySetting=JSON.stringify(querySetting);const rows=await this.client.query('kxjas','modules/kxjscx/cxkxjs.do',values,'cxkxjs',true);
    return {rooms:rows.map(r=>({name:pick(r,['JASMC','JSMC','MC']),building:pick(r,['JXLDM_DISPLAY','JZWDM_DISPLAY','JXLMC']),campus:pick(r,['XXXQDM_DISPLAY','XXXQ_DISPLAY']),seats:pick(r,['SKZWS','ZWS','ZWS1','JASRL']),kind:pick(r,['JASLXDM_DISPLAY','JSLXDM_DISPLAY','JASLX']),free_periods:body.periods})).filter(r=>r.name&&(!minimum||number(r.seats)!==null&&number(r.seats)>=minimum))};
  }
}
module.exports={SchoolData,course,grades,calendar,periods,exam,completion,planCourses};
