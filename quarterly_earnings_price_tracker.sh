#!/bin/bash
#
# Quarterly Earnings Price Tracker Service Control Script
# Usage: ./quarterly_earnings_price_tracker.sh {start|stop|status|logs}
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$SCRIPT_DIR/quarterly_earnings_price_tracker.pid"
LOGFILE="$SCRIPT_DIR/quarterly_earnings_price_tracker.log"

# Configure your command here
SPREADSHEET_ID="1UDqEa__FQPbAFWLSJ69zKDJwtaEbym_o0r3N3GElDIA"
INTERVAL="30"
TAB_NAME="LivePrices"
FETCHED_EARNING_DATA_TAB_NAME="Earnings_Data"




# Optional: earnings script trigger command (leave empty to disable)
ON_NEW_TICKERS_CMD="cd $SCRIPT_DIR/tradingview_scraper && python run_earnings_to_sheets.py --tickers-file ../tickers_from_spreadsheet.txt --spreadsheet-id $SPREADSHEET_ID --date {date} --tab-name $FETCHED_EARNING_DATA_TAB_NAME --quarter-mode forecast --concurrency 5 --expand-to-near-by-days 3 --skip-existing-tickers-col A"

# Build the command
CMD="python $SCRIPT_DIR/update_extended_hours_prices.py"
CMD="$CMD --spreadsheet-id $SPREADSHEET_ID"
CMD="$CMD --tab-name $TAB_NAME"
CMD="$CMD --row 2"
CMD="$CMD --col D"
CMD="$CMD --ticker-col A"
CMD="$CMD --prev-close-col B"
CMD="$CMD --close-col C"
CMD="$CMD --market-price-col E"
CMD="$CMD --pct-change-col F"
CMD="$CMD --diff-col G"
CMD="$CMD --daemon"
CMD="$CMD --interval $INTERVAL"


if [ -n "$ON_NEW_TICKERS_CMD" ]; then
    CMD="$CMD --on-new-tickers-cmd \"$ON_NEW_TICKERS_CMD\""
fi

case "$1" in
    start)
        if [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
            echo "Already running (PID $(cat $PIDFILE))"
            exit 1
        else
            echo "Starting quarterly earnings price tracker..."
            echo "Log file: $LOGFILE"
            cd "$SCRIPT_DIR"
            # Use eval to properly handle quoted arguments
            eval "nohup $CMD >> \"$LOGFILE\" 2>&1 &"
            echo $! > "$PIDFILE"
            sleep 1
            if kill -0 $(cat "$PIDFILE") 2>/dev/null; then
                echo "Started (PID $(cat $PIDFILE))"
            else
                echo "Failed to start. Check $LOGFILE for errors."
                rm -f "$PIDFILE"
                exit 1
            fi
        fi
        ;;
    stop)
        if [ -f "$PIDFILE" ]; then
            PID=$(cat "$PIDFILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "Stopping quarterly earnings price tracker (PID $PID)..."
                kill "$PID"
                sleep 2
                if kill -0 "$PID" 2>/dev/null; then
                    echo "Process didn't stop, forcing..."
                    kill -9 "$PID"
                fi
                rm -f "$PIDFILE"
                echo "Stopped"
            else
                echo "Process not running, cleaning up PID file"
                rm -f "$PIDFILE"
            fi
        else
            echo "Not running (no PID file)"
        fi
        ;;
    restart)
        $0 stop
        sleep 1
        $0 start
        ;;
    status)
        if [ -f "$PIDFILE" ]; then
            PID=$(cat "$PIDFILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "Running (PID $PID)"
                # Show uptime if possible
                if command -v ps &> /dev/null; then
                    ELAPSED=$(ps -o etime= -p "$PID" 2>/dev/null | xargs)
                    if [ -n "$ELAPSED" ]; then
                        echo "Uptime: $ELAPSED"
                    fi
                fi
            else
                echo "Not running (stale PID file)"
            fi
        else
            echo "Not running"
        fi
        ;;
    logs)
        if [ -f "$LOGFILE" ]; then
            tail -f "$LOGFILE"
        else
            echo "No log file found at $LOGFILE"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the quarterly earnings price tracker daemon"
        echo "  stop    - Stop the quarterly earnings price tracker daemon"
        echo "  restart - Restart the quarterly earnings price tracker daemon"
        echo "  status  - Check if the daemon is running"
        echo "  logs    - Tail the log file"
        exit 1
        ;;
esac
