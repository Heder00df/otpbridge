import os
import subprocess
import time
from typing import Optional, Tuple
from otp.extractor import extract_from_text

SILENCE_TIMEOUT   = 5    # segundos sem áudio para encerrar
MAX_CALL_DURATION = 30   # segundos máximos de gravação


class VoiceHandler:
    """
    Atende chamada e grava áudio PCM pela mesma porta AT (AT^DDSETEX=2).
    Recebe o fd já aberto pelo E303Worker — sem abrir porta nova.
    """

    def __init__(self, fd: int):
        self._fd = fd

    def handle(self) -> Tuple[Optional[str], Optional[str], int]:
        """Retorna (codigo, transcricao, duracao_segundos)."""
        pcm_path = f"/tmp/otpbridge_call_{int(time.time())}.pcm"
        wav_path = pcm_path.replace(".pcm", ".wav")
        duracao = 0
        try:
            duracao = self._answer_and_record(pcm_path)
            self._convert_to_wav(pcm_path, wav_path)
            from otp.whisper_engine import transcribe
            transcricao = transcribe(wav_path)
            print(f"[Voice] transcrição: {transcricao}")
            code = extract_from_text(transcricao)
            return code, transcricao, duracao
        except Exception as e:
            print(f"[Voice] erro: {e}")
            return None, None, duracao
        finally:
            for f in [pcm_path, wav_path]:
                try:
                    os.remove(f)
                except Exception:
                    pass

    def _answer_and_record(self, pcm_path: str) -> int:
        # Habilita áudio PCM pela porta USB e atende
        os.write(self._fd, b"AT^DDSETEX=2\r")
        time.sleep(0.5)
        os.write(self._fd, b"ATA\r")
        time.sleep(1)

        # Lê PCM raw da mesma porta serial
        start = time.time()
        last_data = time.time()
        with open(pcm_path, "wb") as out:
            while True:
                try:
                    chunk = os.read(self._fd, 1024)
                    if chunk:
                        out.write(chunk)
                        last_data = time.time()
                except BlockingIOError:
                    time.sleep(0.05)
                elapsed = time.time() - start
                silence = time.time() - last_data
                if silence > SILENCE_TIMEOUT or elapsed > MAX_CALL_DURATION:
                    break

        os.write(self._fd, b"AT+CHUP\r")
        return int(time.time() - start)

    def _convert_to_wav(self, pcm_path: str, wav_path: str):
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "s16le", "-ar", "8000", "-ac", "1",
            "-i", pcm_path,
            wav_path,
        ], check=True, capture_output=True)
