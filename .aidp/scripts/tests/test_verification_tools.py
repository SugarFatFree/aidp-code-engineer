#!/usr/bin/env python3
"""在临时真实项目配置和受控工具替身上验证分类、argv、授权与副作用边界。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verification_tools as tools


class VerificationToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.bin = Path(self.temp.name) / "bin"
        self.bin.mkdir()
        self.env = patch.dict(os.environ, {"PATH": str(self.bin)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write(self, name, text=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def tool(self, name):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\nimport json,sys\nfrom pathlib import Path\n"
                        "Path('actual-argv.json').write_text(json.dumps(sys.argv[1:]))\n"
                        "if '--fix' in sys.argv: Path('source.py').write_text('MUTATED')\n"
                        "if 'build' in sys.argv or 'deploy' in sys.argv: Path('unwanted-side-effect').touch()\n")
        path.chmod(0o755)
        return path

    def inspect(self, argv, **kwargs):
        return tools.inspect_command(self.root, argv, allowed_actions=kwargs.pop("allowed_actions", ["static"]), **kwargs)

    def execute_ready(self, row):
        if row["status"] != "READY":
            return None
        return subprocess.run(row["argv"], cwd=self.root / row["cwd"], capture_output=True, text=True, timeout=10)

    def test_real_python_configuration_chooses_ruff_and_pytest_without_extra_grants(self):
        self.write("pyproject.toml", '[tool.ruff]\nline-length = 88\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        self.write("src/app.py", "value = 1\n")
        self.write("tests/test_app.py", "def test_value(): assert 1 == 1\n")
        self.tool("ruff")
        self.tool("pytest")
        rows = tools.discover_checks(self.root, allowed_actions=["static"], scope_paths=["src/app.py", "tests/test_app.py"])
        lint = next(row for row in rows if row["category"] == "lint")
        self.assertEqual(lint["status"], "READY", lint)
        self.assertIn("pyproject.toml", lint["config_dependencies"])
        self.assertIn("--no-fix", lint["argv"])
        self.assertFalse(any(row["syntax_only"] for row in rows))
        tests = [row for row in rows if row["category"] == "related-test"]
        self.assertTrue(tests)
        self.assertTrue(all(row["status"] == "UNAUTHORIZED" for row in tests))
        self.assertTrue(all(not row["unit_tests_executed"] for row in rows))

    def test_explicit_development_and_ci_sources_are_auditable(self):
        self.write("app.py", "x = 1\n")
        self.write("CONTRIBUTING.md", "```sh\nruff check --no-fix app.py\n```\n")
        self.write(".github/workflows/check.yml", "jobs:\n  check:\n    steps:\n      - run: ruff check --no-fix app.py\n")
        self.tool("ruff")
        rows = tools.discover_checks(self.root, allowed_actions=["static"], scope_paths=["app.py"])
        row = next(row for row in rows if row["argv"] == ["ruff", "check", "--no-fix", "app.py"])
        self.assertEqual({source["path"] for source in row["command_sources"]},
                         {"CONTRIBUTING.md", ".github/workflows/check.yml"})
        self.assertEqual(row["checked_files"], ["app.py"])
        self.assertEqual(self.execute_ready(row).returncode, 0)
        self.assertEqual(json.loads((self.root / "actual-argv.json").read_text()), row["argv"][1:])

    def test_unknown_missing_tool_leaves_unavailable_without_granting_execution(self):
        row = self.inspect(["aidp_missing_static_tool_fixture"])
        self.assertEqual(row["status"], "ENV_UNAVAILABLE", row)
        self.assertFalse(row["available"])
        self.assertIsNone(self.execute_ready(row))
        self.tool("aidp_missing_static_tool_fixture")
        self.assertEqual(self.inspect(["aidp_missing_static_tool_fixture"])["status"], "UNVERIFIED")
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_missing_configured_tool_does_not_fallback_or_install(self):
        self.write("pyproject.toml", "[tool.ruff]\n")
        self.write("app.py", "x=1\n")
        rows = tools.discover_checks(self.root, allowed_actions=["static"], scope_paths=["app.py"])
        self.assertEqual(rows[0]["status"], "ENV_UNAVAILABLE")
        self.assertFalse(any(row["syntax_only"] for row in rows))
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_ten_test_files_syntax_check_is_not_ten_executed_tests(self):
        paths = ["test_" + str(n) + ".py" for n in range(10)]
        for path in paths:
            self.write(path, "def test_example(): assert False\n")
        rows = tools.discover_checks(self.root, allowed_actions=["static"], scope_paths=paths)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["category"], "syntax")
        self.assertTrue(row["syntax_only"])
        self.assertFalse(row["unit_tests_executed"])
        self.assertEqual(row["checked_file_count"], 10)
        self.assertEqual(self.execute_ready(row).returncode, 0)

    def test_fix_flags_and_fix_config_do_not_mutate_sources(self):
        self.write("source.py", "value = 1\n")
        self.tool("ruff")
        for flag in ("--fix", "--fix=true", "--fix-only", "--unsafe-fixes", "--watch"):
            row = self.inspect(["ruff", "check", flag, "source.py"])
            self.assertNotEqual(row["status"], "READY", row)
            self.assertIsNone(self.execute_ready(row))
        self.write("ruff.toml", "fix = true\n")
        self.assertEqual(self.inspect(["ruff", "check", "source.py"])["status"], "UNVERIFIED")
        self.assertEqual(self.inspect(["ruff", "check", "--no-fix", "source.py"])["status"], "READY")
        self.assertEqual((self.root / "source.py").read_text(), "value = 1\n")
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_inline_ast_write_and_dynamic_execution_are_rejected(self):
        self.write("source.py", "value=1\n")
        for code in ("import ast; ast.parse(open('source.py','w').read())", "import os; os.system('deploy')",
                     "import ast; ast.parse(open('source.py', opener=print).read())",
                     "import ast; ast.parse.__globals__.clear()"):
            self.assertNotEqual(self.inspect([sys.executable, "-c", code])["status"], "READY")
        self.assertEqual((self.root / "source.py").read_text(), "value=1\n")

    def test_related_pytest_uses_real_argv_only_after_parent_authorization(self):
        self.write("pytest.ini", "[pytest]\ntestpaths = tests\n")
        self.write("tests/test_app.py", "def test_app(): pass\n")
        self.tool("pytest")
        argv = ["pytest", "-q", "tests/test_app.py::test_app"]
        denied = self.inspect(argv)
        self.assertEqual(denied["status"], "UNAUTHORIZED")
        self.assertEqual(denied["required_action"], "related-test")
        accepted = self.inspect(argv, allowed_actions=["related-test"])
        self.assertEqual(accepted["status"], "READY", accepted)
        self.assertEqual(self.execute_ready(accepted).returncode, 0)
        self.assertEqual(json.loads((self.root / "actual-argv.json").read_text()), argv[1:])
        self.assertFalse(accepted["unit_tests_executed"])
        self.assertNotEqual(self.inspect(["pytest"], allowed_actions=["related-test"])["status"], "READY")
        self.assertNotEqual(self.inspect(["pytest", "."], allowed_actions=["related-test"])["status"], "READY")

    def test_typescript_project_keeps_module_boundary_and_config_dependency(self):
        self.write("web/package.json", '{"scripts":{"typecheck":"tsc --noEmit --project ."}}')
        self.write("web/tsconfig.json", '{"compilerOptions":{"strict":true},"include":["src/**/*.ts"]}')
        self.write("web/src/app.ts", "export const x: number = 1\n")
        self.write("other/unrelated.ts", "const unrelated = true\n")
        self.tool("tsc")
        self.tool("npm")
        row = self.inspect(["npm", "run", "typecheck"], cwd="web", scope_paths=["web/src/app.ts"])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["category"], "typecheck")
        self.assertIn("web/tsconfig.json", row["config_dependencies"])
        self.assertEqual(row["checked_files"], ["web/src/app.ts"])
        self.assertTrue(row["expanded_scope_reason"])
        self.assertEqual(row["command_sources"][0]["location"], "scripts.typecheck")

    def test_package_script_and_pre_hooks_are_not_blanket_approved(self):
        self.write("app.ts", "const x = 1\n")
        self.tool("npm")
        self.tool("tsc")
        for scripts in ({"check": "tsc --noEmit app.ts && npm run build"},
                        {"check": "tsc --noEmit app.ts", "precheck": "deploy"},
                        {"check": "node arbitrary-script.js"}, {"check": "eslint --fix app.ts"}):
            self.write("package.json", json.dumps({"scripts": scripts}))
            row = self.inspect(["npm", "run", "check"])
            self.assertNotEqual(row["status"], "READY", row)
            self.assertIsNone(self.execute_ready(row))
        self.assertFalse((self.root / "unwanted-side-effect").exists())
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_maven_compile_is_narrow_compile_not_full_build(self):
        self.write("pom.xml", "<project><modelVersion>4.0.0</modelVersion><groupId>example</groupId><artifactId>app</artifactId><version>1</version></project>")
        self.write("src/main/java/App.java", "class App {}\n")
        self.tool("mvn")
        row = self.inspect(["mvn", "-o", "compile"], scope_paths=["src/main/java/App.java"])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["category"], "compile")
        self.assertEqual(row["required_action"], "static")
        self.assertTrue(row["side_effects"])
        self.assertEqual(row["checked_files"], ["src/main/java/App.java"])
        self.assertEqual(self.execute_ready(row).returncode, 0)
        self.assertEqual(json.loads((self.root / "actual-argv.json").read_text()), ["-o", "compile"])

    def test_maven_bound_frontend_exec_and_unknown_plugins_block_without_side_effects(self):
        self.write("src/main/java/App.java", "class App {}\n")
        self.tool("mvn")
        for plugin in ("frontend-maven-plugin", "exec-maven-plugin", "unknown-plugin"):
            self.write("pom.xml", '<project><build><plugins><plugin><artifactId>' + plugin + '</artifactId><executions><execution><phase>generate-sources</phase><goals><goal>build</goal></goals></execution></executions></plugin></plugins></build></project>')
            row = self.inspect(["mvn", "-o", "compile"])
            self.assertEqual(row["status"], "UNVERIFIED", row)
            self.assertIn(plugin, row["reason"])
            self.assertIsNone(self.execute_ready(row))
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_maven_requires_offline_explicit_goal_and_selected_module(self):
        self.write("pom.xml", "<project><modules><module>api</module><module>web</module></modules></project>")
        self.write("api/pom.xml", "<project/>")
        self.write("api/src/main/java/App.java", "class App {}\n")
        self.tool("mvn")
        for argv in (["mvn", "compile"], ["mvn", "-o", "package"], ["mvn", "-o", "compile", "deploy"], ["mvn", "-o", "compile"]):
            self.assertNotEqual(self.inspect(argv)["status"], "READY")
        row = self.inspect(["mvn", "-o", "-pl", "api", "compile"])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["checked_files"], ["api/src/main/java/App.java"])
        self.assertIn("pom.xml", row["config_dependencies"])
        self.assertIn("api/pom.xml", row["config_dependencies"])

    def test_gradle_compile_allows_declarative_java_and_blocks_dynamic_build(self):
        self.write("build.gradle", "plugins { id 'java' }\nrepositories { mavenCentral() }\n")
        self.write("settings.gradle", "rootProject.name = 'example'\n")
        self.write("src/main/java/App.java", "class App {}\n")
        self.tool("gradle")
        argv = ["gradle", "--offline", "--no-daemon", "compileJava"]
        accepted = self.inspect(argv)
        self.assertEqual(accepted["status"], "READY", accepted)
        self.assertEqual(self.execute_ready(accepted).returncode, 0)
        (self.root / "actual-argv.json").unlink()
        for code in ("tasks.named('compileJava') { dependsOn 'frontendBuild' }", "exec { commandLine 'npm', 'run', 'build' }", "apply from: 'unknown.gradle'", "tasks.register('startService') {}"):
            self.write("build.gradle", "plugins { id 'java' }\n" + code)
            row = self.inspect(argv)
            self.assertEqual(row["status"], "UNVERIFIED", row)
            self.assertIsNone(self.execute_ready(row))
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_build_environment_hooks_are_unverified_before_compile(self):
        self.write("pom.xml", "<project/>")
        self.write("build.gradle", "plugins { id 'java' }\n")
        self.write("src/main/java/App.java", "class App {}\n")
        self.tool("mvn")
        self.tool("gradle")
        with patch.dict(os.environ, {"MAVEN_OPTS": "-javaagent:unknown.jar"}):
            self.assertEqual(self.inspect(["mvn", "-o", "compile"])["status"], "UNVERIFIED")
        gradle_home = Path(self.temp.name) / "gradle-home"
        gradle_home.mkdir()
        (gradle_home / "init.gradle").write_text("exec { commandLine 'deploy' }\n")
        with patch.dict(os.environ, {"GRADLE_USER_HOME": str(gradle_home)}):
            row = self.inspect(["gradle", "--offline", "compileJava"])
            self.assertEqual(row["status"], "UNVERIFIED", row)
            self.assertIn("用户级", row["reason"])
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_unknown_wrapper_marker_does_not_grant_execution(self):
        script = self.write("approved-check", "#!/bin/sh\n# approved-static: true\ntouch unwanted-side-effect\n")
        script.chmod(0o755)
        row = self.inspect(["./approved-check"])
        self.assertEqual(row["status"], "UNVERIFIED")
        self.assertIsNone(self.execute_ready(row))
        self.assertFalse((self.root / "unwanted-side-effect").exists())

    def test_dynamic_python_tool_plugins_are_not_implicitly_approved(self):
        self.write("app.py", "value=1\n")
        self.tool("mypy")
        self.write("mypy.ini", "[mypy]\nplugins = custom_plugin\n")
        self.assertEqual(self.inspect(["mypy", "app.py"])["status"], "UNVERIFIED")
        self.tool("pylint")
        self.assertEqual(self.inspect(["pylint", "--init-hook=print(1)", "app.py"])["status"], "UNVERIFIED")

    def test_single_command_shell_is_checked_recursively(self):
        self.write("app.py", "x=1\n")
        self.tool("ruff")
        row = self.inspect(["/bin/sh", "-c", "ruff check --no-fix app.py"])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(self.execute_ready(row).returncode, 0)
        self.write("scripts/lint.sh", "#!/bin/sh\n# Project's existing check\nruff check --no-fix app.py\n")
        row = self.inspect(["/bin/sh", "scripts/lint.sh"])
        self.assertEqual(row["status"], "READY", row)
        self.assertIn("scripts/lint.sh", row["config_dependencies"])
        for command in ("ruff check --fix app.py", "ruff check app.py && deploy", "ruff check $(deploy)", "pytest app.py"):
            self.assertNotEqual(self.inspect(["/bin/sh", "-c", command], allowed_actions=["static", "related-test"])["status"], "READY")

    def docker_argv(self, image=None):
        return ["docker", "run", "--rm", "--read-only", "--pull=never", "--network=none", "--entrypoint", "ruff",
                "-v", str(self.root) + ":/work:ro", "-w", "/work", image or "local/check@sha256:" + "a" * 64,
                "check", "--no-fix", "/work/app.py"]

    def test_readonly_container_ruff_does_not_require_host_ruff(self):
        self.write("app.py", "x=1\n")
        self.tool("docker")
        argv = self.docker_argv()
        self.write("CONTRIBUTING.md", "```sh\n" + __import__("shlex").join(argv) + "\n```\n")
        row = self.inspect(argv)
        self.assertEqual(row["status"], "READY", row)
        self.assertTrue(row["available"])
        self.assertEqual(row["checked_files"], ["app.py"])
        self.assertEqual(row["environment"]["container"]["pull"], "never")
        self.assertEqual(row["command_sources"][0]["path"], "CONTRIBUTING.md")
        self.assertEqual(self.execute_ready(row).returncode, 0)
        self.assertEqual(json.loads((self.root / "actual-argv.json").read_text()), argv[1:])
        self.assertFalse(row["unit_tests_executed"])

    def test_mutable_image_requires_explicit_probe_and_pins_actual_argv(self):
        self.write("app.py", "x=1\n")
        self.tool("docker")
        row = self.inspect(self.docker_argv("local/check:latest"))
        self.assertEqual(row["status"], "READY", row)
        self.assertFalse((self.root / "actual-argv.json").exists())
        self.assertEqual(len(row["environment_probes"]), 1)
        probe = row["environment_probes"][0]
        self.assertEqual(probe["argv"], ["docker", "image", "inspect", "--format", "{{.Id}}", "local/check:latest"])
        image_id = "sha256:" + "b" * 64
        bound = tools.bind_environment(row, [{"argv": probe["argv"], "returncode": 0, "stdout": image_id + "\n", "stderr": ""}])
        self.assertEqual(bound["environment"]["container"]["image_id"], image_id)
        self.assertIn(image_id, bound["execution_argv"])
        self.assertNotIn("local/check:latest", bound["execution_argv"])
        self.assertIn("local/check:latest", bound["argv"])
        self.assertEqual(bound["environment_probes"], [])
        missing = tools.bind_environment(row, [{"argv": probe["argv"], "returncode": 1, "stdout": "", "stderr": "No such image"}])
        self.assertEqual(missing["status"], "ENV_UNAVAILABLE")
        self.assertIn("No such image", missing["reason"])
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_controlled_docker_probe_and_run_use_pinned_argv_without_pull(self):
        self.write("app.py", "x=1\n")
        docker = self.tool("docker")
        image_id = "sha256:" + "d" * 64
        docker.write_text("#!" + sys.executable + "\nimport json,sys\nfrom pathlib import Path\n"
                          "if sys.argv[1:3] == ['image','inspect']: print(" + repr(image_id) + ")\n"
                          "else: Path('actual-argv.json').write_text(json.dumps(sys.argv[1:]))\n")
        row = self.inspect(self.docker_argv("local/check:latest"))
        probe = row["environment_probes"][0]
        process = subprocess.run(probe["argv"], cwd=self.root, capture_output=True, text=True, timeout=10)
        bound = tools.bind_environment(row, [{"argv": probe["argv"], "returncode": process.returncode,
                                             "stdout": process.stdout, "stderr": process.stderr}])
        self.assertEqual(bound["status"], "READY")
        process = subprocess.run(bound["execution_argv"], cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0)
        actual = json.loads((self.root / "actual-argv.json").read_text())
        self.assertIn(image_id, actual)
        self.assertIn("--pull=never", actual)
        self.assertNotIn("local/check:latest", actual)
        self.assertEqual((self.root / "app.py").read_text(), "x=1\n")

    def test_shell_container_probe_pins_leaf_command_without_rewriting_project_script(self):
        self.write("app.py", "x=1\n")
        self.tool("docker")
        command = __import__("shlex").join(self.docker_argv("local/check:latest"))
        script = self.write("scripts/check.sh", "#!/bin/sh\n" + command + "\n")
        row = self.inspect(["/bin/sh", "scripts/check.sh"])
        self.assertEqual(row["status"], "READY", row)
        probe = row["environment_probes"][0]
        bound = tools.bind_environment(row, [{"argv": probe["argv"], "returncode": 0, "stdout": "sha256:" + "c" * 64, "stderr": ""}])
        self.assertEqual(bound["execution_argv"][0], "docker")
        self.assertEqual(script.read_text(), "#!/bin/sh\n" + command + "\n")
        self.assertIn("scripts/check.sh", bound["config_dependencies"])

    def test_container_services_unknown_entrypoint_and_writable_mount_rejected(self):
        self.write("app.py", "x=1\n")
        self.tool("docker")
        for old, new in (("--rm", "-d"), ("--network=none", "--network=host"), ("--pull=never", "--pull=always"),
                         ("ruff", "bash"), (str(self.root) + ":/work:ro", str(self.root) + ":/work:rw")):
            argv = self.docker_argv()
            argv[argv.index(old)] = new
            self.assertNotEqual(self.inspect(argv)["status"], "READY", argv)
        for extra in ("--privileged", "--device=/dev/sda"):
            argv = self.docker_argv()
            argv.insert(2, extra)
            self.assertNotEqual(self.inspect(argv)["status"], "READY")
        argv = self.docker_argv()
        argv[argv.index("--no-fix")] = "--fix"
        self.assertEqual(self.inspect(argv)["status"], "UNAUTHORIZED")
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_literal_ast_file_list_filters_count_only_actual_python_inputs(self):
        self.write("app.py", "x=1\n")
        self.write("README.md", "This is not Python.\n")
        code = "import ast; from pathlib import Path; [ast.parse(Path(p).read_text()) for p in ['app.py', 'README.md', 'missing.py'] if Path(p).is_file() and Path(p).suffix == '.py']"
        row = self.inspect([sys.executable, "-B", "-c", code])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["checked_files"], ["app.py"])
        self.assertEqual(self.execute_ready(row).returncode, 0)
        for bad in (code.replace("['app.py', 'README.md', 'missing.py']", "paths"),
                    code.replace("Path(p).is_file()", "__import__('os').system('deploy')")):
            self.assertEqual(self.inspect([sys.executable, "-B", "-c", bad])["status"], "UNVERIFIED")

    def test_syntax_count_requires_file_read_to_feed_parse_or_compile(self):
        self.write("app.py", "invalid syntax ???\n")
        self.write("other.py", "value=1\n")
        for code in ("import ast; open('app.py'); ast.parse('pass')",
                     "import ast; ast.parse(open('app.py').read(0))",
                     "import ast; open('app.py'); ast.parse(open('other.py').read())"):
            row = self.inspect([sys.executable, "-B", "-c", code])
            self.assertEqual(row["status"], "UNVERIFIED", row)
            self.assertEqual(row["checked_file_count"], 0)
        row = self.inspect([sys.executable, "-B", "-c", "compile(open('other.py').read(), 'other.py', 'exec')"])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["checked_files"], ["other.py"])
        self.assertEqual(self.execute_ready(row).returncode, 0)

    def test_unittest_is_selected_as_actual_related_test_not_syntax_success(self):
        self.write("test_example.py", "import unittest\nclass Example(unittest.TestCase):\n    def test_one(self): self.assertEqual(1, 1)\n")
        rows = tools.discover_checks(self.root, allowed_actions=["static", "related-test"], scope_paths=["test_example.py"])
        row = next(item for item in rows if item["category"] == "related-test")
        self.assertEqual(row["status"], "READY", row)
        result = self.execute_ready(row)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ran 1 test", result.stderr)
        self.assertFalse(row["syntax_only"])
        self.assertFalse(row["unit_tests_executed"])
        self.assertTrue(row["environment"]["dependency_files"])

    def test_python_selection_uses_config_module_and_never_pytests_production_input(self):
        self.write("pyproject.toml", '[tool.ruff]\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        self.write("src/app.py", "x=1\n")
        self.write("tests/test_app.py", "def test_one(): pass\n")
        self.tool("ruff")
        self.tool("pytest")
        rows = tools.discover_checks(self.root, allowed_actions=["static", "related-test"], scope_paths=["src/app.py", "tests/test_app.py"])
        lint = next(item for item in rows if item["category"] == "lint")
        tests = next(item for item in rows if item["category"] == "related-test")
        self.assertEqual(lint["cwd"], ".")
        self.assertEqual(tests["argv"], ["pytest", "tests/test_app.py"])
        self.assertEqual(tests["checked_files"], ["tests/test_app.py"])

    def test_package_shell_substitution_never_runs(self):
        self.write("app.py", "x=1\n")
        self.tool("ruff")
        self.tool("npm")
        self.write("package.json", json.dumps({"scripts": {"lint": "ruff check --select=$(deploy) app.py"}}))
        row = self.inspect(["npm", "run", "lint"])
        self.assertEqual(row["status"], "UNVERIFIED", row)
        self.assertIsNone(self.execute_ready(row))
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_npm_local_binary_and_lockfile_are_bound(self):
        self.write("app.ts", "const x=1\n")
        self.write("package.json", '{"scripts":{"typecheck":"tsc --noEmit app.ts"}}')
        self.write("package-lock.json", '{"lockfileVersion":3}')
        target = self.write("node_modules/typescript/bin/tsc", "#!" + sys.executable + "\n")
        target.chmod(0o755)
        self.write("node_modules/typescript/package.json", '{"name":"typescript"}')
        library = self.write("node_modules/typescript/lib/tsc.js", "// controlled local tool fixture\n")
        (self.root / "node_modules/.bin").mkdir()
        (self.root / "node_modules/.bin/tsc").symlink_to(target)
        self.tool("npm")
        row = self.inspect(["npm", "run", "typecheck"])
        self.assertEqual(row["status"], "READY", row)
        self.assertIn("package-lock.json", row["config_dependencies"])
        self.assertIn(str(library), row["environment"]["dependency_files"])
        self.assertEqual(row["execution_argv"], ["npm", "run", "typecheck"])

    def test_typescript_include_exclude_and_local_import_dependencies(self):
        self.write("tsconfig.json", '{"include":["src/**/*.ts"],"exclude":["src/ignored.ts"]}')
        self.write("src/app.ts", "import { helper } from '../shared/helper';\n")
        self.write("src/ignored.ts", "ignored\n")
        self.write("shared/helper.ts", "export const helper = 1;\n")
        self.write("unrelated.ts", "unrelated\n")
        self.tool("tsc")
        row = self.inspect(["tsc", "--noEmit", "--project", "."])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["checked_files"], ["shared/helper.ts", "src/app.ts"])

    def typescript_read_fixture(self):
        self.write("README.md", "tsc --noEmit --project .\n")
        self.write("tsconfig.json", '{"include":["src/**/*.ts"]}')
        self.write("src/app.ts", "import { value } from '../shared/value';\n")
        self.write("shared/value.ts", "export const value = 1;\n")
        self.tool("tsc")
        return ["tsc", "--noEmit", "--project", "."]

    def test_default_selector_reports_actual_config_and_transitive_source_reads(self):
        argv = self.typescript_read_fixture()
        original = Path.read_bytes
        observed = []
        def physical(path):
            data = original(path)
            if path.is_relative_to(self.root):
                observed.append((path, len(data)))
            return data
        with patch.object(Path, "read_bytes", physical):
            row = self.inspect(argv)
        cost = row["selection_read_cost"]
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(cost["content_reads"], len(observed))
        self.assertEqual(cost["content_reads"], 4)
        self.assertEqual(cost["bytes_read"], sum(size for _, size in observed))
        self.assertEqual(set(cost["read_files"]), {str(path) for path, _ in observed})
        self.assertEqual(row["selection_roots"], ["."])
        self.assertIn(".ts", row["checked_suffixes"])
        self.assertEqual(cost["external_tool_io"], "unknown")
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_budget_callback_stops_before_next_physical_read_and_propagates(self):
        argv = self.typescript_read_fixture()
        class BudgetDenied(ValueError):
            pass
        denial = BudgetDenied("BUDGET_EXCEEDED: selector read")
        actual = []
        def budgeted(path):
            if len(actual) >= 1:
                raise denial
            actual.append(path)
            return path.read_bytes().decode("utf-8")
        cost = {}
        with self.assertRaises(BudgetDenied) as caught:
            self.inspect(argv, read_text=budgeted, read_cost=cost)
        self.assertIs(caught.exception, denial)
        self.assertEqual(len(actual), 1)
        self.assertEqual(cost["reader_calls"], 2)
        self.assertIsNone(cost["content_reads"])
        self.assertEqual(cost["physical_cost_owner"], "callback")
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_caller_memory_cache_is_shared_across_selection_calls(self):
        argv = self.typescript_read_fixture()
        cache, actual = {}, []
        def shared(path):
            if path not in cache:
                actual.append(path)
                cache[path] = path.read_bytes().decode("utf-8")
            return cache[path]
        with patch.object(Path, "read_text", side_effect=AssertionError("unmetered read_text")):
            first = self.inspect(argv, read_text=shared)
            second = self.inspect(argv, read_text=shared)
        self.assertEqual(first["status"], "READY", first)
        self.assertEqual(second["status"], "READY", second)
        self.assertEqual(len(actual), 4)
        self.assertEqual(first["selection_read_cost"]["reader_calls"], 4)
        self.assertEqual(second["selection_read_cost"]["reader_calls"], 4)
        self.assertIsNone(second["selection_read_cost"]["content_reads"])
        self.assertFalse((self.root / "actual-argv.json").exists())

    def test_discovery_without_candidates_still_reports_read_cost(self):
        self.write("README.md", "项目说明，没有声明检查命令。\n")
        cost = {}
        rows = tools.discover_checks(self.root, allowed_actions=["static"], read_cost=cost)
        self.assertEqual(rows, [])
        self.assertEqual(cost["scope"], "discovery-batch")
        self.assertEqual(cost["content_reads"], 1)
        self.assertGreater(cost["bytes_read"], 0)

    def test_discovery_and_recursive_wrapper_use_same_guarded_reader(self):
        self.write("package.json", '{"scripts":{"lint":"/bin/sh scripts/lint.sh"}}')
        self.write("scripts/lint.sh", "#!/bin/sh\nruff check --no-fix app.py\n")
        self.write("ruff.toml", "line-length = 88\n")
        self.write("app.py", "value=1\n")
        self.tool("npm")
        self.tool("ruff")
        cache, actual = {}, []
        def shared(path):
            if path not in cache:
                actual.append(path)
                cache[path] = path.read_bytes().decode("utf-8")
            return cache[path]
        cost = {}
        with patch.object(Path, "read_text", side_effect=AssertionError("unmetered read_text")):
            rows = tools.discover_checks(self.root, allowed_actions=["static"], scope_paths=["app.py"], read_text=shared, read_cost=cost)
        wrapper = next(row for row in rows if row["argv"] == ["npm", "run", "lint"])
        self.assertEqual(wrapper["status"], "READY", wrapper)
        self.assertTrue({self.root / "package.json", self.root / "ruff.toml", self.root / "scripts/lint.sh"} <= set(actual))
        self.assertEqual(len(actual), len(set(actual)))
        self.assertGreater(cost["reader_calls"], len(actual))
        self.assertEqual(wrapper["selection_read_cost"], cost)
        self.assertIsNone(cost["content_reads"])

    def test_python_environment_inventory_does_not_read_metadata_implicitly(self):
        self.write("test_example.py", "import unittest\n")
        with patch.object(Path, "read_text", side_effect=AssertionError("unmetered metadata read")):
            row = self.inspect([sys.executable, "-B", "-m", "unittest", "test_example.py"], allowed_actions=["related-test"])
        self.assertEqual(row["status"], "READY", row)
        self.assertEqual(row["selection_read_cost"]["content_reads"], 0)
        self.assertTrue(row["environment"]["dependency_files"])

    def test_paths_outside_root_are_unverified(self):
        self.tool("ruff")
        row = self.inspect(["ruff", "check", "../outside.py"])
        self.assertEqual(row["status"], "UNVERIFIED")
        self.assertIn("root", row["reason"])


if __name__ == "__main__":
    unittest.main()
