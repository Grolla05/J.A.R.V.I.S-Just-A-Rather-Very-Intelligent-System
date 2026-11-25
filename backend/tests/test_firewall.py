"""core/firewall.py e core/elevation.py — argv fixo, nunca LAN, tarefas elevadas. Sem netsh/schtasks de verdade."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

from core import autostart, elevation, firewall  # noqa: E402


def ok(stdout=""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


class TestFirewall(unittest.TestCase):
    def test_validate_ip(self):
        self.assertEqual(firewall.validate_ip(" 185.10.10.10 "), "185.10.10.10")
        for bad in ("192.168.0.1", "10.0.0.5", "127.0.0.1", "224.0.0.1", "0.0.0.0"):
            with self.assertRaises(ValueError):
                firewall.validate_ip(bad)
        with self.assertRaises(ValueError):
            firewall.validate_ip("1.2.3.4 & calc")

    def test_block_ip_creates_inbound_and_outbound(self):
        cmds = firewall.block_ip_commands("185.10.10.10")
        self.assertEqual([c[6] for c in cmds], ["dir=in", "dir=out"])
        for c in cmds:
            self.assertEqual(c[:5], ["netsh", "advfirewall", "firewall", "add", "rule"])
            self.assertIn("remoteip=185.10.10.10", c)
            self.assertTrue(c[5].startswith(f"name={firewall.RULE_PREFIX} 185.10.10.10"))
        self.assertEqual(firewall.ip_rule_names("185.10.10.10"),
                         [f"{firewall.RULE_PREFIX} 185.10.10.10 (entrada)", f"{firewall.RULE_PREFIX} 185.10.10.10 (saida)"])

    def test_program_inbound_only_for_absolute_exe(self):
        cmd = firewall.block_program_inbound_command(r"C:\Users\x\AppData\Local\Temp\svch0st.exe")
        self.assertIn("dir=in", cmd)
        self.assertIn(r"program=C:\Users\x\AppData\Local\Temp\svch0st.exe", cmd)
        self.assertIn("svch0st.exe", firewall.program_rule_name(r"C:\a\svch0st.exe"))
        for bad in ("", "svch0st.exe", r"C:\a\script.ps1", 'C:\\a\\x".exe'):
            with self.assertRaises(ValueError):
                firewall.block_program_inbound_command(bad)

    def test_delete_only_jarvis_rules(self):
        self.assertEqual(firewall.delete_rule_command(f"{firewall.RULE_PREFIX} 1.2.3.4 (entrada)")[3:5],
                         ["delete", "rule"])
        with self.assertRaises(ValueError):
            firewall.delete_rule_command("Regra do Windows")

    def test_run_commands_stops_on_failure_and_never_uses_shell(self):
        run = MagicMock(side_effect=[ok(), SimpleNamespace(returncode=1, stdout="Acesso negado", stderr="")])
        done, error = firewall._run_direct([["a"], ["b"], ["c"]], run)
        self.assertFalse(done)
        self.assertIn("negado", error)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("shell", run.call_args.kwargs)


class TestElevation(unittest.TestCase):
    def test_task_xml_is_on_demand_highest_and_short(self):
        xml = elevation.task_xml(r"C:\r\pythonw.exe", '"C:\a\agent.py" --firewall-queue', r"C:\a", "PC\felipe", "x & y")
        self.assertIn("<Triggers />", xml)
        self.assertIn("<UserId>PC\felipe</UserId>", xml)
        self.assertIn("<RunLevel>HighestAvailable</RunLevel>", xml)
        self.assertIn(f"<ExecutionTimeLimit>{elevation.TASK_TIME_LIMIT}</ExecutionTimeLimit>", xml)
        self.assertIn("x &amp; y", xml)
        self.assertNotIn("LogonTrigger", xml)

    def test_install_creates_only_the_firewall_task(self):
        calls = []

        def run(args, **kw):
            calls.append(args)
            return ok()
        elevation.install(run=run, user="PC\felipe")
        (create,) = [c for c in calls if c[1] == "/Create"]
        self.assertEqual(create[3], elevation.FIREWALL_TASK)
        self.assertIn("/XML", create)

    def test_install_raises_when_schtasks_refuses(self):
        refuse = MagicMock(return_value=SimpleNamespace(returncode=1, stdout="Acesso negado", stderr=""))
        with self.assertRaises(RuntimeError):
            elevation.install(run=refuse, user="u")

    def test_remove_deletes_firewall_and_legacy_tasks(self):
        run = MagicMock(return_value=ok())
        elevation.remove(run=run)
        deleted = [c.args[0][3] for c in run.call_args_list]
        self.assertEqual(deleted, [elevation.FIREWALL_TASK, *elevation.LEGACY_TASKS])

    def test_task_exists(self):
        self.assertTrue(elevation.task_exists(run=MagicMock(return_value=ok("TaskName  Pronto"))))
        missing = SimpleNamespace(returncode=1, stdout="", stderr="ERRO")
        self.assertFalse(elevation.task_exists(run=MagicMock(return_value=missing)))

    def test_main_refuses_without_admin_and_queue_runs_the_queue(self):
        with patch.object(elevation, "is_admin", return_value=False):
            self.assertEqual(elevation.main(["--install"]), 1)
        with patch.object(elevation, "is_admin", return_value=True), \
                patch.object(firewall, "process_queue", return_value=0) as queue:
            self.assertEqual(elevation.main(["--queue"]), 0)
        queue.assert_called_once()

    def test_jarvis_itself_is_never_elevated(self):
        self.assertFalse(hasattr(autostart, "_task_state"))  # o agente sobe pelo Run, sem admin
        self.assertNotIn("JARVIS\TUI", open(autostart.__file__, encoding="utf-8").read())


class TestQueue(unittest.TestCase):
    IP_CMDS = firewall.block_ip_commands("185.10.10.10")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self._p = patch.object(firewall, "_queue_dir", return_value=self.folder)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self.tmp.cleanup()

    def test_allowed_commands_are_exactly_ours(self):
        for cmd in (*self.IP_CMDS, firewall.block_program_inbound_command(r"C:\a\x.exe"),
                    firewall.delete_rule_command(f"{firewall.RULE_PREFIX} 185.10.10.10 (entrada)")):
            self.assertTrue(firewall.is_allowed_command(cmd), cmd)
        bad = [
            ["cmd", "/c", "whoami"],
            ["netsh", "advfirewall", "set", "allprofiles", "state", "off"],
            ["netsh", "advfirewall", "firewall", "add", "rule", "name=JARVIS bloqueio x", "dir=in",
             "action=allow", "remoteip=185.10.10.10"],                                   # allow, não block
            [*self.IP_CMDS[0][:-1], "remoteip=192.168.0.1"],                              # LAN
            ["netsh", "advfirewall", "firewall", "delete", "rule", "name=Regra do Windows"],
            "netsh advfirewall",
        ]
        for cmd in bad:
            self.assertFalse(firewall.is_allowed_command(cmd), cmd)

    def test_run_commands_refuses_foreign_command_without_running(self):
        run = MagicMock()
        done, error = firewall.run_commands([["cmd", "/c", "calc"]], run=run)
        self.assertFalse(done)
        run.assert_not_called()

    def test_not_admin_goes_through_the_task(self):
        with patch.object(firewall, "is_admin", return_value=False), \
                patch.object(firewall, "run_via_task", return_value=(True, "")) as via:
            self.assertEqual(firewall.run_commands(self.IP_CMDS), (True, ""))
        via.assert_called_once_with(self.IP_CMDS)

    def test_round_trip_through_the_elevated_queue(self):
        netsh = MagicMock(return_value=ok())

        def trigger():  # a tarefa elevada: atende a fila
            firewall.process_queue(run=netsh, folder=self.folder)
            return True
        self.assertEqual(firewall.run_via_task(self.IP_CMDS, trigger=trigger, sleep=lambda s: None), (True, ""))
        self.assertEqual([c.args[0] for c in netsh.call_args_list], self.IP_CMDS)
        self.assertEqual(list(self.folder.iterdir()), [])  # pedido e resposta apagados

    def test_queue_refuses_tampered_request(self):
        (self.folder / "req-abc123.json").write_text(json.dumps({"commands": [["cmd", "/c", "calc"]]}),
                                                     encoding="utf-8")
        netsh = MagicMock()
        self.assertEqual(firewall.process_queue(run=netsh, folder=self.folder), 1)
        netsh.assert_not_called()
        self.assertFalse(json.loads((self.folder / "res-abc123.json").read_text(encoding="utf-8"))["ok"])

    def test_missing_task_and_timeout(self):
        done, error = firewall.run_via_task(self.IP_CMDS, trigger=lambda: False)
        self.assertFalse(done)
        self.assertIn("/config", error)
        clock = iter([0.0, 0.0, 99.0])
        done, error = firewall.run_via_task(self.IP_CMDS, trigger=lambda: True, timeout=5,
                                            sleep=lambda s: None, now=lambda: next(clock))
        self.assertFalse(done)
        self.assertIn("não respondeu", error)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_available(self):
        self.assertTrue(firewall.available(admin=lambda: True, task_exists=lambda: False))
        self.assertTrue(firewall.available(admin=lambda: False, task_exists=lambda: True))
        self.assertFalse(firewall.available(admin=lambda: False, task_exists=lambda: False))


if __name__ == "__main__":
    unittest.main()
