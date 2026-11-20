#!/usr/bin/env python3
"""docker_host_user.py：补 --user 的容器包装与脚本 --user 检查（不执行 docker）。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import docker_host_user as wrapper  # noqa: E402


class WrapperTests(unittest.TestCase):
    def test_run_and_exec_get_host_user_unless_explicit(self):
        self.assertEqual(['docker', 'run', '--user', '1000:1001', '--rm', 'img', 'id'],
                         wrapper.build_command('run', ['--rm', 'img', 'id'], 1000, 1001))
        self.assertEqual(['docker', 'exec', '--user', '5:6', 'web', 'ls'],
                         wrapper.build_command('exec', ['web', 'ls'], 5, 6))
        for explicit in (['-u', 'root', 'img'], ['--user', '0', 'img'], ['--user=0', 'img'], ['-u0', 'img']):
            with self.subTest(explicit=explicit):
                self.assertNotIn('1000:1001', ' '.join(wrapper.build_command('run', explicit, 1000, 1001)))

    def test_user_flag_inside_container_command_does_not_count(self):
        command = wrapper.build_command('run', ['--rm', '-v', '/a:/b', 'img', 'psql', '-u', 'admin'], 7, 8)
        self.assertIn('--user', command[:4], '容器内命令的 -u 不是 docker 的 --user')
        self.assertEqual('7:8', command[3])

    def test_dry_run_prints_without_executing(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'docker_host_user.py'), '--dry-run', 'run', '--rm', 'img', 'id'],
                              text=True, capture_output=True)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('--user %d:%d' % (os.getuid(), os.getgid()), done.stdout)

    def test_usage_error_for_other_subcommands(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / 'docker_host_user.py'), 'build', '.'],
                              text=True, capture_output=True)
        self.assertEqual(2, done.returncode)


class ScriptCheckTests(unittest.TestCase):
    def check(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run_tests.sh'
            path.write_text(text)
            return wrapper.scan_script(str(path))

    def test_flags_container_calls_without_user_including_continuations(self):
        findings = self.check('docker run --rm \\\n  -v a:b img pytest\ndocker compose run web x\npodman exec c ls\n')
        self.assertEqual([1, 3, 4], [line for line, _ in findings])

    def test_accepts_user_flags_env_form_and_allow_marker(self):
        text = ('docker run --user "$(id -u):$(id -g)" img x\n'
                'docker exec -u 1000 c ls\n'
                'docker run --user=$HOST_UID:$HOST_GID img x\n'
                'docker run -u "${UID}:${GID}" img x\n'
                'docker run --rm img root-task  # aidp:allow-root\n'
                '# docker run in a comment\n'
                'echo "no container here"\n')
        self.assertEqual([], self.check(text))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            bad, good = Path(directory) / 'bad.sh', Path(directory) / 'good.sh'
            bad.write_text('docker run img x\n')
            good.write_text('docker run --user 1:1 img x\n')
            run = lambda *a: subprocess.run([sys.executable, str(SCRIPTS / 'docker_host_user.py'), '--check', *a],
                                            text=True, capture_output=True)
            self.assertEqual(1, run(str(bad)).returncode)
            self.assertIn('bad.sh:1', run(str(bad)).stdout)
            self.assertEqual(0, run(str(good)).returncode)
            self.assertEqual(2, run().returncode)
            self.assertEqual(2, run(str(Path(directory) / 'missing.sh')).returncode)


if __name__ == '__main__':
    unittest.main()
