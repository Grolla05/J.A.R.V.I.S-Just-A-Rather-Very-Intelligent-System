import re
import time

import speech_recognition as sr

from core import log, settings


class Ear:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(device_index=settings.MIC_INDEX)
        
        # Configurações de Sensibilidade
        # Threshold estático evita que o ruído de ventilador eleve o limiar e o mic
        # pare de ouvir. Se MIC_ENERGY_THRESHOLD <= 0, volta ao modo dinâmico.
        if settings.MIC_ENERGY_THRESHOLD > 0:
            self.recognizer.dynamic_energy_threshold = False
            self.recognizer.energy_threshold = settings.MIC_ENERGY_THRESHOLD
        else:
            self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 1.5
        
        # Configurações de Estado
        self.WAKE_WORDS = ['jarvis', 'jar', 'jair', 'javis', 'davis', 'gervis', 'jarbas', 'garvis', 'jefferson', 'jorge', 'jair vis']
        self.last_interaction_time = 0
        self.conversation_timeout = 60 # 60s de janela de atenção
        
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
        return re.sub(r'[^\w\s]', '', text).strip()

    def listen(self):
        while True:
            if self.is_paused:
                time.sleep(0.5)
                continue

            with self.microphone as source:
                time_since_last = time.time() - self.last_interaction_time
                is_active_mode = time_since_last < self.conversation_timeout

                try:
                    audio = self.recognizer.listen(source, timeout=None)
                    
                    if self.is_paused: 
                        continue

                    phrase = self.recognizer.recognize_google(audio, language=settings.DEFAULT_LANGUAGE).lower()
                    phrase = self._clean_text(phrase)
                    command = None
                    trigger_found = None
                    
                    # Verifica se falou o nome (Wake Word)
                    for trigger in self.WAKE_WORDS:
                        # TRUQUE DE REGEX: \b garante que é a palavra inteira
                        # Ex: aceita "jarvis" mas ignora "viajar"
                        if re.search(rf"\b{trigger}\b", phrase):
                            trigger_found = trigger
                            break
                    
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

jarvis_ear = Ear()

def listen():
    return jarvis_ear.listen()

def ear_pause():
    jarvis_ear.pause()

def ear_resume():
    jarvis_ear.resume()