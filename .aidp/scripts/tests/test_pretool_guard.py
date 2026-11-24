#!/usr/bin/env python3
"""pretool-guard.py：真实 hook 进程——入口协议、独立测试范围门与校验失败拒绝。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

AIDP = Path(__file__).resolve().parents[2]
HOOK = AIDP / 'hooks/pretool-guard.py'
sys.path.insert(0, str(AIDP / 'scripts'))


def run_hook(root, payload, agent='claude', env_extra=None, hook=HOOK, raw=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ('AIDP_TICK_COMMAND', 'AIDP_EXECUTION_CONTEXT', 'CLAUDE_PROJECT_DIR')}
    env['CLAUDE_PROJECT_DIR'] = str(root)
    env.update(env_extra or {})
    cmd = [sys.executable, str(hook)] + (['--agent', agent] if agent != 'claude' else [])
    return subprocess.run(cmd, input=raw if raw is not None else json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=30)


class HookBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aidp-pretool-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'memory').mkdir()
        (self.root / 'code').mkdir()
        self.runtime = self.root / 'memory/.aidp'

    def edit(self, path='code/app.py', tool='Edit', **kw):
        return run_hook(self.root, {'tool_name': tool, 'cwd': str(self.root),
                                    'tool_input': {'file_path': str(self.root / path)}}, **kw)

    def bash(self, command, **kw):
        return run_hook(self.root, {'tool_name': 'Bash', 'cwd': str(self.root),
                                    'tool_input': {'command': command}}, **kw)

    def protocol_done(self, **ctx):
        from entry_context import resolve_context
        result = resolve_context(self.root, ctx.pop('entry', 'sprint-dev'), version='V1.0.0',
                                 write_set=ctx.pop('write_set', ['code']), acceptance=['fixture'])
        path = Path(result['execution_context'])
        data = result['context']
        data.update(ctx)
        path.write_text(json.dumps(data))
        (self.runtime / 'entry-task.json').write_text(json.dumps({
            'root': str(self.root), 'task_id': data['task_id'], 'execution_context': str(path)}))
        import aidp_config
        aidp_config._mark_branch_policy_read(str(self.root), aidp_config.branch_policy(str(self.root)))


class EntryProtocolTests(HookBase):
    def test_skipping_protocol_blocks_code_edit_and_says_what_to_run(self):
        for tool in ('Edit', 'Write', 'MultiEdit'):
            res = self.edit(tool=tool)
            self.assertEqual(2, res.returncode, (tool, res.stderr))
            self.assertIn('entry-context', res.stderr)
            self.assertIn('entry_context.py resolve', res.stderr)
            self.assertIn('branch-policy', res.stderr)
            self.assertIn('entry-guard-off', res.stderr, '须说明逃生舱')
            self.assertEqual('', res.stdout, 'Claude 协议只用 exit 2 + stderr')

    def test_resolved_and_branch_policy_read_allows(self):
        self.protocol_done()
        self.assertEqual(0, self.edit().returncode)

    def test_half_done_still_blocked(self):
        self.protocol_done()
        (self.runtime / 'branch-policy-read.json').unlink()
        res = self.edit()
        self.assertEqual(2, res.returncode)
        self.assertIn('branch-policy', res.stderr)
        self.assertNotIn('entry_context.py resolve', res.stderr)

    def bugfix_entry(self, context=''):
        import re
        text = (AIDP / 'commands/sprint-bugfix.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
        block = block.replace('{{AIDP_HOME}}', str(AIDP)).replace('{version}', 'V1')
        prefix = 'POLICY_ARGS=(); TASK_WRITE_SET=(code/app.py); TASK_ACCEPTANCE=(fixture)\n'
        command = prefix + block
        checked = self.bash(command, env_extra={'AIDP_SESSION_ID': 'bugfix-session'})
        self.assertEqual(0, checked.returncode, checked.stderr)
        result = subprocess.run(['bash', '-e', '-c', command], cwd=self.root,
            env=dict(os.environ, EXECUTION_CONTEXT=context, EXPLICIT_SPRINT='', AIDP_SESSION_ID='bugfix-session'),
            capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_bugfix_actual_entry_binds_first_edit_in_same_session(self):
        result = self.bugfix_entry()
        self.assertEqual('light', result['route'])
        allowed = self.edit(env_extra={'AIDP_SESSION_ID': 'bugfix-session'})
        self.assertEqual(0, allowed.returncode, allowed.stderr)
        self.assertEqual(2, self.edit(env_extra={'AIDP_SESSION_ID': 'another-session'}).returncode)
        self.assertFalse((self.runtime / 'test-allowlist').exists())

    def test_bugfix_readonly_parent_selects_identity_without_write_grant(self):
        from entry_context import resolve_context
        from entry_gate import bind_context, task_marker_path
        writable = self.bugfix_entry()['execution_context']
        other = bind_context(self.root, writable, 'another-session')['marker']
        other_before = Path(other).read_bytes()
        parent = resolve_context(self.root, 'sprint-test', version='V1', write_set=['code/app.py'])
        path = Path(parent['execution_context'])
        before = json.loads(path.read_text())
        result = self.bugfix_entry(str(path))
        self.assertEqual(str(path), result['execution_context'])
        after = json.loads(path.read_text())
        self.assertEqual(before['allowed_actions'], after['allowed_actions'])
        marker = task_marker_path(self.root, 'bugfix-session')
        self.assertEqual(str(path), json.loads(marker.read_text())['execution_context'])
        self.assertEqual(other_before, Path(other).read_bytes())
        blocked = self.edit(env_extra={'AIDP_SESSION_ID': 'bugfix-session'})
        self.assertEqual(2, blocked.returncode, blocked.stderr)
        self.assertIn('implement', blocked.stderr)

    def test_non_code_paths_unaffected(self):
        for path in ('docs/a.md', 'memory/aidp-config.yaml', 'README.md', 'tests/test_a.py'):
            self.assertEqual(0, self.edit(path).returncode, path)

    def test_notebook_and_relative_paths(self):
        res = run_hook(self.root, {'tool_name': 'Edit', 'cwd': str(self.root),
                                   'tool_input': {'file_path': 'code/rel.py'}})
        self.assertEqual(2, res.returncode)
        res = run_hook(self.root, {'tool_name': 'Edit', 'cwd': str(self.root / 'code'),
                                   'tool_input': {'file_path': 'rel.py'}})
        self.assertEqual(2, res.returncode, '相对 cwd 解析后落在 code/ 下同样受约束')

    def test_formal_context_and_tick_not_misfired(self):
        self.protocol_done(mode='formal', entry='sprint-autopilot')
        (self.runtime / 'branch-policy-read.json').unlink()
        self.assertEqual(2, self.edit().returncode, 'formal 仍必须读取 branch-policy')

    def test_unattended_tick_without_context_does_not_wedge(self):
        res = self.edit(env_extra={'AIDP_TICK_COMMAND': 'sprint-autopilot'})
        self.assertEqual(2, res.returncode)

    def test_codex_apply_patch_paths_are_checked_and_deny_json_emitted(self):
        patch = ('*** Begin Patch\n*** Update File: code/svc/a.py\n@@\n-x\n+y\n'
                 '*** Add File: docs/n.md\n+z\n*** End Patch\n')
        res = run_hook(self.root, {'tool_name': 'apply_patch', 'cwd': str(self.root),
                                   'tool_input': {'command': patch}}, agent='codex')
        self.assertEqual(2, res.returncode, res.stderr)
        out = json.loads(res.stdout)['hookSpecificOutput']
        self.assertEqual(('PreToolUse', 'deny'), (out['hookEventName'], out['permissionDecision']))
        self.assertIn('entry-context', out['permissionDecisionReason'])
        docs_only = '*** Begin Patch\n*** Add File: docs/n.md\n+z\n*** End Patch\n'
        res = run_hook(self.root, {'tool_name': 'apply_patch', 'cwd': str(self.root),
                                   'tool_input': {'command': docs_only}}, agent='codex')
        self.assertEqual(0, res.returncode)
        moved = '*** Begin Patch\n*** Update File: docs/a.md\n*** Move to: code/a.md\n*** End Patch\n'
        res = run_hook(self.root, {'tool_name': 'apply_patch', 'cwd': str(self.root),
                                   'tool_input': {'command': moved}}, agent='codex')
        self.assertEqual(2, res.returncode, '改名进 code/ 同样受约束')
        self.protocol_done()
        self.assertEqual(0, run_hook(self.root, {'tool_name': 'apply_patch', 'cwd': str(self.root),
                                                 'tool_input': {'command': patch}}, agent='codex').returncode)


class TestScopeTests(HookBase):
    def test_bare_pytest_blocked(self):
        res = self.bash('pytest')
        self.assertEqual(2, res.returncode, res.stderr)
        self.assertIn('测试范围护栏', res.stderr)
        self.assertIn('select_related_tests', res.stderr)

    def test_run_tests_script_on_directory_blocked(self):
        res = self.bash('bash scripts/run_tests.sh tests/unit')
        self.assertEqual(2, res.returncode, res.stderr)

    def test_git_stash_blocked_with_baseline_alternative(self):
        res = self.bash('git stash')
        self.assertEqual(2, res.returncode, res.stderr)
        self.assertIn('基线', res.stderr)
        self.assertEqual(2, self.bash('git stash push -u -m x').returncode)

    def test_harmless_commands_and_explicit_file_pass(self):
        for cmd in ('ls -la', 'git status', 'git stash list', 'python3 -m pytest tests/test_a.py::T::test_x'):
            self.assertEqual(0, self.bash(cmd).returncode, cmd)

    def test_allowlist_subset_enforced(self):
        d = self.runtime / 'test-allowlist'
        d.mkdir(parents=True)
        (d / 'default.json').write_text(json.dumps({'tests': ['tests/test_a.py']}))
        self.assertEqual(0, self.bash('pytest tests/test_a.py').returncode)
        self.assertEqual(2, self.bash('pytest tests/test_other.py').returncode)

    def test_test_allowlist_uses_tool_workdir(self):
        cwd = self.root / 'code/pkg'
        cwd.mkdir()
        directory = self.runtime / 'test-allowlist'
        directory.mkdir(parents=True)
        allowlist = directory / 'default.json'
        payload = {'tool_name': 'Bash', 'cwd': str(self.root),
                   'tool_input': {'command': 'pytest tests/test_a.py', 'workdir': str(cwd)}}
        allowlist.write_text(json.dumps({'tests': ['tests/test_a.py']}))
        result = run_hook(self.root, payload)
        self.assertEqual(2, result.returncode, result.stderr)
        allowlist.write_text(json.dumps({'tests': ['code/pkg/tests/test_a.py']}))
        result = run_hook(self.root, payload)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_wrap_entry_not_blocked_by_hook_itself(self):
        cmd = 'python3 .aidp/scripts/test_command_guard.py wrap -- pytest tests/test_a.py'
        self.assertEqual(0, self.bash(cmd).returncode)

    def test_bash_check_independent_of_entry_protocol(self):
        self.assertEqual(0, self.bash('git status').returncode)
        self.assertEqual(2, self.bash('pytest').returncode)


class ShellWriteTests(HookBase):
    COMMANDS = (
        "sed -i 's/a/b/' code/app.py", "sed -i.bak 's/a/b/' code/app.py",
        'printf x >code/app.py', 'echo x >> code/app.py', 'echo x >| code/app.py',
        'echo x | tee -a code/app.py', 'cp /tmp/source code/app.py',
        'mv /tmp/source code/app.py', 'mv code/app.py /tmp/destination',
        'install -m 644 /tmp/source code/app.py', 'rm -f code/app.py',
        "cd code && sed -i 's/a/b/' app.py", 'F=code/app.py; echo x > "$F"',
        "env F=code/app.py bash -c 'echo x > \"$F\"'",
        "bash -lc 'echo x > code/app.py'",
        "python3 -c 'from pathlib import Path; Path(\"code/app.py\").write_text(\"x\")'",
        "python3 -c 'open(\"code/app.py\", \"w\").write(\"x\")'",
    )

    def test_shell_writes_require_same_entry_as_edit(self):
        for command in self.COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(2, self.bash(command).returncode, command)
        self.protocol_done()
        for command in self.COMMANDS:
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_reads_and_outside_writes_remain_allowed(self):
        for command in ('cat code/app.py', "sed -n '1,5p' code/app.py", 'rg name code',
                        'echo code/app.py', 'echo x > docs/out.txt',
                        "python3 -c 'from pathlib import Path; print(Path(\"code/app.py\").read_text())'"):
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_dynamic_writes_do_not_silently_pass(self):
        for command in ('echo x > "$UNKNOWN"', 'eval "$WRITE_COMMAND"',
                        'find code -type f -exec sed -i s/a/b/ {} +',
                        'for f in code/*.py; do echo x > "$f"; done',
                        "bash -c 'echo x > \"$(get_target)\"'",
                        "python3 -c 'import os; open(os.getenv(\"TARGET\"), \"w\").write(\"x\")'"):
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual(2, result.returncode, command)
                self.assertIn('入口', result.stderr)

    def test_inline_context_is_checked_without_fallback(self):
        self.protocol_done()
        context = json.loads((self.runtime / 'entry-task.json').read_text())['execution_context']
        for value in ('missing.json', '', '"$UNKNOWN"'):
            result = self.bash('AIDP_EXECUTION_CONTEXT=' + value + ' sed -i s/a/b/ code/app.py')
            self.assertEqual(2, result.returncode, result.stderr)
        (self.runtime / 'entry-task.json').unlink()
        result = self.bash('AIDP_EXECUTION_CONTEXT=' + context + ' sed -i s/a/b/ code/app.py')
        self.assertEqual(0, result.returncode, result.stderr)

    def test_autopilot_tick_bootstrap_and_metadata_fences(self):
        import re
        text = (AIDP / 'flows/sprint-autopilot/phase-3-5b.md').read_text()
        fences = re.findall(r'```bash\n(.*?)```', text, re.S)[:3]
        self.assertEqual(3, len(fences))
        suffix = ("\nprintf '%s\\n' '{}' > memory/.aidp/result.json || exit $?\n"
                  "python3 -c 'import json,sys; print(json.load(sys.stdin).get(\"x\"))' <<< '{}'\n")
        for index, fence in enumerate(fences):
            command = fence.replace('{{AIDP_HOME}}', str(AIDP)) + suffix
            for agent in ('claude', 'codex'):
                with self.subTest(index=index, agent=agent):
                    result = self.bash(command, agent=agent)
                    self.assertEqual(0, result.returncode, result.stderr)
                    result = self.bash(command + 'printf x > code/app.py', agent=agent)
                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertIn('entry-context', result.stderr)
        self.protocol_done()
        for fence in fences:
            command = fence.replace('{{AIDP_HOME}}', str(AIDP)) + suffix + 'printf x > code/app.py'
            result = self.bash(command)
            self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, self.bash('eval "$UNKNOWN"').returncode)
        self.assertEqual(2, self.bash('printf x > "$UNKNOWN" || exit $?').returncode)
        self.assertEqual(2, self.bash("python3 -c 'exec(input())' <<< 'rm code/app.py'").returncode)

    def test_current_sprint_dev_bootstrap_is_not_blocked_before_resolve(self):
        text = (AIDP / 'commands/sprint-dev.md').read_text()
        command = text.split('```bash', 1)[1].split('```', 1)[0]
        result = self.bash(command)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_codex_shell_payloads(self):
        cases = [('Bash', {'command': ['bash', '-lc', 'echo x > code/app.py']}),
                 ('shell', {'command': ['bash', '-lc', 'echo x > code/app.py']}),
                 ('shell_command', {'command': 'echo x > code/app.py'}),
                 ('exec_command', {'cmd': 'echo x > app.py', 'workdir': str(self.root / 'code')})]
        for tool, tool_input in cases:
            with self.subTest(tool=tool):
                result = run_hook(self.root, {'tool_name': tool, 'cwd': str(self.root),
                                             'tool_input': tool_input}, agent='codex')
                self.assertEqual(2, result.returncode, result.stderr)


class FixedMetadataFenceTests(HookBase):
    def test_official_conditional_metadata_fences_pass_without_running_deployment(self):
        import re
        for name, count in (('phase-3-5b.md', 6), ('phase-3-6.md', 5), ('phase-3-7.md', 3)):
            text = (AIDP / 'flows/sprint-autopilot' / name).read_text()
            fences = re.findall(r'(?m)^([ \t]*(?:>[ \t]*)?)```bash[^\n]*\n(.*?)^[ \t]*(?:>[ \t]*)?```', text, re.S)
            self.assertEqual(count, len(fences), name)
            for index, (prefix, fence) in enumerate(fences):
                if '>' in prefix:
                    fence = re.sub(r'(?m)^[ \t]*>[ \t]?', '', fence)
                command = fence.replace('{{AIDP_HOME}}', str(AIDP))
                for agent in ('claude', 'codex'):
                    with self.subTest(name=name, fence=index + 1, agent=agent):
                        result = self.bash(command, agent=agent)
                        self.assertEqual(0, result.returncode, result.stderr)
                        result = self.bash(command + '\nprintf x >> code/app.py', agent=agent)
                        self.assertEqual(2, result.returncode, result.stderr)
                        result = self.bash(command + '\nprintf x > "$UNKNOWN"', agent=agent)
                        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual([], list(self.root.rglob('deploy-watch.json')))
        self.assertEqual([], list(self.root.rglob('cicd-detect.json')))

    def test_conditional_metadata_alias_to_code_is_still_guarded(self):
        (self.root / 'memory/.aidp').symlink_to(self.root / 'code', target_is_directory=True)
        result = self.bash('if true; then printf x > memory/.aidp/app.py; fi')
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn('entry-context', result.stderr)


class BudgetFenceTests(HookBase):
    def budget_fence(self):
        import re
        text = (AIDP / 'flows/sprint-dev/light-context.md').read_text()
        fences = [fence for fence in re.findall(r'```bash\n(.*?)```', text, re.S)
                  if ' reserve-budget ' in fence]
        self.assertEqual(1, len(fences), '必须提取官方完整预算围栏')
        return fences[0].replace('{{AIDP_HOME}}', str(AIDP))

    def test_official_complete_budget_fence_passes_hook(self):
        command = self.budget_fence()
        for agent in ('claude', 'codex'):
            with self.subTest(agent=agent):
                result = self.bash(command, agent=agent)
                self.assertEqual(0, result.returncode, result.stderr)

    def budget_execution(self, **overrides):
        import hashlib
        self.protocol_done()
        context = Path(json.loads((self.runtime / 'entry-task.json').read_text())['execution_context'])
        command = self.budget_fence()
        env = dict(os.environ, EXECUTION_CONTEXT=str(context), ACTION='static',
                   RESOURCE='elapsed_seconds', COST='3', ACTUAL_SECONDS='1',
                   INPUT_HASH=hashlib.sha256(command.encode()).hexdigest(),
                   STATUS='UNVERIFIED', ROOT_CAUSE='fixture', EVIDENCE_JSON='{}',
                   TMPDIR=str(self.root / 'code'))
        env.update(overrides)
        checked = self.bash(command, env_extra=env)
        self.assertEqual(0, checked.returncode, checked.stderr)
        budget = context.with_name('budget.json')
        before = json.loads(budget.read_text()) if budget.exists() else None
        result = subprocess.run(['bash', '-c', command], cwd=self.root, env=env,
                                capture_output=True, text=True, timeout=30)
        return result, budget, before

    def test_budget_fence_really_reserves_settles_and_records_without_temp_files(self):
        result, budget, before = self.budget_execution()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        state = json.loads(budget.read_text())
        self.assertEqual(before['used']['elapsed_seconds'] + 1, state['used']['elapsed_seconds'])
        self.assertEqual(len(before['reservations']) + 1, len(state['reservations']))
        reservation = state['reservations'][-1]
        self.assertEqual((3, 1), (reservation['cost'], reservation['actual_cost']))
        authorized, settled, outcome = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual('AUTHORIZED', authorized['status'])
        self.assertEqual('SETTLED', settled['status'])
        self.assertEqual(reservation['reservation_id'], settled['reservation_id'])
        self.assertEqual([outcome], state['outcomes'])
        self.assertEqual('UNVERIFIED', outcome['status'])
        self.assertEqual([], list(self.root.rglob('reservation.*.json')))
        self.assertEqual([], list((self.root / 'code').iterdir()))

    def test_budget_fence_soft_total_limit_overrun_is_recorded_not_blocked(self):
        result, budget, before = self.budget_execution(COST='1000000000')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        state = json.loads(budget.read_text())
        self.assertTrue(any(row.get('resource') == 'elapsed_seconds' for row in state['soft_events']),
                        '软限超额必须留痕（预警），而不是静默或阻断')

    def test_budget_fence_keeps_authorization_and_over_budget_exit(self):
        # elapsed_seconds 默认是总量软限（超额只预警，见下一用例）；固定硬限 retries 超额仍拒绝且不改账本
        for overrides in ({'ACTION': 'deploy'}, {'RESOURCE': 'retries', 'COST': '1000000000'}):
            with self.subTest(overrides=overrides):
                result, budget, before = self.budget_execution(**overrides)
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertEqual(before, json.loads(budget.read_text()), '拒绝后不能预留或登记结果')
                self.assertNotIn('SETTLED', result.stdout)
                self.assertNotIn('UNVERIFIED', result.stdout)

    def test_budget_fence_does_not_hide_appended_writes(self):
        command = self.budget_fence()
        for agent in ('claude', 'codex'):
            for suffix in ('printf x >> code/app.py', 'printf x > "$UNKNOWN"'):
                with self.subTest(agent=agent, suffix=suffix):
                    result = self.bash(command + '\n' + suffix, agent=agent)
                    self.assertEqual(2, result.returncode, result.stderr)
        self.protocol_done()
        result = self.bash(command + '\nprintf x > "$UNKNOWN"')
        self.assertEqual(2, result.returncode, result.stderr)


class SwitchAndFailOpenTests(HookBase):
    def test_legacy_escape_disables_entry_only(self):
        (self.root / 'memory/.pretool-guard-off').write_text('')
        self.assertEqual(0, self.edit().returncode)
        self.assertEqual(2, self.bash('pytest').returncode)

    def test_entry_config_does_not_disable_test_guard(self):
        (self.root / 'memory/aidp-config.yaml').write_text('entry_guard:\n  enabled: false\n', encoding='utf-8')
        self.assertEqual(0, self.edit().returncode)
        self.assertEqual(2, self.bash('git stash').returncode)
        (self.root / 'memory/aidp-config.yaml').write_text('entry_guard:\n  enabled: true\n', encoding='utf-8')
        self.assertEqual(2, self.edit().returncode)

    def test_test_switch_does_not_disable_entry(self):
        for switch in ('config', 'file'):
            if switch == 'config':
                (self.root / 'memory/aidp-config.yaml').write_text('test_guard:\n  enabled: false\n')
            else:
                (self.root / 'memory/aidp-config.yaml').unlink()
                (self.root / 'memory/.test-guard-off').touch()
            self.assertEqual(0, self.bash('pytest').returncode)
            self.assertEqual(2, self.edit().returncode)
            self.assertEqual(2, self.bash('echo x > code/app.py').returncode)

    def test_garbage_input_rejected_unknown_tools_allowed(self):
        for raw in ('', 'not json', '[]', '{"tool_name": "Bash"}', '{"tool_name": "Bash", "tool_input": 3}',
                    '{"tool_name": "Edit", "tool_input": {"file_path": 5}}'):
            self.assertEqual(2, run_hook(self.root, None, raw=raw).returncode, raw)
        self.assertEqual(0, run_hook(self.root, {'tool_name': 'Read', 'tool_input': {}}).returncode)

    def test_missing_dependency_script_blocks_and_is_noted(self):
        layout = Path(self.temp.name) / 'fake'
        (layout / '.aidp/hooks').mkdir(parents=True)
        (layout / '.aidp/scripts').mkdir(parents=True)
        shutil.copy(HOOK, layout / '.aidp/hooks/pretool-guard.py')
        res = run_hook(self.root, {'tool_name': 'Bash', 'cwd': str(self.root), 'tool_input': {'command': 'pytest'}},
                       hook=layout / '.aidp/hooks/pretool-guard.py')
        self.assertEqual(2, res.returncode, res.stderr)
        notes = (self.runtime / 'pretool-guard-skips.jsonl').read_text().splitlines()
        self.assertEqual(1, len(notes))
        self.assertIn('ModuleNotFoundError', json.loads(notes[0])['detail'])

    def test_guard_exception_is_noted_blocking_and_log_is_bounded(self):
        layout = Path(self.temp.name) / 'stub'
        (layout / '.aidp/hooks').mkdir(parents=True)
        (layout / '.aidp/scripts').mkdir(parents=True)
        shutil.copy(HOOK, layout / '.aidp/hooks/pretool-guard.py')
        (layout / '.aidp/scripts/entry_gate.py').write_text(
            'def find_context(root, env=None):\n    return None, None\n')
        (layout / '.aidp/scripts/test_command_guard.py').write_text(
            'def evaluate(command, root=".", execution_context=None):\n    raise RuntimeError("boom")\n')
        hook = layout / '.aidp/hooks/pretool-guard.py'
        for _ in range(55):
            res = run_hook(self.root, {'tool_name': 'Bash', 'cwd': str(self.root),
                                       'tool_input': {'command': 'pytest'}}, hook=hook)
            self.assertEqual(2, res.returncode)
        notes = (self.runtime / 'pretool-guard-skips.jsonl').read_text().splitlines()
        self.assertEqual(50, len(notes))
        self.assertIn('boom', notes[-1])

    def test_stub_denial_reason_and_hint_are_passed_through(self):
        layout = Path(self.temp.name) / 'stub2'
        (layout / '.aidp/hooks').mkdir(parents=True)
        (layout / '.aidp/scripts').mkdir(parents=True)
        shutil.copy(HOOK, layout / '.aidp/hooks/pretool-guard.py')
        (layout / '.aidp/scripts/entry_gate.py').write_text(
            'def find_context(root, env=None):\n    return None, None\n')
        (layout / '.aidp/scripts/test_command_guard.py').write_text(
            'def evaluate(command, root=".", execution_context=None):\n'
            '    return {"allowed": False, "reason": "REASON-X", "hint": "HINT-Y {{AIDP_HOME}}/scripts/x.py", "kind": "pytest"}\n')
        res = run_hook(self.root, {'tool_name': 'Bash', 'cwd': str(self.root), 'tool_input': {'command': 'x'}},
                       hook=layout / '.aidp/hooks/pretool-guard.py', agent='codex')
        self.assertEqual(2, res.returncode)
        self.assertIn('REASON-X', res.stderr)
        self.assertIn('HINT-Y', res.stderr)
        self.assertNotIn('{{AIDP_HOME}}', res.stderr, '占位须渲染成运行根相对路径')
        self.assertIn('.aidp/scripts/x.py', res.stderr)
        self.assertIn('"permissionDecision": "deny"', res.stdout)

    def test_hook_does_not_modify_project_state_on_allow(self):
        self.protocol_done()
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        self.assertEqual(0, self.edit().returncode)
        self.assertEqual(0, self.bash('git status').returncode)
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')))


class ActionableDenialTests(HookBase):
    """误报收敛 + 可操作报错：类别/命中片段/合规替代/自检，且写集外仍然拒绝。"""

    def setUp(self):
        super().setUp()
        for directory in ('code/backend/x', 'code/frontend/y'):
            (self.root / directory).mkdir(parents=True)
        (self.root / 'code/backend/x/a.py').write_text('x = 1\n')

    def ready(self):
        self.protocol_done(write_set=['code/backend'])

    def test_heredoc_to_literal_path_inside_write_set_passes_outside_denied(self):
        self.ready()
        inside = "cat >> code/backend/x/tests_a.py <<'EOF'\nvalue = 1 > 0; echo $(rm -rf code)\nEOF"
        self.assertEqual(0, self.bash(inside).returncode)
        python_inside = "python3 - <<'EOF'\nfrom pathlib import Path\nPath('code/backend/x/a.py').write_text('y = 2')\nEOF"
        self.assertEqual(0, self.bash(python_inside).returncode)
        outside = self.bash("cat >> code/frontend/y/a.ts <<'EOF'\nx\nEOF")
        self.assertEqual(2, outside.returncode)
        python_outside = self.bash("python3 - <<'EOF'\nopen('code/frontend/y/a.ts', 'w').write('x')\nEOF")
        self.assertEqual(2, python_outside.returncode)

    def test_sed_inplace_literal_path_inside_passes_outside_denied(self):
        self.ready()
        self.assertEqual(0, self.bash("sed -i 's/旧*/新?/' code/backend/x/a.py").returncode)
        self.assertEqual(0, self.bash("sed -i '' 's/a/b/' code/backend/x/a.py").returncode)
        denied = self.bash("sed -i 's/旧/新/' code/frontend/y/a.ts")
        self.assertEqual(2, denied.returncode)
        self.assertEqual(2, self.bash("sed -i 's/a/b/' code/backend/x/*.py").returncode)

    def test_write_set_denial_prints_copyable_in_task_revise_command(self):
        self.ready()
        denied = self.edit('code/frontend/y/app.ts')
        self.assertEqual(2, denied.returncode)
        self.assertIn('超出本任务 write_set', denied.stderr)
        self.assertIn('entry_context.py revise', denied.stderr)
        self.assertIn('--add-write-set code/frontend/y', denied.stderr)
        self.assertIn('--execution-context "memory/.aidp/entry-contexts/', denied.stderr)
        self.assertNotIn('先完成入口 resolve', denied.stderr)

    def test_revise_add_write_set_extends_same_task_without_new_start(self):
        self.ready()
        from entry_gate import find_context
        path, ctx = find_context(self.root, {})
        self.assertEqual(2, self.edit('code/frontend/y/app.ts').returncode)
        done = subprocess.run([sys.executable, str(AIDP / 'scripts/entry_context.py'), 'revise', '--root', str(self.root),
                               '--execution-context', str(path), '--add-write-set', 'code/frontend/y', '--json'],
                              text=True, capture_output=True)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(ctx['task_id'], json.loads(done.stdout)['task_id'])
        self.assertEqual(0, self.edit('code/frontend/y/app.ts').returncode)
        self.assertEqual(0, self.edit('code/backend/x/a.py').returncode, '原写集仍然有效')
        self.assertEqual(2, self.edit('code/other/z.py').returncode, '未声明的路径仍被拒绝')

    def test_protocol_incomplete_and_undecidable_are_distinguished(self):
        protocol = self.bash("echo x > code/backend/x/a.py")
        self.assertEqual(2, protocol.returncode)
        self.assertIn('协议未完成', protocol.stderr)
        self.assertNotIn('静态分析无法判定', protocol.stderr)
        self.ready()
        undecided = self.bash('echo x > "code/$UNKNOWN.py"')
        self.assertEqual(2, undecided.returncode)
        self.assertIn('静态分析无法判定', undecided.stderr)
        self.assertIn('变量/通配符写目标', undecided.stderr)
        self.assertIn('$UNKNOWN', undecided.stderr, '须指出命中片段')
        self.assertIn('Write/Edit', undecided.stderr, '须给合规替代写法')
        self.assertIn('--explain', undecided.stderr)
        self.assertNotIn('先完成入口 resolve', undecided.stderr)

    def test_each_denial_category_names_fragment_and_alternative(self):
        self.ready()
        cases = {
            'wildcard': 'for f in code/backend/*.py; do echo x > "$f"; done',
            'python': "python3 - <<'EOF'\nfor p in ['a']:\n    open(p, 'w').write('x')\nEOF",
            'heredoc': "xargs rm <<'EOF'\ncode/a\nEOF",
        }
        for category, command in cases.items():
            with self.subTest(category=category):
                result = self.bash(command)
                self.assertEqual(2, result.returncode)
                self.assertIn('合规替代', result.stderr)
                self.assertIn('静态分析无法判定', result.stderr)

    def test_docker_container_writes_ask_instead_of_wrapper_denial(self):
        self.ready()
        for command in ('docker cp ./a.txt web:/app/a.txt', 'docker exec web sh -c "echo x > /tmp/a"',
                        'docker run --rm img chown -R 1000:1000 /data'):
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual(0, result.returncode, result.stderr)
                decision = json.loads(result.stdout)['hookSpecificOutput']
                self.assertEqual('ask', decision['permissionDecision'])
                self.assertIn('外部副作用', decision['permissionDecisionReason'])
                self.assertNotIn('包装器', decision['permissionDecisionReason'])
        self.assertEqual(0, self.bash('docker cp ./a.txt web:/app/a.txt', agent='codex').returncode)

    def deploy_ready(self):
        """与 ready() 相同，但任务持有 deploy 授权（经真实入口解析，不改写上下文以免破坏身份校验）。"""
        from entry_context import resolve_context
        result = resolve_context(self.root, 'sprint-dev', version='V1.0.0', write_set=['code'], acceptance=['fixture'],
                                 additional_grants=['deploy'], authorization_source={
                                     'kind': 'user-text', 'request_id': 'deploy-1', 'text': '本次允许部署到容器'})
        (self.runtime / 'entry-task.json').write_text(json.dumps({
            'root': str(self.root), 'task_id': result['task_id'], 'execution_context': result['execution_context']}))
        import aidp_config
        aidp_config._mark_branch_policy_read(str(self.root), aidp_config.branch_policy(str(self.root)))

    def test_unattended_docker_write_is_decided_deterministically_not_asked(self):
        """P1-2：无人值守 tick 里没人能答 ask——无 deploy 授权明确拒绝并说明，有则放行并留痕；各 Agent 行为一致。"""
        command = 'docker cp ./a.txt web:/app/a.txt'
        tick = {'AIDP_TICK_COMMAND': 'sprint-autopilot'}
        self.ready()
        for agent in ('claude', 'codex'):
            denied = self.bash(command, agent=agent, env_extra=tick)
            self.assertEqual(2, denied.returncode, (agent, denied.stderr))
            self.assertIn('deploy 授权', denied.stderr)
            self.assertNotIn('"ask"', denied.stdout)
        self.deploy_ready()
        for agent in ('claude', 'codex'):
            allowed = self.bash(command, agent=agent, env_extra=tick)
            self.assertEqual(0, allowed.returncode, (agent, allowed.stderr))
            self.assertNotIn('"ask"', allowed.stdout)
        ledger = (self.root / 'memory/.aidp/external-side-effects.jsonl').read_text()
        self.assertEqual(2, ledger.count('deploy-authorized-unattended'))
        # 交互会话保持原样：claude 走 ask
        interactive = self.bash(command)
        self.assertEqual('ask', json.loads(interactive.stdout)['hookSpecificOutput']['permissionDecision'])

    def test_docker_bind_mount_follows_host_write_set(self):
        self.ready()
        inside = self.bash(f'docker run --rm -v {self.root}/code/backend:/w img chown -R 1000:1000 /w/x')
        self.assertEqual(0, inside.returncode, inside.stderr)
        self.assertEqual('', inside.stdout, '落在写集内的 bind mount 不弹授权，直接按宿主路径放行')
        outside = self.bash(f'docker run --rm -v {self.root}/code/frontend:/w img chown -R 1000:1000 /w/y')
        self.assertEqual(2, outside.returncode)
        self.assertIn('code/frontend/y', outside.stderr)
        self.assertEqual(2, self.bash(f'docker cp web:/app/o.txt {self.root}/code/frontend/y/o.txt').returncode)
        self.assertEqual(0, self.bash(f'docker cp web:/app/o.txt {self.root}/code/backend/x/o.txt').returncode)

    def test_scratch_directories_are_writable_without_protocol(self):
        for command in ("cat > /tmp/aidp-scratch-check.txt <<'EOF'\nhello\nEOF",
                        "mkdir -p memory/.aidp/scratch && cat > memory/.aidp/scratch/note.md <<'EOF'\nx\nEOF",
                        "python3 - <<'EOF'\nopen('/tmp/aidp-scratch-check.txt', 'w').write('x')\nEOF"):
            with self.subTest(command=command):
                result = self.bash(command)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_explain_reports_decision_without_executing(self):
        self.ready()
        marker = self.root / 'explain-marker.txt'
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        def explain(command, *extra):
            return subprocess.run([sys.executable, str(HOOK), '--explain', command, *extra], text=True,
                                  capture_output=True, env=env, timeout=30)
        denied = explain(f'echo x > {marker}; echo y > code/frontend/y/a.ts')
        self.assertEqual(2, denied.returncode, denied.stdout + denied.stderr)
        self.assertIn('拒绝', denied.stdout)
        self.assertIn('仅解释，未执行', denied.stdout)
        self.assertFalse(marker.exists(), '--explain 不得执行命令')
        allowed = explain("cat >> code/backend/x/a.py <<'EOF'\nx\nEOF")
        self.assertEqual(0, allowed.returncode, allowed.stdout + allowed.stderr)
        self.assertIn('允许', allowed.stdout)
        asked = explain('docker cp ./a web:/a')
        self.assertEqual(0, asked.returncode)
        self.assertIn('需授权提示', asked.stdout)
        as_json = json.loads(explain('echo x > "$UNKNOWN"', '--json').stdout)
        self.assertEqual('deny', as_json['decision'])
        self.assertEqual('static-undecidable', as_json['kind'])
        self.assertFalse(as_json['executed'])
        edit = subprocess.run([sys.executable, str(HOOK), '--explain-edit', 'code/frontend/y/a.ts'], text=True,
                              capture_output=True, env=env, timeout=30)
        self.assertEqual(2, edit.returncode)
        self.assertIn('write_set', edit.stdout)


if __name__ == '__main__':
    unittest.main()
