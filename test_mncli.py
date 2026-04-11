import contextlib
import importlib.machinery
import importlib.util
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("mncli")
LOADER = importlib.machinery.SourceFileLoader("mncli_under_test", str(MODULE_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
mncli = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(mncli)


def _args(**kwargs):
    defaults = {
        "code": None,
        "source": None,
        "json": False,
        "port": None,
        "url": None,
        "session": None,
        "token": None,
        "stream": False,
        "targets": [],
        "run": False,
        "tag": None,
        "notebook": "notebook.py",
        "runner": "auto",
        "log": None,
        "headless": False,
        "mcp": False,
        "sandbox": None,
        "dry_run": False,
        "startup_check_seconds": 0,
        "registration_timeout_seconds": 0,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


class MncliTests(unittest.TestCase):
    def test_default_execute_script_uses_bundled_transport(self):
        self.assertEqual(mncli.DEFAULT_EXECUTE_SCRIPT.name, "mncli-execute-code")
        self.assertTrue(mncli.DEFAULT_EXECUTE_SCRIPT.exists())

    def test_exec_uses_shared_transport_hints(self):
        stderr = "Failed to connect to marimo server\n"
        args = _args(code="print(1)", url="http://localhost:2718")

        with mock.patch.object(mncli, "_run_kernel", return_value=("", stderr, 7)):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as raised:
                    mncli.cmd_exec(args)

        self.assertEqual(raised.exception.code, 1)
        self.assertIn(stderr, err.getvalue())
        self.assertIn("hint: the URL is unreachable", err.getvalue())

    def test_exec_json_keeps_transport_failure_structured(self):
        stderr = "No running marimo instances found.\n"
        args = _args(code="print(1)", json=True)

        with mock.patch.object(mncli, "_run_kernel", return_value=("", stderr, 1)):
            out = io.StringIO()
            err = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as raised:
                    mncli.cmd_exec(args)

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(err.getvalue(), "")
        payload = mncli.json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["exit_code"], 1)
        self.assertTrue(payload["transport_error"])
        self.assertEqual(payload["stderr"], stderr)

    def test_servers_lists_live_registry_entries_and_cleans_stale_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "marimo" / "servers"
            registry.mkdir(parents=True)
            live = registry / "live.json"
            stale = registry / "stale.json"
            live.write_text(mncli.json.dumps({
                "pid": 123,
                "host": "127.0.0.1",
                "port": 2718,
                "base_url": "",
                "server_id": "abc",
            }))
            stale.write_text(mncli.json.dumps({
                "pid": 456,
                "host": "127.0.0.1",
                "port": 2719,
                "base_url": "",
                "server_id": "stale",
            }))

            def live_pid(pid):
                return pid == 123

            with mock.patch.dict(mncli.os.environ, {"XDG_STATE_HOME": tmp}, clear=False):
                with mock.patch.object(mncli, "_pid_is_live", side_effect=live_pid):
                    servers, servers_dir = mncli._discover_servers()

            self.assertEqual(servers_dir, registry)
            self.assertEqual([s["server_id"] for s in servers], ["abc"])
            self.assertTrue(live.exists())
            self.assertFalse(stale.exists())

    def test_servers_json_filters_by_port(self):
        args = _args(json=True, port="2718", no_cleanup=False)
        servers = [
            {"pid": 123, "host": "127.0.0.1", "port": 2718, "server_id": "keep"},
            {"pid": 124, "host": "127.0.0.1", "port": 2719, "server_id": "drop"},
        ]

        with mock.patch.object(mncli, "_discover_servers", return_value=(servers, Path("/registry"))):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                mncli.cmd_servers(args)

        payload = mncli.json.loads(out.getvalue())
        self.assertEqual(payload["registry"], "/registry")
        self.assertEqual([s["server_id"] for s in payload["servers"]], ["keep"])

    def test_run_rejects_all_mixed_with_cell_ids(self):
        args = _args(targets=["all", "abc123"])

        with mock.patch.object(mncli, "_exec_json") as exec_json:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as raised:
                    mncli.cmd_run(args)

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("'all' cannot be combined", err.getvalue())
        exec_json.assert_not_called()

    def test_tag_marker_match_is_exact_first_line(self):
        marker = "# mncli-tag: foo"

        self.assertTrue(mncli._has_exact_tag_marker(f"{marker}\nx = 1", marker))
        self.assertTrue(mncli._has_exact_tag_marker(marker, marker))
        self.assertFalse(mncli._has_exact_tag_marker("# mncli-tag: foobar\nx = 1", marker))
        self.assertFalse(mncli._has_exact_tag_marker(f" {marker}\nx = 1", marker))

    def test_create_rejects_empty_tag_before_kernel_call(self):
        args = _args(code="x = 1", tag="")

        with mock.patch.object(mncli, "_exec_json") as exec_json:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as raised:
                    mncli.cmd_create(args)

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--tag must be a non-empty single-line value", err.getvalue())
        exec_json.assert_not_called()

    def test_start_command_prefers_uvx_outside_project(self):
        args = _args(notebook="analysis.py")

        def which(name):
            return f"/usr/bin/{name}" if name == "uvx" else None

        with mock.patch.object(mncli, "_notebook_uses_project_marimo", return_value=False):
            with mock.patch.object(mncli.shutil, "which", side_effect=which):
                cmd, log_path, notebook, runner = mncli._build_start_command(args)

        self.assertEqual(runner, "uvx")
        self.assertEqual(notebook, Path("analysis.py"))
        self.assertEqual(log_path, Path("analysis.marimo.log"))
        self.assertEqual(
            cmd,
            [
                "uvx",
                "marimo@latest",
                "edit",
                "analysis.py",
                "--no-token",
                "--sandbox",
            ],
        )

    def test_start_command_prefers_project_uv_without_sandbox(self):
        args = _args(notebook="analysis.py")

        def which(name):
            return f"/usr/bin/{name}" if name in {"uv", "uvx"} else None

        with mock.patch.object(mncli, "_notebook_uses_project_marimo", return_value=True):
            with mock.patch.object(mncli.shutil, "which", side_effect=which):
                cmd, _, _, runner = mncli._build_start_command(args)

        self.assertEqual(runner, "uv")
        self.assertEqual(
            cmd,
            ["uv", "run", "marimo", "edit", "analysis.py", "--no-token"],
        )

    def test_start_command_prefers_project_pixi_without_sandbox(self):
        args = _args(notebook="analysis.py")

        def which(name):
            return f"/usr/bin/{name}" if name in {"uv", "uvx", "pixi"} else None

        with mock.patch.object(mncli, "_notebook_uses_pixi_marimo", return_value=True):
            with mock.patch.object(mncli, "_notebook_uses_project_marimo", return_value=True):
                with mock.patch.object(mncli.shutil, "which", side_effect=which):
                    cmd, _, _, runner = mncli._build_start_command(args)

        self.assertEqual(runner, "pixi")
        self.assertEqual(
            cmd,
            ["pixi", "run", "marimo", "edit", "analysis.py", "--no-token"],
        )

    def test_explicit_pixi_runner(self):
        args = _args(notebook="analysis.py", runner="pixi")

        with mock.patch.object(mncli.shutil, "which", return_value="/usr/bin/pixi"):
            cmd, _, _, runner = mncli._build_start_command(args)

        self.assertEqual(runner, "pixi")
        self.assertEqual(
            cmd,
            ["pixi", "run", "marimo", "edit", "analysis.py", "--no-token"],
        )

    def test_start_dry_run_does_not_spawn(self):
        args = _args(
            notebook="analysis.py",
            runner="uvx",
            dry_run=True,
            headless=True,
            port="2718",
        )

        with mock.patch.object(mncli.shutil, "which", return_value="/usr/bin/uvx"):
            with mock.patch.object(mncli.subprocess, "Popen") as popen:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    mncli.cmd_start(args)

        self.assertIn(
            "uvx marimo@latest edit analysis.py --no-token --port 2718 "
            "--headless --sandbox",
            out.getvalue(),
        )
        popen.assert_not_called()

    def test_start_spawns_background_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "server.log"
            args = _args(
                notebook=str(Path(tmp) / "analysis.py"),
                runner="uvx",
                log=str(log_path),
            )
            proc = types.SimpleNamespace(pid=1234, poll=lambda: None)
            server = {
                "pid": 1234,
                "host": "127.0.0.1",
                "port": 2718,
                "server_id": "abc",
            }

            with mock.patch.object(mncli.shutil, "which", return_value="/usr/bin/uvx"):
                with mock.patch.object(mncli, "_discover_servers", return_value=([], Path("/registry"))):
                    with mock.patch.object(
                        mncli,
                        "_wait_for_server_registration",
                        return_value=(server, Path("/registry"), None),
                    ) as wait:
                        with mock.patch.object(mncli, "_read_server_session_ids", return_value=(["sess"], None)):
                            with mock.patch.object(mncli.subprocess, "Popen", return_value=proc) as popen:
                                out = io.StringIO()
                                with contextlib.redirect_stdout(out):
                                    mncli.cmd_start(args)

            self.assertTrue(log_path.exists())
            self.assertIn("started marimo pid 1234", out.getvalue())
            self.assertIn("registered: http://127.0.0.1:2718  pid=1234", out.getvalue())
            self.assertIn("session: sess", out.getvalue())
            popen.assert_called_once()
            _, kwargs = popen.call_args
            self.assertIs(kwargs["stdin"], mncli.subprocess.DEVNULL)
            self.assertIs(kwargs["stderr"], mncli.subprocess.STDOUT)
            self.assertTrue(kwargs["start_new_session"])
            wait.assert_called_once()

    def test_start_reports_no_active_session_after_headless_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "server.log"
            args = _args(
                notebook=str(Path(tmp) / "analysis.py"),
                runner="uvx",
                log=str(log_path),
                headless=True,
                port="2718",
            )
            proc = types.SimpleNamespace(pid=1234, poll=lambda: None)
            server = {
                "pid": 1234,
                "host": "127.0.0.1",
                "port": 2718,
                "server_id": "abc",
            }

            with mock.patch.object(mncli.shutil, "which", return_value="/usr/bin/uvx"):
                with mock.patch.object(mncli, "_discover_servers", return_value=([], Path("/registry"))):
                    with mock.patch.object(
                        mncli,
                        "_wait_for_server_registration",
                        return_value=(server, Path("/registry"), None),
                    ):
                        with mock.patch.object(mncli, "_read_server_session_ids", return_value=([], None)):
                            with mock.patch.object(mncli.subprocess, "Popen", return_value=proc):
                                out = io.StringIO()
                                with contextlib.redirect_stdout(out):
                                    mncli.cmd_start(args)

            self.assertIn("sessions: none", out.getvalue())
            self.assertIn("open: http://127.0.0.1:2718", out.getvalue())
            self.assertIn("next: open the notebook, then mncli --port 2718 status", out.getvalue())

    def test_start_reports_immediate_exit_with_log_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "server.log"
            args = _args(
                notebook=str(Path(tmp) / "analysis.py"),
                runner="uvx",
                log=str(log_path),
            )
            proc = types.SimpleNamespace(pid=1234, poll=lambda: 2)

            with mock.patch.object(mncli.shutil, "which", return_value="/usr/bin/uvx"):
                with mock.patch.object(mncli, "_discover_servers", return_value=([], Path("/registry"))):
                    with mock.patch.object(mncli.subprocess, "Popen", return_value=proc):
                        err = io.StringIO()
                        with contextlib.redirect_stderr(err):
                            with self.assertRaises(SystemExit) as raised:
                                mncli.cmd_start(args)

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("marimo exited immediately with code 2", err.getvalue())
            self.assertIn("log:", err.getvalue())

    def test_start_reports_registration_timeout_with_log_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "server.log"
            log_path.write_text("sandbox failed\n")
            args = _args(
                notebook=str(Path(tmp) / "analysis.py"),
                runner="uvx",
                log=str(log_path),
                registration_timeout_seconds=0,
            )
            proc = types.SimpleNamespace(pid=1234, poll=lambda: None)

            with mock.patch.object(mncli.shutil, "which", return_value="/usr/bin/uvx"):
                with mock.patch.object(mncli, "_discover_servers", return_value=([], Path("/registry"))):
                    with mock.patch.object(
                        mncli,
                        "_wait_for_server_registration",
                        return_value=(None, Path("/registry"), None),
                    ):
                        with mock.patch.object(mncli.subprocess, "Popen", return_value=proc):
                            err = io.StringIO()
                            with contextlib.redirect_stderr(err):
                                with self.assertRaises(SystemExit) as raised:
                                    mncli.cmd_start(args)

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("did not register within 0s", err.getvalue())
            self.assertIn("registry: /registry", err.getvalue())
            self.assertIn("sandbox failed", err.getvalue())

    def test_wait_for_server_registration_requires_new_matching_entry(self):
        old = {"pid": 1111, "host": "127.0.0.1", "port": 2718, "server_id": "old"}
        new = {"pid": 2222, "host": "127.0.0.1", "port": 2719, "server_id": "new"}
        proc = types.SimpleNamespace(pid=3333, poll=lambda: None)

        with mock.patch.object(mncli, "_discover_servers", return_value=([old], Path("/registry"))):
            server, servers_dir, rc = mncli._wait_for_server_registration(
                proc,
                previous_keys={mncli._server_registry_key(old)},
                port="2718",
                timeout_seconds=0,
            )
        self.assertIsNone(server)
        self.assertEqual(servers_dir, Path("/registry"))
        self.assertIsNone(rc)

        with mock.patch.object(mncli, "_discover_servers", return_value=([old, new], Path("/registry"))):
            server, servers_dir, rc = mncli._wait_for_server_registration(
                proc,
                previous_keys={mncli._server_registry_key(old)},
                port="2719",
                timeout_seconds=0,
            )
        self.assertEqual(server, new)
        self.assertEqual(servers_dir, Path("/registry"))
        self.assertIsNone(rc)


if __name__ == "__main__":
    unittest.main()
