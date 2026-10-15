// 由 tests/test_plan.py 调用：node js_tree_test.js <page.js>
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8").split("\n");
const pick = n => { const i = src.findIndex(l => l.startsWith(n)); if (i < 0) throw Error("missing " + n);
  let j = i + 1; while (j < src.length && /^[ \t]/.test(src[j])) j++; return src.slice(i, j).join("\n"); };
const code = ["const esc=s=>String(s??'');", pick("function num"), pick("let PF"), pick("function planCourses"),
  pick("function pfOk"), pick("let PDEPT"), pick("function courseRows"), pick("function pch"),
  pick("const isDone"), pick("function doneCredits"), pick("function fixEarned"), pick("function nodeCount"), pick("function treeNode")].join("\n");
let D = {plan_courses: {courses: []}};
eval(code + `
const C=(c)=>({code:c,name:"N"+c,credit:1,status:"未修"});
const solo={code:"S",name:"单",courses:[C("k1")],children:[]};
const e1={code:"E1",name:"子",courses:[C("k2")],children:[]};
const emp={code:"E",name:"空父",courses:[],children:[e1]};
const mix={code:"M",name:"混",courses:[C("k5")],children:[{code:"M1",name:"混子",courses:[C("k6")],children:[]}]};
const root={code:"R",name:"根",courses:[],children:[solo,emp,mix]};
const h=treeNode(root,0);
const ok=["Nk1","Nk2","Nk5","Nk6"].every(x=>h.includes(x));
const soloOpen=/<details class="tn" open[^>]*><summary><b>单/.test(treeNode(solo,2));
function tableOrder(n){const h=treeNode(n,1);const tb=h.indexOf("<table");const th=h.indexOf("<thead>"),the=h.indexOf("</thead>"),tbo=h.indexOf("<tbody>");
 const firstRow=h.indexOf("<tr>",the);const rows=(h.slice(tbo,h.indexOf("</tbody>")).match(/<tr>/g)||[]).length;
 const headRows=(h.slice(th,the).match(/<tr>/g)||[]).length;
 return tb>=0&&tb<th&&th<the&&the<tbo&&tbo<firstRow&&headRows===1&&h.slice(tb,th).indexOf("<tr")<0?rows:-1}
const g1={code:"G1",name:"劳动教育",required:2,earned:0,courses:[C("a")],children:[]};
const g3={code:"G3",name:"思政",required:18,earned:6,courses:[C("a"),C("b"),C("c")],children:[]};
const sz=fixEarned({code:"SZ",name:"思政",required:18,earned:0,courses:[{...C("x"),credit:"2.5",status:"已修"},{...C("y"),credit:2.5,status_code:"done",status:"已修"},C("z")],children:[{code:"S1",name:"子",earned:null,courses:[{...C("w"),credit:1,status:"已修"}],children:[]}]});
console.log(JSON.stringify({ok,soloOpen,rows1:tableOrder(g1),rows3:tableOrder(g3),sz:sz.earned,szMissing:sz.missing}));`);
