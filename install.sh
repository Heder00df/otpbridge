#!/bin/bash
# OTPBridge — Instalador automático
# Compatível com Ubuntu 22.04+ e Debian 12+
# Uso: sudo bash install.sh

set -euo pipefail

# ── Cores ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✔ $1${NC}"; }
info() { echo -e "${BLUE}► $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
err()  { echo -e "${RED}✘ $1${NC}"; exit 1; }

# ── Verificações iniciais ─────────────────────────────────
[ "$EUID" -ne 0 ] && err "Execute como root: sudo bash install.sh"

. /etc/os-release
[[ "$ID" != "ubuntu" && "$ID" != "debian" ]] && err "Apenas Ubuntu/Debian suportados."

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║          OTPBridge — Instalador          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Configurações ─────────────────────────────────────────
INSTALL_DIR="/opt/otpbridge"
SERVICE_USER="otpbridge"
DB_NAME="otpbridge"
DB_USER="otpbridge"
DB_PASS=$(openssl rand -hex 16)

# ── Coleta de informações ─────────────────────────────────
info "Configuração inicial"
echo ""

read -rp "Chave de agente HeroSMS: " HEROSMS_KEY
[ -z "$HEROSMS_KEY" ] && err "Chave HeroSMS é obrigatória."

read -rp "Chave de acesso da sua API (pressione Enter para gerar): " SUPPLIER_KEY
[ -z "$SUPPLIER_KEY" ] && SUPPLIER_KEY=$(openssl rand -hex 16)

read -rp "Porta da API [8000]: " PORT
PORT=${PORT:-8000}

echo ""
info "Instalando em: $INSTALL_DIR"
info "Usuário do serviço: $SERVICE_USER"
info "Porta: $PORT"
echo ""

# ── Dependências do sistema ───────────────────────────────
info "Instalando dependências do sistema..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    postgresql postgresql-client \
    modemmanager \
    git curl openssl \
    udev \
    > /dev/null
ok "Dependências instaladas"

# ── Usuário do sistema ────────────────────────────────────
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
    ok "Usuário $SERVICE_USER criado"
fi

# Adiciona ao grupo dialout para acesso às portas seriais
usermod -aG dialout "$SERVICE_USER" 2>/dev/null || true

# ── Código-fonte ──────────────────────────────────────────
info "Baixando OTPBridge..."
if [ -d "$INSTALL_DIR" ]; then
    warn "Diretório $INSTALL_DIR já existe — atualizando..."
    git -C "$INSTALL_DIR" pull -q
else
    git clone -q --branch sms-only \
        https://github.com/Heder00df/otpbridge.git "$INSTALL_DIR"
fi
ok "Código obtido"

# ── Ambiente Python ───────────────────────────────────────
info "Criando ambiente virtual Python..."
python3 -m venv "$INSTALL_DIR/.venv" > /dev/null
"$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
ok "Dependências Python instaladas"

# ── Banco de dados ────────────────────────────────────────
info "Configurando PostgreSQL..."
systemctl start postgresql
systemctl enable postgresql -q

# Cria usuário e banco se não existirem
su -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\" | grep -q 1 || \
       psql -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASS'\"" postgres

su -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\" | grep -q 1 || \
       psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER\"" postgres

# Roda o schema
su -c "psql -d $DB_NAME -f $INSTALL_DIR/db/schema.sql" postgres

ok "Banco de dados configurado"

# ── Arquivo .env ──────────────────────────────────────────
info "Criando configuração..."
cat > "$INSTALL_DIR/.env" << EOF
HEROSMS_KEY=$HEROSMS_KEY
SUPPLIER_KEY=$SUPPLIER_KEY
HARDWARE_TYPE=e303
DEVICES=[]
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
PORT=$PORT
EOF
chmod 600 "$INSTALL_DIR/.env"
ok "Arquivo .env criado"

# ── Permissões ────────────────────────────────────────────
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
ok "Permissões configuradas"

# ── udev — Huawei E303 ────────────────────────────────────
info "Configurando regras udev para modems Huawei E303..."

cat > /etc/udev/rules.d/77-huawei-e303.rules << 'EOF'
ACTION!="add|change|move|bind", GOTO="mm_e303_end"
SUBSYSTEMS=="usb", ATTRS{idVendor}=="12d1", ATTRS{idProduct}=="1506", GOTO="mm_e303_check"
GOTO="mm_e303_end"

LABEL="mm_e303_check"
SUBSYSTEMS=="usb-serial", ENV{.MM_USBIFNUM}=="00", ENV{ID_MM_PORT_IGNORE}="1"
SUBSYSTEMS=="usb-serial", ENV{.MM_USBIFNUM}=="01", ENV{ID_MM_PORT_TYPE_AT_PRIMARY}="1"
SUBSYSTEMS=="usb-serial", ENV{.MM_USBIFNUM}=="02", ENV{ID_MM_PORT_TYPE_AT_SECONDARY}="1"

LABEL="mm_e303_end"
EOF

cat > /etc/udev/rules.d/99-usb-autosuspend-huawei.rules << 'EOF'
ACTION=="add", SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", ATTRS{idProduct}=="1506", TEST=="power/autosuspend", ATTR{power/autosuspend}="-1"
EOF

udevadm control --reload-rules
udevadm trigger
ok "Regras udev instaladas"

# ── ModemManager ──────────────────────────────────────────
info "Habilitando ModemManager..."
systemctl enable ModemManager -q
systemctl restart ModemManager
ok "ModemManager ativo"

# ── Serviço systemd ───────────────────────────────────────
info "Instalando serviço systemd..."
cat > /etc/systemd/system/otpbridge.service << EOF
[Unit]
Description=OTPBridge SMS Gateway
After=network.target postgresql.service ModemManager.service
Requires=postgresql.service ModemManager.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/.venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable otpbridge -q
systemctl start otpbridge
ok "Serviço otpbridge instalado e iniciado"

# ── Healthcheck cron ──────────────────────────────────────
info "Instalando healthcheck automático..."
CRON_JOB="*/5 * * * * $INSTALL_DIR/tools/healthcheck_modems.sh >> /var/log/otpbridge-health.log 2>&1"
( crontab -l 2>/dev/null | grep -v "healthcheck_modems"; echo "$CRON_JOB" ) | crontab -
ok "Healthcheck instalado (a cada 5 minutos)"

# ── Resumo final ──────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              Instalação concluída!                   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
ok "OTPBridge rodando em http://0.0.0.0:$PORT"
echo ""
echo "  Chave da sua API : $SUPPLIER_KEY"
echo "  Banco de dados   : postgresql://$DB_USER:****@localhost/$DB_NAME"
echo "  Logs             : sudo journalctl -u otpbridge -f"
echo "  Status           : sudo systemctl status otpbridge"
echo ""
warn "Conecte os modems Huawei E303 e aguarde ~30s para detecção automática."
echo ""
echo "  Verificar modems : mmcli -L"
echo "  Listar números   : source $INSTALL_DIR/.venv/bin/activate && python3 $INSTALL_DIR/tools/list_numbers.py"
echo ""
