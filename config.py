import os
from dotenv import load_dotenv
load_dotenv()

# HeroSMS
HEROSMS_API_URL = os.getenv("HEROSMS_API_URL", "https://hero-sms.ru/stubs/handler_api.php")
HEROSMS_KEY     = os.getenv("HEROSMS_KEY", "")

# Supplier API
SUPPLIER_KEY = os.getenv("SUPPLIER_KEY", "change-me")
PORT         = int(os.getenv("PORT", 8000))

# Hardware — "e303" | "goip" | "openvox"
HARDWARE_TYPE = os.getenv("HARDWARE_TYPE", "e303")

# DEVICES: lista de canais para GoIP/OpenVox.
# Deixar vazio para E303 (auto-detecta via USB).
# Exemplos:
#   GoIP 8 canais:    [{"ip":"192.168.1.200","line":1,"number":"5511..."},...]
#   OpenVox 4 canais: [{"ip":"192.168.1.201","channel":1,"number":"5511..."},...]
import json
_devices_env = os.getenv("DEVICES", "[]")
DEVICES: list = json.loads(_devices_env)

# Modem (E303)
MODEM_BAUD_RATE      = 115200
MODEM_TIMEOUT        = 30
ACTIVATION_TIMEOUT   = 300

# Banco de dados
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://otpbridge:otpbridge@localhost:5432/otpbridge")

# Whisper
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
