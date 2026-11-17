"""core.netwatch — foto, linha de base, diff e vigia. Sem rede: fontes de mentira."""
import time
import unittest
from collections import namedtuple
from datetime import datetime, timedelta

from tests._stubs import install

install()

from core import netwatch  # noqa: E402

Addr = namedtuple("Addr", "ip port")
Conn = namedtuple("Conn", "laddr raddr status pid")
NOW = datetime(2026, 11, 16, 12, 0)

ARP_PT = """
Interface: 192.168.0.10 --- 0x12
  Endereço IP           Endereço físico       Tipo
  192.168.0.1           a4-91-b1-00-11-22     dinâmico
  192.168.0.23          3c-22-fb-aa-bb-cc     dinâmico
  192.168.0.255         ff-ff-ff-ff-ff-ff     estático
  224.0.0.22            01-00-5e-00-00-16     estático
  239.255.255.250       01-00-5e-7f-ff-fa     estático
"""
ROUTE = """
IPv4 Route Table
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      192.168.0.1     192.168.0.10     25
        127.0.0.0        255.0.0.0         On-link         127.0.0.1    331
"""
PROCS = {10: ("chrome.exe", 100.0), 20: ("python.exe", 200.0), 30: ("svch0st.exe", 300.0), 40: ("?", 0.0)}
CONNS = [
    Conn(Addr("192.168.0.10", 51000), Addr("142.250.0.1", 443), "ESTABLISHED", 10),
    Conn(Addr("192.168.0.10", 51001), Addr("142.250.0.2", 443), "ESTABLISHED", 10),
    Conn(Addr("192.168.0.10", 51002), Addr("192.168.0.23", 445), "ESTABLISHED", 10),   # LAN: não é "internet"
    Conn(Addr("127.0.0.1", 8000), (), "LISTEN", 20),                                    # loopback: ignorado
    Conn(Addr("0.0.0.0", 8099), (), "LISTEN", 20),
    Conn(Addr("0.0.0.0", 4444), (), "LISTEN", 40),                                      # processo ilegível
    Conn(Addr("0.0.0.0", 5353), (), "NONE", 20),                                        # UDP
    Conn(Addr("192.168.0.10", 52000), Addr("8.8.8.8", 53), "ESTABLISHED", 0),           # sem PID
]


def snap(conns=CONNS, arp=None, with_arp=True):
    return netwatch.snapshot(connections=lambda: conns, proc_info=lambda pid: PROCS.get(pid, ("?", 0.0)),
                             arp=lambda: netwatch.parse_arp(ARP_PT) if arp is None else arp,
                             gateway=lambda: netwatch.parse_gateway(ROUTE), with_arp=with_arp)


class TestParsing(unittest.TestCase):
    def test_arp_keeps_only_real_devices(self):
        self.assertEqual(netwatch.parse_arp(ARP_PT), {"a4-91-b1-00-11-22": "192.168.0.1",
                                                      "3c-22-fb-aa-bb-cc": "192.168.0.23"})
        self.assertEqual(netwatch.parse_arp(""), {})
        self.assertEqual(netwatch.parse_arp("  10.0.0.5   AA:BB:CC:DD:EE:F0   dynamic"), {"aa-bb-cc-dd-ee-f0": "10.0.0.5"})

    def test_gateway(self):
        self.assertEqual(netwatch.parse_gateway(ROUTE), "192.168.0.1")
        self.assertEqual(netwatch.parse_gateway("nada aqui"), "")

    def test_is_public(self):
        for ip, expected in (("8.8.8.8", True), ("142.250.0.1", True), ("192.168.0.1", False), ("10.1.2.3", False),
                             ("127.0.0.1", False), ("169.254.1.1", False), ("224.0.0.1", False),
                             ("::1", False), ("fe80::1%12", False), ("2001:4860:4860::8888", True), ("lixo", False)):
            with self.subTest(ip=ip):
                self.assertEqual(netwatch.is_public(ip), expected)


class TestSnapshot(unittest.TestCase):
    def test_listeners_talkers_devices_gateway(self):
        s = snap()
        self.assertEqual(list(s["listeners"]), ["python.exe:8099"])
        self.assertEqual(s["listeners"]["python.exe:8099"]["pid"], 20)
        self.assertEqual(list(s["talkers"]), ["chrome.exe"])
        self.assertEqual(s["talkers"]["chrome.exe"]["count"], 2)
        self.assertEqual(len(s["devices"]), 2)
        self.assertEqual(s["gateway"], {"ip": "192.168.0.1", "mac": "a4-91-b1-00-11-22"})

    def test_round_without_arp_or_with_failed_arp_has_no_devices(self):
        self.assertIsNone(snap(with_arp=False)["devices"])
        failed = snap(arp={})
        self.assertIsNone(failed["devices"])
        self.assertIsNone(failed["gateway"])

    def test_connections_failure_is_empty(self):
        def boom():
            raise PermissionError("acesso negado")
        s = netwatch.snapshot(connections=boom, arp=dict, gateway=str)
        self.assertEqual((s["listeners"], s["talkers"]), ({}, {}))

    def test_plain_tuple_addresses(self):
        conns = [Conn(("0.0.0.0", 9000), (), "LISTEN", 20), Conn(("10.0.0.2", 1), ("1.1.1.1", 443), "ESTABLISHED", 20)]
        s = snap(conns=conns)
        self.assertEqual(list(s["listeners"]), ["python.exe:9000"])
        self.assertEqual(s["talkers"]["python.exe"]["ip"], "1.1.1.1")


class TestBaselineAndDiff(unittest.TestCase):
    def setUp(self):
        self.base = netwatch.new_baseline(snap(), NOW)

    def test_same_snapshot_has_no_findings(self):
        self.assertEqual(netwatch.diff(self.base, snap()), [])
        self.assertTrue(netwatch.learning(self.base, NOW + timedelta(minutes=5)))
        self.assertFalse(netwatch.learning(self.base, NOW + timedelta(minutes=11)))
        self.assertFalse(netwatch.learning({}, NOW))

    def test_new_exposed_port(self):
        conns = CONNS + [Conn(Addr("0.0.0.0", 4444), (), "LISTEN", 30)]
        findings = netwatch.diff(self.base, snap(conns=conns))
        self.assertEqual([(f["kind"], f["key"]) for f in findings], [("NEW_LISTENER", "listener:svch0st.exe:4444")])
        self.assertEqual((findings[0]["pid"], findings[0]["created"]), (30, 300.0))
        self.assertIn("porta 4444", findings[0]["text"])

    def test_new_process_talking_to_the_internet(self):
        conns = CONNS + [Conn(Addr("192.168.0.10", 53000), Addr("185.10.10.10", 8443), "ESTABLISHED", 30)]
        findings = netwatch.diff(self.base, snap(conns=conns))
        self.assertEqual([f["key"] for f in findings], ["talker:svch0st.exe"])
        self.assertIn("185.10.10.10:8443", findings[0]["text"])

    def test_new_device_and_round_without_arp_is_silent(self):
        table = {**netwatch.parse_arp(ARP_PT), "de-ad-be-ef-00-02": "192.168.0.77"}
        findings = netwatch.diff(self.base, snap(arp=table))
        self.assertEqual([(f["kind"], f["mac"], f["ip"]) for f in findings],
                         [("NEW_DEVICE", "de-ad-be-ef-00-02", "192.168.0.77")])
        self.assertEqual(netwatch.diff(self.base, snap(with_arp=False)), [])

    def test_gateway_mac_change(self):
        table = {"00-0c-29-66-66-66": "192.168.0.1", "3c-22-fb-aa-bb-cc": "192.168.0.23"}
        findings = netwatch.diff(self.base, snap(arp=table))
        kinds = {f["kind"] for f in findings}
        self.assertEqual(kinds, {"NEW_DEVICE", "GATEWAY_CHANGED"})
        gw = next(f for f in findings if f["kind"] == "GATEWAY_CHANGED")
        self.assertEqual((gw["old_mac"], gw["mac"]), ("a4-91-b1-00-11-22", "00-0c-29-66-66-66"))
        self.assertIn("ARP spoofing", gw["text"])

    def test_trust_silences_each_kind(self):
        conns = CONNS + [Conn(Addr("0.0.0.0", 4444), (), "LISTEN", 30),
                         Conn(Addr("192.168.0.10", 53000), Addr("185.10.10.10", 8443), "ESTABLISHED", 30)]
        table = {"00-0c-29-66-66-66": "192.168.0.1", "3c-22-fb-aa-bb-cc": "192.168.0.23",
                 "de-ad-be-ef-00-02": "192.168.0.77"}
        current = snap(conns=conns, arp=table)
        findings = netwatch.diff(self.base, current)
        self.assertEqual(len(findings), 5)
        for finding in findings:
            netwatch.trust(self.base, finding)
        self.assertEqual(netwatch.diff(self.base, current), [])

    def test_absorb_merges(self):
        conns = CONNS + [Conn(Addr("0.0.0.0", 4444), (), "LISTEN", 30)]
        netwatch.absorb(self.base, snap(conns=conns))
        self.assertIn("svch0st.exe:4444", self.base["listeners"])
        self.assertEqual(self.base["gateway"]["mac"], "a4-91-b1-00-11-22")  # gateway aprendido não muda no absorb


class TestWatch(unittest.TestCase):
    def setUp(self):
        self.store = {"base": None}
        self.snaps = []
        self.now = NOW
        self.found = []
        self.handled = True

    def _watch(self, **kwargs):
        def on_finding(finding):
            self.found.append(finding["key"])
            return self.handled
        return netwatch.NetworkWatch(on_finding, lambda: self.store["base"],
                                     lambda b: self.store.update(base=b),
                                     snapshot_fn=lambda with_arp=True: self.snaps.pop(0) if len(self.snaps) > 1
                                     else self.snaps[0],
                                     clock=lambda: self.now, **kwargs)

    def test_first_round_learns_then_learning_window_absorbs(self):
        new_port = snap(conns=CONNS + [Conn(Addr("0.0.0.0", 4444), (), "LISTEN", 30)])
        self.snaps = [snap(), new_port, new_port]
        watch = self._watch()
        self.assertEqual(watch.check_once(), [])
        self.assertIsNotNone(self.store["base"])
        self.now = NOW + timedelta(minutes=5)
        self.assertEqual(watch.check_once(), [])           # ainda aprendendo: entra na base
        self.now = NOW + timedelta(minutes=30)
        self.assertEqual(watch.check_once(), [])
        self.assertEqual(self.found, [])

    def test_finding_is_delivered_once(self):
        self.store["base"] = {**netwatch.new_baseline(snap(), NOW), "learn_until": NOW.isoformat()}
        self.snaps = [snap(conns=CONNS + [Conn(Addr("0.0.0.0", 4444), (), "LISTEN", 30)])]
        self.now = NOW + timedelta(hours=1)
        watch = self._watch()
        self.assertEqual([f["key"] for f in watch.check_once()], ["listener:svch0st.exe:4444"])
        self.assertEqual(watch.check_once(), [])
        self.assertEqual(self.found, ["listener:svch0st.exe:4444"])

    def test_unhandled_finding_comes_back_and_errors_do_not_break(self):
        self.store["base"] = {**netwatch.new_baseline(snap(), NOW), "learn_until": NOW.isoformat()}
        self.snaps = [snap(conns=CONNS + [Conn(Addr("0.0.0.0", 4444), (), "LISTEN", 30)])]
        self.now = NOW + timedelta(hours=1)
        self.handled = False
        watch = self._watch()
        watch.check_once()
        watch.check_once()
        self.assertEqual(len(self.found), 2)
        watch.on_finding = lambda f: 1 / 0
        self.assertEqual(watch.check_once(), [])

    def test_arp_only_every_n_rounds_and_snapshot_callback(self):
        asked, seen = [], []
        watch = netwatch.NetworkWatch(lambda f: True, lambda: None, lambda b: None,
                                      snapshot_fn=lambda with_arp=True: asked.append(with_arp) or snap(with_arp=with_arp),
                                      arp_every=3, clock=lambda: NOW, on_snapshot=seen.append)
        for _ in range(4):
            watch.check_once()
        self.assertEqual(asked, [True, False, False, True])
        self.assertEqual(len(seen), 4)

    def test_start_stop_idempotent_daemon(self):
        self.snaps = [snap()]
        watch = self._watch(interval=0.01)
        watch.start()
        watch.start()
        self.assertTrue(watch._thread.daemon)
        deadline = time.time() + 2
        while self.store["base"] is None and time.time() < deadline:
            time.sleep(0.01)
        watch.stop()
        watch.stop()
        self.assertFalse(watch.running)
        self.assertIsNotNone(self.store["base"])


if __name__ == "__main__":
    unittest.main()
