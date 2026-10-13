"""
SS8 Maintenance Engineer Toolkit
Offline desktop application for telecom platform maintenance.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import json
import os
import sqlite3
from datetime import datetime, timedelta
import csv
import hashlib

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "toolkit.db")


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    ensure_data_dir()
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id TEXT UNIQUE,
        title TEXT NOT NULL,
        priority TEXT DEFAULT 'P3',
        status TEXT DEFAULT 'Open',
        customer TEXT,
        description TEXT,
        root_cause TEXT,
        resolution TEXT,
        created_at TEXT,
        updated_at TEXT,
        sla_deadline TEXT,
        assigned_to TEXT,
        escalated_to TEXT,
        notes TEXT
    );
    CREATE TABLE IF NOT EXISTS rca_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id INTEGER REFERENCES incidents(id),
        title TEXT,
        summary TEXT,
        timeline TEXT,
        root_cause TEXT,
        impact TEXT,
        corrective_actions TEXT,
        preventive_actions TEXT,
        created_at TEXT,
        author TEXT
    );
    CREATE TABLE IF NOT EXISTS health_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_date TEXT,
        operator TEXT,
        platform TEXT,
        checks_json TEXT,
        notes TEXT,
        status TEXT DEFAULT 'OK'
    );
    CREATE TABLE IF NOT EXISTS runbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        category TEXT,
        content TEXT,
        tags TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS handovers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_engineer TEXT,
        to_engineer TEXT,
        shift_date TEXT,
        open_incidents TEXT,
        pending_actions TEXT,
        notes TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS sql_snippets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        query TEXT,
        category TEXT,
        tags TEXT
    );
    CREATE TABLE IF NOT EXISTS customer_comms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_name TEXT,
        category TEXT,
        subject TEXT,
        body TEXT,
        variables TEXT
    );
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        action TEXT,
        details TEXT
    );
    """)
    conn.commit()
    seed_data(conn)
    conn.close()


def seed_data(conn):
    if conn.execute("SELECT COUNT(*) FROM sql_snippets").fetchone()[0] == 0:
        snippets = [
            ("Check Active Sessions", "Count active LI sessions", "SELECT COUNT(*) AS active_sessions\nFROM li_sessions\nWHERE status = 'ACTIVE';", "Sessions", "LI,active"),
            ("Failed Deliveries Last 24h", "Find failed content deliveries", "SELECT target_id, error_code, COUNT(*) AS failures\nFROM delivery_log\nWHERE status = 'FAILED'\n  AND timestamp > NOW() - INTERVAL '24 HOURS'\nGROUP BY target_id, error_code\nORDER BY failures DESC;", "Delivery", "failed,delivery"),
            ("Queue Depth Check", "Monitor message queue sizes", "SELECT queue_name, pending_count, consumer_count\nFROM message_queues\nWHERE pending_count > 1000\nORDER BY pending_count DESC;", "Monitoring", "queue,health"),
            ("Database Connection Pool", "Check DB connection usage", "SELECT datname, numbackends, \n  (SELECT setting FROM pg_settings WHERE name='max_connections') AS max_conn\nFROM pg_stat_database\nWHERE datname NOT LIKE 'template%';", "Database", "connections,pool"),
            ("Disk Usage by Table", "Find large tables consuming disk", "SELECT schemaname, tablename,\n  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size\nFROM pg_tables\nWHERE schemaname NOT IN ('pg_catalog','information_schema')\nORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC\nLIMIT 20;", "Database", "disk,size"),
            ("Location Data Quality", "Validate location accuracy", "SELECT target_id,\n  AVG(accuracy_meters) AS avg_accuracy,\n  COUNT(*) AS total_records,\n  SUM(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 ELSE 0 END) AS null_coords\nFROM location_data\nWHERE timestamp > NOW() - INTERVAL '24 HOURS'\nGROUP BY target_id\nHAVING AVG(accuracy_meters) > 500 OR SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END) > 0;", "Data Quality", "location,accuracy"),
            ("Slow Queries", "Find slow-running queries", "SELECT pid, now() - pg_stat_activity.query_start AS duration, query\nFROM pg_stat_activity\nWHERE state != 'idle'\n  AND now() - pg_stat_activity.query_start > interval '5 minutes'\nORDER BY duration DESC;", "Performance", "slow,query"),
            ("Service Status Check", "Check systemd services", "-- Run via shell:\n-- systemctl list-units --type=service --state=running | grep ss8\n-- Or query service_status table if available:\nSELECT service_name, status, last_heartbeat,\n  CASE WHEN last_heartbeat < NOW() - INTERVAL '5 MINUTES' THEN 'STALE' ELSE 'OK' END AS health\nFROM service_status\nORDER BY service_name;", "Monitoring", "service,health"),
            ("Replication Lag", "Check database replication status", "SELECT client_addr, state, \n  sent_lsn - write_lsn AS write_lag,\n  sent_lsn - flush_lsn AS flush_lag,\n  sent_lsn - replay_lsn AS replay_lag\nFROM pg_stat_replication;", "Database", "replication,lag"),
            ("Audit Trail", "Query provisioning audit log", "SELECT action, target_id, performed_by, timestamp, details\nFROM audit_log\nWHERE timestamp > NOW() - INTERVAL '7 DAYS'\nORDER BY timestamp DESC\nLIMIT 100;", "Audit", "audit,log"),
        ]
        conn.executemany(
            "INSERT INTO sql_snippets (title,description,query,category,tags) VALUES (?,?,?,?,?)",
            snippets,
        )

    if conn.execute("SELECT COUNT(*) FROM customer_comms").fetchone()[0] == 0:
        templates = [
            ("Incident Acknowledgement", "Incident", "RE: Incident {ticket_id} - {title}",
             "Dear {customer_name},\n\nThank you for reporting this issue. We have received your ticket {ticket_id} regarding \"{title}\".\n\nPriority: {priority}\nAssigned Engineer: {engineer_name}\nSLA Target: {sla_target}\n\nWe are currently investigating and will provide an update within {update_interval}.\n\nBest regards,\n{engineer_name}\nSS8 Support Engineer",
             "ticket_id,title,customer_name,priority,engineer_name,sla_target,update_interval"),
            ("Progress Update", "Incident", "UPDATE: Incident {ticket_id} - {title}",
             "Dear {customer_name},\n\nPlease find below an update on incident {ticket_id}:\n\nCurrent Status: {status}\nActions Taken:\n{actions_taken}\n\nNext Steps:\n{next_steps}\n\nEstimated Resolution: {eta}\n\nPlease do not hesitate to contact us if you have any questions.\n\nBest regards,\n{engineer_name}\nSS8 Support Engineer",
             "ticket_id,title,customer_name,status,actions_taken,next_steps,eta,engineer_name"),
            ("Resolution Notification", "Incident", "RESOLVED: Incident {ticket_id} - {title}",
             "Dear {customer_name},\n\nWe are pleased to inform you that incident {ticket_id} has been resolved.\n\nRoot Cause: {root_cause}\nResolution: {resolution}\nResolution Time: {resolution_time}\n\nPreventive measures have been put in place to avoid recurrence.\n\nPlease confirm if the issue is fully resolved on your end so we can close this ticket.\n\nBest regards,\n{engineer_name}\nSS8 Support Engineer",
             "ticket_id,title,customer_name,root_cause,resolution,resolution_time,engineer_name"),
            ("Maintenance Window", "Planned", "PLANNED MAINTENANCE: {system_name} - {date}",
             "Dear {customer_name},\n\nThis is to notify you of a planned maintenance window:\n\nSystem: {system_name}\nDate: {date}\nTime: {start_time} to {end_time} (Local Time)\nImpact: {impact_description}\n\nDuring this window, {affected_services} may experience brief interruptions.\n\nPlease acknowledge receipt of this notification.\n\nBest regards,\n{engineer_name}\nSS8 Support Engineer",
             "customer_name,system_name,date,start_time,end_time,impact_description,affected_services,engineer_name"),
            ("RCA Delivery", "RCA", "ROOT CAUSE ANALYSIS: Incident {ticket_id}",
             "Dear {customer_name},\n\nPlease find attached the Root Cause Analysis for incident {ticket_id}.\n\nSummary:\n{rca_summary}\n\nKey Findings:\n{key_findings}\n\nCorrective Actions:\n{corrective_actions}\n\nWe are available to discuss this report at your convenience.\n\nBest regards,\n{engineer_name}\nSS8 Support Engineer",
             "customer_name,ticket_id,rca_summary,key_findings,corrective_actions,engineer_name"),
            ("Escalation to R&D", "Internal", "ESCALATION: {ticket_id} - {title}",
             "Hi R&D Team,\n\nEscalating the following issue:\n\nTicket: {ticket_id}\nCustomer: {customer}\nPriority: {priority}\nPlatform: {platform}\n\nProblem Description:\n{description}\n\nTroubleshooting Done:\n{troubleshooting}\n\nLogs Attached: {log_files}\n\nRequested Action: {requested_action}\n\nRegards,\n{engineer_name}",
             "ticket_id,title,customer,priority,platform,description,troubleshooting,log_files,requested_action,engineer_name"),
        ]
        conn.executemany(
            "INSERT INTO customer_comms (template_name,category,subject,body,variables) VALUES (?,?,?,?,?)",
            templates,
        )

    if conn.execute("SELECT COUNT(*) FROM runbooks").fetchone()[0] == 0:
        runbooks = [
            ("Daily Health Check Procedure", "Monitoring", """# Daily Health Check Procedure

## 1. System Services
```bash
systemctl list-units --type=service --state=failed
systemctl status ss8-*
```

## 2. Disk Space
```bash
df -h
du -sh /var/log/ss8/*
```
Alert if any partition > 85%

## 3. Memory & CPU
```bash
free -h
top -bn1 | head -20
vmstat 1 5
```

## 4. Message Queues
- Check queue depths in management console
- Alert if any queue > 10,000 pending
- Check consumer count (should be > 0)

## 5. Database
```bash
psql -c "SELECT pg_is_in_recovery();"
psql -c "SELECT count(*) FROM pg_stat_activity;"
```

## 6. Network Connectivity
```bash
ping -c 3 <mediation_server>
netstat -tlnp | grep ss8
```

## 7. Log Review
```bash
tail -100 /var/log/ss8/platform.log | grep -i error
journalctl -u ss8-platform --since "1 hour ago" --priority=err
```

## 8. Data Pipeline
- Verify data flow from network nodes
- Check last successful delivery timestamp
- Compare input vs output counts
""", "health,daily,monitoring"),
            ("P1 Incident Response", "Incident", """# P1 Incident Response Runbook

## Immediate Actions (First 15 minutes)
1. Acknowledge the incident in ticketing system
2. Join the bridge call if one exists
3. Notify your manager
4. Send initial customer acknowledgement

## Diagnosis (15-60 minutes)
1. Check service status: `systemctl status ss8-*`
2. Review recent logs: `journalctl --since "30 min ago" -u ss8-platform`
3. Check if recent changes were deployed
4. Verify network connectivity to all nodes
5. Check database health and replication

## Common P1 Scenarios

### Total Service Outage
- Check if main process is running
- Check database connectivity
- Verify network/firewall rules
- Check disk space (full disk = service crash)

### Data Loss / Gap
- Check ingestion pipeline status
- Verify network node connectivity
- Check message queue for backlog
- Review mediation function logs

### Performance Degradation
- Check CPU/memory usage
- Review slow query log
- Check for table locks
- Verify no bulk operations running

## Escalation
- If not resolved in 1 hour: escalate to R&D
- Include: logs, timeline, troubleshooting done
- Provide remote access if requested

## Resolution
- Verify service is fully restored
- Monitor for 30 minutes post-fix
- Update customer
- Begin RCA within 24 hours
""", "P1,incident,emergency"),
            ("SS8 Component Installation", "Installation", """# SS8 Component Installation Guide

## Pre-Installation Checklist
- [ ] Hardware meets minimum specs (CPU, RAM, Disk)
- [ ] Red Hat Linux version verified
- [ ] Network configuration confirmed
- [ ] Firewall rules opened
- [ ] DNS entries created
- [ ] NTP configured and synced
- [ ] Required certificates obtained

## Installation Steps

### 1. OS Preparation
```bash
yum update -y
yum install -y java-11-openjdk postgresql-client net-tools
setenforce 0  # or configure SELinux policy
firewall-cmd --add-port=8443/tcp --permanent
firewall-cmd --reload
```

### 2. Package Installation
```bash
rpm -ivh ss8-platform-*.rpm
rpm -ivh ss8-mediation-*.rpm
```

### 3. Configuration
- Edit /etc/ss8/platform.conf
- Set database connection string
- Configure mediation endpoints
- Set logging levels

### 4. Database Setup
```bash
psql -U postgres -f /opt/ss8/sql/schema.sql
psql -U postgres -f /opt/ss8/sql/seed.sql
```

### 5. Service Start
```bash
systemctl enable ss8-platform
systemctl start ss8-platform
systemctl status ss8-platform
```

### 6. Validation
- Access web console: https://<server>:8443
- Verify all services show green
- Run integration test suite
- Confirm data flow from test node

## Post-Installation
- Document configuration in CMDB
- Update network diagram
- Create monitoring alerts
- Schedule handover to operations
""", "installation,setup,deployment"),
            ("Log Analysis Guide", "Troubleshooting", """# Log Analysis Guide

## Key Log Locations
- Platform: /var/log/ss8/platform.log
- Mediation: /var/log/ss8/mediation.log
- Database: /var/lib/pgsql/data/log/
- System: /var/log/messages, journalctl

## Common Log Patterns

### Error Levels
- FATAL: Service crash, immediate action
- ERROR: Functional failure, investigate
- WARN: Potential issue, monitor
- INFO: Normal operation

### Useful grep patterns
```bash
# Errors in last hour
grep -E "ERROR|FATAL" /var/log/ss8/platform.log | tail -50

# Connection failures
grep -i "connection refused\|timeout\|unreachable" /var/log/ss8/*.log

# Out of memory
grep -i "OutOfMemoryError\|oom\|Cannot allocate" /var/log/ss8/*.log

# Specific target/session issues
grep "TARGET_ID_HERE" /var/log/ss8/mediation.log | tail -20

# Timestamp range extraction
awk '/2024-01-15 14:0[0-5]/' /var/log/ss8/platform.log
```

## Log Rotation
```bash
# Check rotation config
cat /etc/logrotate.d/ss8

# Force rotation if logs too large
logrotate -f /etc/logrotate.d/ss8
```

## Performance Logs
```bash
# Find slow operations
grep "took [0-9]\\{4,\\}ms" /var/log/ss8/platform.log

# Thread dumps
jstack <PID> > /tmp/thread_dump_$(date +%Y%m%d_%H%M%S).txt
```
""", "logs,troubleshooting,analysis"),
            ("Database Maintenance", "Database", """# Database Maintenance Procedures

## Regular Maintenance

### Vacuum & Analyze (Weekly)
```sql
VACUUM ANALYZE;
-- Or for specific large tables:
VACUUM ANALYZE delivery_log;
VACUUM ANALYZE audit_log;
```

### Check Table Bloat
```sql
SELECT schemaname, tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
```

### Index Health
```sql
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 20;
-- Low idx_scan = potentially unused index
```

### Replication Check
```sql
SELECT client_addr, state, sent_lsn, write_lsn, replay_lsn,
  sent_lsn - replay_lsn AS lag
FROM pg_stat_replication;
```

## Backup Verification
```bash
# Check last backup
ls -la /backup/pg_dump/
# Test restore to temp DB
pg_restore -d testdb /backup/pg_dump/latest.dump
```

## Archive Cleanup
```sql
-- Archive old records (> 90 days)
INSERT INTO delivery_log_archive
SELECT * FROM delivery_log
WHERE timestamp < NOW() - INTERVAL '90 DAYS';

DELETE FROM delivery_log
WHERE timestamp < NOW() - INTERVAL '90 DAYS';
```

## Emergency: Lock Investigation
```sql
SELECT pid, usename, query, state, wait_event_type, wait_event
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;

-- Kill blocking query (use with caution)
SELECT pg_terminate_backend(<PID>);
```
""", "database,maintenance,postgresql"),
        ]
        conn.executemany(
            "INSERT INTO runbooks (title,category,content,tags,created_at,updated_at) VALUES (?,?,?,?,datetime('now'),datetime('now'))",
            runbooks,
        )
    conn.commit()


def log_activity(conn, action, details=""):
    conn.execute(
        "INSERT INTO activity_log (timestamp,action,details) VALUES (?,?,?)",
        (datetime.now().isoformat(), action, details),
    )
    conn.commit()


# ─── GUI ────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Maintenance Engineer Toolkit")
        self.geometry("1200x750")
        self.minsize(1000, 600)
        self.configure(bg="#1e1e2e")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#1e1e2e", foreground="#cdd6f4", fieldbackground="#313244")
        style.configure("TNotebook", background="#1e1e2e")
        style.configure("TNotebook.Tab", background="#313244", foreground="#cdd6f4", padding=[12, 4])
        style.map("TNotebook.Tab", background=[("selected", "#45475a")])
        style.configure("TButton", background="#45475a", foreground="#cdd6f4", padding=6)
        style.map("TButton", background=[("active", "#585b70")])
        style.configure("Accent.TButton", background="#89b4fa", foreground="#1e1e2e")
        style.map("Accent.TButton", background=[("active", "#74c7ec")])
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabelframe", background="#1e1e2e", foreground="#a6adc8")
        style.configure("TLabelframe.Label", background="#1e1e2e", foreground="#a6adc8")
        style.configure("Treeview", background="#313244", foreground="#cdd6f4", fieldbackground="#313244", rowheight=28)
        style.configure("Treeview.Heading", background="#45475a", foreground="#cdd6f4")
        style.map("Treeview", background=[("selected", "#585b70")])
        style.configure("TEntry", fieldbackground="#313244", foreground="#cdd6f4")
        style.configure("TCombobox", fieldbackground="#313244", foreground="#cdd6f4")

        init_db()
        self.conn = get_db()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.incident_tab = IncidentTab(notebook, self.conn)
        self.rca_tab = RCATab(notebook, self.conn)
        self.health_tab = HealthCheckTab(notebook, self.conn)
        self.runbook_tab = RunbookTab(notebook, self.conn)
        self.sql_tab = SQLSnippetTab(notebook, self.conn)
        self.handover_tab = HandoverTab(notebook, self.conn)
        self.comms_tab = CommsTab(notebook, self.conn)
        self.dashboard_tab = DashboardTab(notebook, self.conn)

        notebook.add(self.dashboard_tab, text=" Dashboard ")
        notebook.add(self.incident_tab, text=" Incidents ")
        notebook.add(self.rca_tab, text=" RCA ")
        notebook.add(self.health_tab, text=" Health Checks ")
        notebook.add(self.runbook_tab, text=" Runbooks ")
        notebook.add(self.sql_tab, text=" SQL Reference ")
        notebook.add(self.handover_tab, text=" Handover ")
        notebook.add(self.comms_tab, text=" Comms Templates ")

        self.linux_tab = LinuxCheatSheetTab(notebook)
        notebook.add(self.linux_tab, text=" Linux RHEL ")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.conn.close()
        self.destroy()


# ─── Dashboard ──────────────────────────────────────────────────────────

class DashboardTab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh()

    def build_ui(self):
        header = ttk.Label(self, text="Maintenance Engineer Toolkit", font=("Segoe UI", 18, "bold"))
        header.pack(pady=(20, 5))
        sub = ttk.Label(self, text="Offline toolkit for SS8 platform maintenance", font=("Segoe UI", 10))
        sub.pack(pady=(0, 20))

        cards = ttk.Frame(self)
        cards.pack(fill="x", padx=40)
        self.card_frames = {}
        labels = [
            ("open_incidents", "Open Incidents", "#f38ba8"),
            ("p1_count", "P1 Active", "#fab387"),
            ("health_today", "Health Checks Today", "#a6e3a1"),
            ("runbooks", "Runbooks", "#89b4fa"),
        ]
        for i, (key, title, color) in enumerate(labels):
            f = tk.Frame(cards, bg="#313244", highlightbackground=color, highlightthickness=2)
            f.grid(row=0, column=i, padx=10, pady=10, sticky="nsew")
            cards.columnconfigure(i, weight=1)
            tk.Label(f, text=title, bg="#313244", fg="#a6adc8", font=("Segoe UI", 10)).pack(pady=(12, 0))
            lbl = tk.Label(f, text="0", bg="#313244", fg=color, font=("Segoe UI", 28, "bold"))
            lbl.pack(pady=(0, 12))
            self.card_frames[key] = lbl

        recent_frame = ttk.LabelFrame(self, text="Recent Activity")
        recent_frame.pack(fill="both", expand=True, padx=40, pady=20)
        self.activity_text = scrolledtext.ScrolledText(recent_frame, height=12, bg="#313244", fg="#cdd6f4",
                                                        insertbackground="#cdd6f4", font=("Consolas", 10), wrap="word")
        self.activity_text.pack(fill="both", expand=True, padx=5, pady=5)

        ttk.Button(self, text="Refresh", command=self.refresh, style="Accent.TButton").pack(pady=10)

    def refresh(self):
        r = self.conn.execute("SELECT COUNT(*) FROM incidents WHERE status IN ('Open','In Progress')").fetchone()[0]
        self.card_frames["open_incidents"].config(text=str(r))
        r = self.conn.execute("SELECT COUNT(*) FROM incidents WHERE priority='P1' AND status IN ('Open','In Progress')").fetchone()[0]
        self.card_frames["p1_count"].config(text=str(r))
        today = datetime.now().strftime("%Y-%m-%d")
        r = self.conn.execute("SELECT COUNT(*) FROM health_checks WHERE check_date LIKE ?", (today + "%",)).fetchone()[0]
        self.card_frames["health_today"].config(text=str(r))
        r = self.conn.execute("SELECT COUNT(*) FROM runbooks").fetchone()[0]
        self.card_frames["runbooks"].config(text=str(r))

        self.activity_text.delete("1.0", "end")
        rows = self.conn.execute("SELECT timestamp, action, details FROM activity_log ORDER BY id DESC LIMIT 30").fetchall()
        if rows:
            for row in rows:
                self.activity_text.insert("end", f"[{row['timestamp'][:19]}] {row['action']}: {row['details']}\n")
        else:
            self.activity_text.insert("end", "No activity yet. Start by creating an incident or running a health check.")


# ─── Incidents ──────────────────────────────────────────────────────────

class IncidentTab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh_list()

    def build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=5)
        ttk.Button(top, text="+ New Incident", command=self.new_incident, style="Accent.TButton").pack(side="left")
        ttk.Button(top, text="Export CSV", command=self.export_csv).pack(side="left", padx=5)

        self.filter_var = tk.StringVar(value="All")
        ttk.Label(top, text="  Filter:").pack(side="left")
        cb = ttk.Combobox(top, textvariable=self.filter_var, values=["All", "Open", "In Progress", "Escalated", "Resolved", "Closed"], width=12, state="readonly")
        cb.pack(side="left", padx=5)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_list())

        cols = ("ticket_id", "priority", "status", "customer", "title", "created_at")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (100, 60, 90, 100, 300, 140)):
            self.tree.heading(c, text=c.replace("_", " ").title())
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self.edit_incident)

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

    def refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        filt = self.filter_var.get()
        if filt == "All":
            rows = self.conn.execute("SELECT * FROM incidents ORDER BY id DESC").fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM incidents WHERE status=? ORDER BY id DESC", (filt,)).fetchall()
        for r in rows:
            self.tree.insert("", "end", iid=r["id"],
                             values=(r["ticket_id"], r["priority"], r["status"], r["customer"], r["title"], r["created_at"][:16] if r["created_at"] else ""))

    def new_incident(self):
        IncidentDialog(self, self.conn, callback=self.refresh_list)

    def edit_incident(self, event):
        sel = self.tree.selection()
        if sel:
            IncidentDialog(self, self.conn, incident_id=int(sel[0]), callback=self.refresh_list)

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = self.conn.execute("SELECT * FROM incidents ORDER BY id DESC").fetchall()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in self.conn.execute("SELECT * FROM incidents LIMIT 0").description])
            for r in rows:
                writer.writerow(list(r))
        messagebox.showinfo("Export", f"Exported {len(rows)} incidents to {path}")


class IncidentDialog(tk.Toplevel):
    def __init__(self, parent, conn, incident_id=None, callback=None):
        super().__init__(parent)
        self.conn = conn
        self.incident_id = incident_id
        self.callback = callback
        self.title("Edit Incident" if incident_id else "New Incident")
        self.geometry("650x700")
        self.configure(bg="#1e1e2e")
        self.grab_set()

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        fields = [
            ("Ticket ID:", "ticket_id", "entry"),
            ("Title:", "title", "entry"),
            ("Priority:", "priority", "combo", ["P1", "P2", "P3", "P4"]),
            ("Status:", "status", "combo", ["Open", "In Progress", "Escalated", "Resolved", "Closed"]),
            ("Customer:", "customer", "combo", ["Mobilis", "Djezzy", "Ooredoo", "Internal"]),
            ("Assigned To:", "assigned_to", "entry"),
            ("SLA Deadline:", "sla_deadline", "entry"),
        ]
        self.vars = {}
        for i, f in enumerate(fields):
            ttk.Label(main, text=f[0]).grid(row=i, column=0, sticky="w", pady=3)
            if f[2] == "entry":
                var = tk.StringVar()
                ttk.Entry(main, textvariable=var, width=50).grid(row=i, column=1, sticky="ew", padx=5, pady=3)
            else:
                var = tk.StringVar(value=f[3][0] if not incident_id else "")
                ttk.Combobox(main, textvariable=var, values=f[3], width=47, state="readonly").grid(row=i, column=1, sticky="ew", padx=5, pady=3)
            self.vars[f[1]] = var

        row = len(fields)
        for label, key in [("Description:", "description"), ("Root Cause:", "root_cause"), ("Resolution:", "resolution"), ("Notes:", "notes")]:
            ttk.Label(main, text=label).grid(row=row, column=0, sticky="nw", pady=3)
            txt = scrolledtext.ScrolledText(main, height=4, width=48, bg="#313244", fg="#cdd6f4",
                                             insertbackground="#cdd6f4", font=("Consolas", 9))
            txt.grid(row=row, column=1, sticky="ew", padx=5, pady=3)
            self.vars[key] = txt
            row += 1

        main.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save, style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)
        if incident_id:
            ttk.Button(btn_frame, text="Generate RCA", command=self.gen_rca).pack(side="left", padx=5)

        if incident_id:
            self.load_incident()

    def load_incident(self):
        r = self.conn.execute("SELECT * FROM incidents WHERE id=?", (self.incident_id,)).fetchone()
        if not r:
            return
        for key, var in self.vars.items():
            val = r[key] or ""
            if isinstance(var, tk.StringVar):
                var.set(val)
            else:
                var.delete("1.0", "end")
                var.insert("1.0", val)

    def get_val(self, key):
        v = self.vars[key]
        return v.get() if isinstance(v, tk.StringVar) else v.get("1.0", "end").strip()

    def save(self):
        title = self.get_val("title")
        if not title:
            messagebox.showwarning("Required", "Title is required")
            return
        now = datetime.now().isoformat()
        data = {k: self.get_val(k) for k in self.vars}
        if self.incident_id:
            self.conn.execute("""UPDATE incidents SET ticket_id=?,title=?,priority=?,status=?,customer=?,
                description=?,root_cause=?,resolution=?,updated_at=?,sla_deadline=?,assigned_to=?,notes=? WHERE id=?""",
                (data["ticket_id"], data["title"], data["priority"], data["status"], data["customer"],
                 data["description"], data["root_cause"], data["resolution"], now, data["sla_deadline"],
                 data["assigned_to"], data["notes"], self.incident_id))
            log_activity(self.conn, "Incident Updated", f"{data['ticket_id']} - {data['title']}")
        else:
            tid = data["ticket_id"] or f"INC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            self.conn.execute("""INSERT INTO incidents (ticket_id,title,priority,status,customer,
                description,root_cause,resolution,created_at,updated_at,sla_deadline,assigned_to,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tid, data["title"], data["priority"], data["status"], data["customer"],
                 data["description"], data["root_cause"], data["resolution"], now, now,
                 data["sla_deadline"], data["assigned_to"], data["notes"]))
            log_activity(self.conn, "Incident Created", f"{tid} - {data['title']}")
        self.conn.commit()
        if self.callback:
            self.callback()
        self.destroy()

    def gen_rca(self):
        r = self.conn.execute("SELECT * FROM incidents WHERE id=?", (self.incident_id,)).fetchone()
        if r:
            self.master.master.master.master.children  # navigate to notebook... complex
            # Instead just open a new RCA dialog
            RCADialog(self, self.conn, incident_row=dict(r), callback=None)


# ─── RCA ────────────────────────────────────────────────────────────────

class RCATab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh_list()

    def build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=5)
        ttk.Button(top, text="+ New RCA", command=self.new_rca, style="Accent.TButton").pack(side="left")
        ttk.Button(top, text="Export Selected", command=self.export_rca).pack(side="left", padx=5)

        cols = ("id", "title", "incident_id", "author", "created_at")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (50, 350, 80, 120, 150)):
            self.tree.heading(c, text=c.replace("_", " ").title())
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self.edit_rca)

    def refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        rows = self.conn.execute("SELECT * FROM rca_reports ORDER BY id DESC").fetchall()
        for r in rows:
            self.tree.insert("", "end", iid=r["id"],
                             values=(r["id"], r["title"], r["incident_id"] or "", r["author"], r["created_at"][:16] if r["created_at"] else ""))

    def new_rca(self):
        RCADialog(self, self.conn, callback=self.refresh_list)

    def edit_rca(self, event):
        sel = self.tree.selection()
        if sel:
            RCADialog(self, self.conn, rca_id=int(sel[0]), callback=self.refresh_list)

    def export_rca(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select an RCA to export")
            return
        r = self.conn.execute("SELECT * FROM rca_reports WHERE id=?", (int(sel[0]),)).fetchone()
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt"), ("All", "*.*")],
                                             initialfile=f"RCA_{r['title'].replace(' ','_')}.txt")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._format_rca(r))
        messagebox.showinfo("Export", f"RCA exported to {path}")

    def _format_rca(self, r):
        return f"""{'='*60}
ROOT CAUSE ANALYSIS REPORT
{'='*60}

Title: {r['title']}
Incident ID: {r['incident_id'] or 'N/A'}
Author: {r['author'] or 'N/A'}
Date: {r['created_at'] or 'N/A'}

{'─'*60}
1. EXECUTIVE SUMMARY
{'─'*60}
{r['summary'] or 'N/A'}

{'─'*60}
2. TIMELINE OF EVENTS
{'─'*60}
{r['timeline'] or 'N/A'}

{'─'*60}
3. ROOT CAUSE
{'─'*60}
{r['root_cause'] or 'N/A'}

{'─'*60}
4. IMPACT ASSESSMENT
{'─'*60}
{r['impact'] or 'N/A'}

{'─'*60}
5. CORRECTIVE ACTIONS
{'─'*60}
{r['corrective_actions'] or 'N/A'}

{'─'*60}
6. PREVENTIVE ACTIONS
{'─'*60}
{r['preventive_actions'] or 'N/A'}

{'='*60}
End of Report
{'='*60}
"""


class RCADialog(tk.Toplevel):
    def __init__(self, parent, conn, rca_id=None, incident_row=None, callback=None):
        super().__init__(parent)
        self.conn = conn
        self.rca_id = rca_id
        self.callback = callback
        self.title("Edit RCA" if rca_id else "New RCA")
        self.geometry("750x800")
        self.configure(bg="#1e1e2e")
        self.grab_set()

        canvas = tk.Canvas(self, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        main = ttk.Frame(canvas)
        main.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=main, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.vars = {}
        simple = [("Title:", "title"), ("Author:", "author"), ("Incident ID:", "incident_id")]
        for i, (label, key) in enumerate(simple):
            ttk.Label(main, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=3)
            var = tk.StringVar()
            ttk.Entry(main, textvariable=var, width=60).grid(row=i, column=1, sticky="ew", padx=10, pady=3)
            self.vars[key] = var

        row = len(simple)
        text_fields = [
            ("Executive Summary:", "summary"),
            ("Timeline of Events:", "timeline"),
            ("Root Cause:", "root_cause"),
            ("Impact Assessment:", "impact"),
            ("Corrective Actions:", "corrective_actions"),
            ("Preventive Actions:", "preventive_actions"),
        ]
        for label, key in text_fields:
            ttk.Label(main, text=label).grid(row=row, column=0, sticky="nw", padx=10, pady=3)
            txt = scrolledtext.ScrolledText(main, height=5, width=58, bg="#313244", fg="#cdd6f4",
                                             insertbackground="#cdd6f4", font=("Consolas", 9))
            txt.grid(row=row, column=1, sticky="ew", padx=10, pady=3)
            self.vars[key] = txt
            row += 1

        main.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Save", command=self.save, style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)

        if rca_id:
            self.load_rca()
        elif incident_row:
            self.prefill_from_incident(incident_row)

    def load_rca(self):
        r = self.conn.execute("SELECT * FROM rca_reports WHERE id=?", (self.rca_id,)).fetchone()
        if not r:
            return
        for key, var in self.vars.items():
            val = str(r[key] or "")
            if isinstance(var, tk.StringVar):
                var.set(val)
            else:
                var.delete("1.0", "end")
                var.insert("1.0", val)

    def prefill_from_incident(self, inc):
        self.vars["title"].set(f"RCA - {inc.get('title', '')}")
        self.vars["incident_id"].set(str(inc.get("id", "")))
        if isinstance(self.vars["summary"], scrolledtext.ScrolledText):
            self.vars["summary"].insert("1.0", f"Investigation of incident: {inc.get('title', '')}\nTicket: {inc.get('ticket_id', '')}\nCustomer: {inc.get('customer', '')}\nPriority: {inc.get('priority', '')}")
        if inc.get("root_cause") and isinstance(self.vars["root_cause"], scrolledtext.ScrolledText):
            self.vars["root_cause"].insert("1.0", inc["root_cause"])

    def get_val(self, key):
        v = self.vars[key]
        return v.get() if isinstance(v, tk.StringVar) else v.get("1.0", "end").strip()

    def save(self):
        title = self.get_val("title")
        if not title:
            messagebox.showwarning("Required", "Title is required")
            return
        now = datetime.now().isoformat()
        data = {k: self.get_val(k) for k in self.vars}
        inc_id = data["incident_id"]
        try:
            inc_id = int(inc_id) if inc_id else None
        except ValueError:
            inc_id = None

        if self.rca_id:
            self.conn.execute("""UPDATE rca_reports SET title=?,incident_id=?,summary=?,timeline=?,
                root_cause=?,impact=?,corrective_actions=?,preventive_actions=?,author=? WHERE id=?""",
                (data["title"], inc_id, data["summary"], data["timeline"],
                 data["root_cause"], data["impact"], data["corrective_actions"],
                 data["preventive_actions"], data["author"], self.rca_id))
            log_activity(self.conn, "RCA Updated", data["title"])
        else:
            self.conn.execute("""INSERT INTO rca_reports (title,incident_id,summary,timeline,
                root_cause,impact,corrective_actions,preventive_actions,created_at,author)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (data["title"], inc_id, data["summary"], data["timeline"],
                 data["root_cause"], data["impact"], data["corrective_actions"],
                 data["preventive_actions"], now, data["author"]))
            log_activity(self.conn, "RCA Created", data["title"])
        self.conn.commit()
        if self.callback:
            self.callback()
        self.destroy()


# ─── Health Checks ──────────────────────────────────────────────────────

HEALTH_CHECKLIST = [
    ("System Services", "All SS8 services running (systemctl status ss8-*)"),
    ("Disk Space", "All partitions below 85% usage"),
    ("CPU/Memory", "CPU < 80%, Memory < 85%"),
    ("Message Queues", "All queues < 10,000 pending, consumers > 0"),
    ("Database", "DB responsive, connections < 80% of max, replication OK"),
    ("Network", "All network nodes reachable"),
    ("Logs", "No FATAL/ERROR in last hour"),
    ("Data Pipeline", "Data flowing, no gaps > 5 minutes"),
    ("Certificates", "SSL certs not expiring within 30 days"),
    ("Backups", "Last backup successful and recent"),
    ("NTP", "Clock drift < 1 second"),
    ("Disk I/O", "No I/O wait > 20%"),
]


class HealthCheckTab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh_history()

    def build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        left = ttk.LabelFrame(paned, text="New Health Check")
        paned.add(left, weight=1)

        top_left = ttk.Frame(left)
        top_left.pack(fill="x", padx=5, pady=5)
        ttk.Label(top_left, text="Operator:").pack(side="left")
        self.operator_var = tk.StringVar(value="Mobilis")
        ttk.Combobox(top_left, textvariable=self.operator_var, values=["Mobilis", "Djezzy", "Ooredoo", "Lab"], width=12, state="readonly").pack(side="left", padx=5)
        ttk.Label(top_left, text="Platform:").pack(side="left")
        self.platform_var = tk.StringVar(value="Production")
        ttk.Combobox(top_left, textvariable=self.platform_var, values=["Production", "Staging", "DR"], width=12, state="readonly").pack(side="left", padx=5)

        self.check_vars = []
        check_frame = ttk.Frame(left)
        check_frame.pack(fill="both", expand=True, padx=5, pady=5)
        for i, (name, desc) in enumerate(HEALTH_CHECKLIST):
            var = tk.StringVar(value="SKIP")
            f = ttk.Frame(check_frame)
            f.pack(fill="x", pady=2)
            ttk.Label(f, text=name, width=20, font=("Segoe UI", 9, "bold")).pack(side="left")
            for val, txt in [("OK", "OK"), ("WARN", "WARN"), ("FAIL", "FAIL"), ("SKIP", "Skip")]:
                ttk.Radiobutton(f, text=txt, variable=var, value=val).pack(side="left", padx=3)
            self.check_vars.append((name, desc, var))

        ttk.Label(left, text="Notes:").pack(anchor="w", padx=5)
        self.notes_text = scrolledtext.ScrolledText(left, height=4, bg="#313244", fg="#cdd6f4",
                                                      insertbackground="#cdd6f4", font=("Consolas", 9))
        self.notes_text.pack(fill="x", padx=5, pady=5)

        ttk.Button(left, text="Save Health Check", command=self.save_check, style="Accent.TButton").pack(pady=5)

        right = ttk.LabelFrame(paned, text="History")
        paned.add(right, weight=1)
        cols = ("id", "date", "operator", "status")
        self.history_tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (40, 140, 80, 60)):
            self.history_tree.heading(c, text=c.title())
            self.history_tree.column(c, width=w)
        self.history_tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.history_tree.bind("<Double-1>", self.view_check)

    def save_check(self):
        checks = {}
        overall = "OK"
        for name, desc, var in self.check_vars:
            v = var.get()
            checks[name] = {"description": desc, "status": v}
            if v == "FAIL":
                overall = "FAIL"
            elif v == "WARN" and overall != "FAIL":
                overall = "WARN"

        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO health_checks (check_date,operator,platform,checks_json,notes,status) VALUES (?,?,?,?,?,?)",
            (now, self.operator_var.get(), self.platform_var.get(), json.dumps(checks),
             self.notes_text.get("1.0", "end").strip(), overall))
        log_activity(self.conn, "Health Check", f"{self.operator_var.get()} - {overall}")
        self.conn.commit()
        self.refresh_history()
        for _, _, var in self.check_vars:
            var.set("SKIP")
        self.notes_text.delete("1.0", "end")
        messagebox.showinfo("Saved", f"Health check saved. Overall: {overall}")

    def refresh_history(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        rows = self.conn.execute("SELECT id, check_date, operator, status FROM health_checks ORDER BY id DESC LIMIT 50").fetchall()
        for r in rows:
            self.history_tree.insert("", "end", iid=r["id"],
                                      values=(r["id"], r["check_date"][:16], r["operator"], r["status"]))

    def view_check(self, event):
        sel = self.history_tree.selection()
        if not sel:
            return
        r = self.conn.execute("SELECT * FROM health_checks WHERE id=?", (int(sel[0]),)).fetchone()
        if not r:
            return
        checks = json.loads(r["checks_json"])
        text = f"Date: {r['check_date']}\nOperator: {r['operator']}\nPlatform: {r['platform']}\nOverall: {r['status']}\n\n"
        for name, info in checks.items():
            text += f"  [{info['status']:4s}] {name}: {info['description']}\n"
        if r["notes"]:
            text += f"\nNotes: {r['notes']}"
        win = tk.Toplevel(self)
        win.title(f"Health Check #{r['id']}")
        win.geometry("500x400")
        win.configure(bg="#1e1e2e")
        st = scrolledtext.ScrolledText(win, bg="#313244", fg="#cdd6f4", font=("Consolas", 10))
        st.pack(fill="both", expand=True, padx=10, pady=10)
        st.insert("1.0", text)
        st.config(state="disabled")


# ─── Runbooks ───────────────────────────────────────────────────────────

class RunbookTab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh_list()

    def build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        top_left = ttk.Frame(left)
        top_left.pack(fill="x", pady=5)
        ttk.Button(top_left, text="+ New", command=self.new_runbook, style="Accent.TButton").pack(side="left")
        ttk.Label(top_left, text=" Search:").pack(side="left", padx=(10, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh_list())
        ttk.Entry(top_left, textvariable=self.search_var, width=25).pack(side="left", padx=5)

        self.listbox = tk.Listbox(left, bg="#313244", fg="#cdd6f4", selectbackground="#585b70",
                                   font=("Segoe UI", 10), activestyle="none")
        self.listbox.pack(fill="both", expand=True, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.rb_ids = []

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        self.rb_title = ttk.Label(right, text="Select a runbook", font=("Segoe UI", 14, "bold"))
        self.rb_title.pack(anchor="w", padx=5, pady=5)
        self.rb_category = ttk.Label(right, text="")
        self.rb_category.pack(anchor="w", padx=5)

        self.rb_content = scrolledtext.ScrolledText(right, bg="#313244", fg="#cdd6f4",
                                                      insertbackground="#cdd6f4", font=("Consolas", 10), wrap="word")
        self.rb_content.pack(fill="both", expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Edit", command=self.edit_runbook).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Delete", command=self.delete_runbook).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Export", command=self.export_runbook).pack(side="left", padx=3)

    def refresh_list(self):
        self.listbox.delete(0, "end")
        self.rb_ids.clear()
        search = self.search_var.get().lower()
        rows = self.conn.execute("SELECT id, title, category, tags FROM runbooks ORDER BY title").fetchall()
        for r in rows:
            if search and search not in r["title"].lower() and search not in (r["tags"] or "").lower() and search not in (r["category"] or "").lower():
                continue
            self.listbox.insert("end", f"[{r['category']}] {r['title']}")
            self.rb_ids.append(r["id"])

    def on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        rb_id = self.rb_ids[sel[0]]
        r = self.conn.execute("SELECT * FROM runbooks WHERE id=?", (rb_id,)).fetchone()
        if r:
            self.rb_title.config(text=r["title"])
            self.rb_category.config(text=f"Category: {r['category']}  |  Tags: {r['tags'] or 'none'}")
            self.rb_content.config(state="normal")
            self.rb_content.delete("1.0", "end")
            self.rb_content.insert("1.0", r["content"])
            self.rb_content.config(state="disabled")

    def new_runbook(self):
        RunbookDialog(self, self.conn, callback=self.refresh_list)

    def edit_runbook(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        RunbookDialog(self, self.conn, runbook_id=self.rb_ids[sel[0]], callback=self.refresh_list)

    def delete_runbook(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        if messagebox.askyesno("Confirm", "Delete this runbook?"):
            self.conn.execute("DELETE FROM runbooks WHERE id=?", (self.rb_ids[sel[0]],))
            self.conn.commit()
            self.refresh_list()

    def export_runbook(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        r = self.conn.execute("SELECT * FROM runbooks WHERE id=?", (self.rb_ids[sel[0]],)).fetchone()
        if not r:
            return
        path = filedialog.asksaveasfilename(defaultextension=".md", initialfile=f"{r['title'].replace(' ','_')}.md")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(r["content"])
            messagebox.showinfo("Export", f"Exported to {path}")


class RunbookDialog(tk.Toplevel):
    def __init__(self, parent, conn, runbook_id=None, callback=None):
        super().__init__(parent)
        self.conn = conn
        self.runbook_id = runbook_id
        self.callback = callback
        self.title("Edit Runbook" if runbook_id else "New Runbook")
        self.geometry("700x600")
        self.configure(bg="#1e1e2e")
        self.grab_set()

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        ttk.Label(main, text="Title:").grid(row=0, column=0, sticky="w", pady=3)
        self.title_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.title_var, width=60).grid(row=0, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(main, text="Category:").grid(row=1, column=0, sticky="w", pady=3)
        self.cat_var = tk.StringVar()
        ttk.Combobox(main, textvariable=self.cat_var, values=["Monitoring", "Incident", "Installation", "Troubleshooting", "Database", "Network", "Security", "Other"], width=57).grid(row=1, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(main, text="Tags:").grid(row=2, column=0, sticky="w", pady=3)
        self.tags_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.tags_var, width=60).grid(row=2, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(main, text="Content:").grid(row=3, column=0, sticky="nw", pady=3)
        self.content_text = scrolledtext.ScrolledText(main, height=25, width=58, bg="#313244", fg="#cdd6f4",
                                                        insertbackground="#cdd6f4", font=("Consolas", 10))
        self.content_text.grid(row=3, column=1, sticky="nsew", padx=5, pady=3)
        main.rowconfigure(3, weight=1)
        main.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save, style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)

        if runbook_id:
            r = self.conn.execute("SELECT * FROM runbooks WHERE id=?", (runbook_id,)).fetchone()
            if r:
                self.title_var.set(r["title"])
                self.cat_var.set(r["category"] or "")
                self.tags_var.set(r["tags"] or "")
                self.content_text.insert("1.0", r["content"] or "")

    def save(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("Required", "Title is required")
            return
        now = datetime.now().isoformat()
        content = self.content_text.get("1.0", "end").strip()
        if self.runbook_id:
            self.conn.execute("UPDATE runbooks SET title=?,category=?,content=?,tags=?,updated_at=? WHERE id=?",
                              (title, self.cat_var.get(), content, self.tags_var.get(), now, self.runbook_id))
            log_activity(self.conn, "Runbook Updated", title)
        else:
            self.conn.execute("INSERT INTO runbooks (title,category,content,tags,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                              (title, self.cat_var.get(), content, self.tags_var.get(), now, now))
            log_activity(self.conn, "Runbook Created", title)
        self.conn.commit()
        if self.callback:
            self.callback()
        self.destroy()


# ─── SQL Snippets ───────────────────────────────────────────────────────

class SQLSnippetTab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh_list()

    def build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        top_left = ttk.Frame(left)
        top_left.pack(fill="x", pady=5)
        ttk.Button(top_left, text="+ New", command=self.new_snippet, style="Accent.TButton").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh_list())
        ttk.Label(top_left, text=" Search:").pack(side="left", padx=(10, 0))
        ttk.Entry(top_left, textvariable=self.search_var, width=20).pack(side="left", padx=5)

        self.listbox = tk.Listbox(left, bg="#313244", fg="#cdd6f4", selectbackground="#585b70",
                                   font=("Segoe UI", 10), activestyle="none")
        self.listbox.pack(fill="both", expand=True, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.snippet_ids = []

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        self.snip_title = ttk.Label(right, text="Select a query", font=("Segoe UI", 13, "bold"))
        self.snip_title.pack(anchor="w", padx=5, pady=5)
        self.snip_desc = ttk.Label(right, text="", wraplength=500)
        self.snip_desc.pack(anchor="w", padx=5)

        self.snip_query = scrolledtext.ScrolledText(right, bg="#313244", fg="#a6e3a1",
                                                      insertbackground="#cdd6f4", font=("Consolas", 11), wrap="word")
        self.snip_query.pack(fill="both", expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Copy to Clipboard", command=self.copy_query, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Edit", command=self.edit_snippet).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Delete", command=self.delete_snippet).pack(side="left", padx=3)

    def refresh_list(self):
        self.listbox.delete(0, "end")
        self.snippet_ids.clear()
        search = self.search_var.get().lower()
        rows = self.conn.execute("SELECT id, title, category, tags FROM sql_snippets ORDER BY category, title").fetchall()
        for r in rows:
            if search and search not in r["title"].lower() and search not in (r["tags"] or "").lower() and search not in (r["category"] or "").lower():
                continue
            self.listbox.insert("end", f"[{r['category']}] {r['title']}")
            self.snippet_ids.append(r["id"])

    def on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        r = self.conn.execute("SELECT * FROM sql_snippets WHERE id=?", (self.snippet_ids[sel[0]],)).fetchone()
        if r:
            self.snip_title.config(text=r["title"])
            self.snip_desc.config(text=f"{r['description']}  |  Category: {r['category']}  |  Tags: {r['tags'] or ''}")
            self.snip_query.config(state="normal")
            self.snip_query.delete("1.0", "end")
            self.snip_query.insert("1.0", r["query"])

    def copy_query(self):
        q = self.snip_query.get("1.0", "end").strip()
        if q:
            self.clipboard_clear()
            self.clipboard_append(q)
            messagebox.showinfo("Copied", "Query copied to clipboard")

    def new_snippet(self):
        SnippetDialog(self, self.conn, callback=self.refresh_list)

    def edit_snippet(self):
        sel = self.listbox.curselection()
        if sel:
            SnippetDialog(self, self.conn, snippet_id=self.snippet_ids[sel[0]], callback=self.refresh_list)

    def delete_snippet(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        if messagebox.askyesno("Confirm", "Delete this snippet?"):
            self.conn.execute("DELETE FROM sql_snippets WHERE id=?", (self.snippet_ids[sel[0]],))
            self.conn.commit()
            self.refresh_list()


class SnippetDialog(tk.Toplevel):
    def __init__(self, parent, conn, snippet_id=None, callback=None):
        super().__init__(parent)
        self.conn = conn
        self.snippet_id = snippet_id
        self.callback = callback
        self.title("Edit SQL Snippet" if snippet_id else "New SQL Snippet")
        self.geometry("650x500")
        self.configure(bg="#1e1e2e")
        self.grab_set()

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        for i, (label, key) in enumerate([("Title:", "title"), ("Description:", "description"), ("Category:", "category"), ("Tags:", "tags")]):
            ttk.Label(main, text=label).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            ttk.Entry(main, textvariable=var, width=55).grid(row=i, column=1, sticky="ew", padx=5, pady=3)
            setattr(self, f"var_{key}", var)

        ttk.Label(main, text="Query:").grid(row=4, column=0, sticky="nw", pady=3)
        self.query_text = scrolledtext.ScrolledText(main, height=15, width=53, bg="#313244", fg="#a6e3a1",
                                                      insertbackground="#cdd6f4", font=("Consolas", 10))
        self.query_text.grid(row=4, column=1, sticky="nsew", padx=5, pady=3)
        main.rowconfigure(4, weight=1)
        main.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save, style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)

        if snippet_id:
            r = self.conn.execute("SELECT * FROM sql_snippets WHERE id=?", (snippet_id,)).fetchone()
            if r:
                self.var_title.set(r["title"] or "")
                self.var_description.set(r["description"] or "")
                self.var_category.set(r["category"] or "")
                self.var_tags.set(r["tags"] or "")
                self.query_text.insert("1.0", r["query"] or "")

    def save(self):
        title = self.var_title.get().strip()
        if not title:
            messagebox.showwarning("Required", "Title is required")
            return
        query = self.query_text.get("1.0", "end").strip()
        if self.snippet_id:
            self.conn.execute("UPDATE sql_snippets SET title=?,description=?,query=?,category=?,tags=? WHERE id=?",
                              (title, self.var_description.get(), query, self.var_category.get(), self.var_tags.get(), self.snippet_id))
        else:
            self.conn.execute("INSERT INTO sql_snippets (title,description,query,category,tags) VALUES (?,?,?,?,?)",
                              (title, self.var_description.get(), query, self.var_category.get(), self.var_tags.get()))
        self.conn.commit()
        if self.callback:
            self.callback()
        self.destroy()


# ─── Handover ───────────────────────────────────────────────────────────

class HandoverTab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh_list()

    def build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=5)
        ttk.Button(top, text="+ New Handover", command=self.new_handover, style="Accent.TButton").pack(side="left")
        ttk.Button(top, text="Export", command=self.export_handover).pack(side="left", padx=5)

        cols = ("id", "shift_date", "from_engineer", "to_engineer")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (50, 150, 150, 150)):
            self.tree.heading(c, text=c.replace("_", " ").title())
            self.tree.column(c, width=w)
        self.tree.pack(fill="x", padx=10, pady=5, ipady=60)
        self.tree.bind("<Double-1>", self.view_handover)

        self.detail_text = scrolledtext.ScrolledText(self, bg="#313244", fg="#cdd6f4",
                                                       insertbackground="#cdd6f4", font=("Consolas", 10), wrap="word")
        self.detail_text.pack(fill="both", expand=True, padx=10, pady=5)

    def refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        rows = self.conn.execute("SELECT * FROM handovers ORDER BY id DESC LIMIT 50").fetchall()
        for r in rows:
            self.tree.insert("", "end", iid=r["id"],
                             values=(r["id"], r["shift_date"], r["from_engineer"], r["to_engineer"]))

    def new_handover(self):
        HandoverDialog(self, self.conn, callback=self.refresh_list)

    def view_handover(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.conn.execute("SELECT * FROM handovers WHERE id=?", (int(sel[0]),)).fetchone()
        if not r:
            return
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        text = f"""SHIFT HANDOVER
{'='*50}
Date: {r['shift_date']}
From: {r['from_engineer']}
To: {r['to_engineer']}

OPEN INCIDENTS:
{r['open_incidents'] or 'None'}

PENDING ACTIONS:
{r['pending_actions'] or 'None'}

NOTES:
{r['notes'] or 'None'}
"""
        self.detail_text.insert("1.0", text)

    def export_handover(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a handover to export")
            return
        content = self.detail_text.get("1.0", "end").strip()
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Export", f"Exported to {path}")


class HandoverDialog(tk.Toplevel):
    def __init__(self, parent, conn, callback=None):
        super().__init__(parent)
        self.conn = conn
        self.callback = callback
        self.title("New Shift Handover")
        self.geometry("600x550")
        self.configure(bg="#1e1e2e")
        self.grab_set()

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        ttk.Label(main, text="Date:").grid(row=0, column=0, sticky="w", pady=3)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        ttk.Entry(main, textvariable=self.date_var, width=50).grid(row=0, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(main, text="From:").grid(row=1, column=0, sticky="w", pady=3)
        self.from_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.from_var, width=50).grid(row=1, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(main, text="To:").grid(row=2, column=0, sticky="w", pady=3)
        self.to_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.to_var, width=50).grid(row=2, column=1, sticky="ew", padx=5, pady=3)

        # Auto-populate open incidents
        open_incidents = self.conn.execute(
            "SELECT ticket_id, priority, title FROM incidents WHERE status IN ('Open','In Progress') ORDER BY priority"
        ).fetchall()
        open_text = "\n".join(f"- [{r['priority']}] {r['ticket_id']}: {r['title']}" for r in open_incidents) if open_incidents else "None"

        for i, (label, key, default) in enumerate([
            ("Open Incidents:", "open_incidents", open_text),
            ("Pending Actions:", "pending_actions", ""),
            ("Notes:", "notes", ""),
        ], start=3):
            ttk.Label(main, text=label).grid(row=i, column=0, sticky="nw", pady=3)
            txt = scrolledtext.ScrolledText(main, height=5, width=48, bg="#313244", fg="#cdd6f4",
                                             insertbackground="#cdd6f4", font=("Consolas", 9))
            txt.grid(row=i, column=1, sticky="ew", padx=5, pady=3)
            if default:
                txt.insert("1.0", default)
            setattr(self, f"txt_{key}", txt)

        main.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save, style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)

    def save(self):
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO handovers (from_engineer,to_engineer,shift_date,open_incidents,pending_actions,notes,created_at) VALUES (?,?,?,?,?,?,?)",
            (self.from_var.get(), self.to_var.get(), self.date_var.get(),
             self.txt_open_incidents.get("1.0", "end").strip(),
             self.txt_pending_actions.get("1.0", "end").strip(),
             self.txt_notes.get("1.0", "end").strip(), now))
        log_activity(self.conn, "Handover Created", f"{self.from_var.get()} -> {self.to_var.get()}")
        self.conn.commit()
        if self.callback:
            self.callback()
        self.destroy()


# ─── Comms Templates ───────────────────────────────────────────────────

class CommsTab(ttk.Frame):
    def __init__(self, parent, conn):
        super().__init__(parent)
        self.conn = conn
        self.build_ui()
        self.refresh_list()

    def build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        ttk.Button(left, text="+ New Template", command=self.new_template, style="Accent.TButton").pack(anchor="w", pady=5)

        self.listbox = tk.Listbox(left, bg="#313244", fg="#cdd6f4", selectbackground="#585b70",
                                   font=("Segoe UI", 10), activestyle="none")
        self.listbox.pack(fill="both", expand=True, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.tmpl_ids = []

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        self.tmpl_title = ttk.Label(right, text="Select a template", font=("Segoe UI", 13, "bold"))
        self.tmpl_title.pack(anchor="w", padx=5, pady=5)

        ttk.Label(right, text="Subject:").pack(anchor="w", padx=5)
        self.subject_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.subject_var, width=60, state="readonly").pack(fill="x", padx=5, pady=3)

        ttk.Label(right, text="Variables (fill in to generate):").pack(anchor="w", padx=5, pady=(10, 0))
        self.vars_frame = ttk.Frame(right)
        self.vars_frame.pack(fill="x", padx=5, pady=5)
        self.var_entries = {}

        ttk.Label(right, text="Preview:").pack(anchor="w", padx=5)
        self.preview_text = scrolledtext.ScrolledText(right, bg="#313244", fg="#cdd6f4",
                                                        insertbackground="#cdd6f4", font=("Consolas", 10), wrap="word")
        self.preview_text.pack(fill="both", expand=True, padx=5, pady=5)

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Generate & Copy", command=self.generate, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Export", command=self.export_template).pack(side="left", padx=3)

        self.current_template = None

    def refresh_list(self):
        self.listbox.delete(0, "end")
        self.tmpl_ids.clear()
        rows = self.conn.execute("SELECT id, template_name, category FROM customer_comms ORDER BY category, template_name").fetchall()
        for r in rows:
            self.listbox.insert("end", f"[{r['category']}] {r['template_name']}")
            self.tmpl_ids.append(r["id"])

    def on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        r = self.conn.execute("SELECT * FROM customer_comms WHERE id=?", (self.tmpl_ids[sel[0]],)).fetchone()
        if not r:
            return
        self.current_template = r
        self.tmpl_title.config(text=r["template_name"])
        self.subject_var.set(r["subject"])

        for w in self.vars_frame.winfo_children():
            w.destroy()
        self.var_entries.clear()

        variables = (r["variables"] or "").split(",")
        for i, v in enumerate(variables):
            v = v.strip()
            if not v:
                continue
            ttk.Label(self.vars_frame, text=f"{v}:").grid(row=i, column=0, sticky="w", pady=2)
            entry = ttk.Entry(self.vars_frame, width=40)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
            self.var_entries[v] = entry
        self.vars_frame.columnconfigure(1, weight=1)

        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", r["body"])

    def generate(self):
        if not self.current_template:
            return
        body = self.current_template["body"]
        subject = self.current_template["subject"]
        for var_name, entry in self.var_entries.items():
            val = entry.get() or f"<{var_name}>"
            body = body.replace(f"{{{var_name}}}", val)
            subject = subject.replace(f"{{{var_name}}}", val)

        full = f"Subject: {subject}\n\n{body}"
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", full)

        self.clipboard_clear()
        self.clipboard_append(full)
        messagebox.showinfo("Generated", "Email generated and copied to clipboard")

    def export_template(self):
        content = self.preview_text.get("1.0", "end").strip()
        if not content:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

    def new_template(self):
        CommsDialog(self, self.conn, callback=self.refresh_list)


class CommsDialog(tk.Toplevel):
    def __init__(self, parent, conn, callback=None):
        super().__init__(parent)
        self.conn = conn
        self.callback = callback
        self.title("New Communication Template")
        self.geometry("650x500")
        self.configure(bg="#1e1e2e")
        self.grab_set()

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=15, pady=10)

        for i, (label, key) in enumerate([("Name:", "name"), ("Category:", "category"), ("Subject:", "subject"), ("Variables (comma-sep):", "variables")]):
            ttk.Label(main, text=label).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            ttk.Entry(main, textvariable=var, width=55).grid(row=i, column=1, sticky="ew", padx=5, pady=3)
            setattr(self, f"var_{key}", var)

        ttk.Label(main, text="Body:").grid(row=4, column=0, sticky="nw", pady=3)
        self.body_text = scrolledtext.ScrolledText(main, height=15, width=53, bg="#313244", fg="#cdd6f4",
                                                     insertbackground="#cdd6f4", font=("Consolas", 10))
        self.body_text.grid(row=4, column=1, sticky="nsew", padx=5, pady=3)
        main.rowconfigure(4, weight=1)
        main.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Save", command=self.save, style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)

    def save(self):
        name = self.var_name.get().strip()
        if not name:
            messagebox.showwarning("Required", "Name is required")
            return
        self.conn.execute("INSERT INTO customer_comms (template_name,category,subject,body,variables) VALUES (?,?,?,?,?)",
                          (name, self.var_category.get(), self.var_subject.get(),
                           self.body_text.get("1.0", "end").strip(), self.var_variables.get()))
        self.conn.commit()
        if self.callback:
            self.callback()
        self.destroy()


# ─── Linux RHEL Cheat Sheet ─────────────────────────────────────────────

LINUX_CHEATSHEET = {
    "System Info": [
        ("Hostname & OS version", "hostnamectl"),
        ("Kernel version", "uname -r"),
        ("RHEL release", "cat /etc/redhat-release"),
        ("System uptime", "uptime"),
        ("CPU info", "lscpu"),
        ("Memory info", "free -h"),
        ("Disk usage summary", "df -h"),
        ("Block devices", "lsblk"),
        ("PCI devices", "lspci"),
        ("Hardware summary", "dmidecode --type system"),
        ("Environment variables", "env"),
        ("Current date/time", "timediff  # or: date"),
        ("Timezone", "timedatectl"),
    ],
    "User & Permissions": [
        ("Current user", "whoami"),
        ("User details", "id <username>"),
        ("List logged-in users", "w"),
        ("Switch user", "su - <username>"),
        ("Run as root", "sudo <command>"),
        ("Add user", "useradd -m <username>"),
        ("Set password", "passwd <username>"),
        ("Add to group", "usermod -aG <group> <username>"),
        ("List groups", "groups <username>"),
        ("Change file owner", "chown <user>:<group> <file>"),
        ("Change permissions", "chmod 755 <file>"),
        ("Set ACL", "setfacl -m u:<user>:rwx <file>"),
        ("View ACL", "getfacl <file>"),
        ("sudoers edit", "visudo"),
        ("Lock user account", "usermod -L <username>"),
        ("Unlock user account", "usermod -U <username>"),
    ],
    "File Operations": [
        ("List files (detailed)", "ls -lah"),
        ("Find file by name", "find / -name '<filename>' 2>/dev/null"),
        ("Find files modified today", "find /path -mtime 0"),
        ("Find large files (>100MB)", "find / -size +100M -type f 2>/dev/null"),
        ("Search file content", "grep -rn '<pattern>' /path/"),
        ("Search case-insensitive", "grep -rni '<pattern>' /path/"),
        ("Compare files", "diff <file1> <file2>"),
        ("Copy with preserve", "cp -a <src> <dst>"),
        ("Sync directories", "rsync -avz <src> <dst>"),
        ("Archive & compress", "tar czf archive.tar.gz /path/to/dir"),
        ("Extract tar.gz", "tar xzf archive.tar.gz"),
        ("Disk usage of dir", "du -sh /path/to/dir"),
        ("Disk usage by subdir", "du -h --max-depth=1 /path/ | sort -h"),
        ("Count files in dir", "find /path -type f | wc -l"),
        ("Tail follow a log", "tail -f /var/log/messages"),
        ("Head of file", "head -n 50 <file>"),
        ("View with paging", "less <file>"),
    ],
    "Service Management (systemd)": [
        ("List all services", "systemctl list-units --type=service"),
        ("List failed services", "systemctl list-units --type=service --state=failed"),
        ("Service status", "systemctl status <service>"),
        ("Start service", "systemctl start <service>"),
        ("Stop service", "systemctl stop <service>"),
        ("Restart service", "systemctl restart <service>"),
        ("Reload config (no restart)", "systemctl reload <service>"),
        ("Enable on boot", "systemctl enable <service>"),
        ("Disable on boot", "systemctl disable <service>"),
        ("Check if enabled", "systemctl is-enabled <service>"),
        ("View service logs", "journalctl -u <service>"),
        ("Service logs since boot", "journalctl -u <service> -b"),
        ("Service logs last hour", "journalctl -u <service> --since '1 hour ago'"),
        ("Follow service logs", "journalctl -u <service> -f"),
        ("List timers", "systemctl list-timers"),
        ("Daemon reload (after unit edit)", "systemctl daemon-reload"),
        ("Mask service (prevent start)", "systemctl mask <service>"),
        ("Unmask service", "systemctl unmask <service>"),
    ],
    "Process Management": [
        ("List all processes", "ps aux"),
        ("Process tree", "pstree -p"),
        ("Find process by name", "ps aux | grep <name>"),
        ("Find process by port", "ss -tlnp | grep <port>"),
        ("Interactive top", "top"),
        ("Better top (if installed)", "htop"),
        ("Kill process by PID", "kill <PID>"),
        ("Force kill", "kill -9 <PID>"),
        ("Kill by name", "pkill <name>"),
        ("List open files by process", "lsof -p <PID>"),
        ("Files opened by user", "lsof -u <username>"),
        ("Background a command", "<command> &"),
        ("Bring to foreground", "fg %1"),
        ("List background jobs", "jobs"),
        ("Run immune to hangup", "nohup <command> &"),
        ("Thread count per process", "ps -eLf | grep <name> | wc -l"),
        ("CPU usage per process", "pidstat -p <PID> 1 5"),
    ],
    "Networking": [
        ("IP addresses", "ip addr show"),
        ("Routing table", "ip route"),
        ("DNS resolution", "nslookup <hostname>  # or: dig <hostname>"),
        ("Test connectivity", "ping -c 4 <host>"),
        ("Trace route", "traceroute <host>"),
        ("Listening ports", "ss -tlnp"),
        ("All connections", "ss -anp"),
        ("Established connections", "ss -tnp state established"),
        ("Firewall rules", "firewall-cmd --list-all"),
        ("Open port in firewall", "firewall-cmd --add-port=<port>/tcp --permanent && firewall-cmd --reload"),
        ("Close port", "firewall-cmd --remove-port=<port>/tcp --permanent && firewall-cmd --reload"),
        ("List firewall zones", "firewall-cmd --get-zones"),
        ("Check specific port open", "firewall-cmd --query-port=<port>/tcp"),
        ("Curl test endpoint", "curl -v https://<host>:<port>/path"),
        ("Download file", "wget <url>  # or: curl -O <url>"),
        ("Network stats", "netstat -s"),
        ("ARP table", "arp -a  # or: ip neigh"),
        ("Capture packets", "tcpdump -i <iface> port <port> -w capture.pcap"),
        ("Read pcap", "tcpdump -r capture.pcap"),
        ("Bandwidth per process", "iftop  # or: nethogs"),
    ],
    "Package Management (yum/dnf)": [
        ("Update all packages", "yum update -y  # RHEL 7\ndnf update -y  # RHEL 8/9"),
        ("Install package", "yum install -y <package>"),
        ("Remove package", "yum remove <package>"),
        ("Search package", "yum search <keyword>"),
        ("List installed", "yum list installed"),
        ("Package info", "yum info <package>"),
        ("Which package owns file", "yum provides <file>"),
        ("List repos", "yum repolist"),
        ("Clean cache", "yum clean all"),
        ("Install local RPM", "rpm -ivh <package>.rpm"),
        ("List RPM contents", "rpm -qlp <package>.rpm"),
        ("Verify installed RPM", "rpm -V <package>"),
        ("Check RPM dependencies", "rpm -qpR <package>.rpm"),
        ("History of yum transactions", "yum history"),
        ("Undo last yum transaction", "yum history undo <id>"),
    ],
    "Disk & Filesystem": [
        ("Disk usage", "df -h"),
        ("Inode usage", "df -i"),
        ("Mount a device", "mount /dev/sdX /mnt/point"),
        ("Unmount", "umount /mnt/point"),
        ("List mounts", "mount | column -t"),
        ("Persistent mounts", "cat /etc/fstab"),
        ("Check filesystem", "fsck /dev/sdX  # unmount first!"),
        ("Create ext4 filesystem", "mkfs.ext4 /dev/sdX"),
        ("Create XFS filesystem", "mkfs.xfs /dev/sdX"),
        ("Resize XFS (grow)", "xfs_growfs /mount/point"),
        ("LVM: list volumes", "lvs"),
        ("LVM: list volume groups", "vgs"),
        ("LVM: list physical volumes", "pvs"),
        ("LVM: extend logical vol", "lvextend -L +10G /dev/vgname/lvname"),
        ("LVM: resize filesystem after", "xfs_growfs /mount  # XFS\nresize2fs /dev/vgname/lvname  # ext4"),
        ("Swap usage", "swapon --show"),
        ("IO stats", "iostat -xz 1 5"),
    ],
    "Logs & Journald": [
        ("System log (traditional)", "tail -100 /var/log/messages"),
        ("Auth log", "tail -100 /var/log/secure"),
        ("Boot log", "journalctl -b"),
        ("Kernel messages", "dmesg | tail -50"),
        ("All errors since boot", "journalctl -b -p err"),
        ("Logs by time range", "journalctl --since '2024-01-15 14:00' --until '2024-01-15 15:00'"),
        ("Logs last N minutes", "journalctl --since '30 min ago'"),
        ("Follow all logs", "journalctl -f"),
        ("Disk used by journal", "journalctl --disk-usage"),
        ("Vacuum old journals", "journalctl --vacuum-time=7d"),
        ("Cron logs", "grep CRON /var/log/messages"),
        ("Boot history", "last reboot"),
        ("Login history", "last"),
        ("Failed logins", "lastb"),
        ("Audit log", "ausearch -m avc -ts recent"),
    ],
    "SELinux": [
        ("Current mode", "getenforce"),
        ("Set permissive (temp)", "setenforce 0"),
        ("Set enforcing (temp)", "setenforce 1"),
        ("Persistent config", "vi /etc/selinux/config  # SELINUX=enforcing|permissive|disabled"),
        ("File context", "ls -Z <file>"),
        ("Restore default context", "restorecon -Rv /path"),
        ("List booleans", "getsebool -a"),
        ("Set boolean", "setsebool -P <bool> on"),
        ("Recent denials", "ausearch -m avc -ts recent"),
        ("Generate policy from denial", "ausearch -m avc -ts recent | audit2allow -M mypolicy"),
        ("Apply generated policy", "semodule -i mypolicy.pp"),
        ("Port labels", "semanage port -l | grep <port>"),
        ("Add port label", "semanage port -a -t <type> -p tcp <port>"),
    ],
    "Cron & Scheduling": [
        ("Edit user crontab", "crontab -e"),
        ("List user crontab", "crontab -l"),
        ("System cron jobs", "ls -la /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/"),
        ("Cron syntax", "# MIN HOUR DOM MON DOW command\n# *    *    *   *   *\n# 0    2    *   *   * /script.sh  = daily at 2:00 AM\n# */5  *    *   *   * /script.sh  = every 5 min\n# 0    9    *   *   1-5 /s.sh     = weekdays 9 AM"),
        ("At (one-time)", "echo '/script.sh' | at now + 30 minutes"),
        ("List at jobs", "atq"),
        ("Systemd timer unit", "systemctl list-timers --all"),
    ],
    "Performance & Monitoring": [
        ("CPU usage", "top -bn1 | head -5"),
        ("Memory usage", "free -h"),
        ("Virtual memory stats", "vmstat 1 5"),
        ("IO wait", "iostat -xz 1 5"),
        ("Per-disk IO", "iotop  # needs iotop package"),
        ("Network throughput", "sar -n DEV 1 5"),
        ("CPU history", "sar -u 1 5"),
        ("Load average", "uptime  # or: cat /proc/loadavg"),
        ("Open file descriptors", "cat /proc/sys/fs/file-nr"),
        ("Per-process memory", "ps aux --sort=-%mem | head -20"),
        ("Per-process CPU", "ps aux --sort=-%cpu | head -20"),
        ("System activity report", "sar -A"),
        ("Trace system calls", "strace -p <PID> -c"),
        ("Java thread dump", "jstack <PID> > /tmp/tdump.txt"),
        ("Java heap dump", "jmap -dump:format=b,file=/tmp/heap.bin <PID>"),
    ],
    "SSH & Remote": [
        ("SSH to host", "ssh user@host"),
        ("SSH with key", "ssh -i /path/to/key user@host"),
        ("SCP file to remote", "scp file.txt user@host:/remote/path/"),
        ("SCP from remote", "scp user@host:/remote/file.txt ./"),
        ("SCP directory", "scp -r /local/dir user@host:/remote/"),
        ("SSH tunnel (local port)", "ssh -L 8080:localhost:8443 user@host"),
        ("SSH tunnel (remote port)", "ssh -R 9090:localhost:8080 user@host"),
        ("Generate SSH key", "ssh-keygen -t ed25519 -C 'comment'"),
        ("Copy key to host", "ssh-copy-id user@host"),
        ("SSH config file", "vi ~/.ssh/config\n# Host myserver\n#   HostName 10.0.0.1\n#   User admin\n#   IdentityFile ~/.ssh/id_ed25519"),
        ("Keep alive", "# In ~/.ssh/config:\n# ServerAliveInterval 60\n# ServerAliveCountMax 3"),
    ],
    "Certificates & TLS": [
        ("View cert details", "openssl x509 -in cert.pem -text -noout"),
        ("Check cert expiry", "openssl x509 -in cert.pem -enddate -noout"),
        ("Check remote cert", "openssl s_client -connect host:443 </dev/null 2>/dev/null | openssl x509 -text -noout"),
        ("Remote cert expiry", "echo | openssl s_client -connect host:443 2>/dev/null | openssl x509 -enddate -noout"),
        ("Generate self-signed", "openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout key.pem -out cert.pem"),
        ("Generate CSR", "openssl req -new -newkey rsa:2048 -nodes -keyout key.pem -out request.csr"),
        ("Verify cert matches key", "openssl x509 -noout -modulus -in cert.pem | md5sum\nopenssl rsa -noout -modulus -in key.pem | md5sum"),
        ("Java keystore: list", "keytool -list -v -keystore keystore.jks"),
        ("Java keystore: import", "keytool -import -alias myalias -file cert.pem -keystore keystore.jks"),
        ("System CA bundle (RHEL)", "/etc/pki/tls/certs/ca-bundle.crt"),
        ("Update CA trust", "update-ca-trust"),
    ],
    "NTP & Time": [
        ("Check time sync", "timedatectl"),
        ("NTP sources (chrony)", "chronyc sources -v"),
        ("NTP tracking", "chronyc tracking"),
        ("Force sync", "chronyc makestep"),
        ("Set timezone", "timedatectl set-timezone Africa/Algiers"),
        ("List timezones", "timedatectl list-timezones"),
        ("Chrony config", "cat /etc/chrony.conf"),
        ("Restart chrony", "systemctl restart chronyd"),
    ],
}


class LinuxCheatSheetTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.build_ui()

    def build_ui(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        ttk.Label(left, text="Categories", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 2))
        self.cat_listbox = tk.Listbox(left, bg="#313244", fg="#cdd6f4", selectbackground="#585b70",
                                       font=("Segoe UI", 10), activestyle="none")
        self.cat_listbox.pack(fill="both", expand=True, pady=5)
        self.categories = list(LINUX_CHEATSHEET.keys())
        for cat in self.categories:
            self.cat_listbox.insert("end", f"  {cat}")
        self.cat_listbox.bind("<<ListboxSelect>>", self.on_cat_select)

        ttk.Label(left, text="Search:").pack(anchor="w", pady=(10, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.do_search())
        ttk.Entry(left, textvariable=self.search_var, width=25).pack(fill="x", pady=5)

        right = ttk.Frame(paned)
        paned.add(right, weight=3)

        self.cat_title = ttk.Label(right, text="Select a category", font=("Segoe UI", 14, "bold"))
        self.cat_title.pack(anchor="w", padx=5, pady=5)

        self.content_text = scrolledtext.ScrolledText(right, bg="#313244", fg="#cdd6f4",
                                                        insertbackground="#cdd6f4", font=("Consolas", 11), wrap="word")
        self.content_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.content_text.tag_configure("title", foreground="#89b4fa", font=("Consolas", 11, "bold"))
        self.content_text.tag_configure("cmd", foreground="#a6e3a1", font=("Consolas", 11))
        self.content_text.tag_configure("sep", foreground="#585b70")

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Copy Selected Command", command=self.copy_cmd, style="Accent.TButton").pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Export All to File", command=self.export_all).pack(side="left", padx=3)

        self.cat_listbox.selection_set(0)
        self.show_category(self.categories[0])

    def on_cat_select(self, event):
        sel = self.cat_listbox.curselection()
        if sel:
            self.show_category(self.categories[sel[0]])

    def show_category(self, cat):
        self.cat_title.config(text=f"RHEL Linux — {cat}")
        self.content_text.config(state="normal")
        self.content_text.delete("1.0", "end")
        for desc, cmd in LINUX_CHEATSHEET[cat]:
            self.content_text.insert("end", f"  {desc}\n", "title")
            for line in cmd.split("\n"):
                self.content_text.insert("end", f"    $ {line}\n", "cmd")
            self.content_text.insert("end", "  " + "─" * 60 + "\n", "sep")

    def do_search(self):
        q = self.search_var.get().lower().strip()
        if not q:
            sel = self.cat_listbox.curselection()
            if sel:
                self.show_category(self.categories[sel[0]])
            return
        self.cat_title.config(text=f"Search: '{q}'")
        self.content_text.config(state="normal")
        self.content_text.delete("1.0", "end")
        found = False
        for cat, commands in LINUX_CHEATSHEET.items():
            for desc, cmd in commands:
                if q in desc.lower() or q in cmd.lower():
                    found = True
                    self.content_text.insert("end", f"  [{cat}] {desc}\n", "title")
                    for line in cmd.split("\n"):
                        self.content_text.insert("end", f"    $ {line}\n", "cmd")
                    self.content_text.insert("end", "  " + "─" * 60 + "\n", "sep")
        if not found:
            self.content_text.insert("end", "  No commands found matching your search.")

    def copy_cmd(self):
        try:
            sel = self.content_text.get("sel.first", "sel.last").strip()
            if sel:
                sel = sel.lstrip("$ ").strip()
                self.clipboard_clear()
                self.clipboard_append(sel)
                messagebox.showinfo("Copied", "Command copied to clipboard")
        except tk.TclError:
            messagebox.showinfo("Select", "Highlight a command first, then click Copy")

    def export_all(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="RHEL_Linux_CheatSheet.txt",
                                             filetypes=[("Text", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("RED HAT ENTERPRISE LINUX — COMMAND CHEAT SHEET\n")
            f.write("=" * 60 + "\n\n")
            for cat, commands in LINUX_CHEATSHEET.items():
                f.write(f"\n{'─'*60}\n  {cat.upper()}\n{'─'*60}\n\n")
                for desc, cmd in commands:
                    f.write(f"  {desc}\n")
                    for line in cmd.split("\n"):
                        f.write(f"    $ {line}\n")
                    f.write("\n")
        messagebox.showinfo("Export", f"Cheat sheet exported to {path}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
