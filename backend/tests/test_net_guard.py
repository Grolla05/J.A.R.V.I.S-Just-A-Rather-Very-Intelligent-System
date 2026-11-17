"""services.net_guard — juiz, alerta com confirmação, encerrar/bloquear e textos. Sem rede nem Ollama."""
import importlib.util
import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from tests._stubs import install

install()

sys.modules.setdefault("services.listen", MagicMock())
sys.modules.setdefault("services.speak", MagicMock())

import core.state as state  # noqa: E402
import services.brain as brain  # noqa: E402
from core import netwatch  # noqa: E402
from services import net_guard, notify_filter  # noqa: E402

FREE = {"presentation": False, "dnd": False, "meeting": False, "fullscreen": False}
QUIET = {**FREE, "dnd": True}
LISTENER = {"kind": "NEW_LISTENER", "key": "listener:svch0st.exe:4444", "proc": "svch0st.exe", "port": 4444,
            "addr": "0.0.0.0", "pid": 30, "created": 300.0, "text": "svch0st.exe abriu a porta 4444."}
TALKER = {"kind": "NEW_TALKER", "key": "talker:updater.exe", "proc": "updater.exe", "pid": 31, "created": 310.0,
          "ip": "185.10.10.10", "port": 8443, "count": 1, "text": "updater.exe está falando com a internet."}
DEVICE = {"kind": "NEW_DEVICE", "key": "device:de-ad-be-ef-00-02", "mac": "de-ad-be-ef-00-02", "ip": "192.168.0.77",
          "text": "Aparelho novo na rede: 192.168.0.77."}
GATEWAY = {"kind": "GATEWAY_CHANGED", "key": "gateway:00-0c", "ip": "192.168.0.1", "mac": "00-0c-29-66-66-66",
           "old_mac": "a4-91-b1-00-11-22", "text": "O roteador mudou de endereço físico."}


class FakeDb:
    def __init__(self):
        self.data = {}

    def get_config(self, key):
        return json.loads(json.dumps(self.data[key])) if key in self.data else None

    def save_config(self, key, value):
        self.data[key] = json.loads(json.dumps(value))


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.said = []
        self._saved = (state.pending_critical_action, state.dnd_active, list(state.dnd_backlog),
                       state.presentation_active)
        state.pending_critical_action = None
        state.dnd_backlog.clear()
        state.presentation_active = False
        net_guard._recent.clear()
        net_guard._judge_cache.clear()
        net_guard._last["snapshot"] = None
        self.ctx = FREE
        self._patches = [patch.object(net_guard, "db", self.db),
                         patch.object(notify_filter, "context", side_effect=lambda: self.ctx)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        state.pending_critical_action, state.dnd_active, backlog, state.presentation_active = self._saved
        state.dnd_backlog[:] = backlog
        net_guard._recent.clear()
        net_guard._judge_cache.clear()

    def _handle(self, finding, verdict=net_guard.SUSPECT):
        return net_guard.handle(finding, judge_fn=lambda f: verdict, announce=self.said.append)


class TestJudge(GuardCase):
    def test_verdicts_and_cache(self):
        calls = []

        def query(messages, temperature):
            calls.append(messages[0]["content"])
            return " suspeito. "

        self.assertEqual(net_guard.judge(LISTENER, query=query), net_guard.SUSPECT)
        self.assertEqual(net_guard.judge(LISTENER, query=query), net_guard.SUSPECT)
        self.assertEqual(len(calls), 1)                       # 2ª vez veio do cache
        self.assertIn("svch0st.exe", calls[0])
        self.assertIn("porta 4444", calls[0])
        self.assertEqual(net_guard.judge(TALKER, query=lambda m, temperature: "SEGURO"), net_guard.SAFE)

    def test_ambiguous_answer_is_suspect_and_cache_expires(self):
        self.assertEqual(net_guard.judge(TALKER, query=lambda m, temperature: "Não é SEGURO, é SUSPEITO"),
                         net_guard.SUSPECT)
        clock = iter([0.0, 99999.0, 99999.0]).__next__  # grava · vencido · regrava
        net_guard._judge_cache.clear()
        net_guard.judge(LISTENER, query=lambda m, temperature: "SUSPEITO", clock=clock)
        self.assertEqual(net_guard.judge(LISTENER, query=lambda m, temperature: "SEGURO", clock=clock), net_guard.SAFE)

    def test_no_answer_decides_nothing(self):
        def boom(messages, temperature):
            raise TimeoutError("ollama fora")
        self.assertIsNone(net_guard.judge(LISTENER, query=boom))
        self.assertIsNone(net_guard.judge(LISTENER, query=lambda m, temperature: None))
        self.assertEqual(net_guard._judge_cache, {})


class TestHandle(GuardCase):
    def test_safe_process_joins_baseline_silently(self):
        self.assertTrue(self._handle(TALKER, net_guard.SAFE))
        self.assertEqual(self.said, [])
        self.assertIsNone(state.pending_critical_action)
        self.assertIn("updater.exe", self.db.data[net_guard.BASELINE_KEY]["talkers"])
        self.assertEqual(net_guard.recent(), [])

    def test_no_verdict_asks_to_retry(self):
        self.assertFalse(self._handle(LISTENER, None))
        self.assertEqual(self.said, [])

    def test_suspect_process_asks_to_kill_and_confirm_kills_by_pid(self):
        self.assertTrue(self._handle(LISTENER))
        pending = state.pending_critical_action
        self.assertEqual((pending["type"], pending["target"]), ("NET_KILL_PROCESS", "svch0st.exe"))
        self.assertIn("Deseja que eu o encerre?", self.said[0])
        self.assertEqual(pending["question"], self.said[0])
        with patch.object(net_guard, "kill_process", return_value="svch0st.exe encerrado, Senhor.") as kill:
            self.assertEqual(brain.confirm_pending_action(True), "svch0st.exe encerrado, Senhor.")
        kill.assert_called_once_with(30, "svch0st.exe", 300.0)
        self.assertIsNone(state.pending_critical_action)
        self.assertNotIn(net_guard.BASELINE_KEY, self.db.data)

    def test_declining_trusts_but_timeout_does_not(self):
        self._handle(LISTENER)
        reply = brain.confirm_pending_action(False)
        self.assertIn("passa a ser conhecido", reply)
        self.assertIn("svch0st.exe:4444", self.db.data[net_guard.BASELINE_KEY]["listeners"])

        self.db.data.clear()
        self._handle(TALKER)
        state.pending_critical_action["timeout"] = time.time() - 1   # ConfirmScreen expirou
        self.assertIsNone(brain.confirm_pending_action(False))
        self.assertNotIn(net_guard.BASELINE_KEY, self.db.data)

    def test_voice_only_trusts_on_explicit_no(self):
        self._handle(LISTENER)
        with patch.object(brain, "classify_intent", return_value={"intent": "CHAT"}), \
             patch.object(brain, "get_vault_context", return_value=("", "")), \
             patch.object(brain, "ask_local_ai", return_value="resposta"):
            brain.execute_command("que horas são agora")          # nem sim nem não: só descarta
        self.assertNotIn(net_guard.BASELINE_KEY, self.db.data)
        self._handle({**LISTENER, "key": "listener:x:1"})
        self.assertIn("passa a ser conhecido", brain._check_pending_action("não, pode manter") or "")

    def test_second_process_waits_while_a_confirmation_is_open(self):
        self._handle(LISTENER)
        self.assertFalse(self._handle(TALKER))
        self.assertEqual(len(self.said), 1)
        self.assertEqual(state.pending_critical_action["target"], "svch0st.exe")

    def test_device_and_gateway_only_announce(self):
        self.assertTrue(self._handle(DEVICE))
        self.assertTrue(self._handle(GATEWAY))
        self.assertIsNone(state.pending_critical_action)
        self.assertIn("/rede confiar 1", self.said[0])
        self.assertIn("roteador", self.said[1])
        self.assertEqual(len(net_guard.recent()), 2)

    def test_quiet_defers_everything_but_gateway(self):
        self.ctx = QUIET
        self.assertTrue(self._handle(LISTENER))
        self.assertTrue(self._handle(DEVICE))
        self.assertEqual(self.said, [])
        self.assertIsNone(state.pending_critical_action)
        self.assertEqual(len(state.dnd_backlog), 2)
        self.assertTrue(self._handle(GATEWAY))                 # crítico: passa pelo silêncio
        self.assertEqual(len(self.said), 1)


class TestActions(unittest.TestCase):
    def _proc(self, name="svch0st.exe", created=300.0):
        proc = MagicMock()
        proc.name.return_value = name
        proc.create_time.return_value = created
        return proc

    def test_kill_same_process(self):
        proc = self._proc()
        with patch.dict(sys.modules, {"psutil": MagicMock(Process=MagicMock(return_value=proc))}):
            self.assertIn("encerrado", net_guard.kill_process(30, "svch0st.exe", 300.0))
        proc.terminate.assert_called_once()

    def test_recycled_pid_is_not_killed(self):
        for proc in (self._proc(name="chrome.exe"), self._proc(created=999.0)):
            with patch.dict(sys.modules, {"psutil": MagicMock(Process=MagicMock(return_value=proc))}):
                self.assertIn("Não encerrei nada", net_guard.kill_process(30, "svch0st.exe", 300.0))
            proc.terminate.assert_not_called()

    def test_gone_process(self):
        with patch.dict(sys.modules, {"psutil": MagicMock(Process=MagicMock(side_effect=ProcessLookupError()))}):
            self.assertIn("Não consegui encerrar", net_guard.kill_process(30, "svch0st.exe", 300.0))

    def test_block_ip_validates_and_never_blocks_the_lan(self):
        run = MagicMock()
        self.assertIn("não é um endereço IP", net_guard.block_ip("185.10.10.10 & calc", admin=lambda: True, run=run))
        self.assertIn("local ou reservado", net_guard.block_ip("192.168.0.1", admin=lambda: True, run=run))
        self.assertIn("local ou reservado", net_guard.block_ip("127.0.0.1", admin=lambda: True, run=run))
        run.assert_not_called()

    def test_block_ip_without_admin_returns_the_command(self):
        run = MagicMock()
        reply = net_guard.block_ip("185.10.10.10", admin=lambda: False, run=run)
        run.assert_not_called()
        self.assertIn("não estou elevado", reply)
        self.assertIn("remoteip=185.10.10.10", reply)

    def test_block_ip_as_admin_runs_netsh_without_shell(self):
        run = MagicMock(return_value=MagicMock(returncode=0, stdout="Ok."))
        reply = net_guard.block_ip(" 185.10.10.10 ", admin=lambda: True, run=run)
        self.assertIn("bloqueada", reply)
        args = run.call_args[0][0]
        self.assertEqual(args[:5], ["netsh", "advfirewall", "firewall", "add", "rule"])
        self.assertIn("remoteip=185.10.10.10", args)
        self.assertNotIn("shell", run.call_args.kwargs)
        run.return_value = MagicMock(returncode=1, stdout="Acesso negado")
        self.assertIn("recusou", net_guard.block_ip("185.10.10.10", admin=lambda: True, run=run))


class TestTexts(GuardCase):
    SNAP = {"listeners": {"python.exe:8099": {"proc": "python.exe", "port": 8099, "addr": "0.0.0.0",
                                             "pid": 20, "created": 200.0}},
            "talkers": {"chrome.exe": {"proc": "chrome.exe", "pid": 10, "created": 100.0, "ip": "142.250.0.1",
                                       "port": 443, "count": 7}},
            "devices": {"a4-91-b1-00-11-22": "192.168.0.1", "de-ad-be-ef-00-02": "192.168.0.77"},
            "gateway": {"ip": "192.168.0.1", "mac": "a4-91-b1-00-11-22"}}

    def test_scan_without_baseline(self):
        text = net_guard.scan_text(snapshot_fn=lambda with_arp=True: self.SNAP)
        self.assertIn("**Aparelhos na rede:** 2", text)
        self.assertIn("8099 · python.exe", text)
        self.assertIn("chrome.exe (7)", text)
        self.assertIn("Ainda sem linha de base", text)

    def test_scan_marks_what_is_outside_the_baseline(self):
        self.db.data[net_guard.BASELINE_KEY] = {"listeners": [], "talkers": ["chrome.exe"],
                                                "devices": {"a4-91-b1-00-11-22": "192.168.0.1"},
                                                "gateway": {"ip": "192.168.0.1", "mac": "a4-91-b1-00-11-22"},
                                                "learn_until": "2020-01-01T00:00:00"}
        text = net_guard.scan_text(snapshot_fn=lambda with_arp=True: self.SNAP)
        self.assertIn("192.168.0.77 · `de-ad-be-ef-00-02` · **novo**", text)
        self.assertIn("Fora da linha de base agora", text)
        self.assertIn("python.exe abriu a porta 8099", text)
        short = net_guard.scan_text(snapshot_fn=lambda with_arp=True: self.SNAP, short=True)
        self.assertIn("2 aparelhos na rede", short)
        self.assertNotIn("**", short)

    def test_scan_sorts_ips_and_tolerates_odd_entries(self):
        odd = {**self.SNAP, "devices": {"aa-01": "192.168.0.10", "aa-02": "192.168.0.9", "aa-03": "fe80::1",
                                        "aa-04": "?"}}
        text = net_guard.scan_text(snapshot_fn=lambda with_arp=True: odd)
        self.assertLess(text.index("192.168.0.9 "), text.index("192.168.0.10 "))   # numérico, não alfabético
        self.assertIn("fe80::1", text)
        self.assertIn("  - ? ·", text)

    def test_trust_reset_and_perimeter(self):
        self.assertIn("vigia desligado", net_guard.perimeter_text())
        self._handle(DEVICE)
        net_guard.remember_snapshot(self.SNAP)
        net_guard.remember_snapshot({**self.SNAP, "devices": None, "gateway": None})  # rodada sem ARP
        perimeter = net_guard.perimeter_text()
        self.assertIn("aparelhos na LAN 2", perimeter)
        self.assertIn("alertas          1", perimeter)
        self.assertIn("Não há achado 3", net_guard.trust_text(3))
        self.assertIn("passa a ser conhecido", net_guard.trust_text(1))
        self.assertIn("de-ad-be-ef-00-02", self.db.data[net_guard.BASELINE_KEY]["devices"])
        self.assertEqual(net_guard.recent(), [])
        self.assertIn("apagada", net_guard.reset_text())
        self.assertIsNone(net_guard.load_baseline())


class TestSkillAndSpeed(unittest.TestCase):
    def test_skill_returns_short_scan(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "skills", "system", "network_guard.py")
        spec = importlib.util.spec_from_file_location("network_guard_skill", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with patch.object(net_guard, "scan_text", return_value="Varredura concluída.") as scan:
            self.assertEqual(mod.execute(None, "tem alguém na minha rede?"), "Varredura concluída.")
        scan.assert_called_once_with(short=True)
        with patch.object(net_guard, "scan_text", side_effect=RuntimeError("sem psutil")):
            self.assertIn("Não consegui varrer", mod.execute(None, "varre a rede"))
        self.assertEqual(mod.INTENT, "NETWORK_SCAN")

    def test_network_speed_uses_its_own_window_and_reports_faults(self):
        """Antes dividia pelo tempo desde o boot: a velocidade encolhia com o uso."""
        from collections import namedtuple

        from core.SystemInfo import SystemInfo
        Net = namedtuple("Net", "bytes_sent bytes_recv errin errout dropin dropout")
        mon = SystemInfo.__new__(SystemInfo)
        mon.last_net_sent, mon.last_net_recv = 0, 0
        mon._net_last_time, mon._net_cache = 1000.0, None
        mon._net_last_faults = {"errin": 0, "errout": 0, "dropin": 0, "dropout": 0}
        counters = [Net(1000, 4000, 2, 0, 1, 0), Net(3000, 10000, 2, 0, 61, 0)]
        times = iter([1002.0, 1002.5, 1006.0])
        with patch("core.SystemInfo.psutil") as psutil_mock, patch("core.SystemInfo.time") as time_mock:
            psutil_mock.net_io_counters.side_effect = lambda: counters.pop(0)
            time_mock.time.side_effect = lambda: next(times)
            first = mon.get_network_speed()
            cached = mon.get_network_speed()      # 0,5 s depois: mesma amostra, sem zerar a janela
            second = mon.get_network_speed()      # 4 s depois da 1ª
        self.assertEqual((first["upload_bps"], first["download_bps"]), (500.0, 2000.0))
        self.assertEqual(cached, first)
        self.assertEqual((second["upload_bps"], second["download_bps"]), (500.0, 1500.0))
        self.assertEqual((first["errin"], first["dropin"], second["dropin"]), (2, 1, 60))
        self.assertEqual(netwatch.NEW_DEVICE, "NEW_DEVICE")


if __name__ == "__main__":
    unittest.main()
