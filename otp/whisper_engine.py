import whisper
from config import WHISPER_MODEL

_model = None

def _get_model():
    global _model
    if _model is None:
        print(f"[Whisper] carregando modelo '{WHISPER_MODEL}'...")
        _model = whisper.load_model(WHISPER_MODEL)
        print("[Whisper] pronto")
    return _model

def transcribe(wav_path: str) -> str:
    model = _get_model()
    result = model.transcribe(wav_path, language="pt")
    return result["text"].strip()
