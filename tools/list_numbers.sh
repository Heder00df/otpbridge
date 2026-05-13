#!/bin/bash
# Lista todos os modems com seus números, ordenado por índice MM.

echo "┌─────────────┬──────────────────┐"
echo "│ Modem       │ Número           │"
echo "├─────────────┼──────────────────┤"

mmcli -L 2>/dev/null | grep -oP 'Modem/\K\d+' | sort -n | while read idx; do
    NUM=$(mmcli -m "$idx" 2>/dev/null | grep -oP '(?<=own: )\S+' | head -1)
    [ -z "$NUM" ] && NUM="desconhecido"
    printf "│ MM:%-8s │ %-16s │\n" "$idx" "$NUM"
done

echo "└─────────────┴──────────────────┘"
