# 🖥️ SystemInfo.py (Monitoramento e Telemetria)

O arquivo `SystemInfo.py` abriga a classe `SystemInfo`, responsável pela **observabilidade de hardware em tempo real** e pela senciência da máquina. Através da biblioteca `psutil` (e blindagem via `GPUtil`), ele traduz números estáticos e percentuais de silício bruto em dor, tédio e humor, permitindo que a IA do J.A.R.V.I.S entenda perfeitamente o corpo cibernético que habita.

## 🎯 Responsabilidades Principais

1. **Vigilância Proativa (`start_proactive_monitor`)**: Não espera o usuário perguntar. Sobe uma *Daemon Thread* que checa o corpo da máquina a cada X segundos (intervalo passado por quem chama: a TUI usa o `TELEMETRY_INTERVAL` de 3 s para a linha de status). Se algo estiver sangrando (bateria < 15%, CPU > 90%), o JARVIS interromperá e avisará sozinho.
2. **Sinal de estado crítico**: Além de falar, o monitor envia sinais silenciosos via `brain_callback("CRITICAL_START", is_status_signal=True)` (e `CRITICAL_END`) para a TUI. É isso que pinta a conversa de vermelho (classe `-critical`) e mostra os motivos (`critical_reasons`) no topo quando a RAM enche ou o disco lota. O alerta falado ainda passa pelo filtro de interrupções (`services/notify_filter.py`).
3. **Sensores de Velocidade (Disco e Rede)**: Utiliza tracking matemático temporal baseado em *timestamps* comparativos (Delta de tempo) para descobrir a banda exata instantânea (em Mbps) da placa de rede e a carga de gravação do disco rígido.
4. **Contextualização Semântica de Stark (`analyze_semantic_state`)**: A alma do módulo. Ele não injeta no cérebro "CPU: 95%". Ele traduz matematicamente para: `"STATUS CPU: CRÍTICO (Processador em regime de esforço máximo. Risco de thermal throttling.)"`, forçando a IA a agir de acordo no LLM.

---

## ⚙️ Arquitetura e Engenharia Interna

### 1. Prevenção de Race Conditions (CPU Caching)

A biblioteca `psutil.cpu_percent()` tem uma falha arquitetural: ela precisa de um delta de tempo para calcular a CPU. Se a TUI (telemetria) e o backend (contexto do chat) chamarem essa função juntos, um deles receberá "0.0%".
Para consertar isso, a classe instiga a thread isolada `_start_cpu_sampler()`. Essa thread passa a vida num *while loop* tirando a foto da CPU e salvando na variável `self._cpu_cache`. O resto inteiro do sistema consome sempre desse cache, nunca gerando fila ou erro 0%.

### 2. O Juiz de Processos (`get_top_processes`)

Quando a CPU ultrapassa `cpu_max` (90%), o sistema quer fofocar quem é o responsável. Ele varre os PIDs do Windows, exclui as métricas vazias do psutil (ZombieProcess, AccessDenied), pula explicitamente o "System Idle Process" (Processo Ocioso que engana scripts normais dizendo usar 99% de CPU), e devolve um array limpo para a IA delatar (Ex: *Top 5: chrome.exe, code.exe*).

### 3. Blindagem Dinâmica de GPU e Discos

- **GPU (`GPUtil`)**: Envelopado em um rígido bloco `try...except` na importação. Se o usuário rodar num notebook básico da Intel e a biblioteca não encontrar hardware da Nvidia, a flag global `HAS_GPU_LIB` assume `False` e o sistema degrada graciosamente retornando dados em branco, não crasheando o JARVIS.
- **Discos (`psutil.disk_partitions`)**: Itera por todas as unidades montadas ativamente. Ele intencionalmente ignora drives marcados como `'cdrom'` ou discos sem sistema de arquivos vazio (como partições encriptadas fechadas).

### 4. Cooldown e Anti-Spam de Hardware

Foi idealizado um sistema de *Debounce* extremamente agressivo no dicionário `self.alert_state` em conjunto com a constante `REMINDER_COOLDOWN = 120`.
Se a GPU do usuário ferver acima de 75 graus (`gpu_temp_max`), o JARVIS notifica em voz alta e trava o *Timestamp*. Durante os próximos 2 minutos literais de relógio, ele se silenciará sobre a GPU. Isso garante que o usuário consiga jogar um jogo pesado sem que o assistente avise da temperatura de 3 em 3 segundos sem parar.

### 5. O Diagnóstico Marvel Completo (`get_realtime_context`)

Esta é a função mestra exportada ao Cérebro na hora do chat. Ela compila:

- Status Dinâmico de Reator Arc/Economia Vital (Bateria).
- Verificação profunda de Pacotes Perdidos ou Instabilidade (`dropin`, `dropout`) na rede.
- Os TOP 3 Apps drenando a máquina naquele milissegundo.
- O bloco estático de hardware advindo de `db.get_system_specs()`.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Ajuste Fino de Limiares (Thresholds)**: O J.A.R.V.I.S vem de fábrica calibrado para PC's Gamer High-End (`ram_max: 90.0, disk_min_gb_critical: 10.0`). Se você for realizar testes massivos em uma máquina fraca (Ex: Raspberry Pi 5), a primeira coisa a fazer é vir no construtor `__init__` e alterar esses *thresholds* para não escutar falsos alertas proativos.
- **Resiliência do psutil (`try/except`)**: Como o Windows é volátil, processos fecham e abrem em microssegundos. Nunca use `p.info['name']` puro sem um belo `except (psutil.NoSuchProcess, psutil.AccessDenied)` ao redor. Se o processo morrer um nano-segundo antes de você lê-lo, a ausência de except matará o loop de CPU instantaneamente.
- **Modificações Visuais de Interface**: A chamada `brain_callback(status_code, is_proactive=True, is_status_signal=True)` possui a crucial flag `is_status_signal`. Essa flag impede que a string "CRITICAL_START" vaze da ponte visual e vá parar no sintetizador de voz (TTS) do Jarvis (fazendo ele pronunciar erroneamente "Critical Start" em voz alta). Nunca a remova nas atualizações de interface gráfica.
