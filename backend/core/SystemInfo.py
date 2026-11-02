import platform
import threading
import time
from datetime import datetime, timedelta

import psutil

from .database import db
from .logger import log

# --- BLINDAGEM DE GPU ---
try:
    import GPUtil
    HAS_GPU_LIB = True
except Exception:
    HAS_GPU_LIB = False
# ------------------------

class SystemInfo:
    def __init__(self, brain_callback=None):
        self.os_name = platform.system()
        self.brain_callback = brain_callback
        self.is_monitoring = False
        self.in_critical_state = False # Rastreia se o HUD está vermelho atualmente
        
        # --- CONFIGURAÇÃO DE LIMITES DE HARDWARE ---
        self.thresholds = {
            'cpu_max': 90.0,
            'ram_max': 90.0,
            'gpu_temp_max': 85.0,
            'disk_space_min': 10.0,
            'disk_min_gb_warning': 20.0,
            'disk_min_gb_critical': 10.0,
            'battery_min': 15.0
        }

        # Estado anterior (Debounce)
        self.alert_state = {
            'cpu': False,
            'ram': False,
            'gpu': False,
            'disk': False,
            'battery': 100
        }
        
        # Armazena QUANDO foi o último aviso (Timestamp)
        self.last_alert_time = {
            'cpu': 0,
            'ram': 0,
            'gpu': 0,
            'disk': 0
        }
        
        # Cooldown: Tempo em segundos para repetir o alerta (120s = 2 min)
        self.REMINDER_COOLDOWN = 120

        # CPU cache — um único sampler thread alimenta; todos os leitores consomem daqui
        self._cpu_cache = 0.0
        self._start_cpu_sampler()

        # Inicializa leituras
        self.last_time = time.time()
        
        # Rede e Disco iniciais
        net = psutil.net_io_counters()
        self.last_net_sent = net.bytes_sent
        self.last_net_recv = net.bytes_recv
        
        disk = psutil.disk_io_counters()
        self.last_disk_read = disk.read_bytes if disk else 0
        self.last_disk_write = disk.write_bytes if disk else 0

    def _start_cpu_sampler(self):
        """Único thread que lê psutil.cpu_percent, evitando race condition entre callers."""
        def _sample():
            psutil.cpu_percent(interval=None)  # prime
            while True:
                time.sleep(1)
                self._cpu_cache = psutil.cpu_percent(interval=None)
        threading.Thread(target=_sample, daemon=True).start()

    def _get_size(self, bytes, suffix="B"):
        """Formata bytes para KB, MB, GB de forma legível."""
        factor = 1024
        for unit in ["", "K", "M", "G", "T", "P"]:
            if bytes < factor:
                return f"{bytes:.2f}{unit}{suffix}"
            bytes /= factor
            
    def get_disk_space(self):
        """Retorna uma LISTA com dados de todos os discos físicos montados."""
        disks_data = []
        try:
            # Itera sobre todas as partições (C:, D:, etc.)
            for partition in psutil.disk_partitions(all=False):
                # Filtra CD-ROMs, pendrives vazios ou sistemas de arquivos virtuais
                if 'cdrom' in partition.opts or partition.fstype == '':
                    continue
                
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    free_gb = usage.free / (1024**3)
                    
                    disks_data.append({
                        "mount": partition.mountpoint,              # Ex: "C:\"
                        "total": self._get_size(usage.total),       # Ex: "500GB"
                        "free_gb": round(free_gb, 1),               # Ex: 15.5 (Float para lógica)
                        "percent": usage.percent,                   # % Usado
                        "free_percent": 100 - usage.percent         # % Livre
                    })
                except PermissionError:
                    continue
                    
        except Exception as e:
            log.error(f"Erro ao ler discos: {e}")
            
        return disks_data

    def _check_disk_health_detailed(self):
        """
        Verifica TODOS os discos físicos montados.
        Retorna uma lista de strings de alerta baseada em GBs livres.
        """
        alerts = []
        try:
            # Pega todas as partições (C:, D:, etc)
            partitions = psutil.disk_partitions(all=False)
            for p in partitions:
                # Ignora CD-ROM ou drives vazios/protegidos
                if 'cdrom' in p.opts or p.fstype == '':
                    continue
                    
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    free_gb = usage.free / (1024**3)
                    
                    if free_gb < self.thresholds['disk_min_gb_critical']:
                        alerts.append(f"Disco {p.mountpoint} CRÍTICO ({free_gb:.1f} GB livres)")
                    elif free_gb < self.thresholds['disk_min_gb_warning']:
                        alerts.append(f"Disco {p.mountpoint} com pouco espaço ({free_gb:.1f} GB livres)")
                except PermissionError:
                    continue # Pula discos que o sistema não deixa ler
        except Exception as e:
            log.error(f"Erro ao verificar discos: {e}")
            
        return alerts

    # --- MÉTODOS EXIGIDOS PELO BRAIN.PY (Restaurados) ---
    def get_cpu_usage(self):
        """Retorna apenas a porcentagem simples (float)."""
        return self._cpu_cache

    def get_battery_status(self):
        """Retorna status da bateria formatado."""
        if not hasattr(psutil, "sensors_battery"):
            return {"percent": 100, "plugged": True, "time_left": "Desktop"}

        try:
            battery = psutil.sensors_battery()
            if battery:
                if battery.secsleft == psutil.POWER_TIME_UNLIMITED:
                    time_left = "Carregada"
                elif battery.secsleft == psutil.POWER_TIME_UNKNOWN:
                    time_left = "Calculando..."
                else:
                    time_left = str(timedelta(seconds=battery.secsleft)).split('.')[0]

                return {
                    "percent": round(battery.percent),
                    "plugged": battery.power_plugged,
                    "time_left": time_left
                }
        except Exception:
            pass
        return {"percent": 100, "plugged": True, "time_left": "Desktop"}
    # ----------------------------------------------------

    def get_cpu_detailed(self):
        """Retorna uso, frequência e núcleos."""
        freq = psutil.cpu_freq()
        return {
            "usage": self._cpu_cache,
            "cores_logical": psutil.cpu_count(logical=True),
            "cores_physical": psutil.cpu_count(logical=False),
            "freq_current": f"{freq.current:.0f}Mhz" if freq else "N/A"
        }

    def get_ram_usage(self):
        try:
            ram = psutil.virtual_memory()
            return {
                "percent": ram.percent,
                "used": self._get_size(ram.used),
                "total": self._get_size(ram.total),
                "used_gb": round(ram.used / (1024 ** 3), 2) # Adicionado para compatibilidade
            }
        except:
            return {"percent": 0, "used": "0B", "total": "0B", "used_gb": 0}

    def get_gpu_info(self):
        if not HAS_GPU_LIB:
            return {"name": "N/A", "load": 0, "temp": 0, "memory_used": 0}

        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                return {
                    "name": gpu.name,
                    "load": round(gpu.load * 100, 1),
                    "temp": gpu.temperature,
                    "memory_total": f"{gpu.memoryTotal}MB",
                    "memory_used": f"{gpu.memoryUsed}MB"
                }
        except:
            pass
        return {"name": "Integrada/N/A", "load": 0, "temp": 0}

    def get_network_speed(self):
        current_time = time.time()
        time_delta = current_time - self.last_time
        if time_delta <= 0: time_delta = 1 

        net = psutil.net_io_counters()
        
        sent_per_sec = (net.bytes_sent - self.last_net_sent) / time_delta
        recv_per_sec = (net.bytes_recv - self.last_net_recv) / time_delta
        
        self.last_net_sent = net.bytes_sent
        self.last_net_recv = net.bytes_recv

        return {
            "upload_speed": self._get_size(sent_per_sec) + "/s",
            "download_speed": self._get_size(recv_per_sec) + "/s",
            "total_sent": self._get_size(net.bytes_sent),
            "total_recv": self._get_size(net.bytes_recv)
        }

    def get_disk_io(self):
        current_time = time.time()
        time_delta = current_time - self.last_time
        if time_delta <= 0: time_delta = 1

        try:
            disk = psutil.disk_io_counters()
            if not disk: return {"read": "0B/s", "write": "0B/s"}

            read_per_sec = (disk.read_bytes - self.last_disk_read) / time_delta
            write_per_sec = (disk.write_bytes - self.last_disk_write) / time_delta

            self.last_disk_read = disk.read_bytes
            self.last_disk_write = disk.write_bytes
            
            self.last_time = current_time

            return {
                "read_speed": self._get_size(read_per_sec) + "/s",
                "write_speed": self._get_size(write_per_sec) + "/s"
            }
        except:
             return {"read_speed": "0B/s", "write_speed": "0B/s"}

    def get_ping(self, host="8.8.8.8"):
        """Verifica latência via Ping ICMP (Windows) para o Google DNS."""
        import re
        import subprocess
        try:
            # -n 1: 1 pacote, -w 1000: timeout 1000ms
            cmd = f"ping -n 1 -w 1000 {host}"
            res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            if res.returncode == 0:
                # Busca 'tempo=Xms' ou 'time=Xms' ou 'time<1ms'
                match = re.search(r"(?:tempo|time)[=<]([\d]+)ms", res.stdout, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        except Exception as e:
            log.error(f"Erro no Ping: {e}")
        return None

    def get_system_general(self):
        boot_time_timestamp = psutil.boot_time()
        # Tempo decorrido absoluto livre de descompassos de timezone
        uptime_seconds = max(0, time.time() - boot_time_timestamp)
        uptime = timedelta(seconds=int(uptime_seconds))
        uptime_str = str(uptime)

        bt = datetime.fromtimestamp(boot_time_timestamp)

        return {
            "uptime": uptime_str,
            "processes": len(psutil.pids()),
            "boot_time": bt.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def get_top_processes(self, resource_type, limit=5):
        """
        Retorna uma lista com os TOP 'limit' processos consumidores.
        resource_type: 'cpu' ou 'memory'
        """
        try:
            if resource_type == 'cpu':
                # --- CORREÇÃO PARA O ZERO POR CENTO ---
                # A CPU precisa de um intervalo (delta) para ser medida.
                
                # Coleta todos os processos vivos
                procs = [p for p in psutil.process_iter(['pid', 'name'])]
                
                # Primeira chamada (Inicia o contador interno do psutil, retorna 0.0)
                for p in procs:
                    try:
                        p.cpu_percent()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                
                # Pequena pausa para acumular dados de uso (0.1s é imperceptível para o usuário)
                time.sleep(0.1)
                
                # Segunda chamada (Retorna a média de uso durante a pausa)
                cpu_data = []
                for p in procs:
                    try:
                        # Pega o valor real agora
                        usage = p.cpu_percent()
                        name = p.info['name']
                        
                        # Filtra ruído (0%) e remove o "System Idle Process" (Ocioso) para não confundir o Juiz
                        if usage > 0.0 and name != "System Idle Process":
                            cpu_data.append((name, usage))
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                
                # Ordena pelo maior uso
                top_cpu = sorted(cpu_data, key=lambda x: x[1], reverse=True)[:limit]
                
                # Formata para texto
                return [f"{name} ({val:.1f}%)" for name, val in top_cpu]

            elif resource_type == 'memory':
                # Memória é instantânea, a lógica anterior funciona bem
                def key_func(p):
                    return p.info['memory_percent']
                attrs = ['pid', 'name', 'memory_percent']
                
                processes = sorted(
                    psutil.process_iter(attrs),
                    key=key_func,
                    reverse=True
                )[:limit]

                result = []
                for proc in processes:
                    result.append(f"{proc.info['name']} ({proc.info['memory_percent']:.1f}%)")
                    
                return result
            
            else:
                return []

        except Exception as e:
            log.error(f"Erro ao buscar processos top ({resource_type}): {e}")
            return []
    
    # --- MONITORAMENTO PROATIVO E CONSTANTE ---
    def start_proactive_monitor(self, interval=10):
        """Inicia a thread de vigilância que roda em paralelo."""
        if self.is_monitoring: return
        self.is_monitoring = True
        # daemon=True: a thread morre quando o programa principal fecha
        thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
        thread.start()
        log.info(f"🛡️ Monitoramento de Infraestrutura Iniciado ({interval}s)")

    def _monitor_loop(self, interval):
        """
        Loop de vigilância:
        - Responsabilidade 1 (Rápida): Alternar estado visual do HUD (Vermelho/Normal).
        - Responsabilidade 2 (Lenta): Gerar relatório verbal detalhado respeitando Cooldowns.
        """
        while self.is_monitoring:
            warnings = []
            now = time.time()
            
            try:
                # --- 1. COLETA DE DADOS (Leve) ---
                cpu = self.get_cpu_usage()
                ram = self.get_ram_usage()
                gpu = self.get_gpu_info()
                bat = self.get_battery_status()
                disk = self.get_disk_space()
                
                # --- 2. CHECAGEM DE LIMITES (Booleanos) ---
                is_cpu_high = cpu > self.thresholds['cpu_max']
                is_ram_high = ram['percent'] > self.thresholds['ram_max']
                is_gpu_hot = gpu['temp'] > self.thresholds['gpu_temp_max']
                is_disk_full = False
                if isinstance(disk, list):
                    for d in disk:
                        if d['free_percent'] < self.thresholds['disk_space_min']:
                            is_disk_full = True
                            break
                
                # Bateria crítica: só se não estiver carregando e abaixo do mínimo
                is_battery_crit = (not bat['plugged'] and bat['percent'] <= self.thresholds['battery_min'])
                
                # Estado Geral: Existe ALGUM problema agora?
                current_danger = is_cpu_high or is_ram_high or is_gpu_hot or is_disk_full or is_battery_crit

                # --- 3. LÓGICA VISUAL (HUD RESPONSIVO) ---
                # Detecta mudança de estado: Entrou em perigo OU Saiu do perigo
                if current_danger != self.in_critical_state:
                    self.in_critical_state = current_danger
                    
                    if self.brain_callback:
                        # Envia sinal puro de estado (sem texto para fala)
                        status_code = "CRITICAL_START" if current_danger else "CRITICAL_END"
                        try:
                            # is_status_signal=True garante que o JARVIS não tente "falar" esse código
                            self.brain_callback(status_code, is_proactive=True, is_status_signal=True)
                        except TypeError:
                            # Fallback caso o callback antigo não aceite o parametro is_status_signal
                            # (Segurança para não quebrar se o main.py não estiver atualizado)
                            pass
                        except Exception as e:
                            log.error(f"Erro ao atualizar HUD Visual: {e}")

                # --- 4. LÓGICA VERBAL (MANTENDO SUA LÓGICA ORIGINAL) ---
                # Só entra aqui se houver perigo, economizando processamento
                if current_danger:
                    
                    # CPU Check (Com a sua lógica de Top 5)
                    if is_cpu_high:
                        if (now - self.last_alert_time['cpu'] > self.REMINDER_COOLDOWN):
                            top_list = self.get_top_processes('cpu', limit=5)
                            culprit_txt = f" (Top 5: {', '.join(top_list)})" if top_list else ""
                            warnings.append(f"Processador em {cpu}%{culprit_txt}")
                            self.last_alert_time['cpu'] = now
                    else:
                        # Reseta o timer se o problema sumiu (para avisar logo se voltar)
                        self.alert_state['cpu'] = False 

                    # RAM Check
                    if is_ram_high:
                        if (now - self.last_alert_time['ram'] > self.REMINDER_COOLDOWN):
                            top_list = self.get_top_processes('memory', limit=5)
                            culprit_txt = f" (Consumo: {', '.join(top_list)})" if top_list else ""
                            warnings.append(f"RAM crítica: {ram['percent']}%{culprit_txt}")
                            self.last_alert_time['ram'] = now

                    # GPU Check
                    if is_gpu_hot:
                        if (now - self.last_alert_time['gpu'] > self.REMINDER_COOLDOWN):
                            top_procs = self.get_top_processes('cpu', limit=1)
                            culprit_txt = f" (Top 5: {top_procs[0]})" if top_procs else ""
                            warnings.append(f"GPU superaquecendo a {gpu['temp']}°C{culprit_txt}")
                            self.last_alert_time['gpu'] = now

                    # Disk Check
                    # --- [ATUALIZADO] Disk Check (Multi-Drive em GB) ---
                    # Verifica a cada loop, mas respeita o Cooldown para avisar
                    if (now - self.last_alert_time['disk'] > self.REMINDER_COOLDOWN):
                        disk_alerts = self._check_disk_health_detailed()
                        if disk_alerts:
                            # Adiciona os alertas encontrados à lista geral de warnings
                            warnings.extend(disk_alerts)
                            self.last_alert_time['disk'] = now
                            # Força o estado crítico visual se tiver disco vermelho
                            if any("CRÍTICO" in a for a in disk_alerts):
                                current_danger = True

                    # Battery Check
                    if is_battery_crit:
                        last_bat = self.alert_state['battery'] if isinstance(self.alert_state['battery'], int) else 100
                        if bat['percent'] <= last_bat - 5: # Avisa a cada 5% de queda
                            warnings.append(f"Bateria crítica: {bat['percent']}%")
                            self.alert_state['battery'] = bat['percent']

                    # --- DISPARO DO ALERTA VERBAL ---
                    if warnings and self.brain_callback:
                        alert_msg = ". ".join(warnings)
                        full_context = f"[SISTEMA CRÍTICO] {alert_msg}"
                        try:
                            # is_status_signal=False -> Isso é fala normal
                            self.brain_callback(full_context, is_proactive=True, is_status_signal=False)
                        except TypeError:
                            # Fallback de compatibilidade
                            self.brain_callback(full_context, is_proactive=True)
                        except Exception as e:
                            log.error(f"Erro no envio de alerta verbal: {e}")

            except Exception as e:
                log.error(f"Erro fatal no loop de monitoramento: {e}")
                # Não dá break, apenas loga e tenta na próxima iteração (Resiliência)
            
            time.sleep(interval)

    # --- INTEGRAÇÃO SEMÂNTICA (CÉREBRO DO HARDWARE) ---
    def analyze_semantic_state(self, cpu, ram, gpu, batt, disks, net):
        """Gera uma narrativa de estado (Mood do JARVIS) baseada em TODOS os sensores."""
        states = []
        
        # --- PROCESSAMENTO (O Cérebro) ---
        if cpu < 5:
            states.append("STATUS CPU: OCIOSIDADE PROFUNDA (Potencial de processamento desperdiçado. Tédio detectado.)")
        elif cpu > 90:
            states.append("STATUS CPU: CRÍTICO (Processador em regime de esforço máximo. Risco de thermal throttling.)")
        elif cpu > 60:
            states.append("STATUS CPU: ALTA DEMANDA (Foco total em tarefas computacionais.)")

        # --- MEMÓRIA (A Consciência) ---
        if ram['percent'] > 90:
            states.append("STATUS RAM: SATURAÇÃO IMINENTE (Swap file ativado. O sistema está engasgando.)")
        elif ram['percent'] < 30:
            states.append("STATUS RAM: DISPONIBILIDADE PLENA (Memória livre para grandes compilações.)")

        # --- DISCO (Armazenamento) ---
        if isinstance(disks, list):
            for d in disks:
                free_gb = d.get('free_gb', 100) 
                mount = d.get('mount', '?')
                
                if free_gb < 10:
                    states.append(f"STATUS DISCO ({mount}): CRÍTICO (Apenas {free_gb}GB livres. Falha iminente.)")
                elif free_gb < 20:
                    states.append(f"STATUS DISCO ({mount}): ALERTA (Espaço baixo: {free_gb}GB.)")

        # --- VÍDEO (A Visão) ---
        if gpu.get('temp', 0) > 80:
            states.append(f"STATUS GPU: SUPERAQUECIMENTO ({gpu['temp']}°C). Ventoinhas operando no limite audível.")
        elif gpu.get('load', 0) > 80:
            states.append("STATUS GPU: RENDERIZAÇÃO INTENSA (Processamento gráfico prioritário.)")

        # --- REDE (A Conectividade) ---
        down_speed = net.get('download_speed', '0B/s')
        try:
            if "MB/s" in down_speed:
                val = float(down_speed.replace("MB/s", "").strip())
                if val > 15.0:
                    states.append(f"STATUS REDE: INFLUXO MASSIVO DE DADOS ({down_speed}). Banda larga saturada.")
            elif "GB/s" in down_speed:
                 states.append(f"STATUS REDE: VELOCIDADE DE FIBRA ÓPTICA EXTREMA ({down_speed}).")
        except ValueError:
            pass
            
        # Monitor de Instabilidade (Pacotes perdidos ou Erros)
        net_errors = net.get('errin', 0) + net.get('errout', 0)
        net_drops = net.get('dropin', 0) + net.get('dropout', 0)
        
        if net_errors > 50 or net_drops > 50:
             states.append("STATUS REDE: INSTABILIDADE (Detectados pacotes perdidos ou erros na transmissão. Conexão degradada.)")

        # --- ENERGIA (A Vida) ---
        if not batt['plugged']:
            if batt['percent'] < 15:
                states.append("STATUS ENERGIA: EMERGÊNCIA (Reservas esgotadas. Desligamento iminente.)")
            elif batt['percent'] < 50:
                states.append("STATUS ENERGIA: MODO ECONOMIA (Operando apenas com suporte vital.)")
        else:
            if batt['percent'] == 100:
                states.append("STATUS ENERGIA: POTÊNCIA MÁXIMA (Reator Arc em 100%.)")

        # Se estiver tudo normal
        if not states:
            states.append("STATUS GERAL: NOMINAL (Todos os sistemas operando dentro dos parâmetros ideais de Stark Industries.)")

        return " | ".join(states)

    def get_realtime_context(self):
        """
        Coleta TODOS os dados e aplica a camada de personalidade Stark.
        """
        try:
            # 1. Coleta os dados brutos (Usando métodos da própria classe)
            cpu = self.get_cpu_usage() 
            ram = self.get_ram_usage()
            gpu = self.get_gpu_info()
            batt = self.get_battery_status()
            disks = self.get_disk_space()
            net = self.get_network_speed()
            top_cpu_apps = self.get_top_processes('cpu', limit=3)
            top_apps_str = ", ".join(top_cpu_apps) if top_cpu_apps else "Nenhum destaque"

            # Gera a interpretação rica
            semantic_status = self.analyze_semantic_state(cpu, ram, gpu, batt, disks, net)
            
            if isinstance(disks, list):
                disk_parts = []
                for d in disks:
                    info = f"{d['mount']} {d['free_gb']}GB Livre ({d['free_percent']:.0f}%)"
                    disk_parts.append(info)
                disk_str = " | ".join(disk_parts)
            else:
                disk_str = "Leitura de disco indisponível"

            # Monta o contexto para o LLM
            context_str = (
                f"[DIAGNÓSTICO DE SISTEMA J.A.R.V.I.S.]\n"
                f"{semantic_status}\n"
                f"\n[TELEMETRIA TÉCNICA]\n"
                f"- CPU: {cpu}% (Top Apps: {top_apps_str})\n"
                f"- RAM: {ram['percent']}% ({ram['used_gb']}GB usados)\n"
                f"- GPU: {gpu['name']} ({gpu.get('temp', 0)}°C)\n"
                f"- Rede: ↓{net['download_speed']} | ↑{net['upload_speed']}\n"
                f"- Disco: {disk_str}\n"
                f"- Energia: {batt['percent']}% ({'AC' if batt['plugged'] else 'Bateria'})\n"
            )
            return context_str
            
        except Exception as e:
            log.critical(f"⚠️ Erro ao ler sensores: {e}")
            return "[ERRO: Sensores offline. Impossível ler status do sistema]"

    def get_detailed_hardware_context(self):
        """Busca os dados estáticos do banco e formata para o Prompt."""
        try:
            # Importante: db agora está disponível na classe via self ou import global
            raw_specs = db.get_system_specs() 
            return f"\n[ARQUIVO CONFIDENCIAL DE HARDWARE - NÃO INVENTE DADOS]\n{raw_specs}"
        except Exception as e:
            log.error(f"Erro ao buscar contexto de hardware: {e}")
            return ""