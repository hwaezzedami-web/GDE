# Maintenance Engineer Toolkit

Offline Windows desktop app for SS8 platform maintenance engineers. No internet, no AI, no Google needed.

## Features

| Tab | What it does |
|-----|-------------|
| **Dashboard** | Overview of open incidents, P1 count, health checks today, recent activity |
| **Incidents** | Create/track trouble tickets with priority, SLA, customer, status. Export to CSV |
| **RCA** | Generate Root Cause Analysis reports with structured sections. Export to text |
| **Health Checks** | Daily checklist (services, disk, CPU, queues, DB, network, logs, pipeline). History |
| **Runbooks** | Searchable knowledge base with pre-loaded procedures (P1 response, install, DB maintenance, log analysis) |
| **SQL Reference** | Pre-loaded query library for sessions, delivery, queues, performance, data quality |
| **Handover** | Shift handover forms — auto-populates open incidents. Export for email |
| **Comms Templates** | Email templates for acknowledgement, updates, resolution, maintenance, RCA delivery, escalation. Fill variables and copy |

## Build to .exe (Windows)

### Prerequisites
- Python 3.8+ installed on Windows
- pip available in PATH

### Steps
1. Copy the `maintenance_toolkit` folder to your Windows machine
2. Open Command Prompt in that folder
3. Run: `build_exe.bat`
4. Your `.exe` will be at `dist\MaintenanceToolkit.exe`

### Manual build
```
pip install pyinstaller
pyinstaller --onefile --windowed --name MaintenanceToolkit app.py
```

## Usage
- Run `MaintenanceToolkit.exe` (or `python app.py` for dev)
- Data is stored in `data/toolkit.db` (SQLite) next to the app
- First run seeds the database with sample runbooks, SQL queries, and email templates
- Add your own runbooks, queries, and templates as you go

## Data
All data stays local in a SQLite database. No network calls. No telemetry.
