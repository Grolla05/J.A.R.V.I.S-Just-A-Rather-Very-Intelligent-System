import asyncio
import os
import re
import sys
import threading
import time
import uuid

import edge_tts
import pygame
import pyttsx3
from colorama import Fore, Style

from core import log, settings

# --- CONFIGURAÇÕES ---
VOICE_ONLINE = "pt-BR-AntonioNeural"

# Inicializa o motor offline (Backup)
engine_offline = pyttsx3.init()
engine_offline.setProperty('rate', settings.SPEECH_RATE)

# --- SINALIZADOR DE ÁUDIO ---
# Esse cadeado impede que duas threads falem ao mesmo tempo
speech_lock = threading.Lock()

# Inicializa o mixer
try:
    pygame.mixer.init()
except:
    log.critical("Erro ao iniciar sistema de áudio.")

def typewriter_effect(text, level="INFO"):
    """Simula a digitação."""
    prefix = f"{Fore.GREEN}[INFO]{Style.RESET_ALL}"
    if level == "WARN": prefix = f"{Fore.YELLOW}[WARN]{Style.RESET_ALL}"
    
    timestamp = time.strftime('%H:%M:%S')
    header = f"{timestamp} | {level} | {prefix} "
    
    sys.stdout.write(header)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.04)
    sys.stdout.write('\n')

def _treat_text(text):
    # (Seu código de tratamento de texto mantém igual)
    SLANG_MAP = {
        r"\bvc\b": "você",
        r"\btmj\b": "tamo junto",
        r"\bpq\b": "porque",
        r"\badd\b": "adicionar",
        r"\bmsg\b": "mensagem",
        r"\bobs\b": "observação",
    }
    text = re.sub(r'[^\w\s,.?!áéíóúàãõâêôçÁÉÍÓÚÀÃÕÂÊÔÇ]', '', text)
    for slang, expansion in SLANG_MAP.items():
        text = re.sub(slang, expansion, text, flags=re.IGNORECASE)
    return text.strip()

async def _generate_audio_online(text, file_path):
    clean_text = _treat_text(text)
    communicate = edge_tts.Communicate(clean_text, VOICE_ONLINE, rate="+10%")
    await communicate.save(file_path)

def speak_online(text, on_play=None):
    filename_path = settings.DIR_SOUNDS / f"audio_{uuid.uuid4().hex}.mp3"
    filename_str = str(filename_path)
    
    try:
        # 1. Gera o arquivo de áudio
        asyncio.run(_generate_audio_online(text, filename_str))

        # 2. VERIFICAÇÃO DE INTEGRIDADE (A correção principal)
        # Se o arquivo não existe ou é vazio (0 bytes), força erro para ir pro offline
        if not os.path.exists(filename_str) or os.path.getsize(filename_str) < 100:
            raise Exception("Arquivo de áudio gerado vazio ou corrompido.")

        # 3. Toca o áudio
        pygame.mixer.music.load(filename_str)
        
        if on_play:
            on_play()
        
        pygame.mixer.music.play()

        visual_thread = threading.Thread(target=typewriter_effect, args=(f"[J.A.R.V.I.S]: {text}",))
        visual_thread.start()
        
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
        visual_thread.join()
        pygame.mixer.music.unload()
        
        if os.path.exists(filename_str):
            try: os.remove(filename_str)
            except: pass
        return True

    except Exception as e:
        log.warning(f"Falha na voz online ({e}). Tentando offline...")
        # Limpeza caso falhe
        if os.path.exists(filename_str):
            try: os.remove(filename_str)
            except: pass
        return False

def speak_offline(text):
    log.info("[MODO OFFLINE] Ativando voz de backup...")
    typewriter_effect(f"[J.A.R.V.I.S]: {text}")
    clean_text = _treat_text(text)
    engine_offline.say(clean_text)
    engine_offline.runAndWait()

# --- AQUI ESTÁ A CORREÇÃO PRINCIPAL ---
def speak(text, play_callback=None): # <--- NOVO PARAMETRO
    """
    Função Thread-Safe com Callback de início de reprodução.
    """
    with speech_lock:
        # Passa o callback para o método online
        if not speak_online(text, on_play=play_callback):
            # Se falhar e for pro offline, chama o callback também
            if play_callback: play_callback()
            speak_offline(text)

if __name__ == "__main__":
    speak("Teste de áudio com bloqueio de thread.")