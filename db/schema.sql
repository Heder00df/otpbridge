-- OTPBridge — Schema inicial

CREATE TABLE IF NOT EXISTS modems (
    id          SERIAL PRIMARY KEY,
    imei        VARCHAR(20)  UNIQUE,
    porta_usb   VARCHAR(20),
    porta_audio VARCHAR(20),
    numero      VARCHAR(20) NOT NULL,
    hardware    VARCHAR(20) NOT NULL DEFAULT 'e303',  -- e303 | goip | openvox
    suporta_voz BOOLEAN     NOT NULL DEFAULT FALSE,
    status      VARCHAR(20) NOT NULL DEFAULT 'OFFLINE', -- OFFLINE | FREE | BUSY | ERROR
    ativacao_id VARCHAR(50),
    criado_em   TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ativacoes (
    id              VARCHAR(50)   PRIMARY KEY,  -- UUID gerado pelo OTPBridge
    modem_id        INTEGER       REFERENCES modems(id),
    servico         VARCHAR(20)   NOT NULL,     -- código HeroSMS: tg, wa, go...
    numero          VARCHAR(20)   NOT NULL,
    pais            VARCHAR(10),               -- código do país: 55=BR, 7=RU...
    status          VARCHAR(30)   NOT NULL DEFAULT 'AGUARDANDO',
    -- AGUARDANDO | SMS_RECEBIDO | VOZ_RECEBIDA | PUSH_ENVIADO | CONCLUIDO | CANCELADO | TIMEOUT
    tipo_otp        VARCHAR(10),               -- SMS | VOZ
    codigo_recebido VARCHAR(20),
    valor_recebido  NUMERIC(10,4),             -- valor pago pela HeroSMS por esta ativação
    criado_em       TIMESTAMP     NOT NULL DEFAULT NOW(),
    concluido_em    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sms_log (
    id          SERIAL PRIMARY KEY,
    modem_id    INTEGER     REFERENCES modems(id),
    ativacao_id VARCHAR(50),
    texto_bruto TEXT        NOT NULL,
    codigo      VARCHAR(20),
    criado_em   TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS voz_log (
    id           SERIAL PRIMARY KEY,
    modem_id     INTEGER     REFERENCES modems(id),
    ativacao_id  VARCHAR(50),
    transcricao  TEXT,
    codigo       VARCHAR(20),
    duracao_seg  INTEGER,
    criado_em    TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS eventos (
    id          SERIAL PRIMARY KEY,
    modem_id    INTEGER,
    ativacao_id VARCHAR(50),
    tipo        VARCHAR(50)  NOT NULL,
    -- MODEM_ONLINE | MODEM_OFFLINE | MODEM_ERRO | ATIVACAO_CRIADA
    -- SMS_RECEBIDO | VOZ_RECEBIDA | PUSH_OK | PUSH_ERRO | CONCLUIDO | CANCELADO | TIMEOUT
    detalhe     TEXT,
    criado_em   TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Índices para consultas frequentes
CREATE INDEX IF NOT EXISTS idx_ativacoes_status     ON ativacoes(status);
CREATE INDEX IF NOT EXISTS idx_ativacoes_modem_id   ON ativacoes(modem_id);
CREATE INDEX IF NOT EXISTS idx_ativacoes_servico    ON ativacoes(servico);
CREATE INDEX IF NOT EXISTS idx_ativacoes_criado_em  ON ativacoes(criado_em);
CREATE INDEX IF NOT EXISTS idx_eventos_ativacao_id  ON eventos(ativacao_id);
CREATE INDEX IF NOT EXISTS idx_eventos_criado_em    ON eventos(criado_em);
