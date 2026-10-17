const a=require('./academic');
function rows(text) {
  const out=[];let row=[],cell='',quoted=false;
  text=String(text).replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(c==='"'){
      if(quoted && text[i+1]==='"'){cell+='"';i++;}
      else if(quoted || cell==='')quoted=!quoted;
      else throw new Error('CSV 引号格式错误');
    } else if(c===',' && !quoted){row.push(cell);cell='';}
    else if((c==='\n' || c==='\r') && !quoted){
      if(c==='\r' && text[i+1]==='\n')i++;
      row.push(cell);if(row.some(s=>s.trim()))out.push(row);
      row=[];cell='';
    } else cell+=c;
  }
  if(quoted)throw new Error('CSV 引号未闭合');
  row.push(cell);if(row.some(s=>s.trim()))out.push(row);
  return out;
}
function parseGrades(text) {
  const data=rows(text);
  const aliases={name:['课程','课程名','课程名称','科目','course'],credit:['学分','credits','credit'],score:['成绩','总成绩','分数','score','grade'],term:['学期','学年学期','term'],nature:['课程性质','性质','nature'],point:['绩点','教务绩点','gpa']};
  const h=(data.shift() || []).map(s=>s.trim().toLowerCase());
  const idx={};Object.keys(aliases).forEach(k=>{idx[k]=h.findIndex(s=>aliases[k].includes(s));});
  if(['name','credit','score'].some(k=>idx[k]<0))throw new Error('CSV 首行需要课程、学分、成绩三列；请使用 UTF-8 编码');
  const occurs={};
  const grades=data.map(r=>{
    const get=k=>idx[k]<0?'':String(r[idx[k]] || '').trim();
    const name=get('name'), credit=Number(get('credit')), pointText=get('point'), p=pointText?Number(pointText):null;
    if(!name || !get('credit') || !Number.isFinite(credit) || credit<0 || (p!==null && (!Number.isFinite(p) || p<0)))throw new Error('课程名、学分或绩点无效');
    const g={name,credit,score:get('score'),term:get('term'),nature:get('nature')||'未标注',point:p,point_source:p===null?'missing':'reported'};
    const sig=JSON.stringify([g.term,g.name,g.nature]);occurs[sig]=(occurs[sig]||0)+1;
    g.key=JSON.stringify([g.term,g.name,g.nature,occurs[sig]]);
    return g;
  });
  if(!grades.length)throw new Error('成绩单中没有课程记录');
  if(grades.length>5000)throw new Error('成绩单不能超过 5000 条课程');
  return grades;
}
module.exports={rows,parseGrades};
