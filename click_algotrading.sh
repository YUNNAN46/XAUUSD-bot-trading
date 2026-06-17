#!/bin/bash
# Enable AlgoTrading by clicking the toolbar button after MT5 fully loads.
export DISPLAY=:1
BUTTON_X=283
BUTTON_Y=56
MAX_WAIT=120

echo "[AlgoTrading] Waiting for MT5 window..."
for i in $(seq 1 $MAX_WAIT); do
    WIN=$(xdotool search --onlyvisible --name ".*Server.*" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
        echo "[AlgoTrading] Window found ($WIN), waiting for mt5linux server (port 8001)..."
        # Wait until mt5linux server is accepting connections (MT5 fully loaded)
        for j in $(seq 1 60); do
            if nc -z localhost 8001 2>/dev/null; then
                echo "[AlgoTrading] mt5linux ready, clicking in 5s..."
                sleep 5
                break
            fi
            sleep 2
        done
        xdotool windowactivate --sync "$WIN" 2>/dev/null
        sleep 1
        xdotool windowfocus --sync "$WIN" 2>/dev/null
        sleep 0.5
        xdotool mousemove $BUTTON_X $BUTTON_Y click 1
        echo "[AlgoTrading] Algo Trading button clicked at ($BUTTON_X, $BUTTON_Y)"
        exit 0
    fi
    sleep 1
done
echo "[AlgoTrading] MT5 window not found after ${MAX_WAIT}s"
exit 1
