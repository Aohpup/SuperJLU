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
assert.deepEqual(JSON.parse(JSON.stringify(context.gradeSelectionCount(rows,new Set(['A','B','C','stale'])))),{selected:3,total:4});
assert.deepEqual(JSON.parse(JSON.stringify(context.gradeSelectionCount([],new Set(['stale'])))),{selected:0,total:0});
const templateRows=Array.from({length:9},(_,i)=>({key:String(i),name:'课程'+i,builtin:{postgraduate:i===8,scholarship:i<2,comprehensive:true}}));
const changes=context.gradeTemplateChanges(templateRows,new Set(['0','1','2','3','4','5','6','7']),'postgraduate');
assert.equal(changes.added.length,8);
assert.equal(changes.removed.length,1);
assert.deepEqual(Array.from(changes.added,g=>g.key),['0','1','2','3','4','5','6','7']);
// Undoing a selection change restores the saved state for every built-in.
for(const base of ['postgraduate','scholarship','comprehensive']){
  const saved=context.gradeSchemeSelection(templateRows,{base},null);
  const selected=new Set(saved);
  assert.equal(context.gradeSelectionChanged(templateRows,selected,saved),false);
  selected.has('0')?selected.delete('0'):selected.add('0');
  assert.equal(context.gradeSelectionChanged(templateRows,selected,saved),true);
  selected.has('0')?selected.delete('0'):selected.add('0');
  assert.equal(context.gradeSelectionChanged(templateRows,selected,saved),false);
}
// Compare custom templates against their saved overrides, not the base template.
const customRule={base:'postgraduate',overrides:{'0':true,'8':false}};
const customSaved=context.gradeSchemeSelection(templateRows,null,customRule);
assert.deepEqual(Array.from(customSaved),['0']);
assert.equal(context.gradeSelectionChanged(templateRows,context.gradeSchemeSelection(templateRows,{base:'postgraduate'},null),customSaved),true);
const customSelection=new Set(customSaved);
customSelection.add('1');
assert.equal(context.gradeSelectionChanged(templateRows,customSelection,customSaved),true);
customSelection.delete('1');
assert.equal(context.gradeSelectionChanged(templateRows,customSelection,customSaved),false);
customSelection.delete('0');
assert.equal(context.gradeSelectionChanged(templateRows,customSelection,customSaved),true);
customSelection.add('0');
assert.equal(context.gradeSelectionChanged(templateRows,customSelection,customSaved),false);
// Equal counts can still contain different courses; stale keys are not active courses.
assert.equal(context.gradeSelectionChanged(templateRows,new Set(['1']),customSaved),true);
assert.equal(context.gradeSelectionChanged(templateRows,new Set(['0','stale']),customSaved),false);
const legacyRows=[{key:'new-key',legacy_key:'T1|旧课程',builtin:{postgraduate:false}}];
const legacySaved=context.gradeSchemeSelection(legacyRows,null,null,['T1|旧课程']);
assert.deepEqual(Array.from(legacySaved),['new-key']);
assert.equal(context.gradeSelectionChanged(legacyRows,new Set(['new-key']),legacySaved),false);
assert.equal(context.gradeSelectionChanged(legacyRows,new Set(),legacySaved),true);
assert.equal(context.gradeSelectionChanged([],new Set(),new Set()),false);
// Older Android WebViews have no Object.hasOwn. Custom overrides (including false)
// and undo detection must still work without throwing during a render.
const legacyWebView=vm.createContext({});
vm.runInContext('Object.hasOwn=undefined;',legacyWebView);
vm.runInContext('// Grade calculation helpers:' + pure,legacyWebView);
const androidSaved=legacyWebView.gradeSchemeSelection(templateRows,null,customRule);
assert.deepEqual(Array.from(androidSaved),['0']);
const androidSelection=new Set(androidSaved);
androidSelection.add('1');
assert.equal(legacyWebView.gradeSelectionChanged(templateRows,androidSelection,androidSaved),true);
androidSelection.delete('1');
assert.equal(legacyWebView.gradeSelectionChanged(templateRows,androidSelection,androidSaved),false);
for(const [base,name] of Object.entries({postgraduate:'保研加权',scholarship:'奖学金加权',comprehensive:'所有课程加权'})){
  assert.equal(context.gradePolicy(base,true),`基于${name}的自定义模板。 不同学院政策不同，请核对当年规则。`);
}
assert.ok(context.gradePolicy('postgraduate',false).startsWith('排除选修、'));
assert.ok(context.gradePolicy('scholarship',false).startsWith('只计必修，'));
assert.ok(context.gradePolicy('comprehensive',false).startsWith('计入所有有学分课程。'));
assert.equal(context.gradeTotals(rows,new Set(['A','D'])).point,null);
assert.equal(context.gradeTotals(rows,new Set()).score,null);
const filters = {q:'',term:'',terms:[],natures:[],inclusion:'',status:'',ranges:[]};
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,term:'T2',natures:['必修']},chosen)).map(g=>g.key),['A']);
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,status:'fail'},chosen)).map(g=>g.key),['D']);
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,inclusion:'out',ranges:[['credit','1','2']]},chosen)).map(g=>g.key),['D']);
assert.deepEqual(rows.filter(g=>context.gradeMatches(g,{...filters,q:'高数'},chosen)).map(g=>g.key),['A']);
assert.equal(context.gradeTotals(rows,chosen).score,80); // Filtering never mutates the selection.
// Pass/fail courses and zero-credit records must not be reported as weighted
// score/GPA errors. Missing nature is still useful when checking a template.
const issueRows=[...rows,
  {key:'E',name:'待核对',nature:'未标注',credit:2,score_valid:false,numeric_score:0,point:null},
  {key:'F',name:'零学分',nature:'必修',credit:0,score_valid:false,point:null}
];
const issueSelection=new Set(['A','C','D','E','F']);
assert.deepEqual(JSON.parse(JSON.stringify(context.gradeDataIssues(issueRows,issueSelection))),{
  unknown:1,'missing-point':2,'missing-nature':1,selectedUnknown:1,selectedMissingPoint:2
});
for(const [status,keys] of [['unknown',['E']],['missing-point',['D','E']],['missing-nature',['E']]]){
  assert.deepEqual(issueRows.filter(g=>context.gradeMatches(g,{...filters,status},issueSelection)).map(g=>g.key),keys);
}
assert.deepEqual(Array.from(issueSelection),['A','C','D','E','F']); // Inspection never changes inclusion.
const before=context.gradeTotals(rows,new Set(['A','B'])),after=context.gradeTotals(rows,new Set(['A']));
const delta=context.gradeDelta(after,before);
assert.equal(delta.score,10);
assert.ok(Math.abs(delta.point-(3.8-17.2/6))<1e-10);
assert.equal(context.gradeSignedDifference(delta.score),'+10.000');
assert.equal(context.gradeSignedDifference(-.015),'-0.015');
assert.equal(context.gradeSignedDifference(-.00001),'0.000');
assert.equal(context.gradeSignedDifference(null),'—');
assert.equal(context.gradeDelta(context.gradeTotals(rows,new Set(['D'])),before).point,null);
assert.equal(context.gradeDelta(context.gradeTotals(rows,new Set()),before).score,null);
// Restoring a saved custom rule removes temporary choices while retaining
// its intentional overrides, even when those differ from the built-in base.
const restoreSelection=new Set(customSaved);restoreSelection.add('3');
const restored=context.gradeSchemeSelection(templateRows,null,customRule);
assert.equal(context.gradeSelectionChanged(templateRows,restoreSelection,customSaved),true);
assert.equal(context.gradeSelectionChanged(templateRows,restored,customSaved),false);
assert.deepEqual(Array.from(restored),['0']);
assert.deepEqual(rows.slice().sort((a,b)=>context.gradeCompare(a,b,{key:'point',dir:-1})).map(g=>g.key),['A','B','C','D']);
assert.deepEqual(rows.slice().sort((a,b)=>context.gradeCompare(a,b,{key:'point',dir:1})).map(g=>g.key),['B','A','C','D']);
console.log('Grade inline scripts parse; weighted totals, missing values, filters and sorting passed.');
