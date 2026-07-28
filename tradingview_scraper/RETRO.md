# Retro: Orphaned Chrome/chromedriver processes after "stopping" a scrape

**Date:** 2026-07-29
**Area:** `quarterly_annual_collector.py` background scraping runs

## TL;DR

Stopping a background scrape via the task-runner's stop command did **not**
actually kill the underlying Python process. It kept running unnoticed for
hours, continuously spawning new Selenium/Chrome sessions. By the time it was
found, 45 orphaned processes (10 `chromedriver` + 35 headless Chrome
instances) were running, some over 3 days old.

## Timeline

1. Kicked off `quarterly_annual_collector.py --concurrency 5` against a
   204-ticker list in the background.
2. User said "let's stop" partway through; the task-runner's stop command was
   called and reported success.
3. Later, asked to check for stray Chrome sessions — found ~140 Chrome-related
   processes via `ps aux`, including `chromedriver` instances dated `Sun06PM`
   (days old).
4. Killed the `chromedriver` processes first, expecting their child Chrome
   processes to die too. They didn't — process count barely dropped, and new
   ones kept appearing on re-check.
5. Checked for the actual collector process directly and found the *original*
   `quarterly_annual_collector.py` invocation still running under its own PID,
   still actively working through the ticker list and spawning new browser
   sessions. The earlier "stop" had not killed it.
6. Killed that Python process directly, then cleaned up the now-truly-orphaned
   `chromedriver` and Chrome children. Verified the user's regular Chrome and
   an unrelated Playwright MCP browser session were untouched throughout.

## Root cause

The task-runner's stop mechanism reported success but didn't actually
terminate the backgrounded shell command's process tree in this case. Nothing
in the immediate aftermath (a clean "stopped" acknowledgment, no error) gave
any indication the process was still alive — the only way to find out was to
independently check `ps` for the actual PID.

## Impact

- Wasted CPU/memory for hours (up to 3+ days for the oldest leaked instances)
  ~45 processes at its worst.
- The scrape kept silently writing to `company_earnings_data/` after it was
  believed stopped, though in this case no bad data resulted (verified via
  `git status` — nothing appeared modified that hadn't already been
  intentionally committed).

## Fix applied (one-time cleanup)

```bash
# Find the real PID of the collector, don't trust the stop confirmation alone
ps aux | grep quarterly_annual_collector

# Kill the actual process first
kill -9 <pid>

# Then clean up now-orphaned children
pgrep -f "selenium/chromedriver" | xargs -r kill -9
pgrep -f "\-\-test-type=webdriver" | xargs -r kill -9
```

## Prevention / follow-up

- **Always verify a "stop" actually worked.** After stopping any long-running
  background scrape, run `ps aux | grep quarterly_annual_collector` (or the
  relevant script name) to confirm the process is actually gone — don't trust
  a success message alone.
- **Chrome/chromedriver process signature for cleanup:** Selenium-launched
  instances are reliably identifiable via `--test-type=webdriver` (Chrome) and
  the `selenium/chromedriver` cache path (chromedriver). This distinguishes
  them from a user's regular Chrome and from other automation tools (e.g. the
  Playwright MCP browser, which uses `--remote-debugging-pipe` and its own
  `ms-playwright-mcp` user-data-dir instead).
- **Killing `chromedriver` alone is not enough.** Its child Chrome processes
  can outlive it; kill both process groups explicitly.
- **Consider a periodic sanity check** during any large/long multi-hour
  scraping session (e.g. after every background task notification) rather
  than only checking at the very end, so a runaway process is caught sooner.
- Possible future improvement: have `quarterly_annual_collector.py` register
  a cleanup handler (e.g. `atexit`, or track and kill its own child
  `chromedriver` PIDs) so a hard-killed parent doesn't leave orphans — worth
  considering if this recurs.
