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



class TestDeviceIdentity(unittest.TestCase):
    """Fabricante/nome do aparelho e MAC privado de celular."""

    def setUp(self):
        self.base = netwatch.new_baseline(snap(), NOW)

    def test_baseline_stores_vendor_and_private_flag(self):
        entry = self.base["devices"]["3c-22-fb-aa-bb-cc"]
        self.assertEqual(entry["ip"], "192.168.0.23")
        self.assertFalse(entry["private"])
        self.assertIn("vendor", entry)

    def test_old_baseline_format_still_works(self):
        old = {"listeners": [], "talkers": [], "devices": {"3c-22-fb-aa-bb-cc": "192.168.0.23",
                                                           "a4-91-b1-00-11-22": "192.168.0.1"},
               "gateway": {"ip": "192.168.0.1", "mac": "a4-91-b1-00-11-22"}}
        self.assertEqual([f for f in netwatch.diff(old, snap()) if f["kind"] == "NEW_DEVICE"], [])
        netwatch.absorb(old, snap())
        self.assertIsInstance(old["devices"]["3c-22-fb-aa-bb-cc"], dict)

    def test_identified_name_and_vendor_go_into_the_alert(self):
        table = {**netwatch.parse_arp(ARP_PT), "b8-27-eb-11-22-33": "192.168.0.50"}
        ident = lambda mac, ip: {"vendor": "Raspberry Pi Foundation", "name": "pihole", "private": False}  # noqa: E731
        (finding,) = netwatch.diff(self.base, snap(arp=table), identify=ident)
        self.assertEqual(finding["kind"], "NEW_DEVICE")
        self.assertIn("Raspberry Pi Foundation (pihole)", finding["text"])
        netwatch.trust(self.base, finding)
        self.assertEqual(self.base["devices"]["b8-27-eb-11-22-33"]["name"], "pihole")

    def test_private_mac_rotation_with_same_name_is_silent_kind(self):
        ident = lambda mac, ip: {"vendor": None, "name": "Galaxy-S23", "private": True}  # noqa: E731
        first = {**netwatch.parse_arp(ARP_PT), "da-00-00-00-00-01": "192.168.0.40"}
        (new,) = netwatch.diff(self.base, snap(arp=first), identify=ident)
        self.assertEqual(new["kind"], "NEW_DEVICE")
        self.assertIn("fixe o MAC", new["text"])
        netwatch.trust(self.base, new)
        rotated = {**netwatch.parse_arp(ARP_PT), "6a-00-00-00-00-02": "192.168.0.41"}  # outro IP, mesmo nome
        (rot,) = netwatch.diff(self.base, snap(arp=rotated), identify=ident)
        self.assertEqual((rot["kind"], rot["old_mac"]), ("MAC_ROTATED", "da-00-00-00-00-01"))
        netwatch.trust(self.base, rot)
        self.assertNotIn("da-00-00-00-00-01", self.base["devices"])
        self.assertEqual(netwatch.diff(self.base, snap(arp=rotated), identify=ident), [])

    def test_private_without_name_matches_by_ip_only(self):
        first = {**netwatch.parse_arp(ARP_PT), "da-00-00-00-00-01": "192.168.0.40"}
        netwatch.trust(self.base, netwatch.diff(self.base, snap(arp=first))[0])
        same_ip = {**netwatch.parse_arp(ARP_PT), "6a-00-00-00-00-02": "192.168.0.40"}
        self.assertEqual([f["kind"] for f in netwatch.diff(self.base, snap(arp=same_ip))], ["MAC_ROTATED"])
        other_ip = {**netwatch.parse_arp(ARP_PT), "6a-00-00-00-00-03": "192.168.0.99"}
        self.assertEqual([f["kind"] for f in netwatch.diff(self.base, snap(arp=other_ip))], ["NEW_DEVICE"])

    def test_fixed_mac_never_counts_as_rotation(self):
        first = {**netwatch.parse_arp(ARP_PT), "da-00-00-00-00-01": "192.168.0.40"}
        netwatch.trust(self.base, netwatch.diff(self.base, snap(arp=first))[0])
        fixed = {**netwatch.parse_arp(ARP_PT), "00-11-22-33-44-55": "192.168.0.40"}  # MAC de fábrica
        self.assertEqual([f["kind"] for f in netwatch.diff(self.base, snap(arp=fixed))], ["NEW_DEVICE"])

    def test_gateway_change_shows_vendors(self):
        table = {"00-0c-29-66-66-66": "192.168.0.1", "3c-22-fb-aa-bb-cc": "192.168.0.23"}
        gw = next(f for f in netwatch.diff(self.base, snap(arp=table)) if f["kind"] == "GATEWAY_CHANGED")
        self.assertIn("→", gw["text"])
        self.assertIn("vendor", gw)

    def test_parse_nbtstat(self):
        out = """
    Tabela de nomes NetBIOS de máquinas remotas

       Nome               Tipo         Status
    ---------------------------------------------
    DESKTOP-ABC    <00>  ÚNICO       Registrado
    WORKGROUP      <00>  GRUPO       Registrado
"""
        self.assertEqual(netwatch.parse_nbtstat(out), "DESKTOP-ABC")
        self.assertEqual(netwatch.parse_nbtstat("    NOTE-1 <00>  UNIQUE  Registered"), "NOTE-1")
        self.assertEqual(netwatch.parse_nbtstat("Host não encontrado."), "")

    def test_resolve_name_falls_back_and_never_raises(self):
        def boom(ip):
            raise OSError("sem DNS")
        self.assertEqual(netwatch.resolve_name("1.2.3.4", rdns=lambda ip: "", nbtstat=lambda ip: "PC-SALA"), "PC-SALA")
        self.assertEqual(netwatch.resolve_name("1.2.3.4", rdns=boom, nbtstat=boom), "")
        self.assertEqual(netwatch.resolve_name("1.2.3.4", rdns=lambda ip: "tv", nbtstat=boom), "tv")

    def test_identify_device_caches_name_per_mac(self):
        calls = []
        netwatch._name_cache.pop("b8-27-eb-99-99-99", None)
        resolver = lambda ip: calls.append(ip) or "pi"  # noqa: E731
        for _ in range(2):
            info = netwatch.identify_device("b8-27-eb-99-99-99", "192.168.0.9", resolver=resolver)
        self.assertEqual(calls, ["192.168.0.9"])
        self.assertEqual(info["name"], "pi")
        self.assertFalse(info["private"])

    def test_watch_passes_identify_to_diff(self):
        store = {"base": netwatch.new_baseline(snap(), NOW - timedelta(hours=1))}
        table = {**netwatch.parse_arp(ARP_PT), "b8-27-eb-11-22-33": "192.168.0.50"}
        got = []
        watch = netwatch.NetworkWatch(lambda f: got.append(f) or True, lambda: store["base"],
                                      lambda b: store.update(base=b),
                                      snapshot_fn=lambda with_arp: snap(arp=table), clock=lambda: NOW,
                                      identify=lambda mac, ip: {"vendor": "X", "name": "sala", "private": False})
        watch.check_once()
        self.assertIn("X (sala)", got[0]["text"])

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
