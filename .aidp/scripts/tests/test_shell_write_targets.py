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

    # ── heredoc：落点可静态确定的不再一律拒绝，正文不是命令 ──
    def test_heredoc_with_literal_target_is_determined(self):
        self.assert_targets("cat >> code/a/tests/t.py <<'EOF'\nx = 1 > 0; y = $(rm -rf code)\nEOF", ['code/a/tests/t.py'])
        self.assert_targets("cat > code/a.txt <<EOF\nplain text > not redirect\nEOF", ['code/a.txt'])
        self.assert_targets("tee code/a.txt <<'EOF'\nhello\nEOF", ['code/a.txt'])
        self.assert_targets("cat <<-'EOF' > code/a.txt\n\tindented\n\tEOF", ['code/a.txt'])

    def test_heredoc_negative_dynamic_target_and_unquoted_substitution_still_checked(self):
        self.assertTrue(self.targets("cat > code/$NAME.py <<'EOF'\nx\nEOF", env={})['uncertain'])
        # 未加引号的 heredoc 正文会真实执行 $(...)，其中的写入必须计入
        result = self.targets("cat <<EOF > /tmp/x\n$(echo hi > code/leak.txt)\nEOF", env={})
        self.assertIn(str(self.root / 'code/leak.txt'), result['targets'])
        # 带引号的正文只是数据
        quoted = self.targets("cat <<'EOF' > /tmp/x\n$(echo hi > code/leak.txt)\nEOF", env={})
        self.assertNotIn(str(self.root / 'code/leak.txt'), quoted['targets'])
        self.assertTrue(self.targets("xargs rm <<'EOF'\ncode/a\nEOF", env={})['uncertain'])

    def test_python_stdin_heredoc_is_analyzed_as_program(self):
        ok = "python3 - <<'EOF'\nfrom pathlib import Path\np = Path('code/a.py')\ntext = p.read_text().replace('a', 'b')\n" \
             "if text:\n    text = text.strip()\np.write_text(text)\nEOF"
        self.assert_targets(ok, ['code/a.py'])
        self.assert_targets("python3 - <<'EOF'\nwith open('code/a.txt', 'w') as f:\n    f.write('hi')\nEOF", ['code/a.txt'])
        self.assertTrue(self.targets("python3 - <<'EOF'\nfor p in ['a', 'b']:\n    open(p, 'w').write('x')\nEOF", env={})['uncertain'])
        escape = self.targets("python3 - <<'EOF'\nimport os\nos.system('rm code/a.py')\nEOF", env={})
        self.assertIn(str(self.root / 'code/a.py'), escape['targets'])
        self.assertTrue(self.targets("python3 - <<'EOF'\nunknown_tool.save()\nEOF", env={})['uncertain'])

    def test_failure_details_name_category_and_fragment(self):
        result = self.targets("cat > code/$NAME.py <<'EOF'\nx\nEOF", env={})
        self.assertEqual('wildcard', result['details'][0]['category'])
        self.assertIn('$NAME', result['details'][0]['fragment'])

    # ── sed -i：只看文件参数，s/…/…/ 里的字符不是通配符 ──
    def test_sed_inplace_checks_only_file_operands(self):
        self.assert_targets("sed -i 's/旧*/新?/' code/a.py", ['code/a.py'])
        self.assert_targets("sed -i '' 's/a*/b/' code/a.py", ['code/a.py'])
        self.assert_targets("sed -i.bak -E 's/x|y/[z]/g' code/a.py", ['code/a.py', 'code/a.py.bak'])
        self.assert_targets("sed -i -e 's/a/b/' -e 's/c*/d/' code/a.py code/b.py", ['code/a.py', 'code/b.py'])
        self.assertTrue(self.targets("sed -i 's/a/b/' code/*.py", env={})['uncertain'])
        self.assertTrue(self.targets("sed -i 's/a/b/'", env={})['uncertain'])

    # ── docker：容器写入单独分类 ──
    def test_docker_container_writes_are_external_side_effects(self):
        for command in ('docker cp ./a.txt web:/app/a.txt', 'docker exec web sh -c "echo hi > /tmp/a"',
                        'docker run --rm img chown -R 1000:1000 /data'):
            with self.subTest(command=command):
                result = self.targets(command, env={})
                self.assertFalse(result['uncertain'], result)
                self.assertEqual([], result['targets'])
                self.assertTrue(result['external'], result)

    def test_docker_bind_mount_and_cp_out_map_to_host_paths(self):
        self.assert_targets('docker cp web:/app/out.txt code/out.txt', ['code/out.txt'])
        self.assert_targets(f'docker run --rm -v {self.root}/code:/w img chown -R 1000:1000 /w/x', ['code/x'])
        mounted = self.targets(f'docker run --rm --mount type=bind,source={self.root}/code,target=/w img rm -rf /w/y', env={})
        self.assertEqual([str(self.root / 'code/y')], mounted['targets'])
        outside = self.targets(f'docker run --rm -v {self.root}/code:/w img chown 1:1 /elsewhere', env={})
        self.assertEqual([], outside['targets'])
        self.assertTrue(outside['external'])

    def test_docker_does_not_hide_host_side_writes(self):
        result = self.targets('docker cp web:/app/a.txt code/a.txt && echo x > code/b.txt', env={})
        self.assertEqual({str(self.root / 'code/a.txt'), str(self.root / 'code/b.txt')}, set(result['targets']))

    def test_python_command_name_variants_are_equivalent(self):
        program = "\nfrom pathlib import Path\nPath('code/a.py').write_text('x')\nEOF"
        for name in ('python3', 'python', 'python3.11', 'python2'):
            with self.subTest(name=name):
                self.assert_targets("%s - <<'EOF'%s" % (name, program), ['code/a.py'])
                self.assert_targets("%s -c \"open('code/b.py', 'w').write('x')\"" % name, ['code/b.py'])
                bad = self.targets("%s - <<'EOF'\nopen(p, 'w').write('x')\nEOF" % name, env={})
                self.assertTrue(bad['uncertain'])

    def test_tick_bootstrap_accepts_python_or_python3(self):
        helper = Path(__file__).resolve().parents[1] / 'autopilot_tick_flags.py'
        for name in ('python3', 'python'):
            with self.subTest(name=name):
                result = self.targets('eval "$(%s %s --shell --command autopilot)"' % (name, helper), env={})
                self.assertFalse(result['uncertain'], result)


if __name__ == '__main__':
    unittest.main()
