import io
import pandas as pd
import streamlit as st

try:
    from snowflake.snowpark.context import get_active_session
    SNOWFLAKE_ENV = True
except Exception:
    SNOWFLAKE_ENV = False


st.set_page_config(page_title="Data Explorer Pro", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .welcome-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 34px;
        border-radius: 16px;
        text-align: center;
        color: white;
        margin: 12px 0 20px;
    }
    .welcome-box h1 { font-size: 2.3em; margin-bottom: 8px; }
    .welcome-box p { font-size: 1.05em; opacity: 0.95; }
    .active-file {
        background: #667eea; color: white; padding: 6px 12px;
        border-radius: 8px; font-weight: 700; display: inline-block;
    }
    .section-card {
        background: #f8f9ff; border: 1px solid #e0e4ff; border-radius: 12px;
        padding: 16px; margin-bottom: 12px;
    }
    .success-box {
        background: #d4edda; border-left: 4px solid #28a745;
        padding: 10px 15px; border-radius: 4px; margin: 5px 0;
    }
    .sql-preview-box {
        background: #1e1e2e; color: #cdd6f4; font-family: monospace;
        font-size: 0.9em; padding: 16px 20px; border-radius: 10px;
        white-space: pre-wrap; line-height: 1.7; margin: 12px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_session():
    if not SNOWFLAKE_ENV:
        return None
    try:
        return get_active_session()
    except Exception:
        return None


SESSION = get_session()

for key, default in {
    "df": None,
    "table_name": None,
    "loaded_name": None,
    "ai_history": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# =========================
# Generic helper functions
# =========================
def fetch_databases():
    if SESSION is None:
        return []
    try:
        return [row["name"] for row in SESSION.sql("SHOW DATABASES").collect()]
    except Exception:
        return []


def fetch_schemas(db):
    if SESSION is None:
        return []
    try:
        rows = SESSION.sql(f'SHOW SCHEMAS IN DATABASE "{db}"').collect()
        return [row["name"] for row in rows if row["name"] != "INFORMATION_SCHEMA"]
    except Exception:
        return []


def fetch_tables(db, schema):
    if SESSION is None:
        return []
    tables, views = [], []
    try:
        tables = [row["name"] for row in SESSION.sql(f'SHOW TABLES IN "{db}"."{schema}"').collect()]
    except Exception:
        pass
    try:
        views = [f'{row["name"]} (view)' for row in SESSION.sql(f'SHOW VIEWS IN "{db}"."{schema}"').collect()]
    except Exception:
        pass
    return tables + views


def fetch_stages(db, schema):
    if SESSION is None:
        return []
    try:
        return [row["name"] for row in SESSION.sql(f'SHOW STAGES IN "{db}"."{schema}"').collect()]
    except Exception:
        return []


def fetch_stage_files(stage_ref):
    if SESSION is None:
        return []
    try:
        rows = SESSION.sql(f"LIST {stage_ref}").collect()
        return [str(row[0]).split("/")[-1] for row in rows]
    except Exception:
        return []


def detect_file_type(filename):
    name = filename.lower()
    if name.endswith(".csv"):
        return "CSV"
    if name.endswith(".parquet"):
        return "PARQUET"
    if name.endswith(".json"):
        return "JSON"
    if name.endswith((".xlsx", ".xls")):
        return "XLSX"
    return "CSV"


def load_stage_file(stage_ref, file_name, file_type):
    if SESSION is None:
        raise RuntimeError("Snowflake session not available")
    full_path = f"{stage_ref}/{file_name}"
    if file_type == "CSV":
        return SESSION.read.option("header", True).option("infer_schema", True).csv(full_path).limit(10000).to_pandas()
    if file_type == "PARQUET":
        return SESSION.read.parquet(full_path).limit(10000).to_pandas()
    if file_type == "JSON":
        return SESSION.read.json(full_path).limit(10000).to_pandas()
    from snowflake.snowpark.files import SnowflakeFile
    with SnowflakeFile.open(full_path, 'rb') as f:
        return pd.read_excel(io.BytesIO(f.readall()))


def save_to_snowflake(df):
    if SESSION is None:
        return None
    table = "DATA_" + str(abs(hash(str(df.columns.tolist()))))[:6]
    safe_df = df.copy()
    for col in safe_df.columns:
        if safe_df[col].dtype == object:
            safe_df[col] = safe_df[col].astype(str)
    SESSION.write_pandas(safe_df, table, auto_create_table=True, overwrite=True)
    return table


def clean_sql_response(response):
    response = response.replace("```sql", "").replace("```", "").strip()
    idx = response.lower().find("select")
    return response[idx:] if idx != -1 else response


def generate_sql(question, df, table_name):
    if SESSION is None or not table_name:
        raise RuntimeError("SQL generation works only inside Snowflake after loading data.")
    col_list = ', '.join([f'"{c}"' for c in df.columns])
    prompt = f"""You are a STRICT Snowflake SQL generator.
Rules:
- Return ONLY a single SQL SELECT statement
- No explanation, no markdown, no comments
- Start directly with SELECT
- ALWAYS double-quote every column name exactly as shown below
- Table name: {table_name}
- Available columns: {col_list}
Question: {question}
Add LIMIT 50."""
    q = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large', $$ {prompt} $$)"
    response = SESSION.sql(q).collect()[0][0]
    return clean_sql_response(response)


def ask_cortex(question, df):
    if SESSION is None:
        raise RuntimeError("AI works only inside Snowflake Streamlit environment.")
    sample = df.head(20).to_string()
    prompt = f"""You are a helpful data analyst.
Dataset columns: {df.columns.tolist()}
Sample data:
{sample}
Question: {question}
Answer clearly in short business-friendly English. Use actual column names when possible."""
    q = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large', $$ {prompt} $$)"
    return SESSION.sql(q).collect()[0][0]


# =========================
# Horizon catalog functions
# =========================
def render_database_explorer():
    st.subheader("🗄️ Database Explorer")
    st.caption("Browse databases, schemas, tables, and preview data")
    if SESSION is None:
        st.warning("This feature works only inside Snowflake Streamlit environment.")
        return
    try:
        db_rows = SESSION.sql("SHOW DATABASES").collect()
        db_names = [row["name"] for row in db_rows]
        db_list = [{"Name": row["name"], "Kind": str(row.get("kind", "")) if hasattr(row, "get") else str(row["kind"]) if "kind" in row else ""} for row in db_rows]
        c1, c2 = st.columns([1, 2])
        with c1:
            selected_db = st.selectbox("Select Database", db_names, key="dbx_db") if db_names else None
            selected_schema = None
            selected_table = None
            if selected_db:
                schemas = fetch_schemas(selected_db)
                selected_schema = st.selectbox("Select Schema", schemas, key="dbx_schema") if schemas else None
            if selected_db and selected_schema:
                objects = fetch_tables(selected_db, selected_schema)
                selected_table = st.selectbox("Select Table/View", objects, key="dbx_table") if objects else None
        with c2:
            st.dataframe(pd.DataFrame(db_list), use_container_width=True, hide_index=True)
        if selected_db and selected_schema and selected_table and st.button("Preview Data", type="primary", key="dbx_preview"):
            obj_real = selected_table.replace(" (view)", "")
            preview_df = SESSION.sql(f'SELECT * FROM "{selected_db}"."{selected_schema}"."{obj_real}" LIMIT 100').to_pandas()
            st.dataframe(preview_df, use_container_width=True)
    except Exception as e:
        st.error(f"Database Explorer error: {e}")


def render_internal_marketplace():
    st.subheader("🏪 Internal Marketplace")
    st.caption("Browse imported or shared marketplace datasets")
    if SESSION is None:
        st.warning("This feature works only inside Snowflake Streamlit environment.")
        return
    try:
        all_dbs = SESSION.sql("SHOW DATABASES").collect()
        def is_marketplace_db(row):
            try:
                origin = str(row['origin']).upper()
                kind = str(row['kind']).upper()
                return origin in ('IMPORTED DATABASE', 'SHARE') or kind in ('IMPORTED DATABASE', 'DATA SHARE')
            except Exception:
                return False
        mkt_dbs = [row for row in all_dbs if is_marketplace_db(row)]
        if not mkt_dbs:
            st.info("No Marketplace datasets found in this account.")
            return
        for db in mkt_dbs:
            with st.expander(f"🛒 {db['name']}"):
                st.write(f"**Database:** {db['name']}")
                try:
                    schemas = fetch_schemas(db['name'])
                    for schema in schemas[:3]:
                        tables = fetch_tables(db['name'], schema)
                        st.write(f"**Schema {schema}:** {len(tables)} tables/views")
                except Exception:
                    pass
    except Exception as e:
        st.error(f"Marketplace error: {e}")


def render_apps():
    st.subheader("📦 Apps")
    st.caption("View installed native apps, Streamlit apps, and app packages")
    if SESSION is None:
        st.warning("This feature works only inside Snowflake Streamlit environment.")
        return
    try:
        c1, c2 = st.columns(2)
        with c1:
            try:
                apps = SESSION.sql("SHOW APPLICATIONS").collect()
                st.markdown("#### Installed Native Apps")
                if apps:
                    st.dataframe(pd.DataFrame([
                        {"App Name": str(a['name']) if 'name' in a else '',
                         "Version": str(a['version']) if 'version' in a else '',
                         "Status": str(a['status']) if 'status' in a else ''}
                        for a in apps
                    ]), use_container_width=True, hide_index=True)
                else:
                    st.info("No Native Apps installed.")
            except Exception as e:
                st.error(f"Apps error: {e}")
        with c2:
            try:
                streamlit_apps = SESSION.sql("SHOW STREAMLITS").collect()
                st.markdown("#### Streamlit Apps")
                if streamlit_apps:
                    st.dataframe(pd.DataFrame([
                        {"App Name": str(a['name']) if 'name' in a else '',
                         "Database": str(a['database_name']) if 'database_name' in a else '',
                         "Schema": str(a['schema_name']) if 'schema_name' in a else ''}
                        for a in streamlit_apps
                    ]), use_container_width=True, hide_index=True)
                else:
                    st.info("No Streamlit apps found.")
            except Exception as e:
                st.error(f"Streamlit apps error: {e}")
        st.markdown("#### Application Packages")
        try:
            packages = SESSION.sql("SHOW APPLICATION PACKAGES").collect()
            if packages:
                st.dataframe(pd.DataFrame([
                    {"Package Name": str(p['name']) if 'name' in p else '',
                     "Distribution": str(p['distribution']) if 'distribution' in p else '',
                     "Owner": str(p['owner']) if 'owner' in p else ''}
                    for p in packages
                ]), use_container_width=True, hide_index=True)
            else:
                st.info("No Application Packages found.")
        except Exception as e:
            st.error(f"Packages error: {e}")
    except Exception as e:
        st.error(f"Apps Manager error: {e}")


def render_external_data():
    st.subheader("🌐 External Data")
    st.caption("Browse external stages, connections, and file formats")
    if SESSION is None:
        st.warning("This feature works only inside Snowflake Streamlit environment.")
        return
    try:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### External Stages")
            dbs = fetch_databases()
            if dbs:
                db = st.selectbox("Database", dbs, key="ext_db")
                schemas = fetch_schemas(db)
                schema = st.selectbox("Schema", schemas if schemas else ["PUBLIC"], key="ext_schema")
                try:
                    stages = SESSION.sql(f'SHOW STAGES IN "{db}"."{schema}"').collect()
                    if stages:
                        st.dataframe(pd.DataFrame([
                            {"Stage Name": str(s['name']) if 'name' in s else '',
                             "Type": str(s['type']) if 'type' in s else '',
                             "URL": str(s['url']) if 'url' in s else ''}
                            for s in stages
                        ]), use_container_width=True, hide_index=True)
                    else:
                        st.info("No stages found.")
                except Exception as e:
                    st.error(f"Stages error: {e}")
        with c2:
            st.markdown("#### External Connections")
            try:
                connections = SESSION.sql("SHOW CONNECTIONS").collect()
                if connections:
                    st.dataframe(pd.DataFrame([
                        {"Name": str(c['name']) if 'name' in c else '',
                         "Type": str(c['type']) if 'type' in c else '',
                         "Owner": str(c['owner']) if 'owner' in c else ''}
                        for c in connections
                    ]), use_container_width=True, hide_index=True)
                else:
                    st.info("No external connections found.")
            except Exception:
                st.info("No external connections configured.")
    except Exception as e:
        st.error(f"External Data error: {e}")


def safe_row(row, key, default=''):
    try:
        return str(row[key])
    except Exception:
        return default


def render_data_sharing():
    st.subheader("🔗 Data Sharing")
    st.caption("View internal and external shares")
    if SESSION is None:
        st.warning("This feature works only inside Snowflake Streamlit environment.")
        return
    try:
        t1, t2 = st.tabs(["Internal Sharing", "External Sharing"])
        with t1:
            shares = SESSION.sql("SHOW SHARES").collect()
            outbound = [s for s in shares if safe_row(s, 'kind').upper() == 'OUTBOUND']
            inbound = [s for s in shares if safe_row(s, 'kind').upper() == 'INBOUND']
            st.markdown("#### Outbound Shares")
            if outbound:
                st.dataframe(pd.DataFrame([
                    {"Share Name": safe_row(s, 'name'), "Owner": safe_row(s, 'owner'), "Created": safe_row(s, 'created_on')[:10]}
                    for s in outbound
                ]), use_container_width=True, hide_index=True)
            else:
                st.info("No outbound shares found.")
            st.markdown("#### Inbound Shares")
            if inbound:
                st.dataframe(pd.DataFrame([
                    {"Share Name": safe_row(s, 'name'), "Owner": safe_row(s, 'owner'), "Created": safe_row(s, 'created_on')[:10]}
                    for s in inbound
                ]), use_container_width=True, hide_index=True)
            else:
                st.info("No inbound shares found.")
        with t2:
            c1, c2, c3 = st.columns(3)
            try:
                all_shares = SESSION.sql("SHOW SHARES").collect()
                total_out = sum(1 for s in all_shares if safe_row(s, 'kind').upper() == 'OUTBOUND')
                total_in = sum(1 for s in all_shares if safe_row(s, 'kind').upper() == 'INBOUND')
                c1.metric("Outbound Shares", total_out)
                c2.metric("Inbound Shares", total_in)
                c3.metric("Total Shares", len(all_shares))
            except Exception as e:
                st.info(f"Share summary unavailable: {e}")
    except Exception as e:
        st.error(f"Data Sharing error: {e}")


def render_governance_security():
    st.subheader("🔐 Governance & Security")
    st.caption("View users, roles, network policies, tags, and policies")
    if SESSION is None:
        st.warning("This feature works only inside Snowflake Streamlit environment.")
        return
    try:
        t1, t2, t3, t4 = st.tabs(["Users & Roles", "Trust Center", "Network Policies", "Tags & Policies"])
        with t1:
            c1, c2 = st.columns(2)
            with c1:
                try:
                    users = SESSION.sql("SHOW USERS").collect()
                    if users:
                        st.dataframe(pd.DataFrame([
                            {"Login Name": str(u['login_name']) if 'login_name' in u else str(u['name']),
                             "Email": str(u['email']) if 'email' in u else '',
                             "Created": str(u['created_on'])[:10] if 'created_on' in u else ''}
                            for u in users
                        ]), use_container_width=True, hide_index=True)
                    else:
                        st.info("No users found.")
                except Exception as e:
                    st.error(f"Users error: {e}")
            with c2:
                try:
                    roles = SESSION.sql("SHOW ROLES").collect()
                    if roles:
                        st.dataframe(pd.DataFrame([
                            {"Role Name": str(r['name']) if 'name' in r else '',
                             "Owner": str(r['owner']) if 'owner' in r else '',
                             "Created": str(r['created_on'])[:10] if 'created_on' in r else ''}
                            for r in roles
                        ]), use_container_width=True, hide_index=True)
                    else:
                        st.info("No roles found.")
                except Exception as e:
                    st.error(f"Roles error: {e}")
        with t2:
            st.info("Trust Center style overview for password, authentication, and security-related policies.")
            try:
                params = SESSION.sql("SHOW PARAMETERS LIKE '%POLICY%' IN ACCOUNT").collect()
                if params:
                    st.dataframe(pd.DataFrame([
                        {"Parameter": str(p['key']) if 'key' in p else '',
                         "Value": str(p['value']) if 'value' in p else '',
                         "Default": str(p['default']) if 'default' in p else ''}
                        for p in params
                    ]), use_container_width=True, hide_index=True)
                else:
                    st.info("No policy parameters found.")
            except Exception as e:
                st.info(f"Account parameters unavailable: {e}")
        with t3:
            try:
                net_policies = SESSION.sql("SHOW NETWORK POLICIES").collect()
                if net_policies:
                    st.dataframe(pd.DataFrame([
                        {"Policy Name": str(n['name']) if 'name' in n else '',
                         "Allowed": str(n['entries_in_allowed_ip_list']) if 'entries_in_allowed_ip_list' in n else '0',
                         "Blocked": str(n['entries_in_blocked_ip_list']) if 'entries_in_blocked_ip_list' in n else '0'}
                        for n in net_policies
                    ]), use_container_width=True, hide_index=True)
                else:
                    st.info("No network policies found.")
            except Exception as e:
                st.error(f"Network policies error: {e}")
        with t4:
            dbs = fetch_databases()
            if not dbs:
                st.info("No databases available.")
                return
            db = st.selectbox("Database", dbs, key="gov_db")
            schemas = fetch_schemas(db)
            schema = st.selectbox("Schema", schemas if schemas else ["PUBLIC"], key="gov_schema")
            c1, c2 = st.columns(2)
            with c1:
                try:
                    tags = SESSION.sql(f'SHOW TAGS IN "{db}"."{schema}"').collect()
                    if tags:
                        st.dataframe(pd.DataFrame([
                            {"Tag Name": str(t['name']) if 'name' in t else '',
                             "Owner": str(t['owner']) if 'owner' in t else ''}
                            for t in tags
                        ]), use_container_width=True, hide_index=True)
                    else:
                        st.info("No tags found.")
                except Exception as e:
                    st.info(f"Tags unavailable: {e}")
            with c2:
                try:
                    masking = SESSION.sql(f'SHOW MASKING POLICIES IN "{db}"."{schema}"').collect()
                    if masking:
                        st.dataframe(pd.DataFrame([
                            {"Policy Name": str(m['name']) if 'name' in m else '',
                             "Kind": str(m['kind']) if 'kind' in m else '',
                             "Owner": str(m['owner']) if 'owner' in m else ''}
                            for m in masking
                        ]), use_container_width=True, hide_index=True)
                    else:
                        st.info("No masking policies found.")
                except Exception as e:
                    st.info(f"Masking policies unavailable: {e}")
    except Exception as e:
        st.error(f"Governance & Security error: {e}")


# =========================
# Sidebar / data loading
# =========================
with st.sidebar:
    st.title("📊 Data Explorer Pro")
    st.markdown("---")
    source = st.radio(
        "Load data from",
        ["Upload File", "Snowflake Table", "Snowflake Stage", "Snowflake Marketplace"],
    )
    st.markdown("---")

    if source == "Upload File":
        file = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx", "xls"])
        if file is not None:
            df = pd.read_csv(file) if file.name.lower().endswith(".csv") else pd.read_excel(file)
            st.session_state.df = df
            st.session_state.loaded_name = file.name
            st.session_state.table_name = save_to_snowflake(df)
            st.markdown(f'<span class="active-file">📄 {file.name}</span>', unsafe_allow_html=True)

    elif source == "Snowflake Table":
        if SESSION is None:
            st.warning("Snowflake environment not available.")
        else:
            dbs = fetch_databases()
            selected_db = st.selectbox("Database", dbs, key="tbl_db") if dbs else None
            if selected_db:
                schemas = fetch_schemas(selected_db)
                selected_schema = st.selectbox("Schema", schemas, key="tbl_schema") if schemas else None
                if selected_schema:
                    tables = fetch_tables(selected_db, selected_schema)
                    selected_table = st.selectbox("Table / View", tables, key="tbl_name") if tables else None
                    if selected_table and st.button("Load Table"):
                        obj = selected_table.replace(" (view)", "")
                        full_name = f'"{selected_db}"."{selected_schema}"."{obj}"'
                        df = SESSION.table(full_name).limit(10000).to_pandas()
                        st.session_state.df = df
                        st.session_state.table_name = full_name
                        st.session_state.loaded_name = full_name
                        st.success(f"Loaded {len(df):,} rows")

    elif source == "Snowflake Stage":
        if SESSION is None:
            st.warning("Snowflake environment not available.")
        else:
            dbs = fetch_databases()
            selected_db = st.selectbox("Database", dbs, key="stg_db") if dbs else None
            if selected_db:
                schemas = fetch_schemas(selected_db)
                selected_schema = st.selectbox("Schema", schemas, key="stg_schema") if schemas else None
                if selected_schema:
                    stages = fetch_stages(selected_db, selected_schema)
                    selected_stage = st.selectbox("Stage", stages, key="stg_stage") if stages else None
                    if selected_stage:
                        stage_ref = f'@"{selected_db}"."{selected_schema}"."{selected_stage}"'
                        files = fetch_stage_files(stage_ref)
                        selected_file = st.selectbox("File", files, key="stg_file") if files else None
                        if selected_file:
                            auto_type = detect_file_type(selected_file)
                            file_type = st.selectbox("File format", ["CSV", "PARQUET", "JSON", "XLSX"], index=["CSV", "PARQUET", "JSON", "XLSX"].index(auto_type))
                            if st.button("Load Stage File"):
                                df = load_stage_file(stage_ref, selected_file, file_type)
                                st.session_state.df = df
                                st.session_state.loaded_name = selected_file
                                st.session_state.table_name = save_to_snowflake(df)
                                st.success(f"Loaded {len(df):,} rows")

    elif source == "Snowflake Marketplace":
        if SESSION is None:
            st.warning("Snowflake environment not available.")
        else:
            all_dbs = SESSION.sql("SHOW DATABASES").collect()
            mp_dbs = []
            for row in all_dbs:
                try:
                    origin = str(row['origin']).upper()
                    kind = str(row['kind']).upper()
                    if origin in ('IMPORTED DATABASE', 'SHARE') or kind in ('IMPORTED DATABASE', 'DATA SHARE'):
                        mp_dbs.append(row['name'])
                except Exception:
                    pass
            selected_db = st.selectbox("Marketplace database", mp_dbs, key="mp_db") if mp_dbs else None
            if selected_db:
                schemas = fetch_schemas(selected_db)
                selected_schema = st.selectbox("Schema", schemas, key="mp_schema") if schemas else None
                if selected_schema:
                    tables = fetch_tables(selected_db, selected_schema)
                    selected_table = st.selectbox("Table / View", tables, key="mp_table") if tables else None
                    if selected_table and st.button("Load Marketplace Dataset"):
                        obj = selected_table.replace(" (view)", "")
                        full_name = f'"{selected_db}"."{selected_schema}"."{obj}"'
                        df = SESSION.table(full_name).limit(10000).to_pandas()
                        st.session_state.df = df
                        st.session_state.loaded_name = full_name
                        st.session_state.table_name = full_name
                        st.success(f"Loaded {len(df):,} rows")


df = st.session_state.df

if df is None:
    st.markdown(
        """
        <div class="welcome-box">
            <h1>📊 Data Explorer Pro</h1>
            <p>Load data from file, Snowflake table, stage, or marketplace and explore it in one clean app.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("## 🗂️ Horizon Catalog")
    ctab1, ctab2, ctab3, ctab4, ctab5, ctab6 = st.tabs([
        "🗄️ Database Explorer",
        "🏪 Internal Marketplace",
        "📦 Apps",
        "🌐 External Data",
        "🔗 Data Sharing",
        "🔐 Governance & Security",
    ])
    with ctab1:
        render_database_explorer()
    with ctab2:
        render_internal_marketplace()
    with ctab3:
        render_apps()
    with ctab4:
        render_external_data()
    with ctab5:
        render_data_sharing()
    with ctab6:
        render_governance_security()
    st.stop()

# normalize possible numeric strings
for col in df.select_dtypes(include="object").columns:
    cleaned = df[col].astype(str).str.replace(r'[\$,\s]', '', regex=True)
    try:
        converted = pd.to_numeric(cleaned, errors='raise')
        df[col] = converted
    except Exception:
        pass

st.title(f"📊 {st.session_state.loaded_name or 'Dataset'}")
st.markdown(f"Analyzing **{len(df):,} rows** × **{len(df.columns)} columns**")
st.markdown("---")

(tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13) = st.tabs([
    "📊 Overview",
    "🗂 Schema",
    "🔍 Preview & Filter",
    "📉 Charts",
    "🧠 SQL Assistant",
    "🤖 Ask Your Data",
    "📤 Export",
    "🔒 Data Masking",
    "🗄️ Database Explorer",
    "🏪 Internal Marketplace",
    "📦 Apps",
    "🌐 External Data",
    "🔗 Governance & Sharing",
])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{df.shape[0]:,}")
    c2.metric("Columns", df.shape[1])
    c3.metric("Missing Values", f"{df.isnull().sum().sum():,}")
    c4.metric("Duplicate Rows", f"{df.duplicated().sum():,}")
    st.markdown("### First 5 Rows")
    st.dataframe(df.head(), use_container_width=True)

with tab2:
    schema_rows = []
    for col in df.columns:
        null_cnt = int(df[col].isnull().sum())
        schema_rows.append({
            "Column Name": col,
            "Data Type": str(df[col].dtype),
            "Non-Null Count": int(df[col].notnull().sum()),
            "Null Count": null_cnt,
            "Unique Values": int(df[col].nunique()),
        })
    st.dataframe(pd.DataFrame(schema_rows), use_container_width=True, hide_index=True)

with tab3:
    col_search, col_filter, col_sort = st.columns(3)
    with col_search:
        search_keyword = st.text_input("Search keyword")
    with col_filter:
        filter_col = st.selectbox("Filter by column", ["None"] + df.columns.tolist())
    with col_sort:
        sort_col = st.selectbox("Sort by column", ["None"] + df.columns.tolist())
    sort_order = st.radio("Order", ["Ascending", "Descending"], horizontal=True)
    filtered_df = df.copy()
    if search_keyword:
        mask = filtered_df.apply(lambda row: row.astype(str).str.contains(search_keyword, case=False).any(), axis=1)
        filtered_df = filtered_df[mask]
    if filter_col != "None":
        col_data = df[filter_col].dropna()
        if not col_data.empty:
            if pd.api.types.is_numeric_dtype(df[filter_col]):
                mn, mx = float(col_data.min()), float(col_data.max())
                if mn != mx:
                    vals = st.slider(f"Range for {filter_col}", min_value=mn, max_value=mx, value=(mn, mx))
                    filtered_df = filtered_df[(filtered_df[filter_col] >= vals[0]) & (filtered_df[filter_col] <= vals[1])]
            else:
                vals = [str(v) for v in col_data.unique().tolist()[:200]]
                selected_val = st.selectbox(f"Select value for {filter_col}", ["All"] + vals)
                if selected_val != "All":
                    filtered_df = filtered_df[filtered_df[filter_col].astype(str) == selected_val]
    if sort_col != "None":
        filtered_df = filtered_df.sort_values(sort_col, ascending=(sort_order == "Ascending"))
    st.caption(f"Showing **{len(filtered_df):,}** of **{len(df):,}** rows")
    st.dataframe(filtered_df, use_container_width=True)

with tab4:
    numeric_cols = [c for c in df.select_dtypes(include="number").columns if df[c].notna().sum() > 0]
    cat_cols = [c for c in df.columns if c not in numeric_cols]
    chart_type = st.selectbox("Chart Type", ["Histogram", "Bar Chart", "Line Chart", "Scatter Chart", "Correlation Matrix"])
    if chart_type == "Histogram":
        if numeric_cols:
            col = st.selectbox("Numeric column", numeric_cols)
            st.bar_chart(df[col].value_counts().sort_index())
        else:
            st.info("No numeric columns found.")
    elif chart_type == "Bar Chart":
        if cat_cols:
            col = st.selectbox("Category column", cat_cols)
            st.bar_chart(df[col].astype(str).value_counts().head(10))
        else:
            st.info("No category columns found.")
    elif chart_type == "Line Chart":
        if numeric_cols:
            col = st.selectbox("Numeric column", numeric_cols, key="line_col")
            st.line_chart(df[[col]])
        else:
            st.info("No numeric columns found.")
    elif chart_type == "Scatter Chart":
        if len(numeric_cols) >= 2:
            x = st.selectbox("X axis", numeric_cols, key="sc_x")
            y = st.selectbox("Y axis", numeric_cols, index=1, key="sc_y")
            st.scatter_chart(df[[x, y]].dropna(), x=x, y=y)
        else:
            st.info("Need at least 2 numeric columns.")
    else:
        if len(numeric_cols) >= 2:
            st.dataframe(df[numeric_cols].corr().round(2), use_container_width=True)
        else:
            st.info("Need at least 2 numeric columns.")

with tab5:
    st.subheader("🧠 SQL Assistant")

    if SESSION is None:
        st.warning("SQL Assistant works only inside Snowflake Streamlit environment.")
    else:
        tname = st.session_state.table_name or "YOUR_TABLE"
        num_cols = df.select_dtypes(include="number").columns.tolist()
        cat_cols = df.select_dtypes(include="object").columns.tolist()
        all_cols = df.columns.tolist()
        col_quoted = ", ".join([f'"{c}"' for c in all_cols[:6]])

        # ── Build suggested queries dynamically based on actual columns ──
        suggested = {}

        suggested["📋 Preview first 100 rows"] = (
            f'SELECT * FROM {tname} LIMIT 100'
        )

        suggested["🔢 Row & column count"] = (
            f'SELECT COUNT(*) AS total_rows FROM {tname}'
        )

        if num_cols:
            nc = f'"{num_cols[0]}"'
            suggested[f"📊 Stats for {num_cols[0]}"] = (
                f'SELECT\n'
                f'  ROUND(AVG({nc}), 2) AS avg_val,\n'
                f'  ROUND(MIN({nc}), 2) AS min_val,\n'
                f'  ROUND(MAX({nc}), 2) AS max_val,\n'
                f'  ROUND(STDDEV({nc}), 2) AS std_dev\n'
                f'FROM {tname}'
            )

        if len(num_cols) >= 2:
            n1, n2 = f'"{num_cols[0]}"', f'"{num_cols[1]}"'
            suggested[f"📈 Top 10 by {num_cols[0]}"] = (
                f'SELECT {col_quoted}\n'
                f'FROM {tname}\n'
                f'ORDER BY {n1} DESC\n'
                f'LIMIT 10'
            )

        if cat_cols:
            cc = f'"{cat_cols[0]}"'
            suggested[f"🗂 Value counts — {cat_cols[0]}"] = (
                f'SELECT {cc}, COUNT(*) AS count\n'
                f'FROM {tname}\n'
                f'GROUP BY {cc}\n'
                f'ORDER BY count DESC\n'
                f'LIMIT 20'
            )

        if len(cat_cols) >= 2 and num_cols:
            cc2 = f'"{cat_cols[1]}"'
            nc = f'"{num_cols[0]}"'
            suggested[f"📉 Avg {num_cols[0]} by {cat_cols[1]}"] = (
                f'SELECT {cc2}, ROUND(AVG({nc}), 2) AS avg_value\n'
                f'FROM {tname}\n'
                f'GROUP BY {cc2}\n'
                f'ORDER BY avg_value DESC\n'
                f'LIMIT 20'
            )

        if num_cols:
            null_checks = ",\n  ".join(
                [f'SUM(CASE WHEN "{c}" IS NULL THEN 1 ELSE 0 END) AS "{c}_nulls"' for c in all_cols[:8]]
            )
            suggested["🔍 Null check (all columns)"] = (
                f'SELECT\n  {null_checks}\nFROM {tname}'
            )

        if num_cols:
            nc = f'"{num_cols[0]}"'
            suggested[f"⚠️ Outliers in {num_cols[0]} (3σ rule)"] = (
                f'WITH stats AS (\n'
                f'  SELECT AVG({nc}) AS mean, STDDEV({nc}) AS sd FROM {tname}\n'
                f')\n'
                f'SELECT t.*\n'
                f'FROM {tname} t, stats\n'
                f'WHERE ABS(t.{nc} - stats.mean) > 3 * stats.sd\n'
                f'LIMIT 50'
            )

        suggested["🔁 Duplicate rows"] = (
            f'SELECT {col_quoted}, COUNT(*) AS dup_count\n'
            f'FROM {tname}\n'
            f'GROUP BY {col_quoted}\n'
            f'HAVING COUNT(*) > 1\n'
            f'ORDER BY dup_count DESC\n'
            f'LIMIT 20'
        )

        # ── Session state to hold active SQL ──
        if "active_sql" not in st.session_state:
            st.session_state.active_sql = ""
        if "sql_result" not in st.session_state:
            st.session_state.sql_result = None

        # ── Section 1: Suggested Queries ──
        st.markdown("### 💡 Suggested Queries")
        st.caption("Click any query below to load it into the editor, then run it.")

        btn_cols = st.columns(4)
        for i, (label, sql_str) in enumerate(suggested.items()):
            with btn_cols[i % 4]:
                if st.button(label, key=f"sq_{i}", use_container_width=True):
                    st.session_state.active_sql = sql_str
                    st.session_state.sql_result = None

        st.markdown("---")

        # ── Section 2: AI-generated SQL ──
        st.markdown("### 🤖 Ask in Plain English")
        user_q = st.text_input("Type your question (e.g. 'Show top 5 countries by driving mobility')", key="sql_ai_input")
        if user_q:
            with st.spinner("Generating SQL via Cortex AI..."):
                try:
                    ai_sql = generate_sql(user_q, df, st.session_state.table_name)
                    st.session_state.active_sql = ai_sql
                    st.session_state.sql_result = None
                except Exception as e:
                    st.error(f"AI SQL generation error: {e}")

        st.markdown("---")

        # ── Section 3: SQL Editor + Run ──
        st.markdown("### ✏️ SQL Editor")
        edited_sql = st.text_area(
            "Edit SQL before running:",
            value=st.session_state.active_sql,
            height=180,
            key="sql_editor_box",
            placeholder=f"SELECT * FROM {tname} LIMIT 100",
        )
        if edited_sql:
            st.session_state.active_sql = edited_sql

        run_col, clear_col, dl_col = st.columns([2, 1, 2])
        with run_col:
            run_clicked = st.button("▶️ Run SQL", type="primary", use_container_width=True)
        with clear_col:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.active_sql = ""
                st.session_state.sql_result = None
                st.rerun()

        if run_clicked and st.session_state.active_sql.strip():
            with st.spinner("Running query..."):
                try:
                    result_df = SESSION.sql(st.session_state.active_sql).to_pandas()
                    st.session_state.sql_result = result_df
                except Exception as e:
                    st.error(f"Query error: {e}")
                    st.session_state.sql_result = None

        # ── Section 4: Results ──
        if st.session_state.sql_result is not None:
            res = st.session_state.sql_result
            st.markdown(f"### 📊 Results — {len(res):,} rows × {len(res.columns)} columns")
            st.dataframe(res, use_container_width=True)
            with dl_col:
                st.download_button(
                    "⬇️ Download Results CSV",
                    data=res.to_csv(index=False),
                    file_name="sql_results.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

with tab6:
    st.subheader("Ask Your Data")
    if SESSION is None:
        st.warning("AI analysis works only inside Snowflake Streamlit environment.")
    else:
        ai_q = st.text_input("Ask a question about your dataset")
        if ai_q:
            try:
                answer = ask_cortex(ai_q, df)
                st.write(answer)
            except Exception as e:
                st.error(f"AI error: {e}")

with tab7:
    schema_export = pd.DataFrame({
        "Column": df.columns,
        "Data Type": [str(dt) for dt in df.dtypes.values],
        "Non-Null": df.notnull().sum().values,
        "Null Count": df.isnull().sum().values,
        "Unique": [df[c].nunique() for c in df.columns],
    })
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download Schema CSV", data=schema_export.to_csv(index=False), file_name="schema_export.csv", mime="text/csv")
    with c2:
        st.download_button("Download Full Data CSV", data=df.to_csv(index=False), file_name="data_export.csv", mime="text/csv")

with tab8:
    st.subheader("🔒 Data Masking")
    st.caption("Mask sensitive columns before exporting — choose masking style per column")

    if "masking_rules" not in st.session_state:
        st.session_state.masking_rules = {}

    import hashlib
    import re

    def apply_mask(series, style):
        if style == "Redact (****)":
            return series.apply(lambda x: "****" if pd.notna(x) and str(x).strip() != "" else x)
        elif style == "Hash (SHA-256)":
            return series.apply(lambda x: hashlib.sha256(str(x).encode()).hexdigest()[:16] if pd.notna(x) else x)
        elif style == "Partial (show last 4)":
            return series.apply(lambda x: ("*" * max(0, len(str(x)) - 4) + str(x)[-4:]) if pd.notna(x) and len(str(x)) >= 4 else "****")
        elif style == "Partial (show first 2)":
            return series.apply(lambda x: (str(x)[:2] + "*" * max(0, len(str(x)) - 2)) if pd.notna(x) else x)
        elif style == "Nullify (blank)":
            return series.apply(lambda x: None if pd.notna(x) else x)
        elif style == "Email Mask":
            def mask_email(v):
                v = str(v)
                if "@" in v:
                    local, domain = v.split("@", 1)
                    return local[:2] + "***@" + domain
                return "***@***.***"
            return series.apply(mask_email)
        elif style == "Phone Mask":
            return series.apply(lambda x: re.sub(r'\d(?=\d{4})', '*', str(x)) if pd.notna(x) else x)
        else:
            return series

    MASK_STYLES = [
        "No Masking",
        "Redact (****)",
        "Hash (SHA-256)",
        "Partial (show last 4)",
        "Partial (show first 2)",
        "Nullify (blank)",
        "Email Mask",
        "Phone Mask",
    ]

    st.markdown("### Step 1 — Configure Masking Rules per Column")
    st.markdown("Select a masking style for each column you want to protect. Columns set to **No Masking** are exported as-is.")

    col_chunks = [df.columns.tolist()[i:i+3] for i in range(0, len(df.columns), 3)]
    for chunk in col_chunks:
        cols_ui = st.columns(3)
        for idx, col_name in enumerate(chunk):
            with cols_ui[idx]:
                current = st.session_state.masking_rules.get(col_name, "No Masking")
                chosen = st.selectbox(
                    f"**{col_name}**",
                    MASK_STYLES,
                    index=MASK_STYLES.index(current) if current in MASK_STYLES else 0,
                    key=f"mask_{col_name}",
                )
                st.session_state.masking_rules[col_name] = chosen

    st.markdown("---")
    st.markdown("### Step 2 — Preview Masked Data")

    masked_cols_count = sum(1 for v in st.session_state.masking_rules.values() if v != "No Masking")
    if masked_cols_count == 0:
        st.info("No columns are masked yet. Select a masking style above to preview.")
    else:
        masked_df_preview = df.head(20).copy()
        for col_name, style in st.session_state.masking_rules.items():
            if style != "No Masking" and col_name in masked_df_preview.columns:
                masked_df_preview[col_name] = apply_mask(masked_df_preview[col_name], style)
        st.caption(f"Preview showing first 20 rows — **{masked_cols_count} column(s) masked**")
        st.dataframe(masked_df_preview, use_container_width=True)

    st.markdown("---")
    st.markdown("### Step 3 — Export Masked Data")

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        if st.button("🔒 Apply & Generate Masked CSV", type="primary"):
            masked_df_full = df.copy()
            for col_name, style in st.session_state.masking_rules.items():
                if style != "No Masking" and col_name in masked_df_full.columns:
                    masked_df_full[col_name] = apply_mask(masked_df_full[col_name], style)
            st.session_state["masked_df_ready"] = masked_df_full
            st.success(f"Masked data ready — {masked_cols_count} column(s) protected across {len(masked_df_full):,} rows.")
    with mc2:
        if "masked_df_ready" in st.session_state and st.session_state["masked_df_ready"] is not None:
            st.download_button(
                "Download Masked CSV",
                data=st.session_state["masked_df_ready"].to_csv(index=False),
                file_name="masked_data_export.csv",
                mime="text/csv",
            )
        else:
            st.button("Download Masked CSV", disabled=True)
    with mc3:
        if st.button("Reset All Masks"):
            st.session_state.masking_rules = {}
            if "masked_df_ready" in st.session_state:
                del st.session_state["masked_df_ready"]
            st.rerun()

    st.markdown("---")
    st.markdown("### Current Masking Rules Summary")
    summary_rows = [
        {"Column": col, "Masking Style": style, "Status": "Masked" if style != "No Masking" else "Plain"}
        for col, style in st.session_state.masking_rules.items()
    ]
    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

with tab9:
    render_database_explorer()
with tab10:
    render_internal_marketplace()
with tab11:
    render_apps()
with tab12:
    render_external_data()
with tab13:
    sub1, sub2 = st.tabs(["🔗 Data Sharing", "🔐 Governance & Security"])
    with sub1:
        render_data_sharing()
    with sub2:
        render_governance_security()
