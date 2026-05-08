#!/bin/bash
# Cria o banco e aplica o schema.
# Rodar uma vez no servidor: bash db/setup.sh

set -e

DB_NAME="otpbridge"
DB_USER="otpbridge"
DB_PASS="otpbridge"

echo "=== OTPBridge — Setup do Banco ==="

# Instala PostgreSQL se necessário
if ! command -v psql &> /dev/null; then
    echo "Instalando PostgreSQL..."
    apt update && apt install -y postgresql postgresql-contrib
fi

# Cria usuário e banco
sudo -u postgres psql <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
    CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
EOF

# Aplica schema
PGPASSWORD=$DB_PASS psql -U $DB_USER -d $DB_NAME -f "$(dirname "$0")/schema.sql"

echo ""
echo "=== Banco pronto ==="
echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
