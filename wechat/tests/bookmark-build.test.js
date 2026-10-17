const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
test('bookmark generation is reproducible across LF and CRLF source checkouts',()=>{
 const script=fs.readFileSync(path.join(root,'scripts/build-phone-bookmark.js'),'utf8');
 const source=require('../phone-browser/sync').toString();
 function generate(eol){
  let output;
  const fakeFs={
   readFileSync:file=>fs.readFileSync(file,'utf8').replace(/\r?\n/g,eol),
   mkdirSync(){},
   writeFileSync(file,content){if(file===path.join(root,'miniprogram/data/phone-bookmark.js'))output=content;}
  };
  const requireStub=name=>name==='node:fs'?fakeFs:name==='node:path'?path:{toString:()=>source.replace(/\r?\n/g,eol)};
  vm.runInNewContext(script,{require:requireStub,__dirname:path.join(root,'scripts'),Buffer,console:{log(){}}});
  assert.ok(output);return output;
 }
 const lf=generate('\n');
 assert.equal(generate('\r\n'),lf);
 assert.equal(fs.readFileSync(path.join(root,'miniprogram/data/phone-bookmark.js'),'utf8').replace(/\r\n/g,'\n'),lf);
});
