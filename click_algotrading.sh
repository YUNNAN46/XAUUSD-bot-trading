#!/bin/bash
# Wait for MT5 window to appear, then click the Algo Trading button to enable it.
export DISPLAY=:1
BUTTON_X=283
BUTTON_Y=56
MAX_WAIT=120

echo "[AlgoTrading] Waiting for MT5 window..."
for i in $(seq 1 $MAX_WAIT); do
    WIN=$(xdotool search --onlyvisible --name ".*Server.*" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
        echo "[AlgoTrading] Window found ($WIN), waiting 20s for full init..."
        sleep 20
        xdotool windowfocus --sync "$WIN" 2>/dev/null
        sleep 1
        xdotool mousemove $BUTTON_X $BUTTON_Y click 1
        echo "[AlgoTrading] Algo Trading button clicked at ($BUTTON_X, $BUTTON_Y)"
        exit 0
    fi
    sleep 1
done
echo "[AlgoTrading] MT5 window not found after ${MAX_WAIT}s"
exit 1
