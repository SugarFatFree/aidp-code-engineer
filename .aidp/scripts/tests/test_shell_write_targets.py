#!/usr/bin/env python3
"""常见 shell 写目标解析：路径、重定向、环境和包装器反例。"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shell_write_targets import analyze


class ShellTargetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'code').mkdir()

    def targets(self, command, **kwargs):
        return analyze(command, self.root, **kwargs)

    def assert_targets(self, command, paths):
        result = self.targets(command, env={})
        self.assertFalse(result['uncertain'], result)
        self.assertEqual({str(self.root / p) for p in paths}, set(result['targets']), result)

    def test_common_redirects_with_quotes_and_descriptors(self):
        self.assert_targets('echo x > "code/a b.py" 2>&1', ['code/a b.py'])
        self.assert_targets('echo x &>code/log', ['code/log'])
        self.assert_targets('echo x >>code/log', ['code/log'])
        self.assert_targets('echo x >|code/log', ['code/log'])

    def test_copy_move_directory_targets_resolve_destination_basename(self):
        self.assert_targets('cp /tmp/a.py code/', ['code/a.py'])
        self.assert_targets('cp -t code /tmp/a.py', ['code/a.py'])
        self.assert_targets('mv /tmp/a.py code/', ['code/a.py', '/tmp/a.py'])
        self.assert_targets('cp -t . /tmp/code', ['code'])

    def test_export_and_known_env_cwd_paths(self):
        self.assert_targets('export F=code/a.py; echo x > "$F"', ['code/a.py'])
        self.assert_targets('cd code && echo x > a.py', ['code/a.py'])
        self.assert_targets('env F=code/a.py bash -c \'echo x > "$F"\'', ['code/a.py'])
        self.assertTrue(self.targets('env -i bash -c \'echo x > "$F"\'', env={'F': 'docs/a'})['uncertain'])

    def test_sed_suffix_is_also_a_write(self):
        self.assert_targets("sed -i.bak 's/a/b/' code/a.py", ['code/a.py', 'code/a.py.bak'])
        self.assert_targets("sed -i -e 's/a/b/' code/a.py", ['code/a.py'])

    def test_python_assignment_order_does_not_hide_prior_write(self):
        result = self.targets("python3 -c 'p=\"code/a.py\"; open(p,\"w\"); p=\"docs/a.py\"'")
        self.assertIn(str(self.root / 'code/a.py'), result['targets'])

    def test_pure_read_substitution_is_not_a_write(self):
        for command in ('echo $(pwd)', 'cat "$(pwd)/code/a.py"', 'cat <(ls code)',
                        "echo '$(rm code/a.py)'", 'cat code/a.py | rg name'):
            with self.subTest(command=command):
                result = self.targets(command)
                self.assertFalse(result['uncertain'], result)
                self.assertEqual([], result['targets'])

    def test_substitution_writes_and_dynamic_destination_rejected(self):
        result = self.targets('echo $(rm code/a.py)')
        self.assertIn(str(self.root / 'code/a.py'), result['targets'])
        self.assertTrue(self.targets('echo x > "$(get_target)"')['uncertain'])

    def test_comment_does_not_hide_later_write(self):
        self.assert_targets('# explanation\nprintf x > code/a.py', ['code/a.py'])
        self.assert_targets('# $(rm code/a.py)\ncat code/a.py', [])

    def test_trusted_tick_flags_eval_is_narrow(self):
        script = Path(__file__).resolve().parents[1] / 'autopilot_tick_flags.py'
        for options in ('--shell', '--command autopilot --shell', '--shell --command aiauto-test'):
            with self.subTest(options=options):
                self.assert_targets(f'eval "$(python3 {script} {options})"', [])
        for command in (f'eval $(python3 {script} --shell)',
                        f'eval "$(python3 {script} --shell)" "$EXTRA"',
                        f'eval "$(python3 {script} --shell; printf rm)"',
                        f'eval "$(python3 {script} set BUILD x)"',
                        'eval "$(python3 /tmp/autopilot_tick_flags.py --shell)"',
                        'eval "$UNKNOWN"', 'eval "rm code/a.py"'):
            with self.subTest(command=command):
                self.assertTrue(self.targets(command)['uncertain'])

    def test_tick_export_is_not_a_static_write_path(self):
        script = Path(__file__).resolve().parents[1] / 'autopilot_tick_flags.py'
        self.assertTrue(self.targets(f'printf x > "$(python3 {script} --shell)"')['uncertain'])

    def test_fixed_metadata_output_and_exit_are_known(self):
        self.assert_targets("printf '%s\\n' '{}' > memory/.aidp/result.json || exit $?",
                            ['memory/.aidp/result.json'])
        self.assert_targets('OUT=memory/.aidp/result.json; printf x > "$OUT" || exit $?',
                            ['memory/.aidp/result.json'])
        self.assertTrue(self.targets('printf x > "$UNKNOWN" || exit $?')['uncertain'])
        self.assertTrue(self.targets('false || cd code; printf x > app.py')['uncertain'])

    def test_readonly_here_string_is_data_not_program(self):
        self.assert_targets("python3 -c 'import json,sys; print(json.load(sys.stdin).get(\"x\"))' <<< '{}'", [])
        for command in ("bash <<< 'rm code/a.py'", "python3 <<< 'open(\"code/a.py\",\"w\")'"):
            with self.subTest(command=command):
                self.assertTrue(self.targets(command)['uncertain'])

    def test_only_literal_metadata_writes_can_ignore_conditional_execution(self):
        self.assert_targets('mkdir -p memory/.aidp; if true; then printf x > memory/.aidp/out.json; fi',
                            ['memory/.aidp', 'memory/.aidp/out.json'])
        self.assert_targets('if true; then printf x > memory/.aidp/a.json; else printf x > memory/.aidp/b.json; fi',
                            ['memory/.aidp/a.json', 'memory/.aidp/b.json'])
        for command in (
            'if true; then printf x > code/app.py; fi',
            'if true; then printf x > docs/out.json; fi',
            'F=code/app.py; if false; then :; F=memory/.aidp/out.json; fi; printf x > "$F"',
            'if true; then cd code; fi; printf x > memory/.aidp/out.json',
            'if true; then cd code; else cd .; fi; printf x > memory/.aidp/out.json',
            'C=cd; if false; then :; C=true; fi; $C code; printf x > memory/.aidp/out.json',
            'C=true; if true; then C=cd; fi; $C code; printf x > memory/.aidp/out.json',
            'A=c; B=d; C=true; if true; then C=$A$B; fi; $C code; printf x > memory/.aidp/out.json',
            'if true; then\nenv -C code sh -c "printf x > memory/.aidp/out.json"; fi',
            'ln --symbolic ../code memory/.aidp; if true; then printf x > memory/.aidp/app.py; fi',
            'C="builtin cd"; $C code; if true; then printf x > memory/.aidp/out.json; fi',
        ):
            with self.subTest(command=command):
                self.assertTrue(self.targets(command, env={})['uncertain'])

    def test_mktemp_outputs_remain_dynamic_even_with_unsafe_environment_or_templates(self):
        commands = (
            'F=$(mktemp); printf x > "$F"',
            'TMPDIR=code; F=$(mktemp); printf x > "$F"',
            'TMPDIR="$UNKNOWN"; F=$(mktemp); printf x > "$F"',
            'F=$(TMPDIR=code mktemp); printf x > "$F"',
            'F=$(mktemp code/reservation.XXXXXX.json); printf x > "$F"',
            'F=$(mktemp "$UNKNOWN/reservation.XXXXXX"); printf x > "$F"',
            'F=$(mktemp -p code); printf x > "$F"',
            'F=$(mktemp; printf code/app.py); printf x > "$F"',
            'F=$(mktemp || printf code/app.py); printf x > "$F"',
        )
        for env in ({}, {'TMPDIR': 'code'}, {'TMPDIR': '$UNKNOWN'}):
            for command in commands:
                with self.subTest(command=command, env=env):
                    self.assertTrue(self.targets(command, env=env)['uncertain'])
        result = self.targets('F=$(mktemp; printf x >> code/app.py); printf x > "$F"')
        self.assertTrue(result['uncertain'])
        self.assertIn(str(self.root / 'code/app.py'), result['targets'])

    def test_unrecognized_writer_wrapper_is_conservative(self):
        self.assertTrue(self.targets('nice -n 5 sed -i s/a/b/ code/a.py')['uncertain'])


if __name__ == '__main__':
    unittest.main()
