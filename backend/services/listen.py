import math
import re
import time
from array import array

import speech_recognition as sr

from core import log, settings

LEVEL_MAX_HZ = 8           # no máx. 8 avisos de nível por segundo (= fps da orb)
# Escala em dBFS (o ouvido é logarítmico): na linear, fala normal mal mexia a barra.
LEVEL_FLOOR_DB = -50.0     # piso padrão (sem calibração): abaixo disso = silêncio
LEVEL_CEIL_DB = -12.0      # fala alta já enche a barra
_FULL_SCALE = 32768.0      # int16


def chunk_rms(chunk):
    """RMS de um bloco PCM 16-bit little-endian (sem audioop, removido no 3.13)."""
    if not chunk:
        return 0.0
    samples = array("h")
    samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _db(rms):
    return 20 * math.log10(rms / _FULL_SCALE) if rms > 0 else float("-inf")


def level_from_rms(rms, floor_rms=None):
    """Nível 0..1 em dBFS. `floor_rms` = limiar de energia do recognizer (mesma
    unidade, RMS int16): abaixo dele o reconhecedor não considera fala, então a
    barra fica zerada — ela sobe exatamente quando o JARVIS está te ouvindo."""
    floor = LEVEL_FLOOR_DB
    if floor_rms and floor_rms > 0:
        floor = min(max(floor, _db(floor_rms)), LEVEL_CEIL_DB - 6)
    db = _db(rms)
    if db <= floor:
        return 0.0
    return min(1.0, (db - floor) / (LEVEL_CEIL_DB - floor))


def rms_level(chunk, floor_rms=None):
    """Nível 0..1 de um bloco PCM 16-bit."""
    return level_from_rms(chunk_rms(chunk), floor_rms)


def _silenced():
    """Modo Apresentação ligado? (o ouvido não abre o microfone)"""
    try:
        from services.presentation import is_silent
        return is_silent()
    except Exception:
        return False


def clean_phrase(text):
    """Minúsculas, pontuação vira espaço e espaços colapsam:
    'Sexta-Feira, abre!' -> 'sexta feira abre'."""
    return " ".join(re.sub(r"[^\w\s]", " ", (text or "").lower()).split())


def find_wake_word(phrase, words):
    """1ª wake word presente em `phrase` (já limpa) como palavra inteira, ou None.

    Cada palavra passa pela mesma limpeza da frase ('sexta-feira' do .env casa
    com 'sexta feira' do STT) e as mais longas são testadas antes ('jair vis'
    vence 'jair'). Retorna a forma limpa, que é a que aparece na frase."""
    cleaned = {clean_phrase(w) for w in words} - {""}
    for word in sorted(cleaned, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", phrase):
            return word
    return None


class _LevelTap:
    """Envolve o stream do microfone: cada read() devolve o áudio intacto ao
    recognizer e mede o RMS de TODOS os blocos; a cada 1/LEVEL_MAX_HZ avisa o
    pico da janela (antes só 1 bloco a cada 125 ms era medido e o resto,
    descartado — sílabas inteiras sumiam da barra). `floor()` devolve o limiar
    de energia atual do recognizer."""

    def __init__(self, stream, on_level, clock=time.monotonic, floor=None):
        self._stream = stream
        self._on_level = on_level
        self._clock = clock
        self._floor = floor
        self._peak = 0.0
        self._last = float("-inf")  # 1º bloco sempre avisa

    def read(self, size):
        data = self._stream.read(size)
        if self._on_level:
            self._peak = max(self._peak, chunk_rms(data))
            now = self._clock()
            if now - self._last >= 1 / LEVEL_MAX_HZ:
                self._last = now
                try:
                    floor = self._floor() if self._floor else None
                    self._on_level(level_from_rms(self._peak, floor))
                except Exception as e:
                    log.debug(f"on_level falhou: {e}")
                self._peak = 0.0
        return data

    def __getattr__(self, name):
        return getattr(self._stream, name)


class Ear:
    def __init__(self):
        from services import user_prefs

        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=settings.MIC_INDEX)
        self.on_level = None  # callback(nível 0..1) do visualizador de voz

        # Configurações de Sensibilidade
        # Threshold estático evita que o ruído de ventilador eleve o limiar e o mic
        # pare de ouvir. Se o limiar for <= 0, volta ao modo dinâmico.
        threshold = user_prefs.get("mic_threshold")
        if threshold > 0:
            self.recognizer.dynamic_energy_threshold = False
            self.recognizer.energy_threshold = threshold
        else:
            self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 1.5

        # Configurações de Estado
        self.WAKE_WORDS = settings.WAKE_WORDS  # WAKE_WORDS no .env
        self.last_interaction_time = 0
        self.conversation_timeout = user_prefs.get("attention_window")  # janela de atenção (s)
        
        # Controle de "Ouvidos Tapados"
        self.is_paused = False

        log.debug("[SISTEMA] 🎚️ Calibrando microfone... (Silêncio)")
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            log.debug("[SISTEMA] ✅ Calibração concluída.")
        except Exception as e:
            log.critical(f"[ERRO CRÍTICO] Microfone não detectado: {e}")

    # --- MÉTODOS DE CONTROLE ---
    def pause(self):
        self.is_paused = True
    
    def resume(self):
        self.is_paused = False
        self.reset_timer() 

    def reset_timer(self):
        self.last_interaction_time = time.time()

    def _clean_text(self, text):
        return clean_phrase(text)

    def listen(self):
        while True:
            if self.is_paused or _silenced():  # Modo Apresentação: microfone fechado
                time.sleep(0.5)
                continue

            with self.microphone as source:
                time_since_last = time.time() - self.last_interaction_time
                is_active_mode = time_since_last < self.conversation_timeout

                if self.on_level and not isinstance(source.stream, _LevelTap):
                    source.stream = _LevelTap(source.stream, self.on_level,
                                               floor=lambda: self.recognizer.energy_threshold)
                try:
                    audio = self.recognizer.listen(source, timeout=None)
                    if self.on_level:
                        self.on_level(0.0)  # fim da fala: barras zeram
                    
                    if self.is_paused: 
                        continue

                    phrase = self.recognizer.recognize_google(audio, language=settings.DEFAULT_LANGUAGE).lower()
                    phrase = self._clean_text(phrase)
                    command = None
                    # Wake word como palavra inteira: aceita "jarvis", ignora "viajar"
                    trigger_found = find_wake_word(phrase, self.WAKE_WORDS)

                    if trigger_found:
                        # Substitui APENAS A PRIMEIRA ocorrência do nome
                        # Isso evita bugar frases como "Jarvis, fale sobre o Jarvis"
                        command = phrase.replace(trigger_found, "", 1).strip()
                        
                        if not command: 
                            # Se sobrou nada (ex: disse só "Jarvis"), pergunta o que deseja
                            self.last_interaction_time = time.time()
                            continue
                        else:
                            # Se tem comando, ativamos o timer e passamos adiante
                            self.last_interaction_time = time.time()
                    
                    elif is_active_mode:
                        # Se não falou o nome, mas está no timer, pega tudo
                        command = phrase 
                    else:
                        continue 

                    # Filtro de Cancelamento
                    if command and any(w in command for w in ['esquece', 'deixa', 'cancelar', 'quieto']):
                        log.info("🚫 Cancelado.")
                        self.last_interaction_time = 0 
                        continue

                    if command:
                        return command

                except sr.WaitTimeoutError:
                    pass
                except sr.UnknownValueError:
                    pass 
                except sr.RequestError:
                    log.critical("❌ [ERRO]: Sem internet.")
                    time.sleep(2)
                    return None
                except Exception as e:
                    log.critical(f"❌ [ERRO GENÉRICO]: {e}")
                    time.sleep(1)

# Singleton lazy: abrir o microfone no import travava o boot e mantinha o
# dispositivo ocupado mesmo com a voz desligada na TUI.
jarvis_ear = None

def get_ear():
    global jarvis_ear
    if jarvis_ear is None:
        jarvis_ear = Ear()
    return jarvis_ear

def listen(on_level=None):
    """Ouve até um comando. `on_level(0..1)` recebe o nível do microfone
    (no máx. LEVEL_MAX_HZ vezes por segundo) para o visualizador da TUI."""
    ear = get_ear()
    ear.on_level = on_level
    return ear.listen()

def ear_pause():
    # Sem ouvido criado não há o que pausar — não abre o mic só pra isso.
    if jarvis_ear is not None:
        jarvis_ear.pause()

def ear_resume():
    if jarvis_ear is not None:
        jarvis_ear.resume()