# Proposta 2 — SMS Supplier HeroSMS (Multi-Nó, LAN)
## Arquitetura Distribuída: Central + 3 Nós com IP Fixo

---

## 1. Premissa

3 PCs na mesma rede local com **IP fixo**. O central chama os nós diretamente via REST — sem polling, sem WebSocket, sem broker.

```
Central API  ──► POST http://192.168.1.101:8001/reserve   (PC 1)
             ──► POST http://192.168.1.102:8001/reserve   (PC 2)
             ──► POST http://192.168.1.103:8001/reserve   (PC 3)

Node Agent   ──► POST http://192.168.1.100:8000/otps      (quando OTP chega)
```

---

## 2. Arquitetura

```
                    ┌────────────────────────────────────────────┐
      HeroSMS       │            CENTRAL (192.168.1.100)          │
   ┌──────────┐     │                                            │
   │          │─GET_SVC──►  FastAPI                             │
   │          │─GET_NUM──►  Orquestrador ──► chama nó via REST  │
   │          │─FINISH───►  /otps  ◄── recebe OTP dos nós       │
   │          │◄─PUSH_SMS─  PUSH_SMS ──► HeroSMS               │
   └──────────┘     │                                            │
                    │  PostgreSQL (banco central, único)         │
                    └────────────────────────────────────────────┘
                          │               │               │
              POST /reserve         POST /reserve   POST /reserve
              GET  /status          GET  /status    GET  /status
                          │               │               │
                  ┌───────┴──┐    ┌───────┴──┐    ┌──────┴───┐
                  │  PC 1    │    │  PC 2    │    │  PC 3    │
                  │ .101:8001│    │ .102:8001│    │ .103:8001│
                  │          │    │          │    │          │
                  │ Node API │    │ Node API │    │ Node API │
                  │ SMS Wkr  │    │ SMS Wkr  │    │ SMS Wkr  │
                  │ Voice H. │    │ Voice H. │    │ Voice H. │
                  │ Whisper  │    │ Whisper  │    │ Whisper  │
                  │ ~33 mod. │    │ ~33 mod. │    │ ~32 mod. │
                  └──────────┘    └──────────┘    └──────────┘
```

---

## 3. Contrato de APIs

### 3.1 Node API (exposta por cada PC)

#### `GET /status`
Central consulta disponibilidade do nó.

```
GET http://192.168.1.101:8001/status

Resposta:
{
  "node_id": "pc1",
  "online": true,
  "modems_total": 33,
  "modems_livres": 12,
  "modems_ocupados": 21,
  "servicos_disponiveis": {
    "telegram": 5,
    "whatsapp": 3,
    "google": 4
  }
}
```

#### `POST /reserve`
Central manda reservar um modem para uma ativação.

```
POST http://192.168.1.101:8001/reserve
{
  "activation_id": "uuid-abc",
  "servico": "telegram",
  "timeout_segundos": 300
}

Resposta (sucesso):
{
  "ok": true,
  "modem_id": 7,
  "numero": "5511999990007"
}

Resposta (sem modem disponível):
{
  "ok": false,
  "motivo": "no_number"
}
```

#### `POST /release`
Central manda liberar o modem (FINISH_ACTIVATION recebido).

```
POST http://192.168.1.101:8001/release
{
  "activation_id": "uuid-abc",
  "status": 3
}
  status 3 = concluído | status 8 = cancelado

Resposta:
{ "ok": true }
```

---

### 3.2 Central API (chamada pelos nós)

#### `POST /otps`
Nó entrega OTP extraído (SMS ou voz) ao central.

```
POST http://192.168.1.100:8000/otps
{
  "activation_id": "uuid-abc",
  "code": "48291",
  "tipo": "SMS",        // ou "VOZ"
  "node_id": "pc1",
  "modem_id": 7
}

Resposta:
{ "ok": true }
```

Central então faz `PUSH_SMS` para a HeroSMS com o código.

---

## 4. Fluxo Completo

```
HeroSMS        Central (.100)       PC 2 (.102)        Modem #7 (PC2)
   │               │                    │                    │
   │─ GET_SERVICES►│                    │                    │
   │               │─ GET /status ─────►│                    │
   │               │◄─ { livres: 8 } ───│                    │
   │◄─ {tel:8} ───│                    │                    │
   │               │                    │                    │
   │─ GET_NUMBER ─►│                    │                    │
   │               │─ POST /reserve ───►│                    │
   │               │◄─ { num: "5511.." }│─ reserva modem #7─►│
   │◄─ { number } ─│                    │                    │
   │               │                    │                    │
   │               │                    │     SMS chega ────►│
   │               │                    │◄─ "code: 48291" ───│
   │               │◄─ POST /otps ──────│                    │
   │◄─ PUSH_SMS ──│                    │                    │
   │               │                    │                    │
   │─ FINISH(3) ──►│                    │                    │
   │               │─ POST /release ───►│                    │
   │               │                    │─ libera modem #7 ─►│
```

---

## 5. Seleção de Nó no Central

```python
# Ao receber GET_SERVICES: agrega totais de todos os nós
def get_services():
    totais = {}
    for no in NODES:                        # [ "192.168.1.101", ... ]
        try:
            r = requests.get(f"http://{no}:8001/status", timeout=2)
            for svc, qtd in r.json()["servicos_disponiveis"].items():
                totais[svc] = totais.get(svc, 0) + qtd
        except:
            pass                            # nó offline, ignora
    return totais

# Ao receber GET_NUMBER: tenta nó com mais folga primeiro
def get_number(servico):
    nos_ordenados = sorted(
        [no for no in NODES if no["online"]],
        key=lambda n: n["modems_livres"],
        reverse=True
    )
    for no in nos_ordenados:
        r = requests.post(f"http://{no['ip']}:8001/reserve", json={
            "activation_id": novo_uuid(),
            "servico": servico,
            "timeout_segundos": 300
        }, timeout=3)
        if r.json()["ok"]:
            return r.json()["numero"]
    return None                             # no_number
```

---

## 6. Detecção de Nó Offline

`GET /status` é chamado a cada `GET_SERVICES` (a cada 10–20s pela HeroSMS).  
Se o `requests.get` lançar exceção (timeout/connection refused), o nó é ignorado na contagem — sem lógica extra de heartbeat.

```python
NODES = [
    {"id": "pc1", "ip": "192.168.1.101"},
    {"id": "pc2", "ip": "192.168.1.102"},
    {"id": "pc3", "ip": "192.168.1.103"},
]
```

Se PC 1 cair, `GET /status` para .101 dá timeout → central não conta seus modems → HeroSMS não manda GET_NUMBER para números do PC 1 → PC 2 e PC 3 continuam normalmente.

---

## 7. Estrutura de Arquivos

```
sms-supplier/
│
├── central/                    # roda no servidor central (.100)
│   ├── main.py
│   ├── config.py               # NODES = [{id, ip}, ...]
│   ├── api/
│   │   ├── herosms.py          # GET_SERVICES, GET_NUMBER, FINISH_ACTIVATION
│   │   └── otps.py             # POST /otps (recebe OTP dos nós)
│   ├── orchestrator/
│   │   └── node_client.py      # chama GET /status e POST /reserve nos nós
│   ├── herosms/
│   │   └── client.py           # chama PUSH_SMS na HeroSMS
│   └── db/
│       └── repository.py
│
└── node/                       # roda em cada PC (mesmo código, NODE_ID diferente)
    ├── main.py
    ├── config.py               # NODE_ID, CENTRAL_URL
    ├── api/
    │   └── node_api.py         # GET /status, POST /reserve, POST /release
    ├── modems/
    │   ├── pool.py
    │   ├── modem_worker.py
    │   ├── sms_reader.py
    │   └── voice_handler.py
    ├── otp/
    │   ├── extractor.py
    │   └── whisper_engine.py
    └── central/
        └── reporter.py         # POST /otps no central quando OTP chega
```

---

## 8. Banco de Dados

Igual à Proposta 1, com `node_id` adicionado às tabelas `modems` e `ativacoes`.  
Nós não acessam o banco diretamente — apenas o central grava e lê.

```sql
ALTER TABLE modems    ADD COLUMN node_id VARCHAR(20);
ALTER TABLE ativacoes ADD COLUMN node_id VARCHAR(20);
```

---

## 9. Comparação das Abordagens de Comunicação

| | HTTP Polling (nó puxa) | **RPC Direto (esta)** | WebSocket |
|---|---|---|---|
| Latência | ~2s | ~50ms | ~10ms |
| Complexidade | baixa | **baixa** | média |
| Infra extra | nenhuma | **nenhuma** | nenhuma |
| IP fixo necessário | não | **sim** | não |
| Funciona em NAT | sim | não | sim |
| Para LAN com IP fixo | ok | **ideal** | overkill |

---

## 10. Exposição Pública — Como a HeroSMS Chama Seu Servidor

A HeroSMS está na internet e precisa alcançar seu Central API. Os nós (PC1, PC2, PC3) ficam **invisíveis na LAN** — só o Central é exposto.

```
HeroSMS (internet)
    │
    ▼
URL pública  →  Central API (192.168.1.100)
                    │ LAN direta
              ┌─────┼─────┐
             PC1   PC2   PC3
```

### Opções para expor o Central

| Opção | Custo | Indicado para |
|---|---|---|
| **Cloudflare Tunnel** | gratuito | produção — recomendado |
| IP fixo na operadora | ~R$30–50/mês | alternativa simples |
| VPS (Hetzner, DigitalOcean) | ~R$20/mês | se quiser Central na nuvem |
| Ngrok | gratuito (limitado) | testes apenas |

### Recomendação: Cloudflare Tunnel

Sem contratar IP fixo de operadora. Você instala o agente `cloudflared` no PC Central — ele abre um túnel de saída para a Cloudflare e você ganha uma URL pública permanente.

```bash
# Instalar no PC Central
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg
apt install cloudflared

# Autenticar e criar túnel
cloudflared tunnel login
cloudflared tunnel create sms-supplier
cloudflared tunnel route dns sms-supplier supplier.seudominio.com

# Configurar /etc/cloudflared/config.yml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: supplier.seudominio.com
    service: http://localhost:8000
  - service: http_status:404

# Subir como serviço
cloudflared service install
systemctl start cloudflared
```

Resultado: HeroSMS chama `https://supplier.seudominio.com` → Cloudflare → Central na sua LAN.

### IPs fixos internos (LAN)

Os IPs `192.168.1.10x` dos nós são apenas internos — configurados no roteador via DHCP reservation (associar MAC address ao IP). Gratuito, sem contratar nada.

```
Roteador
  └── Central  MAC aa:bb:cc... → 192.168.1.100
  └── PC 1     MAC dd:ee:ff... → 192.168.1.101
  └── PC 2     MAC 11:22:33... → 192.168.1.102
  └── PC 3     MAC 44:55:66... → 192.168.1.103
```

---

## 11. Etapas de Implementação

### Fase 1 — Validar com Proposta 1 (1 PC, 1 modem)
Não pular. **Todo o código de modem é reaproveitado sem alteração** — a migração para multi-nó consiste apenas em expor esse código via HTTP (`node_api.py`) e mover os endpoints HeroSMS para o Central.

### Fase 2 — Separar Central e Node
- Extrair código de modem para `node/`
- Criar `node/api/node_api.py` com os 3 endpoints
- Criar `central/orchestrator/node_client.py`
- Testar com 2 PCs na LAN

### Fase 3 — 3 PCs completos
- Deploy via systemd em cada PC
- Configurar IPs fixos no roteador (DHCP reservation)
- Central agrega `GET /status` dos 3 nós
- Configurar Cloudflare Tunnel no Central
- Registrar URL pública no painel de parceiro HeroSMS
