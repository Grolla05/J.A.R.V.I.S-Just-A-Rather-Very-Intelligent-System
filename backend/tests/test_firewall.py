"""core/firewall.py e core/elevation.py — argv fixo, nunca LAN, tarefas elevadas. Sem netsh/schtasks de verdade."""
import unittest
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
        done, error = firewall.run_commands([["a"], ["b"], ["c"]], run=run)
        self.assertFalse(done)
        self.assertIn("negado", error)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("shell", run.call_args.kwargs)


class TestElevation(unittest.TestCase):
    def test_task_xml_is_logon_of_this_user_highest_and_no_time_limit(self):
        xml = elevation.task_xml(r"C:\r\pythonw.exe", '"C:\\a\\agent.py" --logon', r"C:\a", "PC\\felipe", True, "x & y")
        self.assertIn("<UserId>PC\\felipe</UserId>", xml)
        self.assertIn("<LogonTrigger>", xml)
        self.assertIn("<RunLevel>HighestAvailable</RunLevel>", xml)
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", xml)
        self.assertIn("x &amp; y", xml)
        self.assertIn('"C:\\a\\agent.py" --logon', xml)
        self.assertNotIn("<LogonTrigger>", elevation.task_xml("c", "", "w", "u", False, "d"))

    def test_task_state(self):
        csv_ready = ok('"\\JARVIS\\Agente","N/A","Pronto"\n')
        csv_off = ok('"\\JARVIS\\Agente","N/A","Desabilitado"\n')
        self.assertTrue(elevation.task_state("x", run=MagicMock(return_value=csv_ready)))
        self.assertFalse(elevation.task_state("x", run=MagicMock(return_value=csv_off)))
        missing = SimpleNamespace(returncode=1, stdout="", stderr="ERRO: tarefa não existe")
        self.assertIsNone(elevation.task_state("x", run=MagicMock(return_value=missing)))

    def test_install_creates_agent_task_and_drops_run_value(self):
        calls = []

        def run(args, **kw):
            calls.append(args)
            return ok()
        with patch.object(autostart, "delete_run_value", return_value=True) as drop, \
                patch.object(elevation, "_tui_launcher", return_value=None):
            elevation.install(autostart=False, run=run, user="PC\\felipe")
        creates = [c for c in calls if c[1] == "/Create"]
        self.assertEqual(creates[0][3], elevation.AGENT_TASK)
        self.assertIn("/XML", creates[0])
        self.assertTrue(any(c[1] == "/Change" and "/DISABLE" in c for c in calls))  # sem autostart
        drop.assert_called_once()

    def test_install_raises_when_schtasks_refuses(self):
        refuse = MagicMock(return_value=SimpleNamespace(returncode=1, stdout="Acesso negado", stderr=""))
        with self.assertRaises(RuntimeError):
            elevation.install(run=refuse, user="u")

    def test_remove_restores_run_value_when_autostart_was_on(self):
        def run(args, **kw):
            return ok('"x","N/A","Pronto"') if args[1] == "/Query" else ok()
        with patch.object(autostart, "write_run_value", return_value=True) as write:
            elevation.remove(run=run)
        write.assert_called_once()

    def test_main_refuses_without_admin(self):
        with patch.object(elevation, "is_admin", return_value=False):
            self.assertEqual(elevation.main(["--install"]), 1)


class TestAutostartWithTask(unittest.TestCase):
    def test_task_wins_over_run_value(self):
        with patch.object(autostart, "_task_state", return_value=False), \
                patch.object(elevation, "set_task_enabled", return_value=True) as toggle:
            self.assertFalse(autostart.is_enabled())
            self.assertTrue(autostart.enable())
            toggle.assert_called_with(elevation.AGENT_TASK, True)
            self.assertTrue(autostart.disable())
            toggle.assert_called_with(elevation.AGENT_TASK, False)


if __name__ == "__main__":
    unittest.main()
