"""Vigia de rede: o que mudou nesta máquina e na rede local desde a linha de base.

Não é um IDS: é detecção por diferença. `snapshot()` fotografa
- portas TCP em escuta **expostas** (fora do loopback) — `processo:porta`;
- processos com conexão estabelecida a IP público — por nome de processo;
- aparelhos na rede local (tabela ARP: IP → MAC) e o MAC do gateway.

`diff(baseline, snap)` devolve os achados (`NEW_LISTENER`, `NEW_TALKER`,
`NEW_DEVICE`, `GATEWAY_CHANGED`). A primeira foto e os `LEARN_MINUTES` seguintes
só aprendem: nada vira alerta. `NetworkWatch` roda isso numa thread daemon e
entrega cada achado novo a `on_finding` (services/net_guard decide se alerta).

Coleta só leitura (psutil + `arp -a` + `route print`), sem privilégio de
administrador. Fontes injetáveis: os testes não tocam na rede.
"""
import ipaddress
import re
import subprocess
import threading
from datetime import datetime, timedelta

from core.logger import log

NEW_LISTENER, NEW_TALKER, NEW_DEVICE, GATEWAY_CHANGED = "NEW_LISTENER", "NEW_TALKER", "NEW_DEVICE", "GATEWAY_CHANGED"
INTERVAL_S = 60
ARP_EVERY = 5         # a tabela ARP é lida a cada N rodadas
LEARN_MINUTES = 10    # depois da 1ª foto, tudo que aparecer nesse tempo entra na base em silêncio
CMD_TIMEOUT_S = 6
_WILDCARD = ("0.0.0.0", "::", "")

_ARP_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-f]{2}(?:[-:][0-9a-f]{2}){5})\b", re.I | re.M)
_ROUTE_RE = re.compile(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d{1,3}(?:\.\d{1,3}){3})\s", re.M)


# ------------------------------------------------------------------- coleta
def is_public(ip):
    """IP roteável na internet (fora de LAN, loopback, link-local, multicast)."""
    try:
        addr = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    # is_global sozinho aceita multicast (224.0.0.0/4)
    return addr.is_global and not (addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def _run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, errors="ignore", timeout=CMD_TIMEOUT_S,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return result.stdout or ""
    except Exception as e:
        log.debug(f"[REDE] '{args[0]}' falhou: {e}")
        return ""


def parse_arp(output):
    """Saída do `arp -a` → {mac: ip} só de aparelhos (sem broadcast/multicast)."""
    devices = {}
    for ip, mac in _ARP_RE.findall(output or ""):
        mac = mac.lower().replace(":", "-")
        first = int(mac[:2], 16)
        if mac == "ff-ff-ff-ff-ff-ff" or first & 1:  # bit de grupo: broadcast/multicast
            continue
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if addr.is_multicast or addr.is_loopback or ip.endswith(".255"):
            continue
        devices[mac] = ip
    return devices


def parse_gateway(output):
    """Saída do `route print -4` → IP do gateway padrão ('' se não achou)."""
    match = _ROUTE_RE.search(output or "")
    return match.group(1) if match else ""


def _arp_table():
    return parse_arp(_run(["arp", "-a"]))


def _gateway_ip():
    return parse_gateway(_run(["route", "print", "-4", "0.0.0.0"]))


def _connections():
    import psutil
    return psutil.net_connections(kind="inet")


def _proc_info(pid):
    """(nome, hora de criação, executável) do processo; ('?', 0.0, '') se sumiu ou é protegido.
    O executável sai '' quando o Windows nega acesso (processo de outro usuário/elevado)."""
    try:
        import psutil
        proc = psutil.Process(pid)
        name, created = proc.name(), float(proc.create_time())
    except Exception:
        return "?", 0.0, ""
    try:
        exe = proc.exe() or ""
    except Exception:
        exe = ""
    return name, created, exe


def _addr(value):
    """(ip, porta) de um laddr/raddr do psutil (namedtuple, tupla ou vazio)."""
    if not value:
        return "", 0
    ip = getattr(value, "ip", None)
    if ip is None:
        ip, port = (list(value) + ["", 0])[:2]
        return str(ip), int(port or 0)
    return str(ip), int(getattr(value, "port", 0) or 0)


def snapshot(connections=_connections, proc_info=_proc_info, arp=_arp_table, gateway=_gateway_ip, with_arp=True):
    """Foto da rede agora:
    {'listeners': {chave: {...}}, 'talkers': {processo: {...}}, 'devices': {mac: ip} | None, 'gateway': {...} | None}.
    `devices`/`gateway` None = não lidos nesta rodada (ou leitura falhou): o diff os ignora."""
    listeners, talkers, names = {}, {}, {}
    try:
        conns = list(connections())
    except Exception as e:
        log.debug(f"[REDE] Conexões indisponíveis: {e}")
        conns = []
    for conn in conns:
        status = str(getattr(conn, "status", "") or "").upper()
        pid = getattr(conn, "pid", None) or 0
        if status not in ("LISTEN", "ESTABLISHED") or not pid:
            continue
        if pid not in names:
            info = tuple(proc_info(pid)) + ("",)   # proc_info antigo devolvia só (nome, criação)
            names[pid] = info[:3]
        name, created, exe = names[pid]
        if not name or name == "?":
            continue
        lip, lport = _addr(getattr(conn, "laddr", None))
        if status == "LISTEN":
            if lip in _WILDCARD or is_public(lip) or _is_lan(lip):
                key = f"{name}:{lport}"
                listeners.setdefault(key, {"proc": name, "port": lport, "addr": lip or "0.0.0.0",
                                           "pid": pid, "created": created, "exe": exe})
        else:
            rip, rport = _addr(getattr(conn, "raddr", None))
            if is_public(rip):
                entry = talkers.setdefault(name, {"proc": name, "pid": pid, "created": created, "exe": exe,
                                                  "ip": rip, "port": rport, "count": 0})
                entry["count"] += 1
    devices = gw = None
    if with_arp:
        table = arp()
        if table:
            devices = table
            gw_ip = gateway()
            gw_mac = next((mac for mac, ip in table.items() if ip == gw_ip), "") if gw_ip else ""
            gw = {"ip": gw_ip, "mac": gw_mac} if gw_mac else None
    return {"listeners": listeners, "talkers": talkers, "devices": devices, "gateway": gw}


def _is_lan(ip):
    try:
        addr = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    return addr.is_private and not addr.is_loopback and not addr.is_link_local


# ---------------------------------------------------------------- linha de base
def new_baseline(snap, now=None):
    now = now or datetime.now()
    base = {"listeners": [], "talkers": [], "devices": {}, "gateway": {},
            "learn_until": (now + timedelta(minutes=LEARN_MINUTES)).isoformat(timespec="seconds")}
    return absorb(base, snap)


def absorb(baseline, snap):
    """Incorpora a foto inteira à base (aprendizado). Devolve a base."""
    baseline["listeners"] = sorted(set(baseline.get("listeners", [])) | set(snap["listeners"]))
    baseline["talkers"] = sorted(set(baseline.get("talkers", [])) | set(snap["talkers"]))
    if snap.get("devices"):
        baseline.setdefault("devices", {}).update(snap["devices"])
    if snap.get("gateway") and not baseline.get("gateway"):
        baseline["gateway"] = dict(snap["gateway"])
    return baseline


def learning(baseline, now=None):
    try:
        return (now or datetime.now()) < datetime.fromisoformat(baseline.get("learn_until", ""))
    except (TypeError, ValueError):
        return False


def diff(baseline, snap):
    """Achados: o que está na foto e não está na base. Cada achado é um dict com
    'kind', 'key' (única), 'text' (frase para o usuário) e os dados do alvo."""
    findings = []
    known_listeners, known_talkers = set(baseline.get("listeners", [])), set(baseline.get("talkers", []))
    for key, item in snap["listeners"].items():
        if key not in known_listeners:
            where = "em todas as interfaces" if item["addr"] in _WILDCARD else f"em {item['addr']}"
            findings.append({"kind": NEW_LISTENER, "key": f"listener:{key}", **item,
                             "text": f"{item['proc']} abriu a porta {item['port']} {where} — acessível pela rede."})
    for name, item in snap["talkers"].items():
        if name not in known_talkers:
            findings.append({"kind": NEW_TALKER, "key": f"talker:{name}", **item,
                             "text": f"{name} está falando com a internet pela primeira vez "
                                     f"({item['ip']}:{item['port']})."})
    devices = snap.get("devices")
    if devices:
        known = baseline.get("devices", {})
        for mac, ip in devices.items():
            if mac not in known:
                findings.append({"kind": NEW_DEVICE, "key": f"device:{mac}", "mac": mac, "ip": ip,
                                 "text": f"Aparelho novo na rede: {ip} ({mac})."})
    gateway, known_gw = snap.get("gateway"), baseline.get("gateway") or {}
    if gateway and known_gw.get("mac") and gateway["ip"] == known_gw.get("ip") and gateway["mac"] != known_gw["mac"]:
        findings.append({"kind": GATEWAY_CHANGED, "key": f"gateway:{gateway['mac']}", "ip": gateway["ip"],
                         "mac": gateway["mac"], "old_mac": known_gw["mac"],
                         "text": f"O roteador ({gateway['ip']}) mudou de endereço físico: "
                                 f"{known_gw['mac']} → {gateway['mac']}. Pode ser troca de aparelho — ou alguém "
                                 "se passando por ele (ARP spoofing)."})
    return findings


def trust(baseline, finding):
    """Marca o achado como conhecido. Devolve a base."""
    kind = finding["kind"]
    if kind == NEW_LISTENER:
        baseline["listeners"] = sorted(set(baseline.get("listeners", [])) | {f"{finding['proc']}:{finding['port']}"})
    elif kind == NEW_TALKER:
        baseline["talkers"] = sorted(set(baseline.get("talkers", [])) | {finding["proc"]})
    elif kind == NEW_DEVICE:
        baseline.setdefault("devices", {})[finding["mac"]] = finding["ip"]
    elif kind == GATEWAY_CHANGED:
        baseline["gateway"] = {"ip": finding["ip"], "mac": finding["mac"]}
        baseline.setdefault("devices", {})[finding["mac"]] = finding["ip"]
    return baseline


# -------------------------------------------------------------------- vigia
class NetworkWatch:
    """Thread daemon: foto → diff → `on_finding(achado)`. `on_finding` devolve True
    quando o achado foi tratado (alertado ou incorporado); False = tente de novo
    na próxima rodada (ex.: já havia uma confirmação aberta)."""

    def __init__(self, on_finding, load_baseline, save_baseline, snapshot_fn=snapshot,
                 interval=INTERVAL_S, arp_every=ARP_EVERY, clock=datetime.now, on_snapshot=None):
        self.on_finding = on_finding
        self.load_baseline, self.save_baseline = load_baseline, save_baseline
        self.snapshot_fn = snapshot_fn
        self.interval, self.arp_every = interval, max(1, arp_every)
        self.clock = clock
        self.on_snapshot = on_snapshot
        self._handled = set()  # chaves já tratadas nesta sessão (não repete o alerta)
        self._round = 0
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        with self._lock:
            if self.running:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="jarvis-netwatch", daemon=True)
            self._thread.start()
        log.info("[REDE] Vigia de rede ligado.")

    def stop(self):
        with self._lock:
            self._stop.set()
            thread, self._thread = self._thread, None
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        if thread:
            log.info("[REDE] Vigia de rede desligado.")

    def check_once(self):
        """Uma rodada. Devolve os achados entregues (lista vazia aprendendo ou sem novidade)."""
        snap = self.snapshot_fn(with_arp=self._round % self.arp_every == 0)
        self._round += 1
        if self.on_snapshot:
            try:
                self.on_snapshot(snap)
            except Exception as e:
                log.debug(f"[REDE] on_snapshot falhou: {e}")
        now = self.clock()
        baseline = self.load_baseline()
        if not baseline:
            self.save_baseline(new_baseline(snap, now))
            log.info("[REDE] Linha de base criada; aprendendo a rede nos próximos minutos.")
            return []
        if learning(baseline, now):
            self.save_baseline(absorb(baseline, snap))
            return []
        delivered = []
        for finding in diff(baseline, snap):
            if finding["key"] in self._handled:
                continue
            log.info(f"[REDE] Achado: {finding['kind']} ({finding['key']})")
            try:
                handled = self.on_finding(finding)
            except Exception as e:
                log.warning(f"[REDE] Tratamento do achado falhou: {e}")
                handled = False
            if handled:
                self._handled.add(finding["key"])
                delivered.append(finding)
        return delivered

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as e:
                log.debug(f"[REDE] Erro no vigia: {e}")
            if self._stop.wait(self.interval):
                break
