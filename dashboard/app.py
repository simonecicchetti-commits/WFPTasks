"""
WFP IDB Database Monitor Dashboard
===================================
Streamlit-based monitoring interface for WFP IDB infrastructure.
"""

import streamlit as st
import pandas as pd
import sys
import os
from datetime import datetime, timedelta
from io import BytesIO
import json

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from db_explorer import explore_database, DB_CONFIG, IDB_KEY_TABLES, KNOWN_VIEWS

# Page configuration
st.set_page_config(
    page_title="WFP IDB Monitor",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f4e79;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        margin-top: 0;
    }
    .status-card {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .metric-container {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
    .stDataFrame {
        font-size: 0.9rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
    }
</style>
""", unsafe_allow_html=True)


def get_status_info(last_date_str, today):
    """Determine status based on date."""
    if not last_date_str or last_date_str == 'None' or last_date_str == 'null':
        return "⚪", "N/A", "No Data", "#gray"

    try:
        # Parse date
        date_str = str(last_date_str).split('T')[0].split(' ')[0]
        if len(date_str) == 4:  # Year only
            last_date = datetime.strptime(date_str, '%Y').date()
        else:
            last_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        days_old = (today - last_date).days
        if days_old < 0:
            days_old = 0

        if days_old <= 7:
            return "🟢", f"{days_old}d", "Current", "#28a745"
        elif days_old <= 30:
            return "🟡", f"{days_old}d", "Recent", "#ffc107"
        elif days_old <= 90:
            return "🟠", f"{days_old}d", "Outdated", "#fd7e14"
        elif days_old <= 365:
            return "🔴", f"{days_old}d", "Stale", "#dc3545"
        else:
            return "⛔", f"{days_old}d", "CRITICAL", "#721c24"
    except Exception:
        return "⚪", "N/A", "Parse Error", "#gray"


def create_status_dataframe(results):
    """Create a formatted DataFrame for table status."""
    if not results or 'idb_specific' not in results:
        return pd.DataFrame()

    today = datetime.now().date()
    last_updates = results.get('idb_specific', {}).get('last_updates', {})

    categories = {
        'Food Security (RTM)': ['RBP_fcs', 'RBP_fcs_adm0', 'RBP_rcsi', 'RBP_rcsi_adm0'],
        'Alerts (Trigger)': ['RBP_climate_alert', 'RBP_conflict_alert', 'RBP_economic_alert',
                             'RBP_food_security_alert', 'RBP_hazard_alert', 'RBP_trigger_result'],
        'Conflict (ACLED)': ['RBP_ACLED_conflict'],
        'Economic': ['RBP_food_inflation', 'RBP_currency_exchange'],
        'Climate': ['RBP_climate_anomaly', 'RBP_rainfall_ndvi_seasonality'],
        'Natural Hazards': ['RBP_ADAM_cyclon', 'RBP_ADAM_earthquake', 'RBP_ADAM_flood', 'RBP_PDC_hazard'],
        'HungerMap Alerts': ['RBP_adm0_hml_alert', 'RBP_adm1_hml_alert'],
        'Population': ['RBP_population', 'RBP_population_adm1'],
        'Migration': ['RBP_panama_darien_nationality', 'RBP_panama_darien_agesex', 'RBP_usa_encounters'],
        'Food Security (Ext)': ['RBP_ipc_adm0', 'RBP_pou'],
        'Output': ['RBP_IDB_tableau']
    }

    rows = []
    for category, tables in categories.items():
        for table in tables:
            info = last_updates.get(table, {})
            if 'error' in info:
                emoji, age, status, color = "❌", "-", "Error", "#dc3545"
                last_update = "-"
                column = "-"
            else:
                last_update = info.get('last_update', 'N/A')
                column = info.get('column', '-')
                emoji, age, status, color = get_status_info(last_update, today)
                if last_update:
                    last_update = str(last_update)[:10]

            rows.append({
                'Category': category,
                'Table': table,
                'Column': column,
                'Last Update': last_update,
                'Age': age,
                'Status': f"{emoji} {status}"
            })

    return pd.DataFrame(rows)


def create_trigger_dataframe(results):
    """Create DataFrame for trigger status by country."""
    if not results or 'idb_specific' not in results:
        return pd.DataFrame()

    today = datetime.now().date()
    trigger_summary = results.get('idb_specific', {}).get('trigger_summary', [])
    enabled_countries = results.get('idb_specific', {}).get('enabled_countries', [])

    # Get enabled ISO3 codes
    enabled_iso3 = set()
    for c in enabled_countries:
        if isinstance(c, dict):
            enabled_iso3.add(c.get('iso3', ''))

    rows = []
    triggered_iso3 = set()

    for t in trigger_summary:
        iso3 = t.get('iso3', '???')
        triggered_iso3.add(iso3)
        last_date = t.get('last_date', 'N/A')
        triggers = int(t.get('triggers_fired', 0))
        emoji, age, status, color = get_status_info(str(last_date), today)

        rows.append({
            'Country': iso3,
            'Last Trigger': str(last_date)[:10] if last_date else 'N/A',
            'Age': age,
            'Triggers Fired': triggers,
            'Status': f"{emoji} {status}",
            'Enabled': '✓' if iso3 in enabled_iso3 else ''
        })

    # Add enabled countries that never triggered
    missing = enabled_iso3 - triggered_iso3
    for iso3 in sorted(missing):
        rows.append({
            'Country': iso3,
            'Last Trigger': 'Never',
            'Age': '-',
            'Triggers Fired': 0,
            'Status': '⚠️ Never Run',
            'Enabled': '✓'
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values('Last Trigger', ascending=False)
    return df


def create_views_dataframe(results):
    """Create DataFrame for SQL views status."""
    if not results or 'idb_specific' not in results:
        return pd.DataFrame()

    views_status = results.get('idb_specific', {}).get('views_status', {})
    rows = []

    for view, info in views_status.items():
        if info.get('exists'):
            rows.append({
                'View': view,
                'Status': '✅ OK',
                'Row Count': f"{info.get('row_count', 0):,}"
            })
        else:
            rows.append({
                'View': view,
                'Status': '❌ Error',
                'Row Count': info.get('error', 'Unknown')[:50]
            })

    return pd.DataFrame(rows)


def count_statuses(df):
    """Count status occurrences."""
    if df.empty:
        return {}

    counts = {
        '🟢 Current': 0,
        '🟡 Recent': 0,
        '🟠 Outdated': 0,
        '🔴 Stale': 0,
        '⛔ Critical': 0,
        '❌ Error': 0,
        '⚪ N/A': 0
    }

    for status in df['Status']:
        if '🟢' in status:
            counts['🟢 Current'] += 1
        elif '🟡' in status:
            counts['🟡 Recent'] += 1
        elif '🟠' in status:
            counts['🟠 Outdated'] += 1
        elif '🔴' in status:
            counts['🔴 Stale'] += 1
        elif '⛔' in status:
            counts['⛔ Critical'] += 1
        elif '❌' in status:
            counts['❌ Error'] += 1
        else:
            counts['⚪ N/A'] += 1

    return counts


def export_to_excel(results, status_df, trigger_df, views_df):
    """Export results to Excel."""
    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not status_df.empty:
            status_df.to_excel(writer, sheet_name='Table Status', index=False)
        if not trigger_df.empty:
            trigger_df.to_excel(writer, sheet_name='Trigger Status', index=False)
        if not views_df.empty:
            views_df.to_excel(writer, sheet_name='Views Status', index=False)

        # Metadata sheet
        meta_df = pd.DataFrame([
            {'Key': 'Environment', 'Value': results.get('metadata', {}).get('environment', 'N/A')},
            {'Key': 'Host', 'Value': results.get('metadata', {}).get('host', 'N/A')},
            {'Key': 'Timestamp', 'Value': results.get('metadata', {}).get('timestamp', 'N/A')},
            {'Key': 'Script Version', 'Value': results.get('metadata', {}).get('script_version', 'N/A')},
        ])
        meta_df.to_excel(writer, sheet_name='Metadata', index=False)

    return output.getvalue()


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    # Header
    st.markdown('<p class="main-header">🔷 WFP IDB Database Monitor</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Real-time database health monitoring for IDB infrastructure</p>', unsafe_allow_html=True)
    st.markdown("---")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")

        env = st.selectbox(
            "Environment",
            options=['dev', 'prod'],
            index=0,
            help="Select database environment"
        )

        st.markdown("---")

        st.markdown(f"""
        **Connection Info:**
        - Host: `{DB_CONFIG[env]['host'][:30]}...`
        - Port: `{DB_CONFIG[env]['port']}`
        """)

        st.markdown("---")
        st.markdown("""
        **Requirements:**
        - ✅ VPN Connected
        - ✅ Network Access
        """)

        st.markdown("---")
        st.caption("v1.0 | WFP IDB Monitor")

    # Main content
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        run_button = st.button("🔄 Run Analysis", type="primary", use_container_width=True)

    with col2:
        auto_refresh = st.checkbox("Auto-refresh", value=False)

    with col3:
        if auto_refresh:
            refresh_interval = st.selectbox("Interval", [5, 10, 30, 60], index=1)

    # Initialize session state
    if 'results' not in st.session_state:
        st.session_state.results = None
    if 'last_run' not in st.session_state:
        st.session_state.last_run = None

    # Run analysis
    if run_button:
        with st.status("🔄 Running database analysis...", expanded=True) as status:
            st.write("Connecting to database...")

            try:
                st.write(f"Connecting to {env.upper()} environment...")
                results = explore_database(env)

                if results:
                    st.session_state.results = results
                    st.session_state.last_run = datetime.now()
                    status.update(label="✅ Analysis complete!", state="complete", expanded=False)
                else:
                    status.update(label="❌ Analysis failed - Check VPN connection", state="error")
                    st.error("Failed to connect. Please ensure VPN is connected.")
            except Exception as e:
                status.update(label="❌ Error occurred", state="error")
                st.error(f"Error: {str(e)}")

    # Display results
    if st.session_state.results:
        results = st.session_state.results

        # Last run info
        if st.session_state.last_run:
            st.success(f"✅ Last analysis: {st.session_state.last_run.strftime('%Y-%m-%d %H:%M:%S')} | Environment: **{results.get('metadata', {}).get('environment', 'N/A').upper()}**")

        # Create DataFrames
        status_df = create_status_dataframe(results)
        trigger_df = create_trigger_dataframe(results)
        views_df = create_views_dataframe(results)

        # Summary metrics
        st.markdown("### 📊 Summary")
        counts = count_statuses(status_df)

        cols = st.columns(7)
        metrics = [
            ('🟢 Current', counts.get('🟢 Current', 0), 'Tables ≤7 days'),
            ('🟡 Recent', counts.get('🟡 Recent', 0), 'Tables 8-30 days'),
            ('🟠 Outdated', counts.get('🟠 Outdated', 0), 'Tables 31-90 days'),
            ('🔴 Stale', counts.get('🔴 Stale', 0), 'Tables 91-365 days'),
            ('⛔ Critical', counts.get('⛔ Critical', 0), 'Tables >365 days'),
            ('❌ Error', counts.get('❌ Error', 0), 'Tables with errors'),
            ('⚪ N/A', counts.get('⚪ N/A', 0), 'No date column'),
        ]

        for col, (label, value, help_text) in zip(cols, metrics):
            col.metric(label, value, help=help_text)

        st.markdown("---")

        # Tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Table Status", "🌍 Country Triggers", "👁️ SQL Views", "📁 Raw Data"])

        with tab1:
            st.markdown("### Database Tables Health")

            # Filter options
            col1, col2 = st.columns([1, 3])
            with col1:
                filter_status = st.multiselect(
                    "Filter by status",
                    options=['🟢', '🟡', '🟠', '🔴', '⛔', '❌', '⚪'],
                    default=[]
                )

            display_df = status_df.copy()
            if filter_status:
                mask = display_df['Status'].apply(lambda x: any(f in x for f in filter_status))
                display_df = display_df[mask]

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                height=500
            )

        with tab2:
            st.markdown("### Trigger Status by Country")

            if not trigger_df.empty:
                # Highlight countries that never ran
                st.dataframe(
                    trigger_df,
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )

                # Warning for missing countries
                never_run = trigger_df[trigger_df['Status'].str.contains('Never')]
                if not never_run.empty:
                    st.warning(f"⚠️ **{len(never_run)} enabled countries never triggered:** {', '.join(never_run['Country'].tolist())}")
            else:
                st.info("No trigger data available")

        with tab3:
            st.markdown("### SQL Views Status")

            if not views_df.empty:
                st.dataframe(
                    views_df,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No views data available")

        with tab4:
            st.markdown("### Raw JSON Data")
            st.json(results, expanded=False)

        # Export section
        st.markdown("---")
        st.markdown("### 📥 Export Data")

        col1, col2, col3 = st.columns(3)

        with col1:
            json_str = json.dumps(results, indent=2, default=str)
            st.download_button(
                label="📄 Download JSON",
                data=json_str,
                file_name=f"idb_status_{env}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )

        with col2:
            excel_data = export_to_excel(results, status_df, trigger_df, views_df)
            st.download_button(
                label="📊 Download Excel",
                data=excel_data,
                file_name=f"idb_status_{env}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        with col3:
            st.button("📄 Download PDF", disabled=True, use_container_width=True, help="Coming soon")

    else:
        # No data yet
        st.info("👆 Click **Run Analysis** to start monitoring the database")

        st.markdown("""
        ### What this tool does:

        1. **Connects** to the WFP IDB database (dev or prod)
        2. **Scans** all key tables and checks their last update dates
        3. **Analyzes** trigger execution status by country
        4. **Verifies** SQL views are working correctly
        5. **Reports** data freshness with color-coded status indicators

        ### Status Legend:

        | Status | Meaning | Age |
        |--------|---------|-----|
        | 🟢 Current | Data is fresh | ≤ 7 days |
        | 🟡 Recent | Data is recent | 8-30 days |
        | 🟠 Outdated | Data needs attention | 31-90 days |
        | 🔴 Stale | Data is old | 91-365 days |
        | ⛔ Critical | Data is very old | > 365 days |
        | ❌ Error | Table/query error | - |
        | ⚪ N/A | No date column | - |
        """)


if __name__ == "__main__":
    main()
