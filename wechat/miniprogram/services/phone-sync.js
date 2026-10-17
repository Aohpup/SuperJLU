// Parse a user-pasted snapshot; never execute clipboard text or reuse credentials.
const academic=require('../utils/academic');
const MODULES={courses:'课表',grades:'成绩',exams:'考试',calendar:'校历',periods:'节次时间',official_gpa:'官方绩点',completion:'学业完成',plan_courses:'培养方案'};
const fail=message=>{throw new Error(message);};
const object=v=>!!v&&typeof v==='object'&&!Array.isArray(v);
function text(v,max=160){if(v===undefined||v===null)return '';if(typeof v!=='string'||v.length>max)fail('同步结果的文本字段不符合要求');return v;}
function num(v,min,max,nullable=false){if(nullable&&(v===null||v===undefined))return null;if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max)fail('同步结果的数值字段不符合要求');return v;}
function int(v,min,max){num(v,min,max);if(!Number.isInteger(v))fail('同步结果的整数字段不符合要求');return v;}
function list(v,max=2000){if(!Array.isArray(v)||v.length>max)fail('同步结果的记录数量异常');return v;}
function record(v){if(!object(v))fail('同步记录格式不正确');return v;}
function date(v){const value=text(v,10);if(value&&!academic.date(value))fail('同步结果中的校历日期无效');return value;}
function course(v){record(v);const start=int(v.start,1,20),end=int(v.end,start,20),name=text(v.name);if(!name)fail('课程缺少名称');return {name,teacher:text(v.teacher,300),location:text(v.location),weekday:int(v.weekday,1,7),start,end,weeks:[...new Set(list(v.weeks,60).map(n=>int(n,1,60)))]};}
function grade(v,i){record(v);const name=text(v.name),score=text(v.score,40);if(!name||!score)fail('成绩缺少课程或分数');const jw_point=num(v.jw_point,0,100,true);return {name,score,credit:num(v.credit,0.01,100),term:text(v.term,40),nature:text(v.nature,80),jw_point,point:jw_point===null?academic.point(score):jw_point,numeric_score:academic.score(score),point_source:jw_point===null?'estimated':'reported',key:JSON.stringify([text(v.term,40),name,text(v.nature,80),i+1])};}
function exam(v){record(v);const timestamp=x=>{const s=text(x,16);if(s&&!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(s))fail('考试时间格式无效');if(s&&(!academic.date(s.slice(0,10))||+s.slice(11,13)>23||+s.slice(14)>59))fail('考试时间无效');return s;};return {name:text(v.name),start:timestamp(v.start),end:timestamp(v.end),location:text(v.location),seat:text(v.seat,30),kind:text(v.kind,80),term:text(v.term,40)};}
function calendar(v){record(v);if(!Object.keys(v).length)return {};const monday=date(v.first_monday);if(monday&&academic.date(monday).getDay()!==1)fail('校历第一周起始日不是周一');return {term:text(v.term,40),start_date:date(v.start_date),first_monday:monday,total_weeks:int(v.total_weeks,0,60),teaching_weeks:int(v.teaching_weeks,0,60)};}
function periods(v){record(v);const out={};if(Object.keys(v).length>20)fail('节次过多');for(const key of Object.keys(v)){if(!/^(?:[1-9]|1\d|20)$/.test(key))fail('节次序号无效');const pair=list(v[key],2);if(pair.length!==2||pair.some(x=>typeof x!=='string'||!/^([01]\d|2[0-3]):[0-5]\d$/.test(x)))fail('节次时间无效');out[key]=pair.slice();}return out;}
function completion(v){if(v===null||v===undefined)return null;record(v);return {plan:text(v.plan),required:num(v.required,0,1000,true),earned:num(v.earned,0,1000,true),groups:list(v.groups,200).map(g=>{record(g);const required=num(g.required,0,1000,true),earned=num(g.earned,0,1000,true);return {name:text(g.name),required,earned,passed:g.passed===true,missing:required!==null&&earned!==null?Math.max(0,required-earned):null};})};}
function plan(v){if(v===null||v===undefined)return null;record(v);return {courses:list(v.courses).map(c=>{record(c);if(!['已修','未通过','在修','未修'].includes(c.status))fail('培养方案修读状态无效');return {name:text(c.name),code:text(c.code,80),credit:num(c.credit,0,100,true),group:text(c.group),nature:text(c.nature,80),term:text(c.term,40),score:text(c.score,40),status:c.status};})};}
function parse(raw,now=Date.now()){
  if(typeof raw!=='string'||raw.length>1024*1024||!raw.startsWith('SUPERJLU-PHONE-1\n'))fail('请复制 Safari 同步窗口中的完整结果，而不是书签脚本或网址');
  let p;try{p=JSON.parse(raw.slice('SUPERJLU-PHONE-1\n'.length));}catch(e){fail('同步结果不是完整 JSON，请重新复制');}
  if(!object(p)||p.version!==1||p.origin!=='https://iedu.jlu.edu.cn'||!object(p.data))fail('同步结果来源或版本不正确');
  const captured=text(p.capturedAt,40),stamp=Date.parse(captured);
  if(!Number.isFinite(stamp)||stamp>now+5*60000||stamp<now-30*60000)fail('结果已超过 30 分钟或设备时间有误，请在 Safari 重新读取');
  const d=p.data,updated={};record(d.module_updated);
  for(const key of Object.keys(MODULES))if(d.module_updated[key]){const value=text(d.module_updated[key],40),n=Date.parse(value);if(!Number.isFinite(n)||n>stamp+60000||n<stamp-30*60000)fail('模块读取时间无效');updated[key]=value;}
  if(!updated.courses)fail('本次没有成功读取课表，请在学校课表页重新同步');
  const failures=list(d.failures||[],8).map(k=>{if(!Object.prototype.hasOwnProperty.call(MODULES,k))fail('未知失败模块');return k;});
  const snapshot={courses:list(d.courses).map(course),grades:list(d.grades).map(grade),exams:list(d.exams).map(exam),calendar:calendar(d.calendar),periods:periods(d.periods),completion:completion(d.completion),plan_courses:plan(d.plan_courses),official_gpa:null,updated:captured,module_updated:updated,failures,connectionSource:'phone-browser'};
  if(d.official_gpa){record(d.official_gpa);snapshot.official_gpa={items:list(d.official_gpa.items,20).map(x=>{record(x);return {label:text(x.label,80),value:text(x.value,40)};})};}
  snapshot.first_monday=snapshot.calendar.first_monday||'';
  for(const key of ['courses','grades','exams'])if(snapshot[key].length&&!updated[key])fail('存在未标明读取时间的记录');
  const local=new Date(stamp),pad=n=>String(n).padStart(2,'0');
  return {snapshot,preview:{courses:snapshot.courses.length,grades:snapshot.grades.length,exams:snapshot.exams.length,term:snapshot.calendar.term||'学校当前学期',captured:academic.iso(local)+' '+pad(local.getHours())+':'+pad(local.getMinutes())+':'+pad(local.getSeconds()),failures:failures.map(k=>MODULES[k]).join('、'),names:snapshot.courses.slice(0,3).map(c=>c.name).join('、')}};
}
module.exports={parse,MODULES};
