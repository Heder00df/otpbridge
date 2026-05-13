#!/bin/bash
# Envia um SMS de teste de cada modem para o número alvo.
# Uso: ./tools/test_send_sms.sh 61999342035

DESTINO="${1:?Informe o número destino: ./test_send_sms.sh 61999342035}"

# Garante prefixo +55
[[ "$DESTINO" == +* ]] || DESTINO="+55$DESTINO"

MODEMS=$(mmcli -L 2>/dev/null | grep -oP 'Modem/\K\d+')

for idx in $MODEMS; do
    TEXTO="OTPBridge-MM$idx"
    echo -n "Enviando de MM:$idx → $DESTINO ... "

    SMS_OBJ=$(mmcli -m "$idx" --messaging-create-sms="number=$DESTINO,text=$TEXTO" 2>&1 \
        | grep -oP '/org/freedesktop/ModemManager1/SMS/\d+')

    if [ -z "$SMS_OBJ" ]; then
        echo "ERRO ao criar SMS"
        continue
    fi

    RESULT=$(mmcli --sms "$SMS_OBJ" --send 2>&1)
    if echo "$RESULT" | grep -q "successfully"; then
        echo "OK"
    else
        echo "FALHOU: $RESULT"
    fi
    sleep 2
done
