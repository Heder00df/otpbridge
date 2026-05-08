import re
from typing import Optional

# Padrões comuns de OTP em SMS e transcrições de voz
_PATTERNS = [
    r'\b(\d{4,8})\b',                         # sequência de 4-8 dígitos
    r'code[:\s]+(\d{4,8})',                    # "code: 12345"
    r'c[oó]digo[:\s]+(\d{4,8})',              # "código: 12345"
    r'verification[:\s]+(\d{4,8})',
    r'(\d{4,8})\s+is your',
    r'your.*?(\d{4,8})',
]

def extract_from_sms(text: str) -> Optional[str]:
    return _extract(text)

def extract_from_text(text: str) -> Optional[str]:
    # Para voz: remove espaços entre dígitos falados ("4 8 2 9 1" → "48291")
    collapsed = re.sub(r'(?<=\d)\s+(?=\d)', '', text)
    return _extract(collapsed) or _extract(text)

def _extract(text: str) -> Optional[str]:
    for pattern in _PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
