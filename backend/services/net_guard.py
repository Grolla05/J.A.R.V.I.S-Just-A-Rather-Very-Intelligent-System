"""Guarda de rede: decide o que fazer com cada achado do `core.netwatch`.

- Processo novo (porta exposta ou falando com a internet): o modelo julga
  (`prompts/judge_connection.md`, cache de 1 h). "SEGURO" entra na linha de base em
  silêncio; "SUSPEITO" vira alerta com pedido de confirmação para **encerrar o
  processo** (ConfirmScreen; "Manter" = grava o software em `net_trusted_apps`,
  via `services/net_trust.py`). "PERIGOSO" faz o mesmo, mas antes **bloqueia no
  firewall** (IP público em entrada+saída; porta exposta = entrada do executável)
  quando a pref `net_autoblock` está ligada e o JARVIS está elevado; `/rede
  desbloquear <n>` desfaz. Sem resposta do modelo nada é decidido — o achado
  volta na próxima rodada.
- Software mantido é conferido **antes** do juiz: entra na linha de base em silêncio,
  mesmo depois de `/rede reset` (o reset apaga só a base, nunca a tabela).
- Aparelho novo na rede e troca do MAC do roteador: sempre avisam (sem ação automática).
- Tudo passa pelo filtro de interrupções; troca de gateway é prioridade crítica.

Encerrar fica sempre atrás de confirmação e confere nome e hora de criação do PID
(não mata um PID reciclado). Firewall (`core/firewall.py`) só roda com o JARVIS
elevado; sem isso `/rede bloquear` devolve o comando para rodar como admin. As
regras criadas ficam em `config.net_blocks` (lista do `/rede bloqueios`).
"""
import ipaddress
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

from core import firewall, netwatch, pending, processes
from core.database import db
from core.logger import log
from core.prompts import load_prompt
from services import net_trust

BASELINE_KEY = "net_baseline"
BLOCKS_KEY = "net_blocks"
SAFE, SUSPECT, DANGER = "SEGURO", "SUSPEITO", "PERIGOSO"
JUDGE_TTL_S = 3600
CONFIRM_TIMEOUT_S = 30
RECENT_MAX = 20
RULE_PREFIX = firewall.RULE_PREFIX
_PROCESS_KINDS = (netwatch.NEW_LISTENER, netwatch.NEW_TALKER)

_judge_cache = {}                     # processo -> (veredito, expira)
_recent = deque(maxlen=RECENT_MAX)    # achados alertados: {'time', 'finding'}
_last = {"snapshot": None}
_warned = {"admin": False}            # aviso "sem admin para bloquear" uma vez por sessão
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


def keep_software(finding):
    """Decisão do usuário: o software do achado passa a ser mantido (tabela + linha de base)."""
    trust(finding)
    if finding["kind"] in _PROCESS_KINDS:
        net_trust.keep(finding["proc"], finding.get("exe", ""), finding["kind"])


# ---------------------------------------------------------------- julgamento
def judge(finding, query=None, clock=time.time):
    """SAFE | SUSPECT | DANGER | None (modelo não respondeu). Só para achados de processo."""
    name = finding["proc"]
    cached = _judge_cache.get(name.lower())
    if cached and clock() < cached[1]:
        return cached[0]
    what = (f"abriu a porta {finding['port']} para a rede" if finding["kind"] == netwatch.NEW_LISTENER
            else f"conectou-se ao IP público {finding['ip']} na porta {finding['port']}")
    try:
        if query is None:
            from core.llm import query_ollama as query
        exe = finding.get("exe") or "desconhecido"
        answer = query([{"role": "user", "content": load_prompt("judge_connection.md", process=name, action=what,
                                                                exe=exe)}],
                       temperature=0)
    except Exception as e:
        log.debug(f"[REDE] Juiz indisponível: {e}")
        return None
    text = (answer or "").strip().upper()
    if not text:
        return None
    if text.startswith(DANGER) or (DANGER in text and not text.startswith((SAFE, SUSPECT))):
        verdict = DANGER
    elif text.startswith(SAFE) or (SAFE in text and SUSPECT not in text):
        verdict = SAFE
    else:
        verdict = SUSPECT
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
    return firewall.is_admin()


def block_command(ip):
    """Regra de saída (mantida para quem só quer ver o comando); `block_ip` cria entrada e saída."""
    return firewall.block_ip_commands(ip)[1]


# ------------------------------------------------------------- bloqueios
def load_blocks():
    data = db.get_config(BLOCKS_KEY)
    return data if isinstance(data, list) else []


def _record_block(target, kind, rules, reason, auto):
    with _lock:
        blocks = [b for b in load_blocks() if b.get("target") != target]
        blocks.append({"target": target, "kind": kind, "rules": rules, "reason": reason, "auto": auto,
                       "at": datetime.now().strftime("%d/%m %H:%M")})
        db.save_config(BLOCKS_KEY, blocks)


def block_ip(ip, admin=is_admin, run=subprocess.run, reason="pedido do usuário", auto=False):
    """Regras de entrada e saída no Firewall do Windows para um IP público. Devolve a fala.
    Manual: só depois da confirmação (/rede bloquear <ip>). Automático: veredito PERIGOSO."""
    try:
        ip = firewall.validate_ip(ip)
    except ValueError as e:
        return str(e)
    commands = firewall.block_ip_commands(ip)
    if not admin():
        listed = "\n".join(firewall.shown(c) for c in commands)
        return ("O Firewall do Windows exige administrador e eu não estou elevado, Senhor. "
                "Ligue **Executar como administrador** no `/config` → SISTEMA, ou rode num terminal como "
                f"administrador:\n\n```\n{listed}\n```")
    ok, error = firewall.run_commands(commands, run=run)
    if not ok:
        return f"O firewall recusou a regra para {ip}, Senhor: {error}"
    _record_block(ip, "ip", firewall.ip_rule_names(ip), reason, auto)
    log.info(f"[REDE] Bloqueio de entrada e saída criado para {ip} ({reason}).")
    return f"Entrada e saída para {ip} bloqueadas no Firewall do Windows (regras \"{RULE_PREFIX} {ip}\"), Senhor."


def block_program_inbound(exe, admin=is_admin, run=subprocess.run, reason="", auto=False):
    """Bloqueia a entrada de rede de um executável (processo com porta exposta). Devolve a fala ou None."""
    try:
        command = firewall.block_program_inbound_command(exe)
    except ValueError:
        return None
    if not admin():
        return None
    ok, error = firewall.run_commands([command], run=run)
    if not ok:
        log.warning(f"[REDE] Firewall recusou o bloqueio de {exe}: {error}")
        return None
    _record_block(exe, "program", [firewall.program_rule_name(exe)], reason, auto)
    return f"Entrada de rede de {firewall.program_rule_name(exe).removeprefix(RULE_PREFIX + ' programa ')} bloqueada."


def blocks_text():
    """/rede bloqueios — regras criadas pelo JARVIS."""
    blocks = load_blocks()
    if not blocks:
        return "Nenhum bloqueio do JARVIS no firewall, Senhor."
    lines = ["**Bloqueios no firewall** (`/rede desbloquear <n>`):", ""]
    for i, b in enumerate(blocks, 1):
        what = f"`{b['target']}` (entrada e saída)" if b.get("kind") == "ip" else f"`{b['target']}` (entrada)"
        origin = "automático" if b.get("auto") else "manual"
        lines.append(f"{i}. {what} · {origin} · {b.get('at', '')} · {b.get('reason', '')}")
    return "\n".join(lines)


def unblock(arg, admin=is_admin, run=subprocess.run):
    """/rede desbloquear <n|ip> — apaga as regras do JARVIS daquele alvo. Devolve a fala."""
    arg = (arg or "").strip()
    blocks = load_blocks()
    index = next((i for i, b in enumerate(blocks) if b.get("target") == arg), None)
    if index is None and arg.isdigit() and 1 <= int(arg) <= len(blocks):
        index = int(arg) - 1
    if index is None:
        return f"Não há bloqueio `{arg}`, Senhor. `/rede bloqueios` lista os números."
    block = blocks[index]
    if not admin():
        return "Desbloquear exige administrador e eu não estou elevado, Senhor."
    for name in block.get("rules", []):
        ok, error = firewall.run_commands([firewall.delete_rule_command(name)], run=run)
        if not ok and "No rules match" not in error and "Nenhuma regra" not in error:
            return f"O firewall recusou apagar \"{name}\", Senhor: {error}"
    with _lock:
        db.save_config(BLOCKS_KEY, [b for b in load_blocks() if b.get("target") != block["target"]])
    log.info(f"[REDE] Bloqueio removido: {block['target']}.")
    return f"Bloqueio de `{block['target']}` removido do firewall, Senhor."


def _autoblock(finding, admin, run):
    """Veredito PERIGOSO: bloqueia já (sem esperar o usuário). Devolve a frase do que fez, ou ''."""
    reason = f"automático: {finding['proc']} julgado perigoso"
    if finding["kind"] == netwatch.NEW_TALKER and finding.get("ip"):
        reply = block_ip(finding["ip"], admin=admin, run=run, reason=reason, auto=True)
        return reply if "bloqueadas" in reply else ""
    if finding["kind"] == netwatch.NEW_LISTENER:
        return block_program_inbound(finding.get("exe", ""), admin=admin, run=run, reason=reason, auto=True) or ""
    return ""


def _autoblock_enabled():
    try:
        from services import user_prefs
        return bool(user_prefs.get("net_autoblock"))
    except Exception:
        return False


# ------------------------------------------------------------------ tratamento
def _announce(text):
    from core.alerts import _announce as announce
    announce(text)


def handle(finding, judge_fn=judge, announce=_announce, clock=time.time, admin=is_admin, run=subprocess.run,
           autoblock=_autoblock_enabled):
    """Chamado pelo NetworkWatch (thread dele). True = tratado; False = tente depois."""
    from services import notify_filter
    if finding["kind"] == netwatch.MAC_ROTATED:  # mesmo aparelho, MAC privado novo: só atualiza a base
        trust(finding)
        log.info(f"[REDE] {finding['text']} Incorporado em silêncio.")
        return True
    is_process = finding["kind"] in _PROCESS_KINDS
    if is_process and net_trust.is_trusted(finding["proc"], finding.get("exe", "")):
        trust(finding)
        log.info(f"[REDE] {finding['proc']} já foi mantido pelo usuário; incorporado à linha de base.")
        return True
    verdict = None
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
    prio = _priority(finding, notify_filter)
    if notify_filter.decide(prio, notify_filter.context()) == notify_filter.DEFER:
        from services.focus import remember_alert
        remember_alert(f"Rede: {finding['text']}")
        return True

    if is_process:
        blocked = ""
        if verdict == DANGER:
            if not autoblock():
                pass
            elif admin():
                blocked = _autoblock(finding, admin, run)
            elif not _warned["admin"]:
                _warned["admin"] = True
                blocked = ("Eu bloquearia isso no firewall, mas não estou elevado: ligue **Executar como "
                           "administrador** no `/config` → SISTEMA.")
        if blocked and "bloqueada" in blocked:
            blocked += f" (`/rede desbloquear {len(load_blocks())}` desfaz.)"
        alarm = "Parece malicioso." if verdict == DANGER else "Não reconheço esse processo."
        question = (f"Alerta de rede: {finding['text']} {alarm} {blocked + ' ' if blocked else ''}"
                    "Deseja que eu o encerre?")
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


def _priority(finding, notify_filter):
    """Roteador trocado = crítico; celular com MAC privado = normal (vai e volta); resto = alto."""
    if finding["kind"] == netwatch.GATEWAY_CHANGED:
        return notify_filter.CRITICAL
    if finding["kind"] == netwatch.NEW_DEVICE and (finding.get("device") or {}).get("private"):
        return notify_filter.NORMAL
    return notify_filter.HIGH


def _keep(finding):
    keep_software(finding)
    return f"Mantido, Senhor. {finding['proc']} passa a ser conhecido na rede e fica na lista de mantidos."


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
    keep_software(finding)
    del _recent[index - 1]
    return f"Anotado, Senhor: passa a ser conhecido — {finding['text']}"


def reset_text():
    """/rede reset — apaga a linha de base; a próxima rodada reaprende a rede."""
    with _lock:
        db.save_config(BASELINE_KEY, {})
    _recent.clear()
    _judge_cache.clear()
    return ("Linha de base da rede apagada, Senhor. Reaprendo nos próximos "
            f"{netwatch.LEARN_MINUTES} minutos — nesse tempo nada vira alerta. "
            "Os softwares mantidos foram preservados (`/rede mantidos`).")


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
    known_devices = baseline.get("devices", {}) if baseline else {}
    for mac, ip in sorted(devices.items(), key=lambda kv: _ip_key(kv[1]))[:15]:
        known = "" if not baseline or mac in known_devices else " · **novo**"
        entry = known_devices.get(mac)
        label = netwatch.describe(entry if isinstance(entry, dict) else netwatch.device_entry(mac, ip), mac)
        lines.append(f"  - {ip} · {label} · `{mac}`{known}")
    lines.append(f"- **Portas expostas nesta máquina:** {len(listeners)}")
    for item in sorted(listeners.values(), key=lambda i: i["port"])[:15]:
        lines.append(f"  - {item['port']} · {item['proc']}")
    lines.append(f"- **Programas falando com a internet:** {len(talkers)}")
    top = sorted(talkers.values(), key=lambda i: -i["count"])[:10]
    if top:
        lines.append("  - " + ", ".join(f"{i['proc']} ({i['count']})" for i in top))
    lines.append(f"- **Softwares mantidos:** {net_trust.count()} (`/rede mantidos`)")
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
             f"alertas          {len(_recent)}",
             f"firewall         {'admin ✓' if is_admin() else 'sem admin'} · {len(load_blocks())} bloqueios"]
    if _recent:
        lines.append(_recent[0]["finding"]["text"][:60])
    return "\n".join(lines)
