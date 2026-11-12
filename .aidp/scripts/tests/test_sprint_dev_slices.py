#!/usr/bin/env python3
"""sprint-dev 薄入口、formal 阶段可达性与真实路由围栏回归。"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

from flow_test_helpers import REPO, SPRINT_DEV_PARTS, sprint_dev_text

HOME = REPO / '.aidp'
ENTRY = HOME / 'commands/sprint-dev.md'
FLOW = HOME / 'flows/sprint-dev'


def bash_blocks(text):
    return re.findall(r'^[ \t]*```bash\n(.*?)\n[ \t]*```[ \t]*$', text, re.M | re.S)


class SprintDevSlicesTests(unittest.TestCase):
    def test_light_entry_budget_and_conditional_reads(self):
        text = ENTRY.read_text()
        self.assertLessEqual(ENTRY.stat().st_size, 6 * 1024)
        light, formal = text.split('## formal 流程', 1)
        self.assertIn('只 Read `{{AIDP_HOME}}/reference/light-entry.md`', light)
        self.assertNotIn('先 Read `{{AIDP_HOME}}/flows/sprint-dev/light-context.md`', light)
        self.assertNotRegex(light, r'Read[^\n]*formal-')
        self.assertIn('终端 **return**', light)
        self.assertIn('不要再执行一次 start/route', light)
        self.assertIn('light_task.py start', light)
        self.assertIn('entry_gate.py bind', light)
        self.assertIn('light_task.py all', light)
        self.assertIn('light-parallel.md', light)
        self.assertIn('dispatch_plan.py --task', light)
        self.assertIn('各读≥3或改≥2文件', light)
        self.assertIn('只有 `route=formal`', light)
        self.assertIn('禁止一次加载全部 formal 片', formal)
        self.assertNotIn('check_sprint_numbering.py next', text)
        self.assertNotIn('TAG_OK=1', text)

    def test_explicit_parts_only_and_sizes(self):
        with self.assertRaises(ValueError):
            sprint_dev_text()
        with self.assertRaises(ValueError):
            sprint_dev_text('missing')
        for part in SPRINT_DEV_PARTS:
            with self.subTest(part=part):
                self.assertLessEqual((FLOW / f'{part}.md').stat().st_size, 20 * 1024)
                # 不得从表格/围栏中切断：每片独立闭合全部 Markdown 围栏。
                self.assertEqual(len(re.findall(r'^\s*```', sprint_dev_text(part), re.M)) % 2, 0)

    def test_formal_branch_paths_and_original_child_calls(self):
        entry = ENTRY.read_text()
        for part in SPRINT_DEV_PARTS:
            self.assertIn(part + '.md', entry)
        edges = {
            'formal-preflight': ('formal-existing', 'formal-increment'),
            'formal-existing': ('formal-development',),
            'formal-increment': ('formal-docs',),
            'formal-docs': ('formal-reversal',),
            'formal-reversal': ('formal-development',),
            'formal-development': ('formal-writeback',),
            'formal-writeback': ('formal-completion',),
        }
        for source, targets in edges.items():
            text = sprint_dev_text(source)
            for target in targets:
                with self.subTest(source=source, target=target):
                    self.assertIn(f'{{{{AIDP_HOME}}}}/flows/sprint-dev/{target}.md', text)
                    self.assertIn('Read', text)
            if source == 'formal-existing':
                self.assertNotIn('formal-increment.md', text)
                self.assertNotIn('formal-docs.md', text)
        common = sprint_dev_text('formal-development', 'formal-writeback')
        for name in ('phase-1-dev-1', 'phase-1-dev-2', 'postdev-writeback-1',
                     'postdev-writeback-2', 'postdev-writeback-3'):
            self.assertIn(f'{{{{AIDP_HOME}}}}/flows/sprint-dev/{name}.md', common)
            self.assertTrue((FLOW / f'{name}.md').is_file())
        docs = sprint_dev_text('formal-docs')
        self.assertIn('Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`', docs)
        self.assertIn('**S**', docs)
        self.assertIn('**M**', docs)
        self.assertIn('**L**', docs)
        self.assertIn('完整文档硬门移到本轮汇合、先于 `/sprint-test`', docs)
        self.assertIn('下面配方与完整文档硬门均在开发前完成', docs)

    def test_old_stage_titles_and_key_fences_are_extractable(self):
        titles = {
            'formal-existing': ('### Phase 0A：', '### Phase 0A.5：'),
            'formal-increment': ('### Phase 0B.00：', '### Phase 0B.0：', '### Phase 0B.1：'),
            'formal-docs': ('### Phase 0B.1.1：',),
            'formal-reversal': ('### Phase 0B.1.3：', '### Phase 0B.2：'),
            'formal-development': ('### Phase 1：',),
            'formal-writeback': ('### ★ 开发完成后：',),
            'formal-completion': ('### 完成前验证', '### Phase 2-4：'),
        }
        for part, markers in titles.items():
            for marker in markers:
                self.assertIn(marker, sprint_dev_text(part))
        fences = {
            'formal-preflight': ('SNAP="memory/',),
            'formal-existing': ('SPRINT_NNN=',),
            'formal-increment': ('check_open_sprints.py', 'TAG_OK=1',
                                 'check_sprint_numbering.py next', 'CONTEXT_OPERATION=fork'),
            'formal-docs': ('check_case_ledger_pending.py',),
        }
        for part, markers in fences.items():
            blocks = bash_blocks(sprint_dev_text(part))
            for marker in markers:
                self.assertTrue(any(marker in block for block in blocks), (part, marker))
        text = '\n'.join(bash_blocks(sprint_dev_text('formal-increment')))
        self.assertLess(text.index('check_open_sprints.py'), text.index('TAG_OK=1'))
        self.assertLess(text.index('TAG_OK=1'), text.index('check_sprint_numbering.py next'))
        self.assertLess(text.index('check_sprint_numbering.py next'), text.index('CONTEXT_OPERATION=fork'))

    def run_entry(self, root, context=None, sprint=None, *,
                  write_set=('code/app.py',), acceptance=('功能验收',)):
        block = bash_blocks(ENTRY.read_text())[0]
        block = block.replace('{{AIDP_HOME}}', str(HOME)).replace('{version}', 'V1.0.0')
        env = {k: v for k, v in os.environ.items()
               if k not in ('EXECUTION_CONTEXT', 'EXPLICIT_SPRINT', 'AIDP_EXECUTION_CONTEXT', 'AIDP_SESSION_ID')}
        if context:
            env['EXECUTION_CONTEXT'] = context
        if sprint:
            env['EXPLICIT_SPRINT'] = sprint
        inputs = (f'TASK_WRITE_SET=({shlex.join(write_set)}); '
                  f'TASK_ACCEPTANCE=({shlex.join(acceptance)}); POLICY_ARGS=()\n')
        cp = subprocess.run(['bash', '-c', inputs + block],
                            cwd=root, env=env, capture_output=True, text=True)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        return json.loads(cp.stdout)

    def test_real_default_light_and_inherited_task_route_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / 'memory/V1.0.0/user/activeContext.md'
            active.parent.mkdir(parents=True)
            active.write_text('当前 Sprint：077\n')
            original = active.read_bytes()
            started = self.run_entry(root)
            self.assertEqual(started['route'], 'light')
            self.assertEqual(started['step'], 'start')
            contexts = list((root / 'memory/.aidp/entry-contexts').glob('*/context.json'))
            self.assertEqual(len(contexts), 1)
            resumed = self.run_entry(root, started['execution_context'])
            self.assertEqual(resumed['route'], 'light')
            self.assertEqual(resumed['task_id'], started['task_id'])
            self.assertEqual(resumed['execution_context'], started['execution_context'])
            self.assertEqual(active.read_bytes(), original)
            self.assertFalse((active.parent / 'sprints').exists())
            self.assertFalse((root / 'docs').exists())
            self.assertEqual(list((root / 'memory/.aidp/entry-contexts').glob('*/context.json')), contexts)

    def test_real_entry_preserves_multiple_paths_and_acceptance_items(self):
        writes = ('code/first app.py', 'code/second.py')
        acceptance = ('第一个结果必须保留', '第二个结果独立验收')
        for sprint in (None, '007'):
            with self.subTest(sprint=sprint), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result = self.run_entry(root, sprint=sprint, write_set=writes, acceptance=acceptance)
                self.assertEqual(result['route'], 'formal' if sprint else 'light')
                ctx = json.loads(Path(result['execution_context']).read_text())
                self.assertEqual(ctx['write_set'], list(writes))
                self.assertEqual(ctx['acceptance'], list(acceptance))
                inherited = self.run_entry(root, context=result['execution_context'])
                self.assertEqual(inherited['task_id'], result['task_id'])
                ctx = json.loads(Path(inherited['execution_context']).read_text())
                self.assertEqual(ctx['write_set'], list(writes))
                self.assertEqual(ctx['acceptance'], list(acceptance))

    def test_real_explicit_sprint_and_formal_parent_do_not_start_light(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formal = self.run_entry(root, sprint='007')
            self.assertEqual(formal['route'], 'formal')
            resumed = self.run_entry(root, formal['execution_context'])
            self.assertEqual(resumed['route'], 'formal')
            self.assertEqual(resumed['task_id'], formal['task_id'])
            self.assertNotIn('step', formal)
            self.assertFalse(list(root.rglob('light-task.json')))
            # 新绑定应指向本次真实任务，不能让任意旧 context 放行。
            sys.path.insert(0, str(HOME / 'scripts'))
            import entry_gate
            gate = entry_gate.check(root, 'code/app.py', env={})
            self.assertTrue(gate['ok'], gate)

    def test_real_fork_and_bind_sprint_for_session_and_task_markers(self):
        sys.path.insert(0, str(HOME / 'scripts'))
        import entry_gate
        blocks = bash_blocks(sprint_dev_text('formal-increment'))
        fork = next(block for block in blocks if 'CONTEXT_OPERATION=fork' in block)
        bind = next(block for block in blocks if 'entry_gate.py bind --if-writable' in block)
        for session, parent_entry in ((None, 'sprint-batch'), ('dev-session', 'sprint-batch'),
                                      (None, 'sprint-full'), ('dev-session', 'sprint-full')):
            for has_scope in (True, False):
                with self.subTest(session=session, has_scope=has_scope, entry=parent_entry), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    args = [sys.executable, str(HOME / 'scripts/entry_context.py'), 'resolve',
                            '--root', str(root), '--entry', parent_entry, '--version', 'V1.0.0',
                            '--acceptance', '本轮验收', '--json']
                    if has_scope:
                        args += ['--write-set', 'code/app.py']
                    parent = subprocess.run(args, capture_output=True, text=True)
                    self.assertEqual(parent.returncode, 0, parent.stdout + parent.stderr)
                    context = json.loads(parent.stdout)['execution_context']
                    env = {k: v for k, v in os.environ.items()
                           if k not in ('AIDP_SESSION_ID', 'AIDP_EXECUTION_CONTEXT')}
                    env.update(EXECUTION_CONTEXT=context, NEXT='008')
                    if session:
                        env['AIDP_SESSION_ID'] = session
                    shell = (fork + '\n' + bind + '\nprintf "\\n%s\\n" "$EXECUTION_CONTEXT"')
                    shell = shell.replace('{{AIDP_HOME}}', str(HOME))
                    result = subprocess.run(['bash', '-e', '-c', shell], cwd=root, env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    child_path = result.stdout.strip().splitlines()[-1]
                    if parent_entry == 'sprint-full':
                        self.assertEqual(child_path, context)
                    else:
                        self.assertNotEqual(child_path, context)
                    child = json.loads(Path(child_path).read_text())
                    self.assertEqual(child['sprint'], '008')
                    gate_env = {'AIDP_SESSION_ID': session} if session else {}
                    checked = entry_gate.check(root, 'code/app.py', env=gate_env)
                    self.assertEqual(checked['ok'], has_scope, checked)
                    marker = entry_gate.task_marker_path(root, session)
                    if has_scope:
                        self.assertEqual(checked['context'], child_path)
                        self.assertEqual(json.loads(marker.read_text())['task_id'], child['task_id'])
                        self.assertFalse(entry_gate.check(root, 'code/outside.py', env=gate_env)['ok'])
                        if session:
                            self.assertFalse(entry_gate.task_marker_path(root).exists())
                            self.assertFalse(entry_gate.check(root, 'code/app.py', env={})['ok'])
                    else:
                        self.assertEqual(json.loads(marker.read_text())['task_id'], child['task_id'])
                        self.assertEqual(checked['context'], child_path)
                        self.assertIn('write-set', checked['missing'])
                        skipped = json.loads(result.stdout.strip().splitlines()[0])
                        self.assertTrue(skipped['skipped'])
                        self.assertFalse(skipped['ok'])
                        # 实际范围补齐后重跑同一围栏；不换任务、不重新取号。
                        revised = subprocess.run([sys.executable, str(HOME / 'scripts/entry_context.py'),
                            'revise', '--root', str(root), '--execution-context', child_path,
                            '--write-set', 'code/app.py', '--json'], capture_output=True, text=True)
                        self.assertEqual(revised.returncode, 0, revised.stdout + revised.stderr)
                        env['EXECUTION_CONTEXT'] = child_path
                        rebound = subprocess.run(['bash', '-e', '-c', bind.replace('{{AIDP_HOME}}', str(HOME))],
                            cwd=root, env=env, capture_output=True, text=True)
                        self.assertEqual(rebound.returncode, 0, rebound.stdout + rebound.stderr)
                        checked = entry_gate.check(root, 'code/app.py', env=gate_env)
                        self.assertTrue(checked['ok'], checked)
                        self.assertEqual(checked['context'], child_path)

    def test_binding_does_not_promote_readonly_context_with_nonempty_scope(self):
        sys.path.insert(0, str(HOME / 'scripts'))
        import entry_context
        import entry_gate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = entry_context.resolve_context(root, 'sprint-dev', version='V1.0.0',
                sprint='007', write_set=['code/app.py'], acceptance=['只审查'], task_scope='review')
            context = resolved['execution_context']
            self.assertNotIn('implement', entry_context.load_context(root, context)['allowed_actions'])
            bind = next(block for block in bash_blocks(sprint_dev_text('formal-increment'))
                        if 'entry_gate.py bind --if-writable' in block)
            env = dict(os.environ, EXECUTION_CONTEXT=context)
            env.pop('AIDP_SESSION_ID', None)
            result = subprocess.run(['bash', '-e', '-c', bind.replace('{{AIDP_HOME}}', str(HOME))],
                cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)['skipped'])
            self.assertFalse(json.loads(result.stdout)['ok'])
            selected = json.loads(entry_gate.task_marker_path(root).read_text())
            self.assertEqual(selected['execution_context'], context)
            self.assertFalse(entry_gate.check(root, 'code/app.py', env={})['ok'])
            self.assertNotIn('implement', entry_context.load_context(root, context)['allowed_actions'])


if __name__ == '__main__':
    unittest.main()
