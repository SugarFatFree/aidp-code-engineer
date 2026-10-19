#!/usr/bin/env python3
import json, pathlib, subprocess, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT/'.aidp/scripts/batch_probe.py'
with tempfile.TemporaryDirectory() as d:
    root=pathlib.Path(d); target=root/'sample.txt'; target.write_text('BASE\n', encoding='utf-8')
    probes=root/'probes.json'; probes.write_text(json.dumps({'probes':[{'id':'P1','file':'sample.txt','anchor':'BASE','inject':'BAD'}]}), encoding='utf-8')
    cmd="python3 -c \"import pathlib,sys; sys.exit(1 if 'BAD' in pathlib.Path('sample.txt').read_text() else 0)\""
    cp=subprocess.run([sys.executable,str(SCRIPT),'--root',str(root),'--probes',str(probes),'--cmd',cmd,'--json'],capture_output=True,text=True)
    out=json.loads(cp.stdout)
    assert cp.returncode == 0 and out['probe_hits'] == 1 and out['rows'][0]['reddened']
    assert target.read_text(encoding='utf-8') == 'BASE\n'
print('✅ batch_probe 阳性变红、阴性绿、失败后还原全部通过')
