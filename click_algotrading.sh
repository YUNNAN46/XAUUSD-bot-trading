#!/bin/bash
# Enable AlgoTrading by clicking the toolbar button after MT5 fully loads.
export DISPLAY=:1
BUTTON_X=312
BUTTON_Y=55
MAX_WAIT=120

echo "[AlgoTrading] Waiting for MT5 window..."
for i in $(seq 1 $MAX_WAIT); do
    WIN=$(xdotool search --onlyvisible --name ".*Server.*" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
        echo "[AlgoTrading] Window found ($WIN), waiting for mt5linux server (port 8001)..."
        for j in $(seq 1 60); do
            if nc -z localhost 8001 2>/dev/null; then
                echo "[AlgoTrading] mt5linux ready, waiting 20s for full MT5 init..."
                sleep 20
                break
            fi
            sleep 2
        done

        # Click up to 5 times with 10s intervals until trade_allowed becomes True
        for attempt in $(seq 1 5); do
            xdotool windowactivate --sync "$WIN" 2>/dev/null
            sleep 0.5
            xdotool windowraise "$WIN" 2>/dev/null
            sleep 0.5
            xdotool windowfocus --sync "$WIN" 2>/dev/null
            sleep 0.5
            xdotool mousemove $BUTTON_X $BUTTON_Y click 1
            echo "[AlgoTrading] Attempt $attempt: clicked at ($BUTTON_X, $BUTTON_Y)"
            sleep 5

            # Verify by checking common.ini Enabled field
            ENABLED=$(python3 -c "
import sys
try:
    path = '/config/.wine/drive_c/Program Files/MetaTrader 5/Config/common.ini'
    c = open(path,'rb').read().decode('utf-16-le','ignore')
    for ln in c.split('\n'):
        if ln.strip().startswith('Enabled='):
            print(ln.strip())
            break
except: print('Enabled=unknown')
" 2>/dev/null)
            echo "[AlgoTrading] common.ini: $ENABLED"
            if [ "$ENABLED" = "Enabled=1" ]; then
                echo "[AlgoTrading] AlgoTrading confirmed ON after attempt $attempt"
                exit 0
            fi
            echo "[AlgoTrading] Not yet ON, retrying in 10s..."
            sleep 10
        done

        echo "[AlgoTrading] All attempts done"
        exit 0
    fi
    sleep 1
done
echo "[AlgoTrading] MT5 window not found after ${MAX_WAIT}s"
exit 1
