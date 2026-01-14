# WFP Tasks

Personal utility scripts and tools for WFP projects monitoring and analysis.

## Scripts

### db_explorer.py
Database health monitoring tool for WFP IDB infrastructure.

**Features:**
- Comprehensive schema exploration
- Data freshness assessment with status indicators
- Trigger system health check by country
- JSON export for further analysis

**Usage:**
```bash
# Requires VPN connection
python3 scripts/db_explorer.py dev   # Development environment
python3 scripts/db_explorer.py prod  # Production environment
```

**Requirements:**
- Python 3.8+
- pymysql
- VPN connection to WFP network

## Structure

```
WFPTasks/
├── scripts/           # Utility scripts
│   └── db_explorer.py
├── .gitignore
└── README.md
```
