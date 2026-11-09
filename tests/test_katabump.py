"""Hosting startup checks; pip and external bot connections are mocked."""

from importlib import metadata
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import zipfile
import venv

import bootstrap
import build_katabump
import config
import main
from paths import PROJECT_ROOT, project_path


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "requirements.txt").write_text("python-dotenv==1.2.4\n", encoding="utf-8")
        self.patchers = [patch.object(bootstrap, "ROOT", self.root),
                         patch.object(bootstrap, "ensure_pip"),
                         patch.object(bootstrap.metadata, "version", side_effect=metadata.PackageNotFoundError),
                         patch.object(bootstrap.util, "find_spec", return_value=None),
                         patch.dict(os.environ, {"MAGOJ_BOOTSTRAP_ATTEMPTED": "0"})]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_missing_dotenv_installs_using_same_interpreter_then_restarts(self):
        with patch.object(bootstrap.subprocess, "run") as pip, \
             patch.object(bootstrap.os, "execv") as restart, \
             patch.object(sys, "argv", ["main.py", "--check"]):
            bootstrap.ensure_dependencies()
        command = pip.call_args.args[0]
        self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
        self.assertIn(str(self.root / "requirements.txt"), command)
        self.assertIn("--no-cache-dir", command)
        restart.assert_called_once_with(sys.executable,
                                        [sys.executable, str(self.root / "main.py"), "--check"])

    def test_installed_dependencies_do_not_run_pip(self):
        with patch.object(bootstrap.metadata, "version", return_value="1.2.4"), \
             patch.object(bootstrap.util, "find_spec", return_value=object()), \
             patch.object(bootstrap.subprocess, "run") as pip:
            bootstrap.ensure_dependencies()
        pip.assert_not_called()

    def test_check_without_install_reports_missing_package(self):
        with patch.object(bootstrap.subprocess, "run") as pip:
            with self.assertRaisesRegex(SystemExit, "python-dotenv"):
                bootstrap.ensure_dependencies(install=False)
        pip.assert_not_called()

    def test_pip_failure_and_repeated_install_stop_with_clear_error(self):
        with patch.object(bootstrap.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")):
            with self.assertRaisesRegex(SystemExit, "Cài dependencies thất bại"):
                bootstrap.ensure_dependencies()
        with patch.dict(os.environ, {"MAGOJ_BOOTSTRAP_ATTEMPTED": "1"}), \
             patch.object(bootstrap.subprocess, "run") as pip:
            with self.assertRaisesRegex(SystemExit, "không tự cài lặp lại"):
                bootstrap.ensure_dependencies()
            pip.assert_not_called()

    def test_virtualenv_does_not_use_user_install(self):
        with patch.object(sys, "prefix", "virtualenv"), \
             patch.object(sys, "base_prefix", "system"), \
             patch.object(bootstrap.subprocess, "run") as pip, \
             patch.object(bootstrap.os, "execv"):
            bootstrap.ensure_dependencies()
        self.assertNotIn("--user", pip.call_args.args[0])


class PipBootstrapTests(unittest.TestCase):
    @unittest.skipUnless(bootstrap.util.find_spec("ensurepip"), "Offline pip seeding requires ensurepip")
    def test_real_venv_created_without_pip_is_repaired_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            venv.EnvBuilder(with_pip=False).create(folder)
            executable = Path(folder) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            script = ("import bootstrap; "
                      "bootstrap.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError('offline test')); "
                      "bootstrap.ensure_pip()")
            env = dict(os.environ, PIP_NO_INDEX="1")
            result = subprocess.run([str(executable), "-c", script], cwd=PROJECT_ROOT,
                                    env=env, capture_output=True, text=True, encoding="utf-8", timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(executable), "-m", "pip", "--version"],
                                    capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(Path(folder)).lower(), result.stdout.lower())

    def test_existing_pip_does_not_install_or_download(self):
        with patch.object(bootstrap.util, "find_spec", return_value=object()), \
             patch.object(bootstrap.subprocess, "run") as run, \
             patch.object(bootstrap, "urlopen") as download:
            bootstrap.ensure_pip()
        run.assert_not_called()
        download.assert_not_called()

    def test_venv_without_pip_uses_ensurepip_in_same_interpreter(self):
        with patch.object(bootstrap.util, "find_spec", return_value=None), \
             patch.object(sys, "prefix", "venv"), patch.object(sys, "base_prefix", "system"), \
             patch.object(bootstrap.subprocess, "run") as run, \
             patch.object(bootstrap, "urlopen") as download:
            bootstrap.ensure_pip()
        self.assertEqual(run.call_args_list[0].args[0],
                         [sys.executable, "-m", "ensurepip", "--upgrade"])
        self.assertEqual(run.call_args_list[1].args[0], [sys.executable, "-m", "pip", "--version"])
        download.assert_not_called()

    def test_missing_ensurepip_downloads_official_bootstrap_and_cleans_up(self):
        response = SimpleNamespace(geturl=lambda: bootstrap.GET_PIP_URL,
                                   read=lambda size: b"# mocked pip bootstrap\n")
        from unittest.mock import MagicMock
        context = MagicMock()
        context.__enter__.return_value = response
        with patch.object(bootstrap.util, "find_spec", return_value=None), \
             patch.object(sys, "prefix", "venv"), patch.object(sys, "base_prefix", "system"), \
             patch.object(bootstrap.subprocess, "run", side_effect=[
                 subprocess.CalledProcessError(1, "ensurepip"), None, None]) as run, \
             patch.object(bootstrap, "urlopen", return_value=context) as download:
            bootstrap.ensure_pip()
        download.assert_called_once_with(bootstrap.GET_PIP_URL, timeout=30)
        command = run.call_args_list[1].args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("get-pip.py"))
        self.assertNotIn("--user", command)
        self.assertFalse(Path(command[1]).exists())

    def test_blocked_download_reports_recovery_instead_of_looping(self):
        with patch.object(bootstrap.util, "find_spec", return_value=None), \
             patch.object(bootstrap.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "ensurepip")), \
             patch.object(bootstrap, "urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(SystemExit, "Không khởi tạo được pip"):
                bootstrap.ensure_pip()


class HostingConfigTests(unittest.TestCase):
    def test_missing_compiler_does_not_block_games(self):
        with patch.dict(os.environ, {"ZALO_BOT_TOKEN": "fake", "ZALO_ADMIN_IDS": "owner",
                                    "TELEGRAM_BOT_TOKEN": "", "DISCORD_TOKEN": "",
                                    "MAGOJ_JUDGE_BACKEND": "local"}, clear=True), \
             patch.object(config.shutil, "which", return_value=None):
            errors, warnings = config.check_config()
        self.assertFalse(errors)
        self.assertTrue(any("g++" in warning for warning in warnings))

    def test_paths_are_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = Path.cwd()
            try:
                os.chdir(folder)
                self.assertEqual(project_path("data.sqlite3"), PROJECT_ROOT / "data.sqlite3")
                self.assertEqual(project_path(folder), Path(folder))
            finally:
                os.chdir(previous)

    def test_upload_archive_has_games_and_bootstrap_without_live_data(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = build_katabump.build(Path(folder) / "upload.zip")
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                self.assertIsNone(bundle.testzip())
        for name in ("main.py", "requirements.txt", "bootstrap.py", "paths.py",
                     "zalo.tictactoe/game.py", "zalo.tictactoe/der.json", "examples/seed-data.json"):
            self.assertIn(name, names)
        self.assertNotIn(".env", names)
        self.assertNotIn("data.json", names)
        self.assertFalse(any("sqlite" in name or "__pycache__" in name for name in names))

    def test_archive_can_check_config_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = build_katabump.build(root / "upload.zip")
            app = root / "app"
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(app)
            env = dict(os.environ, ZALO_BOT_TOKEN="offline-test-token", TELEGRAM_BOT_TOKEN="",
                       DISCORD_TOKEN="", MAGOJ_DB_PATH="", MAGOJ_LEGACY_PATH="",
                       MAGOJ_JUDGE_BACKEND="local", MAGOJ_MAX_JOBS="1", MAGOJ_WEBAPP_URL="",
                       MAGOJ_BOOTSTRAP_ATTEMPTED="0")
            result = subprocess.run([sys.executable, str(app / "main.py"), "--no-install", "--check"],
                                    cwd=root, env=env, text=True, encoding="utf-8",
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Cấu hình: OK", result.stdout)
            self.assertNotIn("offline-test-token", result.stdout + result.stderr)
            self.assertFalse((app / "data.sqlite3").exists())

    def test_missing_site_packages_get_actionable_error_before_dotenv_import(self):
        result = subprocess.run([sys.executable, "-S", str(PROJECT_ROOT / "main.py"),
                                 "--no-install", "--check"], capture_output=True,
                                text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn("python-dotenv", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)


class HostingLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_telegram_startup_is_cleaned_up(self):
        events = []

        class FakeApp:
            running = False
            updater = SimpleNamespace(running=False, start_polling=AsyncMock(side_effect=RuntimeError("offline")))

            async def __aenter__(self):
                events.append("initialize")
                return self

            async def __aexit__(self, *args):
                events.append("shutdown")

            async def start(self):
                self.running = True
                events.append("start")

            async def stop(self):
                self.running = False
                events.append("stop")

        import bot_telegram
        with patch.object(bot_telegram, "create_app", return_value=FakeApp()), \
             patch.object(bot_telegram, "register_handlers"):
            with self.assertRaises(RuntimeError):
                await main.run_telegram()
        self.assertEqual(events, ["initialize", "start", "stop", "shutdown"])

    async def test_failure_of_one_bot_does_not_cancel_other_bot(self):
        entered, closed = asyncio.Event(), asyncio.Event()

        async def waiting():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()

        with patch.object(main, "RUN_DISCORD", True), patch.object(main, "RUN_TELEGRAM", True), \
             patch.object(main, "RUN_ZALO", False), \
             patch.object(main, "run_discord", AsyncMock(side_effect=RuntimeError("offline"))), \
             patch.object(main, "run_telegram", waiting), patch("builtins.print"):
            with self.assertLogs(main.__name__, level="ERROR"):
                task = asyncio.create_task(main.main())
                await asyncio.wait_for(entered.wait(), timeout=2)
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertTrue(closed.is_set())


if __name__ == "__main__":
    unittest.main()
