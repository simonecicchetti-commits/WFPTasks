#!/usr/bin/env python3
"""
WFP IDB Database Explorer v1.6
==============================
Database health monitoring and analysis tool for WFP IDB infrastructure.

Features:
- Comprehensive schema exploration
- Data freshness assessment with status indicators
- Trigger system health check by country
- Automatic reconnection handling
- JSON export for further analysis

Requirements:
- VPN connection to WFP network
- Python 3.8+
- pymysql

Usage:
    python3 db_explorer.py [dev|prod]

Example:
    python3 db_explorer.py dev
"""

import pymysql
import json
import os
import sys
import time
from datetime import datetime, date, timedelta
from decimal import Decimal

# Database configuration
DB_CONFIG = {
    'dev': {
        'host': 'rdp-idb-dev.chsu4ma0ibqc.eu-west-1.rds.amazonaws.com',
        'port': 3306,
        'user': 'dev',
        'password': '2024devHelloWorld.',
    },
    'prod': {
        'host': 'rbp-idb-prod.cxai6uauo3yn.eu-west-1.rds.amazonaws.com',
        'port': 3306,
        'user': 'prod',
        'password': '2024panamaIDB!',
    }
}

# Schemas to explore
SCHEMAS_TO_EXPLORE = ['idb', 'rbp', 'rtm_raw', 'rtm_clean', 'rtm_analytics', 'caricom_other_data']

# Column types to exclude from sample (to avoid large JSON output)
BLOB_TYPES = ('blob', 'longblob', 'mediumblob', 'tinyblob', 'binary', 'varbinary')

# Known SQL views (from modules/trigger/src/domain/utils/db_utils.py)
KNOWN_VIEWS = [
    'RBP_combined_prevalence_fs',
    'RBP_conflict_related_fatalities_30days',
    'RBP_protests_riots_30days',
    'RBP_combined_prevalence_fs_adm1'
]

# Key IDB tables - Complete list from RBP_IDB repository
# Source: modules/fetcher/src/domain/utils/db_utils.py (DBHelper class)
#         modules/trigger/src/domain/utils/db_utils.py (DBHelper class)
IDB_KEY_TABLES = [
    # === MAPPING TABLES (static) ===
    'RBP_adm0_mapping',
    'RBP_adm1_mapping',

    # === FOOD SECURITY INDICATORS ===
    'RBP_fcs',
    'RBP_fcs_adm0',
    'RBP_fcs_low_quality',
    'RBP_rcsi',
    'RBP_rcsi_adm0',
    'RBP_rcsi_low_quality',
    'RBP_ipc_adm0',
    'RBP_pou',

    # === ECONOMIC INDICATORS ===
    'RBP_food_inflation',
    'RBP_currency_exchange',

    # === CONFLICT DATA (ACLED) ===
    'RBP_ACLED_conflict',

    # === CLIMATE DATA ===
    'RBP_climate_anomaly',
    'RBP_rainfall_ndvi_seasonality',

    # === NATURAL HAZARDS ===
    'RBP_ADAM_cyclon',
    'RBP_ADAM_earthquake',
    'RBP_ADAM_flood',
    'RBP_PDC_hazard',

    # === POPULATION ===
    'RBP_population',
    'RBP_population_adm1',

    # === MIGRATION (Panama Darien) ===
    'RBP_panama_darien_nationality',
    'RBP_panama_darien_agesex',
    'RBP_usa_encounters',

    # === ALERTS (HungerMap Live) ===
    'RBP_adm0_hml_alert',
    'RBP_adm1_hml_alert',

    # === TRIGGER SYSTEM OUTPUT ===
    'RBP_climate_alert',
    'RBP_conflict_alert',
    'RBP_economic_alert',
    'RBP_food_security_alert',
    'RBP_hazard_alert',
    'RBP_trigger_result',
    'RBP_IDB_tableau'
]

# Timeout configuration - Aligned with RBP_IDB repository
# Source: modules/fetcher/src/domain/utils/db_utils.py line 40
CONNECTION_TIMEOUT = 300  # 5 minutes
READ_TIMEOUT = 300        # 5 minutes
WRITE_TIMEOUT = 300       # 5 minutes


def json_serializer(obj):
    """Custom JSON serializer for non-standard types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8', errors='replace')
        except Exception:
            return "<binary data>"
    if obj is None:
        return None
    raise TypeError(f"Type {type(obj)} not serializable")


def get_row_count_fast(cursor, schema, table_name):
    """
    Get row count efficiently.
    First tries information_schema (fast but estimated),
    then falls back to COUNT(*) for small tables.
    """
    try:
        cursor.execute("""
            SELECT TABLE_ROWS
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """, (schema, table_name))
        result = cursor.fetchone()
        if result and result.get('TABLE_ROWS') is not None:
            estimated = result['TABLE_ROWS']
            if estimated < 100000:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`;")
                return cursor.fetchone()['cnt'], False
            return estimated, True
    except Exception:
        pass

    try:
        cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`;")
        return cursor.fetchone()['cnt'], False
    except Exception:
        return None, False


def create_connection(config):
    """Create a new database connection with proper timeout settings."""
    return pymysql.connect(
        host=config['host'],
        port=config['port'],
        user=config['user'],
        password=config['password'],
        charset='utf8mb4',
        connect_timeout=CONNECTION_TIMEOUT,
        read_timeout=READ_TIMEOUT,
        write_timeout=WRITE_TIMEOUT,
        cursorclass=pymysql.cursors.DictCursor
    )


def safe_execute(cursor, connection, config, query, params=None, max_retries=2):
    """
    Execute a query with automatic retry on disconnection.
    Handles error (0, '') which indicates lost connection.
    """
    for attempt in range(max_retries + 1):
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall() if cursor.description else None
        except pymysql.err.Error as e:
            error_code = e.args[0] if e.args else 'unknown'
            if error_code in (0, 2013, 2006) and attempt < max_retries:
                print(f"   ⚠ Connection lost, attempt {attempt + 2}...")
                time.sleep(2)
                try:
                    connection.ping(reconnect=True)
                except Exception:
                    pass
            else:
                raise
    return None


def explore_database(env='dev'):
    """Explore the database and collect information."""

    config = DB_CONFIG.get(env)
    if not config:
        print(f"Invalid environment '{env}'. Use 'dev' or 'prod'.")
        return None

    results = {
        'metadata': {
            'environment': env,
            'host': config['host'],
            'timestamp': datetime.now().isoformat(),
            'script_version': '1.6',
            'timeouts': {
                'connect': CONNECTION_TIMEOUT,
                'read': READ_TIMEOUT,
                'write': WRITE_TIMEOUT
            }
        },
        'databases': [],
        'schemas': {},
        'errors': []
    }

    try:
        print(f"\n{'='*60}")
        print(f"Connecting to {env.upper()}: {config['host']}")
        print(f"Timeout: connect={CONNECTION_TIMEOUT}s, read={READ_TIMEOUT}s")
        print(f"{'='*60}\n")

        connection = create_connection(config)

        print("✓ Connection established!\n")

        with connection.cursor() as cursor:
            # 1. List all databases
            print("1. Retrieving database list...")
            cursor.execute("SHOW DATABASES;")
            databases = [row['Database'] for row in cursor.fetchall()]
            results['databases'] = databases
            print(f"   Found {len(databases)} databases: {', '.join(databases)}\n")

            # 2. Explore each schema of interest
            for schema in SCHEMAS_TO_EXPLORE:
                if schema not in databases:
                    print(f"⚠ Schema '{schema}' not found, skipping...")
                    continue

                print(f"2. Exploring schema: {schema}")
                results['schemas'][schema] = {
                    'tables': [],
                    'views': [],
                    'table_details': {}
                }

                try:
                    cursor.execute(f"USE `{schema}`;")

                    cursor.execute("SHOW FULL TABLES;")
                    tables_info = cursor.fetchall()

                    for table_row in tables_info:
                        table_name = list(table_row.values())[0]
                        table_type = list(table_row.values())[1]

                        if table_type == 'BASE TABLE':
                            results['schemas'][schema]['tables'].append(table_name)
                        else:
                            results['schemas'][schema]['views'].append(table_name)

                        try:
                            try:
                                connection.ping(reconnect=True)
                                cursor.execute(f"USE `{schema}`;")
                            except Exception:
                                print(f"   ⚠ Reconnecting to {schema}...")
                                connection = create_connection(config)
                                cursor = connection.cursor()
                                cursor.execute(f"USE `{schema}`;")

                            row_count, is_estimated = get_row_count_fast(cursor, schema, table_name)

                            cursor.execute(f"DESCRIBE `{table_name}`;")
                            columns = cursor.fetchall()

                            safe_columns = [
                                c['Field'] for c in columns
                                if not any(bt in c['Type'].lower() for bt in BLOB_TYPES)
                            ]

                            sample = []
                            if safe_columns:
                                safe_cols_str = ', '.join([f"`{c}`" for c in safe_columns[:20]])
                                cursor.execute(f"SELECT {safe_cols_str} FROM `{table_name}` LIMIT 3;")
                                sample = cursor.fetchall()

                            date_columns = [
                                c['Field'] for c in columns
                                if any(dt in c['Type'].lower() for dt in ('date', 'datetime', 'timestamp'))
                                or c['Field'].lower() in ('year', 'date', 'end_date', 'start_date', 'last_update', 'create_date')
                            ]
                            date_range = {}
                            for date_col in date_columns[:1]:
                                try:
                                    cursor.execute(f"SELECT MIN(`{date_col}`) as min_date, MAX(`{date_col}`) as max_date FROM `{table_name}`;")
                                    dr = cursor.fetchone()
                                    if dr and dr.get('min_date'):
                                        date_range = {
                                            'column': date_col,
                                            'min': str(dr['min_date']),
                                            'max': str(dr['max_date'])
                                        }
                                except Exception as e:
                                    results['errors'].append({
                                        'table': f"{schema}.{table_name}",
                                        'operation': 'date_range',
                                        'error': str(e)
                                    })

                            results['schemas'][schema]['table_details'][table_name] = {
                                'type': table_type,
                                'row_count': row_count,
                                'row_count_estimated': is_estimated,
                                'column_count': len(columns),
                                'columns': columns,
                                'sample_data': sample,
                                'date_range': date_range
                            }

                            count_str = f"~{row_count:,}" if is_estimated else f"{row_count:,}"
                            print(f"   ✓ {table_name}: {count_str} rows, {len(columns)} columns")

                        except Exception as e:
                            results['schemas'][schema]['table_details'][table_name] = {
                                'error': str(e)
                            }
                            print(f"   ✗ {table_name}: error - {e}")

                    print(f"   Schema {schema}: {len(results['schemas'][schema]['tables'])} tables, {len(results['schemas'][schema]['views'])} views\n")

                except Exception as e:
                    results['errors'].append({
                        'schema': schema,
                        'error': str(e)
                    })
                    print(f"   ✗ Schema error {schema}: {e}\n")

            # 3. IDB-specific queries
            print("3. Running IDB-specific queries...")
            if 'idb' in results['schemas']:
                try:
                    try:
                        connection.ping(reconnect=True)
                    except Exception:
                        print("   ⚠ Reconnecting for IDB queries...")
                        connection = create_connection(config)
                        cursor = connection.cursor()

                    cursor.execute("USE idb;")
                    results['idb_specific'] = {}

                    # 3.1 Enabled countries
                    try:
                        cursor.execute("SELECT * FROM RBP_adm0_mapping WHERE enabled = 1;")
                        enabled_countries = cursor.fetchall()
                        results['idb_specific']['enabled_countries'] = enabled_countries
                        print(f"   ✓ Enabled countries: {len(enabled_countries)}")
                    except Exception as e:
                        print(f"   ✗ RBP_adm0_mapping: {e}")
                        results['idb_specific']['enabled_countries'] = []
                        results['idb_specific']['enabled_countries_error'] = str(e)

                    # 3.2 Last update for key tables
                    results['idb_specific']['last_updates'] = {}
                    print("\n   Last updates for key tables:")

                    for table in IDB_KEY_TABLES:
                        try:
                            try:
                                connection.ping(reconnect=True)
                                cursor.execute("USE idb;")
                            except Exception:
                                connection = create_connection(config)
                                cursor = connection.cursor()
                                cursor.execute("USE idb;")

                            cursor.execute(f"""
                                SHOW COLUMNS FROM `{table}`
                                WHERE Type LIKE '%%date%%'
                                   OR Type LIKE '%%datetime%%'
                                   OR Type LIKE '%%timestamp%%'
                                   OR Field IN ('date', 'year', 'end_date', 'start_date', 'last_update', 'create_date');
                            """)
                            date_cols = cursor.fetchall()
                            if date_cols:
                                date_col = date_cols[0]['Field']
                                cursor.execute(f"SELECT MAX(`{date_col}`) as last_update FROM `{table}`;")
                                last = cursor.fetchone()
                                results['idb_specific']['last_updates'][table] = {
                                    'column': date_col,
                                    'last_update': str(last['last_update']) if last and last.get('last_update') else None
                                }
                                print(f"   ✓ {table}: {last.get('last_update') if last else 'N/A'} (col: {date_col})")
                            else:
                                print(f"   ⚠ {table}: no date column found")
                                results['idb_specific']['last_updates'][table] = {'column': None, 'last_update': None}
                        except Exception as e:
                            print(f"   ✗ {table}: {e}")
                            results['idb_specific']['last_updates'][table] = {'error': str(e)}

                    # 3.3 Trigger result analysis (main system output)
                    print("\n   Analyzing RBP_trigger_result (system output):")
                    try:
                        cursor.execute("""
                            SELECT iso3, MAX(date) as last_date,
                                   SUM(CASE WHEN trigger_outcome = 1 THEN 1 ELSE 0 END) as triggers_fired
                            FROM RBP_trigger_result
                            GROUP BY iso3
                            ORDER BY last_date DESC;
                        """)
                        trigger_summary = cursor.fetchall()
                        results['idb_specific']['trigger_summary'] = trigger_summary
                        print(f"   ✓ Trigger results: {len(trigger_summary)} countries analyzed")

                        cursor.execute("SELECT MAX(date) as last_run FROM RBP_trigger_result;")
                        last_run = cursor.fetchone()
                        results['idb_specific']['last_trigger_run'] = str(last_run['last_run']) if last_run and last_run.get('last_run') else None
                        print(f"   ✓ Last trigger run: {last_run.get('last_run') if last_run else 'N/A'}")
                    except Exception as e:
                        print(f"   ✗ RBP_trigger_result analysis: {e}")
                        results['idb_specific']['trigger_summary_error'] = str(e)

                    # 3.4 SQL views verification
                    print("\n   Verifying SQL views:")
                    results['idb_specific']['views_status'] = {}
                    for view in KNOWN_VIEWS:
                        try:
                            cursor.execute(f"SELECT COUNT(*) as cnt FROM `{view}`;")
                            cnt = cursor.fetchone()
                            results['idb_specific']['views_status'][view] = {
                                'exists': True,
                                'row_count': cnt['cnt'] if cnt else 0
                            }
                            print(f"   ✓ {view}: {cnt['cnt'] if cnt else 0} rows")
                        except Exception as e:
                            results['idb_specific']['views_status'][view] = {
                                'exists': False,
                                'error': str(e)
                            }
                            print(f"   ✗ {view}: {e}")

                except Exception as e:
                    results['errors'].append({'idb_specific': str(e)})
                    print(f"   ✗ IDB query error: {e}")
            else:
                print("   ⚠ Schema 'idb' not available, skipping specific queries")

        connection.close()
        print("\n✓ Connection closed.")

    except pymysql.err.OperationalError as e:
        error_msg = f"Connection error: {e}"
        results['errors'].append({'connection': error_msg})
        print(f"\n✗ {error_msg}")
        print("\nPossible causes:")
        print("  - VPN not connected")
        print("  - IP not in whitelist")
        print("  - Credentials changed")
        return None

    except Exception as e:
        error_msg = f"Error: {type(e).__name__}: {e}"
        results['errors'].append({'general': error_msg})
        print(f"\n✗ {error_msg}")
        return None

    return results


def save_results(results, env):
    """Save results to a JSON file."""
    if not results:
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filename = os.path.join(script_dir, f"db_exploration_{env}_{timestamp}.json")

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=json_serializer, ensure_ascii=False)

        print(f"\n{'='*60}")
        print(f"✓ Results saved to: {filename}")
        print(f"{'='*60}")

        return filename
    except Exception as e:
        print(f"\n✗ Save error: {e}")
        fallback = f"db_exploration_{env}_{timestamp}.json"
        with open(fallback, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=json_serializer, ensure_ascii=False)
        print(f"✓ Saved to: {fallback}")
        return fallback


def print_summary(results):
    """Print a summary of the results."""
    if not results:
        return

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}\n")

    print(f"Databases found: {len(results['databases'])}")
    print(f"Schemas explored: {len(results['schemas'])}")

    total_tables = 0
    total_views = 0
    total_rows = 0

    for schema, data in results['schemas'].items():
        tables = len(data['tables'])
        views = len(data['views'])
        rows = sum(
            t.get('row_count', 0) or 0
            for t in data['table_details'].values()
            if isinstance(t.get('row_count'), (int, float))
        )
        total_tables += tables
        total_views += views
        total_rows += rows
        print(f"  {schema}: {tables} tables, {views} views, ~{int(rows):,} rows")

    print(f"\nTOTAL: {total_tables} tables, {total_views} views, ~{int(total_rows):,} rows")

    if results.get('idb_specific', {}).get('enabled_countries'):
        countries = results['idb_specific']['enabled_countries']
        iso3_list = []
        for c in countries:
            if isinstance(c, dict):
                iso3_list.append(c.get('iso3', c.get('ISO3', str(c))))
            else:
                iso3_list.append(str(c))
        print(f"\nEnabled countries ({len(iso3_list)}): {', '.join(iso3_list)}")

    if results.get('errors'):
        print(f"\n⚠ Errors encountered: {len(results['errors'])}")
        for err in results['errors'][:5]:
            print(f"   - {err}")


def print_update_status_table(results):
    """
    Print a summary table of update status.
    Highlights what is updated, outdated, and problematic.
    """
    if not results or 'idb_specific' not in results:
        return

    from datetime import datetime, timedelta

    today = datetime.now().date()

    print(f"\n{'='*80}")
    print("DATABASE UPDATE STATUS REPORT")
    print(f"Analysis Date: {today.strftime('%Y-%m-%d')}")
    print(f"{'='*80}\n")

    categories = {
        'Food Security (RTM)': ['RBP_fcs', 'RBP_fcs_adm0', 'RBP_rcsi', 'RBP_rcsi_adm0'],
        'Alerts (Trigger Output)': ['RBP_climate_alert', 'RBP_conflict_alert', 'RBP_economic_alert',
                                     'RBP_food_security_alert', 'RBP_hazard_alert', 'RBP_trigger_result'],
        'Conflict (ACLED)': ['RBP_ACLED_conflict'],
        'Economic': ['RBP_food_inflation', 'RBP_currency_exchange'],
        'Climate': ['RBP_climate_anomaly', 'RBP_rainfall_ndvi_seasonality'],
        'Natural Hazards': ['RBP_ADAM_cyclon', 'RBP_ADAM_earthquake', 'RBP_ADAM_flood', 'RBP_PDC_hazard'],
        'HungerMap Alerts': ['RBP_adm0_hml_alert', 'RBP_adm1_hml_alert'],
        'Population': ['RBP_population', 'RBP_population_adm1'],
        'Migration': ['RBP_panama_darien_nationality', 'RBP_panama_darien_agesex', 'RBP_usa_encounters'],
        'Food Security (External)': ['RBP_ipc_adm0', 'RBP_pou'],
        'Output/Export': ['RBP_IDB_tableau']
    }

    last_updates = results.get('idb_specific', {}).get('last_updates', {})

    def parse_date(date_str):
        """Parse various date formats."""
        if not date_str or date_str == 'null':
            return None
        try:
            for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y']:
                try:
                    return datetime.strptime(str(date_str).split('T')[0].split(' ')[0], fmt.split('T')[0].split(' ')[0]).date()
                except ValueError:
                    continue
            if len(str(date_str)) == 4:
                return datetime.strptime(str(date_str), '%Y').date()
        except Exception:
            pass
        return None

    def get_status_emoji(last_date, table_name):
        """Determine status based on date."""
        if last_date is None:
            return "⚪", "N/A", "No Data"

        days_old = (today - last_date).days

        if days_old < 0:
            days_old = 0

        if days_old <= 7:
            return "🟢", f"{days_old}d", "Current"
        elif days_old <= 30:
            return "🟡", f"{days_old}d", "Recent"
        elif days_old <= 90:
            return "🟠", f"{days_old}d", "Outdated"
        elif days_old <= 365:
            return "🔴", f"{days_old}d", "Stale"
        else:
            return "⛔", f"{days_old}d", "CRITICAL"

    print(f"{'Category':<25} {'Table':<40} {'Last Update':<12} {'Age':<8} {'Status':<10}")
    print("-" * 95)

    status_counts = {'🟢': 0, '🟡': 0, '🟠': 0, '🔴': 0, '⛔': 0, '⚪': 0, '❌': 0}

    for category, tables in categories.items():
        first_in_category = True
        for table in tables:
            info = last_updates.get(table, {})

            if 'error' in info:
                emoji = "❌"
                date_str = "-"
                age_str = "-"
                status = "Error"
                status_counts['❌'] += 1
            else:
                last_update = info.get('last_update')
                last_date = parse_date(last_update)
                emoji, age_str, status = get_status_emoji(last_date, table)
                date_str = str(last_update)[:10] if last_update else "N/A"
                status_counts[emoji] += 1

            cat_display = category if first_in_category else ""
            print(f"{cat_display:<25} {table:<40} {date_str:<12} {age_str:<8} {emoji} {status}")
            first_in_category = False

        if tables:
            print()

    print("-" * 95)
    print("\nSTATUS LEGEND:")
    print(f"  🟢 Current (≤7 days)      : {status_counts['🟢']}")
    print(f"  🟡 Recent (8-30 days)     : {status_counts['🟡']}")
    print(f"  🟠 Outdated (31-90 days)  : {status_counts['🟠']}")
    print(f"  🔴 Stale (91-365 days)    : {status_counts['🔴']}")
    print(f"  ⛔ CRITICAL (>365 days)   : {status_counts['⛔']}")
    print(f"  ⚪ N/A (no date column)   : {status_counts['⚪']}")
    print(f"  ❌ Error (table missing)  : {status_counts['❌']}")

    # Trigger status by country
    trigger_summary = results.get('idb_specific', {}).get('trigger_summary', [])
    if trigger_summary:
        print(f"\n{'='*80}")
        print("TRIGGER STATUS BY COUNTRY")
        print(f"{'='*80}\n")
        print(f"{'Country':<8} {'Last Trigger':<15} {'Age':<10} {'Triggers Fired':<15} {'Status'}")
        print("-" * 60)

        for t in sorted(trigger_summary, key=lambda x: x.get('last_date', '') or '', reverse=True):
            iso3 = t.get('iso3', '???')
            last_date_str = t.get('last_date', 'N/A')
            triggers = int(t.get('triggers_fired', 0))

            last_date = parse_date(last_date_str)
            emoji, age_str, status = get_status_emoji(last_date, iso3)

            print(f"{iso3:<8} {str(last_date_str):<15} {age_str:<10} {triggers:<15} {emoji} {status}")

        enabled = results.get('idb_specific', {}).get('enabled_countries', [])
        enabled_iso3 = set()
        for c in enabled:
            if isinstance(c, dict):
                enabled_iso3.add(c.get('iso3', ''))
            else:
                enabled_iso3.add(str(c))

        triggered_iso3 = set(t.get('iso3', '') for t in trigger_summary)
        missing = enabled_iso3 - triggered_iso3

        if missing:
            print(f"\n⚠️  ENABLED COUNTRIES WITHOUT TRIGGERS: {', '.join(sorted(missing))}")

    # Views status
    views_status = results.get('idb_specific', {}).get('views_status', {})
    if views_status:
        print(f"\n{'='*80}")
        print("SQL VIEWS STATUS")
        print(f"{'='*80}\n")
        for view, info in views_status.items():
            if info.get('exists'):
                print(f"  ✓ {view}: {info.get('row_count', 0):,} rows")
            else:
                print(f"  ✗ {view}: {info.get('error', 'Unknown error')}")


if __name__ == '__main__':
    env = 'dev'
    if len(sys.argv) > 1:
        env = sys.argv[1].lower()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           WFP IDB Database Explorer v1.6                     ║
║                                                              ║
║  Database Health Monitoring & Analysis Tool                  ║
║                                                              ║
║  Features:                                                   ║
║  - Comprehensive schema exploration                          ║
║  - Data freshness assessment with status indicators          ║
║  - Trigger system health check by country                    ║
║  - Critical data alerts (>1 year old)                        ║
║                                                              ║
║  Ensure VPN connection before running this tool.             ║
╚══════════════════════════════════════════════════════════════╝
    """)

    results = explore_database(env)

    if results:
        print_summary(results)
        print_update_status_table(results)
        output_file = save_results(results, env)

        print(f"\n✓ Database health assessment complete.")
        print(f"  Review the JSON report for detailed analysis.")
    else:
        print("\n✗ Exploration failed. Please verify VPN connection.")
