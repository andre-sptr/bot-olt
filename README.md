# bot-olt

Python automation scripts for OLT and telecom operations workflows. This repository groups reporting, reminder, and mirroring scripts used to reduce repeated manual work in network operations.

## Scope

- OLT and network operation reporting scripts.
- Reminder and scheduled operational workflows.
- Mirror scripts for several operational data sources.
- Small focused scripts organized by workflow name.

## Project Structure

- `kirim_*.py` - scripts for sending or generating workflow-specific reports.
- `mirror_*.py` - scripts for mirroring operational data.
- `server_reminder.py` - reminder service entrypoint.
- `backup/` - supporting backup assets.
- `tests/` - validation scripts/tests where available.

## Tech Stack

- Python
- Script-based workflow automation
- Telecom and OLT operations

## Getting Started

Use Python 3 and run the script that matches the operational workflow you need:

```bash
python kirim_olt.py
```

Some scripts may depend on local credentials, network access, or operational data sources. Keep real configuration in a local `.env` file and do not commit it.

## Status

Active operational automation project.