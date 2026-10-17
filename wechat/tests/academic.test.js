const test=require('node:test'),assert=require('node:assert/strict');
const a=require('../miniprogram/utils/academic'),csv=require('../miniprogram/utils/csv');
test('teaching week boundaries include dates before semester',()=>{
 assert.equal(a.currentWeek('2026-09-07',new Date(2026,8,7)),1);
 assert.equal(a.currentWeek('2026-09-07',new Date(2026,8,13)),1);
 assert.equal(a.currentWeek('2026-09-07',new Date(2026,8,14)),2);
 assert.equal(a.currentWeek('2026-09-07',new Date(2026,8,6)),0);
 assert.equal(a.date('2026-02-31'),null);
});
test('course filtering respects odd and even weeks',()=>{
 const cs={courses:[{name:'odd',weekday:1,start:3,weeks:[1,3]},{name:'all',weekday:1,start:1,weeks:[1,2,3]}]};
 assert.deepEqual(a.coursesOn(cs,2,1).map(c=>c.name),['all']);
 assert.deepEqual(a.coursesOn(cs,3,1).map(c=>c.name),['all','odd']);
});
test('failed scores become 55, pass-only courses are excluded, credit weighted',()=>{
 const gs=[{key:'a',score:'40',credit:2,point:0},{key:'b',score:'90',credit:4,point:4},{key:'c',score:'通过',credit:2,point:null}];
 const result=a.weighted(gs,{a:true,b:true,c:true});
 assert.equal(result.average,'78.33');assert.equal(result.gpa,'2.667');assert.equal(result.count,2);assert.equal(result.credits,6);
});
test('missing point prevents misleading aggregate; zero score is counted',()=>{
 const gs=[{key:'a',score:'0',credit:2,point:null}];
 assert.equal(a.weighted(gs,{a:true}).average,'55.00');
 assert.equal(a.weighted(gs,{a:true}).gpa,'—');
 assert.equal(a.weighted(gs,{a:false}).average,'—');
});
test('levels, point boundaries, invalid values',()=>{
 assert.equal(a.score('优秀'),95);assert.equal(a.point('60'),1);assert.equal(a.point('90'),4);assert.equal(a.point('100'),4);
 assert.equal(a.point('59'),0);assert.equal(a.point('通过'),null);assert.equal(a.score(''),null);assert.equal(a.score('101'),null);
});
test('selection templates follow upstream rules',()=>{
 assert.equal(a.selectedBy({name:'体育Ⅰ',credit:1,nature:'必修'},'postgraduate'),false);
 assert.equal(a.selectedBy({name:'大学英语',credit:3,nature:'必修'},'scholarship'),false);
 assert.equal(a.selectedBy({name:'专业课',credit:3,nature:'限选'},'postgraduate'),false);
 assert.equal(a.selectedBy({name:'数据结构',credit:4,nature:'必修'},'scholarship'),true);
});
test('exam dates use school timezone, include ongoing and undated exams',()=>{
 const now=Date.parse('2026-10-17T14:00:00+08:00');
 const items=a.examList([{name:'next',start:'2026-11-03T08:00',end:'2026-11-03T10:00'},{name:'now',start:'2026-10-17T13:30',end:'2026-10-17T15:30'},{name:'unknown',start:''}],now);
 assert.deepEqual(items.map(e=>e.name),['now','next','unknown']);
 assert.equal(items[0].countdown,'进行中');assert.equal(items[0].past,false);assert.equal(items[2].unknown,true);
});
test('UTF8 CSV handles BOM, quoted names and duplicate identities',()=>{
 const g=csv.parseGrades('\ufeff课程,学分,成绩,绩点\r\n"课程,一",3,90,4\r\n"课程,一",3,85,3.5');
 assert.equal(g[0].name,'课程,一');assert.notEqual(g[0].key,g[1].key);
 assert.equal(g[0].point_source,'reported');
});
test('CSV missing point remains missing and invalid inputs fail',()=>{
 assert.equal(csv.parseGrades('课程,学分,成绩\n数学,3,90')[0].point,null);
 assert.throws(()=>csv.parseGrades('课程,学分,成绩\n数学,-3,90'));
 assert.throws(()=>csv.parseGrades('课程,学分,成绩\n"未闭合,3,90'));
 assert.throws(()=>csv.parseGrades('错误列,成绩\n课程,90'));
});
