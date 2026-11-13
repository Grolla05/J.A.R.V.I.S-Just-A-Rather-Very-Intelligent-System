# 👂 listen.py (Ouvidos e Transcrição)

O arquivo `listen.py` abriga a classe Singleton `Ear`, construída sobre a biblioteca `SpeechRecognition`. Ele atua como o **Córtex Auditivo** do J.A.R.V.I.S., encarregado não apenas de traduzir som para texto (STT - *Speech-To-Text*), mas de orquestrar a janela de atenção e garantir que a IA não sofra com alucinações sonoras ou ouça a si mesma falando pelas caixas de som da sua casa.

## 🎯 Responsabilidades Principais

0. **Ouvido sob demanda (lazy)**: importar `services.listen` não abre nada. O `Ear` só é criado por `get_ear()` quando a voz é ligada (`/voice`, `Ctrl+T` ou entrada no Copilot); com `state.voice_enabled = False` o microfone fica fechado. No Modo Apresentação o mic também não abre.
1. **Auto-Calibração Acústica**: Quando o `Ear` é criado, ele espera 1 segundo executando `adjust_for_ambient_noise`. Ele ouve o ambiente para definir o chão de ruído (*Noise Floor*). Isso impede que o chiado de um ar-condicionado ou ventilador seja interpretado como alguém tentando falar com o Jarvis.
2. **Sistema Híbrido de Wake Word (Gatilho)**: Enquanto a voz está ligada, o motor ouve via Nuvem (Google STT), porém ele ignora ativamente qualquer frase que não contenha a *Wake Word* ("Jarvis" e suas miscelâneas de transcrições erradas).
3. **Janela de Atenção (Active Mode)**: Após ser ativado com sucesso pelo nome, o `Ear` dispara um *Timer* invisível (`conversation_timeout`, pref "Janela de atenção" no `/config` → MICROFONE, padrão 60 s). Durante esse minuto, o usuário pode metralhar comandos diretos ("apaga a luz", "aumenta o volume") e o Jarvis executará tudo sem exigir que a pessoa fique repetindo o nome dele que nem um robô.
4. **Isolamento de Retroalimentação (Ear Plugging)**: Implementa as funções `ear_pause()` e `ear_resume()`. Isso permite que o módulo `speak.py` "tape os ouvidos" do Jarvis micro-segundos antes de emitir a voz no alto-falante, prevenindo que o Jarvis ouça a própria resposta e tente responder a si mesmo num loop infinito.

---

## ⚙️ Arquitetura e Engenharia Interna

### 1. Parametrização Sensorial Estrita

O construtor injeta duas configurações cruciais na biblioteca:

- `dynamic_energy_threshold = True`: Permite que a calibração de ruído de fundo se ajuste sozinha se o dia ficar mais barulhento repentinamente.
- `pause_threshold = 1.5`: Define que o usuário precisa ficar 1.5 segundos em silêncio absoluto para o sistema declarar que a frase "acabou". Isso impede que o Jarvis corte a pessoa no meio se ela pausar brevemente para respirar ou pensar.

### 2. Regex Robusto de Recuperação Fonética

O Google STT é treinado massivamente em sotaque PT-BR casual, então a palavra "Jarvis" falha terrivelmente na conversão em nuvem. A lista `WAKE_WORDS` (padrão em `core/config.py`, sobrescrita pela variável `WAKE_WORDS` do `.env`) mapeia as alucinações fonéticas do Google (`'jar', 'jair', 'davis', 'gervis', 'jorge', 'jair vis'`).

- A checagem utiliza Padrão Regex Restrito: `re.search(rf"\b{trigger}\b", phrase)`. O `\b` (Word Boundary) garante que a *Wake Word* só é detectada se for uma palavra isolada no meio da frase. Se o script recebesse "Eu fui viajar" e não tivesse Regex, o "jar" da palavra "viajar" ativaria o assistente do nada.

### 3. Preservação de Contexto (Replace Otimizado)

Se o gatilho é encontrado, a classe o remove da frase antes de mandar para o Cérebro: `phrase.replace(trigger_found, "", 1)`.
**Detalhe Crítico**: O `, 1` restringe a deleção para estritamente a *primeira* vez que a *Wake Word* aparece. Sem isso, se você pedisse *"Jarvis, crie uma pasta chamada projeto Jarvis"*, a frase chegaria no cérebro decepada como *"crie uma pasta chamada projeto "*.

### 4. Botão de Pânico (Cancelamento Verbal)

Se o microfone captar você falando com alguém, ou se você se arrepender no meio do comando, a detecção intercepta palavras destrutivas (`'esquece', 'deixa', 'cancelar', 'quieto'`).
Quando essas palavras são flagradas no meio da frase, o `listen.py` não apenas joga o áudio no lixo (`continue`), mas pune duramente o sistema zerando a janela de atenção de 60 segundos com `self.last_interaction_time = 0`. O Jarvis volta a dormir instantaneamente e exigirá ser chamado pelo nome de novo.

---

## 🛠️ Manutenção e Boas Práticas (Developer Guide)

- **Limitações e Quedas do Google STT**: O `recognize_google` no Python usa a chave API não documentada da *Web Speech API*. Se você estiver sem placa de rede ou a internet de casa cair, a exceção lançada no bloco será a `sr.RequestError`. O script avisará no console, dormirá 2 segundos e retornará `None`, permitindo que o Jarvis não trave (a saúde do microfone aparece no `/status`).
- **Indexação Física do Microfone**: A configuração vital `settings.MIC_INDEX` é lida do seu arquivo secreto `.env`. O Windows sofre com o roteamento constante de IDs de áudio sempre que você espeta um Controle de Xbox, fone Bluetooth ou VR no PC. Se o Copilot ficar surdo, confira a etapa de microfone da tela de boot e o `/status`, e ajuste o `MIC_INDEX` no `.env`. Não enumere o PortAudio em outro lugar: ele não é thread-safe, e o único ponto autorizado é `core/health.check_microphone()` (com lock e cache).
- **Multithreading Lock**: A mutação `self.is_paused` opera na *Main Thread*, então no loop `while True`, mesmo após ouvir e capturar os pacotes gigantes de Bytes do microfone, existe um *segundo* `if self.is_paused:` minúsculo antes de acionar o processamento de texto. Isso garante que áudios que bateram no microfone frações de segundo após o Jarvis mandar calar a boca sejam completamente descartados e não atrasem as transcrições do motor do Google.
