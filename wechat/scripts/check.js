const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {root,boot,page}=require('../tests/helpers');
const mini=path.join(root,'miniprogram');
const app=JSON.parse(fs.readFileSync(path.join(mini,'app.json'),'utf8'));
const allowed=new Set(['view','text','block','scroll-view','button','input','picker','image','checkbox-group','checkbox','label','progress']);
const tags=/<\/?([\w-]+)(?:\s+[\w:-]+(?:\s*=\s*(?:"[^"]*"|'[^']*'))?)*\s*\/?>/g;
function walk(p){
 for(const e of fs.readdirSync(p,{withFileTypes:true})){
  const f=path.join(p,e.name);
  if(e.isDirectory())walk(f);
  else if(f.endsWith('.json'))JSON.parse(fs.readFileSync(f,'utf8'));
  else if(f.endsWith('.js')){
   const code=fs.readFileSync(f,'utf8');new vm.Script(code,{filename:f});
   for(const m of code.matchAll(/require\(['"](\.[^'"]+)['"]\)/g)){
    const target=path.resolve(path.dirname(f),m[1]);
    assert.ok(!path.extname(target)||path.extname(target)==='.js','WeChat require must load JS: '+f+' → '+m[1]);
    assert.ok(fs.existsSync(target.endsWith('.js')?target:target+'.js'),'Missing WeChat module '+m[1]);
   }
  }
 }
}
walk(mini);boot();
for(const route of app.pages){
 for(const ext of ['.js','.wxml','.json'])assert.ok(fs.existsSync(path.join(mini,route+ext)),route+ext);
 const markup=fs.readFileSync(path.join(mini,route+'.wxml'),'utf8');
 const p=page(route.split('/')[1]);
 for(const match of markup.matchAll(/(?:bind|catch)[\w:]*="([^"]+)"/g))assert.equal(typeof p[match[1]],'function',route+' handler '+match[1]);
 const stack=[];
 for(const m of markup.matchAll(tags)){
  assert.ok(allowed.has(m[1]),'Unsupported native tag '+m[1]);
  if(m[0].startsWith('</'))assert.equal(stack.pop(),m[1],route+' closing tag');
  else if(!m[0].endsWith('/>'))stack.push(m[1]);
 }
 assert.deepEqual(stack,[],route+' unclosed tags');
 for(const m of markup.matchAll(/\{\{([\s\S]*?)\}\}/g)){
  // WXML expressions are compiled as written; decoding entities here hides errors.
  const expr=m[1];
  new vm.Script('('+expr+')',{filename:route+'.wxml'});
 }
}
for(const item of app.tabBar.list)for(const key of ['iconPath','selectedIconPath'])assert.ok(fs.existsSync(path.join(mini,item[key])));
const upstream=JSON.parse(fs.readFileSync(path.join(root,'server/vendor/UPSTREAM.json'),'utf8'));
assert.match(upstream.commit,/^[0-9a-f]{40}$/);
console.log(app.pages.length+' pages: JS/JSON, WXML tags and expressions, event bindings, tab assets and upstream pin validated.');
