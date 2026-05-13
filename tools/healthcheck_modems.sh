#!/bin/bash
# Reinicia modems Huawei E303 que estiverem em estado 'failed' no ModemManager.
# Rodar via cron a cada 5 minutos:
#   */5 * * * * /home/heder/dev/projetos/otpbridge/tools/healthcheck_modems.sh >> /var/log/otpbridge-health.log 2>&1

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

mapfile -t FAILED < <(mmcli -L 2>/dev/null | grep -oP 'Modem/\K\d+' | while read idx; do
    state=$(mmcli -m "$idx" 2>/dev/null | grep -oP '(?<=state: )\S+' | head -1)
    [ "$state" = "failed" ] && echo "$idx"
done)

if [ ${#FAILED[@]} -eq 0 ]; then
    exit 0
fi

echo "[$TIMESTAMP] modems em failed: ${FAILED[*]}"

for idx in "${FAILED[@]}"; do
    echo "[$TIMESTAMP] resetando modem $idx..."
    mmcli -m "$idx" --reset 2>/dev/null && echo "[$TIMESTAMP] modem $idx resetado OK" || echo "[$TIMESTAMP] falha ao resetar modem $idx"
done
