"""Regenerate native JS DES tables from the pinned upstream MIT implementation."""
import ast
import importlib.util
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
source = root / 'server/vendor/jlu_toolkit/des_tpass.py'
spec = importlib.util.spec_from_file_location('tpass', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sboxes = {}
for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
        if name in ['s' + str(i) for i in range(1, 9)]: sboxes[name] = ast.literal_eval(node.value)
tables = {'ip': module.initPermute(list(range(64))), 'fp': module.finallyPermute(list(range(64))),
          'expand': module.expandPermute(list(range(32))), 'p': module.pPermute(list(range(32))),
          'pc1': [8*k+i for i in range(7) for k in range(7,-1,-1)],
          'pc2': [13,16,10,23,0,4,2,27,14,5,20,9,22,18,11,3,25,7,15,6,26,19,12,1,40,51,30,36,46,54,29,39,50,44,32,47,43,48,38,55,33,52,45,41,49,35,28,31],
          'shifts': [1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1], 'sboxes': [sboxes['s'+str(i)] for i in range(1,9)]}
out = root / 'miniprogram/services/school'
out.mkdir(exist_ok=True, parents=True)
(out/'des-tables.js').write_text('// Generated from pinned upstream des_tpass.py (MIT).\nmodule.exports='+json.dumps(tables,separators=(',',':'))+';\n',encoding='utf-8')
vectors = [{'text':s,'expected':module.strEnc(s,'1','2','3')} for s in ['', 'a','abcd','abcde','studenttest-passwordLT-fixture','测试口令LT-fixture','x'*80]]
(root/'tests/tpass-vectors.json').write_text(json.dumps(vectors,ensure_ascii=False,indent=2),encoding='utf-8')
print('DES tables and synthetic reference vectors generated.')
