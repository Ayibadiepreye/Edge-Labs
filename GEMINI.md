# MANDATORY AGENT RULE: STRICT DATA PRESERVATION & TRASH-ARCHIVE PROTOCOL

> [!CAUTION]
> **ABSOLUTE PROHIBITION ON PERMANENTLY DELETING OR WIPING LOGS / FILES**

1. **NO PERMANENT DELETIONS (SAFE TRASH VAULT ONLY):**
   - You must NEVER execute permanent deletion commands (
m, del, Remove-Item, os.remove, shutil.rmtree, file truncation) on any logs, screenshots, datasets, or code files.
   - If any log rotation, cleanup, or reset is ever needed or requested, you MUST move the files into the designated .trash/ folder instead of deleting them.
   - Files moved to .trash/ must have unique, descriptive timestamped names (e.g., .trash/trade_journal_20260904_215900_backup.csv) so that they can be 100% recovered at any moment.

2. **MANDATORY DOUBLE-CHECK & CONFIRMATION:**
   - Always verify and confirm with the user before performing any cleanup or moving files to .trash/.

3. **PROTECTED DIRECTORIES:**
   - logs/ (trade journals, simulations, tick telemetry)
   - screenshots/ (setup trigger and outcome images)
   - data/ (1s, 1m, 5m price history and streaming ticks)
   - Source code and configurations.
