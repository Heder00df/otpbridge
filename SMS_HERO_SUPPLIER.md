# Proposta de Implementação — SMS Supplier HeroSMS
## Sistema de Ativação com 98 Modems Huawei E303

---

## 1. Visão Geral

Sistema que atua como **fornecedor (supplier)** na plataforma HeroSMS, usando 98 modems Huawei E303 com SIMs físicos para receber SMS e chamadas de voz com OTP, entregando os códigos de volta à HeroSMS automaticamente.

```
HeroSMS Platform ←——→ Servidor Supplier ←——→ 98 Modems Huawei E303
  (marketplace)         (este sistema)          (SIMs físicos)
```

**Receita:** pagamento por ativação concluída (OTP entregue com sucesso).

---

## 2. Python ou Node.js?

### Recomendação: **Python**

| Critério | Python | Node.js |
|---|---|---|
| Whisper (STT para voz) | ✅ nativo | ❌ chama Python como subprocess |
| Biblioteca GSM modem | ✅ `python-gsmmodem` (madura) | ⚠️ `serialport` (genérica) |
| Processamento de áudio | ✅ `pydub`, `numpy`, `scipy` | ❌ limitado |
| Exemplos da comunidade | ✅ abundantes para este caso | ❌ escassos |
| Gerenciar 98 threads | ✅ `threading` / `asyncio` | ✅ event loop |
| HTTP Supplier API | ✅ `FastAPI` / `Flask` | ✅ `Express` |

**Conclusão:** Python vence porque o Whisper roda nativamente, a `python-gsmmodem` é a melhor biblioteca para controle de modems GSM, e toda a cadeia (AT commands → áudio PCM → STT → regex) é nativa em Python sem subprocessos.

---

## 3. Arquitetura do Sistema

```
                        ┌─────────────────────────────────────────────────────────────┐
                        │                      SERVIDOR LINUX                          │
                        │                                                               │
      HeroSMS           │  ┌─────────────────┐      ┌──────────────────────────────┐  │
   ┌──────────┐         │  │   HTTP Server   │      │       Modem Pool Manager     │  │
   │          │─GET_SVC→│  │   (FastAPI)     │      │       (98 threads)           │  │
   │          │─GET_NUM→│  │                 │─────→│                              │  │
   │          │─FINISH──│  │ GET_SERVICES    │      │  Modem #1 ... Modem #98      │  │
   │          │         │  │ GET_NUMBER      │←─────│  status: LIVRE | OCUPADO     │  │
   │          │←PUSH_SMS│  │ FINISH_ACT.     │      │                              │  │
   └──────────┘         │  └─────────────────┘      └──────────┬───────────────────┘  │
        ↑               │                                       │                       │
        │               │       ┌───────────────────────────────┘                       │
        │               │       │  SMS recebido           Chamada de voz recebida       │
        │               │       │  (ttyUSB0)              (ttyUSB0 + ttyUSB1)           │
        │               │       ↓                                  ↓                    │
        │               │  ┌──────────┐                    ┌────────────────────┐       │
        │               │  │  SMS     │                    │  Voice Handler     │       │
        │               │  │ Reader   │                    │                    │       │
        │               │  │          │                    │ 1. ATA (atende)    │       │
        │               │  │ Lê texto │                    │ 2. AT^DDSETEX=2    │       │
        │               │  │ do modem │                    │ 3. Grava PCM       │       │
        │               │  └────┬─────┘                    │ 4. DTMF se pedido  │       │
        │               │       │                          │ 5. AT+CHUP (deslig)│       │
        │               │       │                          └────────┬───────────┘       │
        │               │       │                                   │                   │
        │               │       │                          ┌────────▼───────────┐       │
        │               │       │                          │   Whisper Engine   │       │
        │               │       │                          │   (modelo base)    │       │
        │               │       │                          │                    │       │
        │               │       │                          │ PCM → WAV → texto  │       │
        │               │       │                          └────────┬───────────┘       │
        │               │       │                                   │                   │
        │               │       └──────────────┬────────────────────┘                   │
        │               │                      ↓                                        │
        │               │            ┌─────────────────┐                                │
        │               │            │  OTP Extractor  │                                │
        │               │            │                 │                                │
        │               │            │ SMS:   regex    │                                │
        │               │            │ Voz:   regex    │                                │
        │               │            │        após STT │                                │
        │               │            └────────┬────────┘                                │
        │               │                     │                                         │
        │               │            ┌────────▼────────┐   ┌─────────────────────────┐ │
        └───────────────│────────────│  HeroSMS Client │   │  PostgreSQL             │ │
                        │            │  PUSH_SMS →     │   │  modems | ativacoes     │ │
                        │            └─────────────────┘   │  logs                   │ │
                        │                                   └─────────────────────────┘ │
                        └─────────────────────────────────────────────────────────────┘
                                              ↕ USB (98x)
                        ┌─────────────────────────────────────────────────────────────┐
                        │   E303 #1        E303 #2        E303 #3   ...   E303 #98    │
                        │   ttyUSB0 (AT)   ttyUSB3 (AT)  ttyUSB6 (AT)    ttyUSB...   │
                        │   ttyUSB1 (voz)  ttyUSB4 (voz) ttyUSB7 (voz)   ttyUSB...   │
                        └─────────────────────────────────────────────────────────────┘

  Legenda:
  ttyUSB0 (AT)  → comandos AT: SMS, RING, ATA, AT+CHUP, DTMF
  ttyUSB1 (voz) → áudio PCM bruto 8kHz 16-bit mono (apenas durante chamada)
  Voz = 100% automatizada: robocall atendido e transcrito sem interação humana
  DTMF = enviado automaticamente se o robô pedir "pressione 1 para ouvir o código"
```

---

## 4. Protocolo Supplier HeroSMS

A HeroSMS chama **seu servidor** — você expõe os endpoints abaixo.  
Todas as requisições incluem o parâmetro `key` (fornecido pela HeroSMS no cadastro de parceiro).

### 4.1 GET_SERVICES
HeroSMS pergunta quantos números você tem disponíveis por serviço.  
Chamado a cada **10–20 segundos**.

```
GET /supplier?action=GET_SERVICES&key=SUA_CHAVE

Resposta:
{
  "status": "success",
  "services": {
    "telegram": 12,
    "whatsapp": 8,
    "google": 20,
    "instagram": 5
  }
}
```

### 4.2 GET_NUMBER
HeroSMS solicita um número para uma ativação específica.

```
GET /supplier?action=GET_NUMBER&key=SUA_CHAVE&service=telegram&country=7

Resposta (sucesso):
{
  "status": "success",
  "number": "5511999990001",
  "activationId": "uuid-interno"
}

Resposta (sem número disponível):
{ "status": "no_number" }
```

### 4.3 FINISH_ACTIVATION
HeroSMS informa que a ativação terminou.

```
GET /supplier?action=FINISH_ACTIVATION&key=SUA_CHAVE&activationId=uuid&status=3

status:
  1 = aguardando SMS
  3 = concluído com sucesso (você recebe o pagamento)
  8 = cancelado pelo comprador
```

### 4.4 PUSH_SMS (você chama a HeroSMS)
Quando o OTP chegar, você notifica a HeroSMS.

```
POST https://hero-sms.com/api/push
{
  "key": "SUA_CHAVE",
  "activationId": "uuid",
  "text": "Your code: 48291",
  "code": "48291"
}
```

---

## 5. Fluxo Completo de Ativação

```
HeroSMS              Servidor              Modem #7
   │                    │                     │
   │── GET_SERVICES ───→│                     │
   │←── { telegram:8 } ─│                     │
   │                    │                     │
   │── GET_NUMBER ──────→│                     │
   │                    │── reserva modem #7  │
   │←── { number: ... } ─│                     │
   │                    │                     │
   │                    │                     │ ← SMS chega
   │                    │←── "code: 48291" ───│
   │                    │                     │
   │←── PUSH_SMS ────────│                     │
   │  { code: "48291" } │                     │
   │                    │                     │
   │── FINISH (status=3)→│                     │
   │                    │── libera modem #7   │
   │                    │                     │
```

---

## 6. Pipeline de Voz (OTP por chamada)

Alguns serviços enviam o OTP via **chamada de voz** (robô lê os dígitos).

### 6.1 Fluxo técnico

```
1. RING detectado no ttyUSB0
         ↓
2. AT^DDSETEX=2   → ativa roteamento de áudio
   ATA            → atende a chamada
         ↓
3. Captura PCM do ttyUSB1 (áudio bruto 8kHz 16-bit mono)
   subprocess: cat /dev/ttyUSB1 > /tmp/call_uuid.pcm
         ↓
4. Detecta silêncio (fim da mensagem) → encerra
   AT+CHUP
         ↓
5. Converte PCM → WAV
   ffmpeg -f s16le -ar 8000 -ac 1 -i call.pcm call.wav
         ↓
6. Transcreve com Whisper local (modelo "base")
   result = whisper_model.transcribe("call.wav")
   # → "Seu código de verificação é 4 8 2 9 1"
         ↓
7. Extrai dígitos com regex
   code = re.sub(r'\D', '', result["text"])
   # → "48291"
         ↓
8. PUSH_SMS para HeroSMS com o código
```

### 6.2 Dependências de voz

```bash
pip install openai-whisper
apt install ffmpeg
```

Modelo recomendado: **`base`** (39MB, roda na CPU, preciso o suficiente para dígitos)  
Alternativa mais leve: **`tiny`** (39MB → 75MB de RAM, ainda mais rápido)

---

## 7. ⚠️ Ponto de Atenção — E303 e Voz

**Nem todos os Huawei E303 têm voz habilitada de fábrica.**

### Como verificar antes de comprar/usar em escala

Conectar o modem e executar:

```bash
# Abrir terminal serial do modem
minicom -D /dev/ttyUSB0 -b 115200

# Enviar o comando:
AT^CVOICE?
```

**Interpretação da resposta:**

| Resposta | Significado | Ação |
|---|---|---|
| `^CVOICE: 0` ou `^CVOICE: 1` | ✅ Voz habilitada | Nenhuma |
| `ERROR` | ❌ Voz bloqueada | Ver opções abaixo |

### Se retornar ERROR (voz bloqueada)

**Opção A:** Atualizar firmware para versão com voz desbloqueada (processo específico por modelo/região — testar primeiro em 1 unidade)

**Opção B:** Usar os modems E303 apenas para SMS e adicionar modems com voz garantida (ex: Huawei E1750, E173, SIM800 modules) para chamadas

**Opção C:** Separar o pool — modems com voz habilitada ficam disponíveis para serviços que usam voz, os demais apenas para SMS

### Recomendação prática

**Antes de configurar os 98 modems, testar 3–5 unidades** com o comando `AT^CVOICE?`. Se a maioria retornar ERROR, avaliar troca de hardware ou firmware antes de escalar.

---

## 8. Banco de Dados

```sql
-- Pool de modems
CREATE TABLE modems (
    id          SERIAL PRIMARY KEY,
    porta_usb   VARCHAR(20) NOT NULL,   -- ex: /dev/ttyUSB0
    porta_audio VARCHAR(20),            -- ex: /dev/ttyUSB1
    numero      VARCHAR(20) NOT NULL,
    suporta_voz BOOLEAN DEFAULT FALSE,
    status      VARCHAR(20) DEFAULT 'LIVRE',  -- LIVRE | OCUPADO | ERRO | OFFLINE
    ativacao_id VARCHAR(50),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Ativações
CREATE TABLE ativacoes (
    id              VARCHAR(50) PRIMARY KEY,  -- UUID interno
    modem_id        INTEGER REFERENCES modems(id),
    servico         VARCHAR(50),              -- telegram, whatsapp, etc.
    numero          VARCHAR(20),
    status          VARCHAR(20) DEFAULT 'AGUARDANDO',
    tipo_otp        VARCHAR(10),              -- SMS | VOZ
    codigo_recebido VARCHAR(20),
    criado_em       TIMESTAMP DEFAULT NOW(),
    concluido_em    TIMESTAMP
);

-- Log de eventos
CREATE TABLE logs (
    id        SERIAL PRIMARY KEY,
    modem_id  INTEGER,
    evento    VARCHAR(50),   -- SMS_RECEBIDO | CHAMADA | PUSH_OK | ERRO
    detalhe   TEXT,
    criado_em TIMESTAMP DEFAULT NOW()
);
```

---

## 9. Estrutura de Arquivos do Projeto

```
sms-supplier/
├── main.py                  # entry point — sobe HTTP + modem pool
├── config.py                # KEY HeroSMS, ports, configurações
│
├── api/
│   └── supplier.py          # endpoints: GET_SERVICES, GET_NUMBER, FINISH_ACTIVATION
│
├── modems/
│   ├── pool.py              # gerencia os 98 modems, status, fila
│   ├── modem_worker.py      # 1 instância por modem (thread)
│   ├── sms_reader.py        # lê SMS via AT commands
│   └── voice_handler.py     # atende chamada, captura PCM
│
├── otp/
│   ├── extractor.py         # regex para SMS + Whisper para voz
│   └── whisper_engine.py    # singleton do modelo Whisper
│
├── herosms/
│   └── client.py            # chama PUSH_SMS na HeroSMS
│
└── db/
    └── repository.py        # acesso ao banco de dados
```

---

## 10. Stack Tecnológica

| Componente | Tecnologia | Justificativa |
|---|---|---|
| Linguagem | **Python 3.11+** | Whisper nativo, melhor ecossistema GSM |
| HTTP Server | **FastAPI** | Async, rápido, documentação automática |
| Modems | **python-gsmmodem-new** | Biblioteca madura para AT commands |
| Speech-to-Text | **OpenAI Whisper local** | Gratuito, offline, preciso para dígitos |
| Áudio | **ffmpeg + pydub** | Conversão PCM → WAV |
| Banco de dados | **PostgreSQL** | Confiável para produção |
| ORM | **SQLAlchemy** | Padrão Python |
| Concorrência | **threading** (1 por modem) | Simples e eficaz para I/O bound |

---

## 11. Caminho de Migração para Multi-Nó

Esta proposta (1 PC) é a **base da Proposta 2** (3 PCs). Todo o código de modem, SMS, voz e Whisper é reaproveitado sem alteração. A migração consiste em:

1. Mover `api/supplier.py` e `herosms/client.py` para um **Central**
2. Adicionar `node/api/node_api.py` — apenas 3 endpoints que expõem o que já existe internamente (`/status`, `/reserve`, `/release`)
3. Adicionar `central/orchestrator/node_client.py` — chama esses endpoints nos nós por IP fixo LAN

Nada no processamento de modem muda. Comece aqui, migre quando precisar de mais capacidade.

---

## 12. Etapas de Implementação

### Fase 1 — Prova de Conceito (1 modem)
- [ ] Instalar dependências e conectar 1 E303
- [ ] Verificar `AT^CVOICE?` → confirmar voz
- [ ] Ler SMS com `python-gsmmodem`
- [ ] Atender chamada e capturar PCM
- [ ] Converter PCM → WAV → Whisper → extrair dígitos
- [ ] Subir endpoint HTTP básico (GET_SERVICES, GET_NUMBER, FINISH_ACTIVATION)
- [ ] Testar PUSH_SMS para HeroSMS

### Fase 2 — Pool de Modems (todos os 98)
- [ ] Detectar todos os dispositivos USB automaticamente
- [ ] Gerenciador de pool com status por modem
- [ ] Fila de ativações e distribuição automática
- [ ] Dashboard simples (status, ativações/hora, saldo)

### Fase 3 — Produção e Escala
- [ ] Monitoramento e alertas (modem offline, erro recorrente)
- [ ] Auto-restart de modems com erro
- [ ] Métricas: taxa de sucesso por modem, por serviço
- [ ] Separação de pool SMS / pool Voz

---

## 12. Hardware Recomendado para o Servidor

Com 98 modems USB, o servidor precisa de:

| Componente | Mínimo | Recomendado |
|---|---|---|
| CPU | 4 cores | 8 cores (Whisper roda na CPU) |
| RAM | 8 GB | 16 GB |
| USB | Hubs USB 3.0 ativos (com fonte própria) | 7x hub 16 portas |
| SO | Ubuntu Server 22.04 LTS | — |
| Armazenamento | SSD 128 GB | SSD 256 GB |

**Atenção com USB hubs:** usar hubs com fonte de alimentação própria — modems 3G consomem ~500mA cada. 98 modems = ~49A total, hubs passivos não suportam.
