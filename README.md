# WFP Tasks

Personal utility scripts and tools for WFP projects monitoring and analysis.

## Quick Start

```bash
# 1. Install dependencies
pip install -r dashboard/requirements.txt

# 2. Connect to VPN

# 3. Launch dashboard
streamlit run dashboard/app.py

# 4. Open browser at http://localhost:8501
```

## Dashboard

Modern web interface for monitoring WFP IDB database health.

### Features

- Real-time monitoring - Connect to dev/prod environments
- Status indicators - Color-coded data freshness
- Trigger analysis - Track trigger execution by country
- SQL views check - Verify views are working
- Export options - JSON, Excel

### Status Legend

| Status | Meaning | Age |
|--------|---------|-----|
| Current | Data is fresh | 0-7 days |
| Recent | Data is recent | 8-30 days |
| Outdated | Data needs attention | 31-90 days |
| Stale | Data is old | 91-365 days |
| Critical | Data is very old | >365 days |

## Scripts

### db_explorer.py

Core database analysis engine (CLI version).

```bash
python3 scripts/db_explorer.py dev   # Development
python3 scripts/db_explorer.py prod  # Production
```

## Requirements

- Python 3.8+
- VPN connection to WFP network
- Dependencies in `dashboard/requirements.txt`

## Structure

```
WFPTasks/
├── dashboard/
│   ├── app.py              # Streamlit dashboard
│   └── requirements.txt    # Python dependencies
├── scripts/
│   └── db_explorer.py      # Database analysis engine
├── .gitignore
└── README.md
```
