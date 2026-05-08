# OTPBridge

Servidor de recebimento de OTP via SMS e Voz, integrando modems USB (Huawei E303), GoIP e OpenVox com a API HeroSMS.

---

## Pré-requisitos

- Python 3.11+
- PostgreSQL
- ModemManager (`mmcli`) — para E303
- Asterisk 18+ com chan_dongle — para voz E303
- ffmpeg — para conversão de áudio (não mais necessário com chan_dongle)

---

## Instalação

```bash
git clone git@github.com:Heder00df/otpbridge.git
cd otpbridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar com suas credenciais
```

---

## Configuração de Voz com Asterisk + chan_dongle (E303)

### 1. Instalar Asterisk e chan_dongle

```bash
sudo apt update
sudo apt install -y asterisk asterisk-dev

# chan_dongle (Huawei USB voice channel driver)
sudo apt install -y asterisk-chan-dongle
# ou compilar da fonte se o pacote não estiver disponível:
# https://github.com/bg111/asterisk-chan-dongle
```

### 2. Identificar as portas USB dos modems

O E303 expõe 3 interfaces. O ModemManager usa a porta AT; o chan_dongle usa a porta de áudio.

```bash
# Listar modems detectados pelo ModemManager
mmcli -L

# Ver detalhes de um modem (substitua 0 pelo índice)
mmcli -m 0

# Identificar as portas ttyUSB do modem
ls -la /dev/ttyUSB*
# Ou pelo ID USB:
udevadm info --query=all --name=/dev/ttyUSB0 | grep -i "ID_MODEL\|DEVPATH"
```

Mapeamento típico do E303:

| Porta | Uso |
|---|---|
| `/dev/ttyUSB0` | Áudio (chan_dongle usa esta) |
| `/dev/ttyUSB1` | AT commands (ModemManager usa esta) |
| `/dev/ttyUSB2` | PCUI/dados |

### 3. Configurar o chan_dongle

Copiar e editar o arquivo de configuração:

```bash
sudo cp asterisk/dongle.conf /etc/asterisk/dongle.conf
sudo nano /etc/asterisk/dongle.conf
```

Ajustar os campos `audio=` e `data=` com as portas corretas de cada modem.

### 4. Configurar o dialplan do Asterisk

```bash
# Fazer backup do extensions.conf original
sudo cp /etc/asterisk/extensions.conf /etc/asterisk/extensions.conf.bak

# Incluir o dialplan do OTPBridge no final do arquivo
echo "" | sudo tee -a /etc/asterisk/extensions.conf
echo "#include /etc/asterisk/otpbridge_extensions.conf" | sudo tee -a /etc/asterisk/extensions.conf

# Copiar o dialplan
sudo cp asterisk/extensions.conf /etc/asterisk/otpbridge_extensions.conf
```

### 5. Instalar o AGI script

```bash
sudo cp modems/asterisk_agi.py /usr/share/asterisk/agi-bin/otpbridge_agi.py
sudo chmod +x /usr/share/asterisk/agi-bin/otpbridge_agi.py
```

### 6. Recarregar o Asterisk

```bash
sudo systemctl restart asterisk
# ou, sem derrubar chamadas ativas:
sudo asterisk -rx "module reload chan_dongle.so"
sudo asterisk -rx "dialplan reload"
```

### 7. Verificar que o modem foi reconhecido

```bash
sudo asterisk -rx "dongle show devices"
# Esperado:
#   ID     Group State      RSSI  Mode  Start  DNS  Number        Dev        
#   dongle0  0   Free          18   0    No     Yes  Unknown  /dev/ttyUSB0
```

### 8. Iniciar o OTPBridge

```bash
source .venv/bin/activate
python3 main.py
```

---

## Fluxo de voz (todos os hardwares)

```
Chamada entrante
      │
      ▼
  Asterisk
  Answer() → Wait(1s) → Record(WAV, silêncio=3s, max=30s)
      │
      ▼
  AGI: otpbridge_agi.py <modem_number> <wav_path>
      │  POST /internal/voice
      ▼
  OTPBridge
  pool.find_by_number() → worker.deliver_voice(wav_path)
      │
      ▼
  Whisper (transcrição PT)
      │
      ▼
  Extrator de OTP → push_sms() → HeroSMS
```

---

## Variáveis de ambiente (.env)

```env
HARDWARE_TYPE=e303          # e303 | goip | openvox
DATABASE_URL=postgresql://otpbridge:otpbridge@localhost:5432/otpbridge
HEROSMS_KEY=sua_chave_aqui
SUPPLIER_KEY=sua_chave_aqui
WHISPER_MODEL=base          # tiny | base | small | medium
PORT=8000
```

---

## Descoberta de números dos SIMs M2M

Os chips M2M costumam ter o CNUM errado. Use o script de descoberta:

```bash
python3 tools/discover_numbers.py +55619XXXXXXXX
```

O script envia um SMS de cada modem para o número informado e permite mapear manualmente ID → número real.
