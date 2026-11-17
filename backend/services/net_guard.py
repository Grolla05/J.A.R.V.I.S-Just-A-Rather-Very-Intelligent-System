"""Guarda de rede: decide o que fazer com cada achado do `core.netwatch`.

- Processo novo (porta exposta ou falando com a internet): o modelo julga
  (`prompts/judge_connection.md`, cache de 1 h). "SEGURO" entra na linha de base em
  silêncio; "SUSPEITO" vira alerta com pedido de confirmação para **encerrar o
  processo** (ConfirmScreen; "Manter" = passa a ser conhecido). Sem resposta do
  modelo nada é decidido — o achado volta na próxima rodada.
- Aparelho novo na rede e troca do MAC do roteador: sempre avisam (sem ação automática).
- Tudo passa pelo filtro de interrupções; troca de gateway é prioridade crítica.

Ações ficam sempre atrás de confirmação do usuário. Encerrar confere nome e hora
de criação do PID (não mata um PID reciclado). Bloqueio por firewall (`block_ip`)
só roda com o JARVIS elevado; sem isso devolve o comando para rodar como admin.
"""
import ipaddress
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

from core import netwatch, pending, processes
from core.database import db
from core.logger import log
from core.prompts import load_prompt

BASELINE_KEY = "net_baseline"
SAFE, SUSPECT = "SEGURO", "SUSPEITO"
JUDGE_TTL_S = 3600
CONFIRM_TIMEOUT_S = 30
RECENT_MAX = 20
RULE_PREFIX = "JARVIS bloqueio"
_PROCESS_KINDS = (netwatch.NEW_LISTENER, netwatch.NEW_TALKER)

_judge_cache = {}                     # processo -> (veredito, expira)
_recent = deque(maxlen=RECENT_MAX)    # achados alertados: {'time', 'finding'}
_last = {"snapshot": None}
_lock = threading.Lock()


# ---------------------------------------------------------------- linha de base
def load_baseline():
    data = db.get_config(BASELINE_KEY)
    return data if isinstance(data, dict) and data else None


def save_baseline(baseline):
    db.save_config(BASELINE_KEY, baseline)


def remember_snapshot(snap):
    """Guarda a última foto com tabela ARP para o /status (sem varrer de novo)."""
    previous = _last["snapshot"] or {}
    if snap.get("devices") is None:  # rodada sem ARP: mantém os aparelhos já vistos
        snap = {**snap, "devices": previous.get("devices"), "gateway": previous.get("gateway")}
    _last["snapshot"] = snap


def trust(finding):
    with _lock:
        baseline = load_baseline() or {}
        save_baseline(netwatch.trust(baseline, finding))


# ---------------------------------------------------------------- julgamento
def judge(finding, query=None, clock=time.time):
    """SAFE | SUSPECT | None (modelo não respondeu). Só para achados de processo."""
    name = finding["proc"]
    cached = _judge_cache.get(name.lower())
    if cached and clock() < cached[1]:
        return cached[0]
    what = (f"abriu a porta {finding['port']} para a rede" if finding["kind"] == netwatch.NEW_LISTENER
            else f"conectou-se ao IP público {finding['ip']} na porta {finding['port']}")
    try:
        if query is None:
            from core.llm import query_ollama as query
        answer = query([{"role": "user", "content": load_prompt("judge_connection.md", process=name, action=what)}],
                       temperature=0)
    except Exception as e:
        log.debug(f"[REDE] Juiz indisponível: {e}")
        return None
    text = (answer or "").strip().upper()
    if not text:
        return None
    verdict = SAFE if text.startswith(SAFE) or (SAFE in text and SUSPECT not in text) else SUSPECT
    _judge_cache[name.lower()] = (verdict, clock() + JUDGE_TTL_S)
    return verdict


# --------------------------------------------------------------------- ações
def kill_process(pid, name, created):
    """Encerra o processo se ainda for o mesmo (nome e hora de criação). Devolve a fala."""
    result = processes.terminate_if_same(pid, name, created)
    if result == "ok":
        log.info(f"[REDE] Processo encerrado a pedido: {name} (PID {pid}).")
        return f"{name} encerrado, Senhor."
    if result == "changed":
        return f"O processo {name} já não é o mesmo (PID {pid} foi reaproveitado). Não encerrei nada, Senhor."
    if result == "protected":
        return f"{name} é um processo do sistema; não o encerro, Senhor."
    return f"Não consegui encerrar {name}, Senhor: ele já fechou ou exige privilégio de administrador."


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def block_command(ip):
    return ["netsh", "advfirewall", "firewall", "add", "rule", f"name={RULE_PREFIX} {ip}",
            "dir=out", "action=block", f"remoteip={ip}"]


def block_ip(ip, admin=is_admin, run=subprocess.run):
    """Regra de saída no Firewall do Windows para um IP público. Devolve a fala.
    Só é chamado depois da confirmação do usuário (/rede bloquear <ip>)."""
    ip = (ip or "").strip()
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return f"`{ip}` não é um endereço IP válido, Senhor."
    if not addr.is_global:
        return f"{ip} é um endereço local ou reservado. Não bloqueio a sua própria rede, Senhor."
    command = block_command(str(addr))
    if not admin():
        shown = " ".join(f'"{part}"' if " " in part else part for part in command)
        return ("O Firewall do Windows exige administrador e eu não estou elevado, Senhor. "
                f"Rode num terminal como administrador:\n\n```\n{shown}\n```")
    try:
        result = run(command, capture_output=True, text=True, errors="ignore", timeout=10,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        log.warning(f"[REDE] Bloqueio de {ip} falhou: {e}")
        return f"Não consegui criar a regra no firewall, Senhor: `{e}`"
    if result.returncode != 0:
        return f"O firewall recusou a regra para {ip}, Senhor: {(result.stdout or '').strip()[:160]}"
    log.info(f"[REDE] Regra de bloqueio criada para {ip}.")
    return f"Saída para {ip} bloqueada no Firewall do Windows (regra \"{RULE_PREFIX} {ip}\"), Senhor."


# ------------------------------------------------------------------ tratamento
def _announce(text):
    from core.alerts import _announce as announce
    announce(text)


def handle(finding, judge_fn=judge, announce=_announce, clock=time.time):
    """Chamado pelo NetworkWatch (thread dele). True = tratado; False = tente depois."""
    from services import notify_filter
    is_process = finding["kind"] in _PROCESS_KINDS
    if is_process:
        verdict = judge_fn(finding)
        if verdict is None:
            return False
        if verdict == SAFE:
            trust(finding)
            log.info(f"[REDE] {finding['proc']} julgado seguro; incorporado à linha de base.")
            return True
        if pending.active(clock):
            return False  # já há uma confirmação aberta: este achado espera a vez

    _recent.appendleft({"time": datetime.now().strftime("%d/%m %H:%M"), "finding": finding})
    prio = notify_filter.CRITICAL if finding["kind"] == netwatch.GATEWAY_CHANGED else notify_filter.HIGH
    if notify_filter.decide(prio, notify_filter.context()) == notify_filter.DEFER:
        from services.focus import remember_alert
        remember_alert(f"Rede: {finding['text']}")
        return True

    if is_process:
        question = f"Alerta de rede: {finding['text']} Não reconheço esse processo. Deseja que eu o encerre?"
        armed = pending.arm("NET_KILL_PROCESS", question,
                            lambda f=finding: kill_process(f["pid"], f["proc"], f["created"]),
                            target=finding["proc"], on_decline=lambda f=finding: _keep(f),
                            timeout_s=CONFIRM_TIMEOUT_S, clock=clock)
        if armed is None:
            _recent.popleft()
            return False  # outra confirmação abriu no meio do caminho: tenta na próxima rodada
        announce(question)
    else:
        hint = (" `/rede confiar 1` marca como conhecido." if finding["kind"] == netwatch.NEW_DEVICE
                else " Se o senhor trocou o roteador, `/rede confiar 1`; senão, desconfie da rede.")
        announce(f"Alerta de rede: {finding['text']}{hint}")
    return True


def _keep(finding):
    trust(finding)
    return f"Mantido, Senhor. {finding['proc']} passa a ser conhecido na rede."


# --------------------------------------------------------------------- telas
def recent():
    return list(_recent)


def _recent_lines():
    return [f"{i}. `{item['time']}` {item['finding']['text']}" for i, item in enumerate(_recent, 1)]


def trust_text(index):
    """/rede confiar <n> — número da lista de achados."""
    items = list(_recent)
    if not 1 <= index <= len(items):
        return f"Não há achado {index}, Senhor. `/rede` lista os números."
    finding = items[index - 1]["finding"]
    trust(finding)
    del _recent[index - 1]
    return f"Anotado, Senhor: passa a ser conhecido — {finding['text']}"


def reset_text():
    """/rede reset — apaga a linha de base; a próxima rodada reaprende a rede."""
    with _lock:
        db.save_config(BASELINE_KEY, {})
    _recent.clear()
    _judge_cache.clear()
    return ("Linha de base da rede apagada, Senhor. Reaprendo nos próximos "
            f"{netwatch.LEARN_MINUTES} minutos — nesse tempo nada vira alerta.")


def _ip_key(ip):
    """Ordena IPs numericamente; o que não for IPv4 válido vai para o fim, sem quebrar a lista."""
    try:
        return (0, int(ipaddress.ip_address(ip)))
    except ValueError:
        return (1, str(ip))


def scan_text(snapshot_fn=netwatch.snapshot, short=False):
    """Varredura agora (/rede e skill NETWORK_SCAN). `short` = fala curta para a voz."""
    snap = snapshot_fn(with_arp=True)
    remember_snapshot(snap)
    baseline = load_baseline() or {}
    findings = netwatch.diff(baseline, snap) if baseline else []
    listeners, talkers = snap["listeners"], snap["talkers"]
    devices = snap.get("devices") or {}
    if short:
        parts = [f"{len(devices)} aparelhos na rede" if devices else "não consegui ler os aparelhos da rede",
                 f"{len(listeners)} portas expostas nesta máquina", f"{len(talkers)} programas falando com a internet"]
        news = (f"{len(findings)} novidades desde a linha de base: " + " ".join(f["text"] for f in findings[:3])
                if findings else "nada de novo desde a linha de base")
        return f"Varredura concluída, Senhor: {', '.join(parts)}. {news[0].upper() + news[1:]}."

    lines = ["**Perímetro de rede**", ""]
    gateway = snap.get("gateway")
    if gateway:
        lines.append(f"- **Roteador:** {gateway['ip']} · `{gateway['mac']}`")
    lines.append(f"- **Aparelhos na rede:** {len(devices)}" if devices else "- **Aparelhos na rede:** tabela ARP indisponível")
    for mac, ip in sorted(devices.items(), key=lambda kv: _ip_key(kv[1]))[:15]:
        known = "" if not baseline or mac in baseline.get("devices", {}) else " · **novo**"
        lines.append(f"  - {ip} · `{mac}`{known}")
    lines.append(f"- **Portas expostas nesta máquina:** {len(listeners)}")
    for item in sorted(listeners.values(), key=lambda i: i["port"])[:15]:
        lines.append(f"  - {item['port']} · {item['proc']}")
    lines.append(f"- **Programas falando com a internet:** {len(talkers)}")
    top = sorted(talkers.values(), key=lambda i: -i["count"])[:10]
    if top:
        lines.append("  - " + ", ".join(f"{i['proc']} ({i['count']})" for i in top))
    lines.append("")
    if not baseline:
        lines.append("_Ainda sem linha de base: ligue o **Vigia de rede** no `/config` → ROTINAS._")
    elif netwatch.learning(baseline):
        lines.append("_Aprendendo a rede: por alguns minutos nada vira alerta._")
    elif findings:
        lines += ["**Fora da linha de base agora:**", ""] + [f"- {f['text']}" for f in findings[:10]]
    else:
        lines.append("Nada fora da linha de base, Senhor.")
    if _recent:
        lines += ["", "**Últimos alertas** (`/rede confiar <n>` marca como conhecido):", ""] + _recent_lines()
    return "\n".join(lines)


def perimeter_text():
    """Bloco PERÍMETRO do /status: usa a última foto do vigia (não varre de novo)."""
    snap = _last["snapshot"]
    if not snap:
        return "vigia desligado ou aguardando"
    devices = snap.get("devices")
    lines = [f"portas expostas  {len(snap['listeners'])}",
             f"na internet      {len(snap['talkers'])} programas",
             f"aparelhos na LAN {len(devices) if devices else '—'}",
             f"alertas          {len(_recent)}"]
    if _recent:
        lines.append(_recent[0]["finding"]["text"][:60])
    return "\n".join(lines)
