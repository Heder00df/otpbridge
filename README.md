# OTPBridge

Servidor de recebimento de OTP via SMS e Voz, integrando modems USB (Huawei E303) com a API HeroSMS via Asterisk + chan_dongle.

---

## Índice

1. [Pré-requisitos](#1-pré-requisitos)
2. [Instalação do projeto](#2-instalação-do-projeto)
3. [Banco de dados](#3-banco-de-dados)
4. [Asterisk + chan_dongle](#4-asterisk--chan_dongle)
5. [Configuração do .env](#5-configuração-do-env)
6. [Descoberta de números dos SIMs](#6-descoberta-de-números-dos-sims)
7. [Subindo o servidor](#7-subindo-o-servidor)
8. [Verificação do sistema](#8-verificação-do-sistema)
9. [Operação do dia a dia](#9-operação-do-dia-a-dia)
10. [Fluxo completo](#10-fluxo-completo)

---

## 1. Pré-requisitos

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \
                   postgresql postgresql-client \
                   asterisk asterisk-dev \
                   libsqlite3-dev build-essential git
```

> **Atenção:** O ModemManager deve estar **desabilitado** — o chan_dongle assume o controle dos modems.
> ```bash
> sudo systemctl stop ModemManager
> sudo systemctl disable ModemManager
> ```

---

## 2. Instalação do projeto

```bash
git clone git@github.com:Heder00df/otpbridge.git
cd otpbridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Banco de dados

```bash
# Criar usuário e banco
sudo -u postgres psql -c "CREATE USER otpbridge WITH PASSWORD 'otpbridge';"
sudo -u postgres psql -c "CREATE DATABASE otpbridge OWNER otpbridge;"

# Aplicar schema
sudo -u postgres psql -d otpbridge < db/schema.sql
```

---

## 4. Asterisk + chan_dongle

### 4.1 Compilar chan_dongle (patch para single-port E303)

O pacote `asterisk-chan-dongle` do apt não inclui o patch necessário para modems E303 de porta única. É preciso compilar da fonte:

```bash
git clone https://github.com/wdoekes/asterisk-chan-dongle.git
cd asterisk-chan-dongle

# Aplicar patch (permite audio=data no mesmo ttyUSB)
patch -p1 << 'EOF'
--- a/chan_dongle.c
+++ b/chan_dongle.c
@@ -174,7 +174,7 @@ EXPORT_DEF int lock_try(const char * devname, char ** lockname)
 				if(len == getpid() && assigned > 1)
 				{
-					if(port_status(fd2) == 0)
-						pid = len;
+					/* Same process: audio=data same device — allow re-open */
 				}
 				else
 					pid = len;
EOF

# Também aplicar o patch de shared fd (ver chan_dongle.c no repo para referência)
# O patch completo está em /tmp/chan-dongle-src após a primeira compilação

./bootstrap
./configure --with-astversion=$(asterisk -V | grep -oP '\d+\.\d+' | head -1) \
            DESTDIR=/usr/lib/x86_64-linux-gnu/asterisk/modules
make
sudo cp chan_dongle.so /usr/lib/x86_64-linux-gnu/asterisk/modules/
```

### 4.2 Configurar o chan_dongle

```bash
# Copiar configuração com os 16 modems mapeados
sudo cp asterisk/dongle.conf /etc/asterisk/dongle.conf

# Identificar portas de cada modem (com ModemManager ainda ativo)
mmcli -L
for idx in $(mmcli -L | grep -oP '/Modem/\K\d+'); do
  port=$(mmcli -m $idx | grep "primary port:" | awk '{print $NF}')
  echo "MM:$idx → /dev/$port"
done

# Editar dongle.conf ajustando audio= e data= para cada modem
sudo nano /etc/asterisk/dongle.conf
```

### 4.3 Configurar o dialplan

```bash
# Adicionar include no extensions.conf
echo "#include /etc/asterisk/otpbridge_extensions.conf" | sudo tee -a /etc/asterisk/extensions.conf

# Copiar dialplan
sudo cp asterisk/extensions.conf /etc/asterisk/otpbridge_extensions.conf
```

### 4.4 Instalar os AGI scripts

```bash
sudo cp modems/asterisk_agi.py /usr/share/asterisk/agi-bin/otpbridge_agi.py
sudo cp modems/asterisk_sms_agi.py /usr/share/asterisk/agi-bin/otpbridge_sms_agi.py
sudo chmod +x /usr/share/asterisk/agi-bin/otpbridge_agi.py
sudo chmod +x /usr/share/asterisk/agi-bin/otpbridge_sms_agi.py
```

### 4.5 Iniciar o Asterisk

```bash
sudo systemctl start asterisk
sudo systemctl enable asterisk

# Verificar dongles conectados
sudo asterisk -rx "dongle show devices"
# Esperado: todos com State = Free
```

---

## 5. Configuração do .env

Copiar e editar o arquivo de ambiente:

```bash
cp .env.example .env
nano .env
```

Variáveis obrigatórias:

```env
HARDWARE_TYPE=e303
DATABASE_URL=postgresql://otpbridge:otpbridge@localhost:5432/otpbridge
HEROSMS_KEY=sua_chave_herosms
SUPPLIER_KEY=senha_forte_aqui
WHISPER_MODEL=base

# Lista de modems — gerada automaticamente após dongle show devices
# Formato: [{"dongle_name":"dongle0","number":"5511999001122"}, ...]
DEVICES=[{"dongle_name":"dongle0","number":"55..."},...]
```

Para gerar a linha DEVICES automaticamente:

```bash
sudo asterisk -rx "dongle show devices" | awk 'NR>1 && $1~/dongle/ {
  name=$1; number=$NF
  gsub(/^\+/,"",number)
  if(number=="Unknown") number="unknown-" NR
  printf "{\"dongle_name\":\"%s\",\"number\":\"%s\"},\n", name, number
}'
```

---

## 6. Descoberta de números dos SIMs

Os chips M2M costumam ter o CNUM errado. O script tenta USSD automático (TIM `*846#`, Claro `*544#`, Oi `*461#`) e, para os que não responderem, envia SMS para confirmação manual.

```bash
source .venv/bin/activate

# Só USSD automático:
python3 tools/discover_numbers.py

# USSD + SMS manual para os que falharem:
python3 tools/discover_numbers.py +5561999342035
```

Após rodar, atualizar a linha `DEVICES=` no `.env` com os números confirmados.

---

## 7. Subindo o servidor

```bash
cd /home/heder/dev/projetos/otpbridge
source .venv/bin/activate
python3 main.py
```

Para rodar em background como serviço:

```bash
# Criar serviço systemd
sudo tee /etc/systemd/system/otpbridge.service << 'EOF'
[Unit]
Description=OTPBridge
After=network.target asterisk.service postgresql.service
Requires=asterisk.service postgresql.service

[Service]
User=heder
WorkingDirectory=/home/heder/dev/projetos/otpbridge
ExecStart=/home/heder/dev/projetos/otpbridge/.venv/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable otpbridge
sudo systemctl start otpbridge
```

---

## 8. Verificação do sistema

```bash
# Asterisk — dongles conectados
sudo asterisk -rx "dongle show devices"

# OTPBridge — modems disponíveis
curl "http://localhost:8000/supplier?action=GET_SERVICES&key=SUA_SUPPLIER_KEY"

# Logs do OTPBridge
sudo journalctl -u otpbridge -f

# Logs do Asterisk
sudo tail -f /var/log/asterisk/messages.log
```

---

## 9. Operação do dia a dia

### Reiniciar tudo (ordem correta)

```bash
sudo systemctl restart postgresql
sudo systemctl restart asterisk
sudo systemctl restart otpbridge
```

### Após reconectar modems USB

```bash
sudo systemctl restart asterisk
sleep 10
sudo asterisk -rx "dongle show devices"
```

### Atualizar código

```bash
cd /home/heder/dev/projetos/otpbridge
git pull origin main
sudo systemctl restart otpbridge
```

### Ver OTPs recebidos no banco

```bash
psql postgresql://otpbridge:otpbridge@localhost:5432/otpbridge \
  -c "SELECT * FROM ativacoes ORDER BY criado_em DESC LIMIT 20;"
```

---

## 10. Fluxo completo

```
SMS entrante:
  E303 → chan_dongle → Asterisk dialplan (sms)
       → AGI otpbridge_sms_agi.py
       → POST /e303/sms
       → E303Worker.deliver_sms()
       → extrator OTP → HeroSMS

Voz entrante:
  E303 → chan_dongle → Asterisk dialplan (s)
       → Answer → Record(WAV)
       → AGI otpbridge_agi.py
       → POST /internal/voice
       → E303Worker.deliver_voice()
       → Whisper → extrator OTP → HeroSMS
```

---

## Troubleshooting

| Problema | Verificação | Solução |
|---|---|---|
| Dongles "Not connected" | `sudo asterisk -rx "dongle show devices"` | Verificar se ModemManager está parado |
| Porta "Device busy" | `sudo fuser /dev/ttyUSBx` | `sudo fuser -k /dev/ttyUSBx` |
| SMS não chega | `sudo tail -f /var/log/asterisk/messages.log` | Verificar contexto `otpbridge-dongle` no dialplan |
| Número "unknown" | `dongle show devices` | Rodar `tools/discover_numbers.py` |
| OTPBridge não sobe | `sudo journalctl -u otpbridge` | Verificar `.env` e conexão com banco |
