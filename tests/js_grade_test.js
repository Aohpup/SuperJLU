// Run with node tests/js_grade_test.js. Exercises the production inline helpers.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const page = fs.readFileSync('jlu_toolkit/ui_page.py', 'utf8');
for (const [, script] of page.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(script);
const pure = page.split('// Grade calculation helpers:')[1].split('// Grade rendering')[0];
const context = vm.createContext({});
vm.runInContext('// Grade calculation helpers:' + pure, context);
const rows = [
  {key:'A',name:'高数',term:'T2',nature:'必修',numeric_score:90,score_valid:true,credit:4,point:3.8,point_source:'reported'},
  {key:'B',name:'理论',term:'T1',nature:'必修',numeric_score:60,score_valid:true,credit:2,point:1,point_source:'estimated'},
  {key:'C',name:'通过类',term:'T1',nature:'选修',numeric_score:null,score_valid:false,credit:1,point:null,ungraded:true},
  {key:'D',name:'缺绩点',term:'T2',nature:'限选',numeric_score:55,score_valid:true,credit:1,point:null},
];
const chosen = new Set(['A','B','C']);
const totals = context.gradeTotals(rows,chosen);
assert.equal(totals.count,2);
assert.equal(totals.credits,6);
assert.equal(totals.score,80);
assert.ok(Math.abs(totals.point - 17.2/6) < 1e-10);
assert.equal(totals.estimated,1);
assert.equal(context.gradeTotals(rows,new Set(['A','D'])).point,null);
assert.equal(context.gradeTotals(rows,new Set()).score,null);
const filters = {q:'',term:'',terms:[],natures:[],inclusion:'',status:'',ranges:[]};
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,term:'T2',natures:['必修']},chosen)).map(g=>g.key),['A']);
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,status:'fail'},chosen)).map(g=>g.key),['D']);
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,inclusion:'out',ranges:[['credit','1','2']]},chosen)).map(g=>g.key),['D']);
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,q:'高数'},chosen)).map(g=>g.key),['A']);
assert.equal(context.gradeTotals(rows,chosen).score,80); // Filtering never mutates the selection.
assert.deepEqual(rows.slice().sort((a,b)=>context.gradeCompare(a,b,{key:'point',dir:-1})).map(g=>g.key),['A','B','C','D']);
assert.deepEqual(rows.slice().sort((a,b)=>context.gradeCompare(a,b,{key:'point',dir:1})).map(g=>g.key),['B','A','C','D']);
console.log('Grade inline scripts parse; weighted totals, missing values, filters and sorting passed.');
