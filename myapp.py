import streamlit as st
import pandas as pd
import numpy as np

# ---- PAGE CONFIG ----
st.set_page_config(
    page_title="Data Explorer Pro",
    page_icon="📊",
    layout="wide"
)

# ---- CUSTOM CSS ----
st.markdown("""
<style>
    .welcome-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 40px;
        border-radius: 16px;
        text-align: center;
        color: white;
        margin: 20px 0;
    }
    .welcome-box h1 { font-size: 2.5em; margin-bottom: 10px; }
    .welcome-box p { font-size: 1.1em; opacity: 0.9; }
    .type-badge {
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.75em;
        font-weight: bold;
    }
    .type-number { background: #d1fae5; color: #065f46; }
    .type-text { background: #dbeafe; color: #1e40af; }
    .type-bool { background: #fef3c7; color: #92400e; }
    .type-other { background: #f3f4f6; color: #374151; }
    .success-box {
        background: #d4edda;
        border-left: 4px solid #28a745;
        padding: 10px 15px;
        border-radius: 4px;
        margin: 5px 0;
    }
    .active-file {
        background: #667eea;
        color: white;
        padding: 6px 12px;
        border-radius: 8px;
        font-weight: bold;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# SIDEBAR — MULTI-FILE SUPPORT
# ==========================================
with st.sidebar:
    st.title("📊 Data Explorer Pro")
    st.markdown("---")
    st.subheader("📁 Upload Files")

    uploaded_files = st.file_uploader(
        "Upload one or more CSV files",
        type=["csv"],
        accept_multiple_files=True,
        help="You can upload multiple CSV files and switch between them!"
    )

    if uploaded_files:
        st.markdown("---")
        st.subheader("🗂 Switch Files")

        file_names = [f.name for f in uploaded_files]

        selected_file_name = st.radio(
            "Select active file:",
            file_names
        )

        selected_file = next(f for f in uploaded_files if f.name == selected_file_name)

        st.markdown("---")
        st.markdown("**Active File:**")
        st.markdown(f'<span class="active-file">📄 {selected_file_name}</span>', unsafe_allow_html=True)

# ==========================================
# LANDING PAGE — WHEN NO FILE IS UPLOADED
# ==========================================
if not uploaded_files:
    st.markdown("""
    <div class="welcome-box">
        <h1>📊 Data Explorer Pro</h1>
        <p>Upload any CSV file from the sidebar and instantly explore,<br>
        analyze, visualize, and export your data — no coding needed!</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("📁 **Multi-File Support**\nUpload & switch between multiple CSV files easily")
    with col2:
        st.info("📊 **Advanced Charts**\nCorrelation matrix, box plots, missing value heatmap")
    with col3:
        st.info("📤 **Export Reports**\nDownload schema, statistics as CSV files")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.info("🔍 **Smart Filters**\nSearch, filter & sort your data instantly")
    with col5:
        st.info("🧹 **Data Quality**\nFind duplicates, nulls & high cardinality columns")
    with col6:
        st.info("🎨 **Beautiful UI**\nColor-coded types, tooltips & clean layout")

    st.markdown("### 👈 Upload a CSV file from the sidebar to get started!")

else:
    # ---- LOAD SELECTED FILE ----
    df = pd.read_csv(selected_file)

    # Auto-convert columns that look numeric but are stored as text
    # e.g. "$10,819" or "1,234.56" → actual numbers
    for col in df.select_dtypes(include="object").columns:
        cleaned = df[col].astype(str).str.replace(r'[\$,\s]', '', regex=True)
        try:
            converted = pd.to_numeric(cleaned, errors='raise')
            df[col] = converted
        except (ValueError, TypeError):
            pass  # keep as text if conversion fails

    st.title(f"📊 {selected_file_name}")
    st.markdown(f"Analyzing **{len(df):,} rows** × **{len(df.columns)} columns**")
    st.markdown("---")

    # ---- TABS ----
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Overview",
        "🗂 Schema",
        "📈 Statistics",
        "🔍 Preview & Filter",
        "🧹 Data Quality",
        "📉 Charts",
        "📤 Export"
    ])

    # ==========================================
    # TAB 1 — OVERVIEW
    # ==========================================
    with tab1:
        st.subheader("Dataset Overview")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📋 Total Rows", f"{df.shape[0]:,}")
        col2.metric("📌 Total Columns", df.shape[1])
        col3.metric("❓ Missing Values", f"{df.isnull().sum().sum():,}")
        col4.metric("🔁 Duplicate Rows", f"{df.duplicated().sum():,}")

        col5, col6, col7, col8 = st.columns(4)
        memory = df.memory_usage(deep=True).sum()
        num_cols = len(df.select_dtypes(include="number").columns)
        cat_cols = len(df.select_dtypes(include="object").columns)
        miss_pct = round(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100, 1)

        col5.metric("💾 Memory Usage", f"{memory / 1024:.1f} KB")
        col6.metric("🔢 Numeric Columns", num_cols)
        col7.metric("🔤 Text Columns", cat_cols)
        col8.metric("⚠️ Missing %", f"{miss_pct}%")

        st.markdown("---")
        st.subheader("First 5 Rows")
        st.dataframe(df.head(), use_container_width=True)

    # ==========================================
    # TAB 2 — SCHEMA EXPLORER
    # ==========================================
    with tab2:
        st.subheader("Schema Explorer")
        st.caption("Color-coded by data type: 🟢 Numeric 🔵 Text 🟡 Boolean ⚪ Other")

        def get_type_badge(dtype):
            dtype_str = str(dtype)
            if "int" in dtype_str or "float" in dtype_str:
                return "number"
            elif "object" in dtype_str or "string" in dtype_str:
                return "text"
            elif "bool" in dtype_str:
                return "bool"
            else:
                return "other"

        schema_rows = []
        for col in df.columns:
            dtype = df[col].dtype
            type_cat = get_type_badge(dtype)
            null_cnt = df[col].isnull().sum()
            null_pct = round(null_cnt / len(df) * 100, 1)
            unique = df[col].nunique()
            schema_rows.append({
                "Column Name": col,
                "Data Type": str(dtype),
                "Type Category": type_cat.capitalize(),
                "Non-Null Count": df[col].notnull().sum(),
                "Null Count": null_cnt,
                "Null %": f"{null_pct}%",
                "Valid %": f"{round(100 - null_pct, 1)}%",
                "Unique Values": unique
            })

        schema_df = pd.DataFrame(schema_rows)
        st.dataframe(schema_df, use_container_width=True)

    # ==========================================
    # TAB 3 — STATISTICS
    # ==========================================
    with tab3:
        st.subheader("Numeric Columns — Statistics Summary")
        num_df = df.select_dtypes(include="number")
        # Drop columns where ALL values are null — nothing useful to show
        num_df = num_df.dropna(axis=1, how="all")
        if not num_df.empty:
            st.dataframe(num_df.describe().round(2), use_container_width=True)
        else:
            st.info("No numeric columns found!")

        st.markdown("---")
        st.subheader("Categorical Columns — Top 5 Values")
        cat_cols_list = df.select_dtypes(include="object").columns.tolist()
        if cat_cols_list:
            selected_cat = st.selectbox("Select column:", cat_cols_list)
            top5 = df[selected_cat].value_counts().head(5).reset_index()
            top5.columns = [selected_cat, "Count"]
            st.dataframe(top5, use_container_width=True)
        else:
            st.info("No categorical columns found!")

        st.markdown("---")
        st.subheader("Missing Values per Column")
        miss_df = pd.DataFrame({
            "Column": df.columns,
            "Missing": df.isnull().sum().values,
            "Missing %": (df.isnull().sum().values / len(df) * 100).round(2)
        })
        st.dataframe(miss_df, use_container_width=True)

    # ==========================================
    # TAB 4 — PREVIEW & FILTER
    # ==========================================
    with tab4:
        st.subheader("🔍 Data Preview & Filters")

        col_search, col_filter, col_sort = st.columns(3)

        with col_search:
            search_keyword = st.text_input(
                "🔎 Search keyword",
                help="Searches across ALL columns"
            )
        with col_filter:
            filter_col = st.selectbox(
                "📌 Filter by column",
                ["None"] + df.columns.tolist(),
                help="Select a column to filter by specific value"
            )
        with col_sort:
            sort_col = st.selectbox(
                "⬆️ Sort by column",
                ["None"] + df.columns.tolist()
            )

        sort_order = st.radio("Order:", ["Ascending", "Descending"], horizontal=True)

        filtered_df = df.copy()

        # ── Keyword search across all columns ──
        if search_keyword:
            mask = filtered_df.apply(
                lambda row: row.astype(str).str.contains(search_keyword, case=False).any(),
                axis=1
            )
            filtered_df = filtered_df[mask]

        # ── Filter by column — range slider for numeric, dropdown for text ──
        if filter_col != "None":
            col_data = df[filter_col].dropna()

            if pd.api.types.is_numeric_dtype(df[filter_col]):
                # Numeric column → show range slider
                col_min = float(col_data.min())
                col_max = float(col_data.max())

                if col_min == col_max:
                    st.info(f"Column '{filter_col}' has only one value: {col_min}")
                else:
                    range_vals = st.slider(
                        f"📊 Range for '{filter_col}'",
                        min_value=col_min,
                        max_value=col_max,
                        value=(col_min, col_max),
                        help=f"Drag to filter rows where {filter_col} falls in this range"
                    )
                    filtered_df = filtered_df[
                        (filtered_df[filter_col] >= range_vals[0]) &
                        (filtered_df[filter_col] <= range_vals[1])
                    ]
                    st.caption(f"🔢 Filtering: **{filter_col}** between **{range_vals[0]:,.2f}** and **{range_vals[1]:,.2f}**")

            else:
                # Text / categorical column → dropdown as before
                unique_vals = col_data.unique().tolist()
                selected_val = st.selectbox(f"Select value for '{filter_col}':", ["All"] + unique_vals)
                if selected_val != "All":
                    filtered_df = filtered_df[filtered_df[filter_col] == selected_val]

        # ── Sort by column — range slider preview for numeric ──
        if sort_col != "None":
            ascending = sort_order == "Ascending"
            filtered_df = filtered_df.sort_values(sort_col, ascending=ascending)

            # Show min–max range info for the sorted column
            if pd.api.types.is_numeric_dtype(df[sort_col]):
                s_min = filtered_df[sort_col].min()
                s_max = filtered_df[sort_col].max()
                st.caption(f"📈 Sorted by **{sort_col}** ({sort_order}) — Range in view: **{s_min:,.2f}** → **{s_max:,.2f}**")

        st.caption(f"Showing **{len(filtered_df):,}** of **{len(df):,}** rows")
        st.dataframe(filtered_df, use_container_width=True)

    # ==========================================
    # TAB 5 — DATA QUALITY  (clean table style, no red/yellow boxes)
    # ==========================================
    with tab5:
        st.subheader("🧹 Data Quality Report")

        # --- Duplicates ---
        st.markdown("#### 🔁 Duplicate Rows")
        dup_count = df.duplicated().sum()
        if dup_count > 0:
            st.dataframe(
                pd.DataFrame([{"Status": "⚠️ Issue Found", "Details": f"{dup_count} duplicate row(s) detected"}]),
                use_container_width=True, hide_index=True
            )
            if st.checkbox("Preview duplicate rows"):
                st.dataframe(df[df.duplicated(keep=False)], use_container_width=True)
        else:
            st.markdown('<div class="success-box">✅ No duplicate rows found!</div>', unsafe_allow_html=True)

        st.markdown("---")

        # --- All-null columns — clean table, NO red boxes ---
        st.markdown("#### ❌ Columns with ALL Null Values")
        all_null_cols = [col for col in df.columns if df[col].isnull().all()]
        if all_null_cols:
            null_table = pd.DataFrame({
                "Column Name": all_null_cols,
                "Null Count": [df[c].isnull().sum() for c in all_null_cols],
                "Null %": ["100.0%" for _ in all_null_cols],
                "Recommendation": ["Drop this column" for _ in all_null_cols]
            })
            st.dataframe(null_table, use_container_width=True, hide_index=True)
        else:
            st.markdown('<div class="success-box">✅ No fully-null columns found!</div>', unsafe_allow_html=True)

        st.markdown("---")

        # --- High cardinality — clean table, NO yellow boxes ---
        st.markdown("#### 🔢 High Cardinality Columns")
        st.caption("Columns where unique values > 50% of total rows — may not be useful for grouping")
        threshold = 0.5
        high_card = []
        for col in df.select_dtypes(include="object").columns:
            ratio = df[col].nunique() / len(df)
            if ratio > threshold:
                high_card.append({
                    "Column Name": col,
                    "Unique Values": df[col].nunique(),
                    "Uniqueness %": f"{ratio * 100:.1f}%",
                    "Recommendation": "Avoid using for grouping"
                })

        if high_card:
            st.dataframe(
                pd.DataFrame(high_card),
                use_container_width=True, hide_index=True
            )
        else:
            st.markdown('<div class="success-box">✅ No high cardinality columns found!</div>', unsafe_allow_html=True)

        st.markdown("---")

        # --- Missing value summary — clean table, NO yellow boxes ---
        st.markdown("#### ⚠️ Columns with Missing Values")
        miss_cols = df.columns[df.isnull().any()].tolist()
        if miss_cols:
            missing_table = pd.DataFrame({
                "Column Name": miss_cols,
                "Missing Count": [df[c].isnull().sum() for c in miss_cols],
                "Missing %": [f"{round(df[c].isnull().sum() / len(df) * 100, 1)}%" for c in miss_cols],
                "Non-Null Count": [df[c].notnull().sum() for c in miss_cols]
            })
            st.dataframe(missing_table, use_container_width=True, hide_index=True)
        else:
            st.markdown('<div class="success-box">✅ No missing values found!</div>', unsafe_allow_html=True)

    # ==========================================
    # TAB 6 — ADVANCED CHARTS
    # ==========================================
    with tab6:
        st.subheader("📉 Advanced Visualizations")

        # Only exclude numeric columns where every single value is null
        num_cols_list = [c for c in df.select_dtypes(include="number").columns
                         if df[c].isnull().sum() < len(df)]
        cat_cols_list = [c for c in df.select_dtypes(include="object").columns
                         if df[c].isnull().sum() < len(df)]

        chart_type = st.radio(
            "Select Chart Type:",
            ["📊 Histogram", "📦 Box Plot", "🔥 Correlation Matrix", "🗺 Missing Value Heatmap", "📈 Bar Chart"],
            horizontal=True
        )

        if chart_type == "📊 Histogram":
            if num_cols_list:
                col = st.selectbox("Select numeric column:", num_cols_list)
                st.bar_chart(df[col].value_counts().sort_index())
            else:
                st.info("No numeric columns found!")

        elif chart_type == "📦 Box Plot":
            if num_cols_list:
                col = st.selectbox("Select numeric column:", num_cols_list)
                stats = df[col].describe()
                box_df = pd.DataFrame({
                    "Statistic": ["Min", "Q1 (25%)", "Median (50%)", "Q3 (75%)", "Max"],
                    "Value": [stats["min"], stats["25%"], stats["50%"], stats["75%"], stats["max"]]
                })
                st.dataframe(box_df, use_container_width=True)
                st.bar_chart(box_df.set_index("Statistic"))
                st.caption(f"Mean: {stats['mean']:.2f} | Std Dev: {stats['std']:.2f}")

                Q1 = stats["25%"]
                Q3 = stats["75%"]
                IQR = Q3 - Q1
                outliers = df[(df[col] < Q1 - 1.5 * IQR) | (df[col] > Q3 + 1.5 * IQR)]
                if len(outliers) > 0:
                    st.warning(f"⚠️ Found **{len(outliers)}** potential outliers in '{col}'!")
                    if st.checkbox("Show outlier rows"):
                        st.dataframe(outliers[[col]], use_container_width=True)
                else:
                    st.success(f"✅ No outliers detected in '{col}'!")
            else:
                st.info("No numeric columns found!")

        elif chart_type == "🔥 Correlation Matrix":
            # Drop all-null columns first — they produce None values which render as black
            clean_num = df[num_cols_list].dropna(axis=1, how="all")
            valid_cols = clean_num.columns.tolist()
            if len(valid_cols) >= 2:
                corr = clean_num[valid_cols].corr().round(2)
                st.dataframe(
                    corr.style.background_gradient(cmap="RdYlGn", axis=None).format("{:.2f}"),
                    use_container_width=True
                )
                st.caption("🟢 Green = Strong positive | 🔴 Red = Strong negative | White = No correlation")
            else:
                st.info("Need at least 2 numeric columns with actual data for correlation!")

        elif chart_type == "🗺 Missing Value Heatmap":
            miss_map = df.isnull().sum().reset_index()
            miss_map.columns = ["Column", "Missing Count"]
            miss_map["Missing %"] = (miss_map["Missing Count"] / len(df) * 100).round(1)
            miss_map = miss_map.sort_values("Missing Count", ascending=False)
            if miss_map["Missing Count"].sum() > 0:
                st.dataframe(
                    miss_map.style.background_gradient(subset=["Missing Count"], cmap="Reds"),
                    use_container_width=True
                )
            else:
                st.success("✅ No missing values — your data is clean!")

        elif chart_type == "📈 Bar Chart":
            if cat_cols_list:
                col = st.selectbox("Select categorical column:", cat_cols_list)
                chart_data = df[col].value_counts().head(10)
                st.bar_chart(chart_data)
            else:
                st.info("No categorical columns found!")

    # ==========================================
    # TAB 7 — EXPORT
    # ==========================================
    with tab7:
        st.subheader("📤 Export Summary")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### 🗂 Schema CSV")
            st.caption("Column names, types, null counts")
            schema_export = pd.DataFrame({
                "Column": df.columns,
                "Data Type": [str(dt) for dt in df.dtypes.values],
                "Non-Null": df.notnull().sum().values,
                "Null Count": df.isnull().sum().values,
                "Null %": (df.isnull().sum().values / len(df) * 100).round(2),
                "Unique": [df[c].nunique() for c in df.columns]
            })
            st.download_button(
                label="⬇️ Download Schema",
                data=schema_export.to_csv(index=False),
                file_name="schema_export.csv",
                mime="text/csv"
            )

        with col2:
            st.markdown("#### 📈 Statistics CSV")
            st.caption("Mean, std, min, max, percentiles")
            num_df = df.select_dtypes(include="number")
            if not num_df.empty:
                stats_export = num_df.describe().round(2)
                st.download_button(
                    label="⬇️ Download Statistics",
                    data=stats_export.to_csv(),
                    file_name="statistics_export.csv",
                    mime="text/csv"
                )
            else:
                st.info("No numeric columns to export!")

        with col3:
            st.markdown("#### 📋 Full Data CSV")
            st.caption("Download complete dataset as CSV")
            st.download_button(
                label="⬇️ Download Full Data",
                data=df.to_csv(index=False),
                file_name=f"exported_{selected_file_name}",
                mime="text/csv"
            )

        st.markdown("---")

        st.markdown("#### 🧹 Data Quality Report CSV")
        quality_data = []
        quality_data.append({"Check": "Total Rows", "Result": len(df), "Status": "Info"})
        quality_data.append({"Check": "Total Columns", "Result": len(df.columns), "Status": "Info"})
        quality_data.append({"Check": "Duplicate Rows", "Result": df.duplicated().sum(), "Status": "❌ Issue" if df.duplicated().sum() > 0 else "✅ OK"})
        quality_data.append({"Check": "Missing Values", "Result": df.isnull().sum().sum(), "Status": "❌ Issue" if df.isnull().sum().sum() > 0 else "✅ OK"})
        quality_data.append({"Check": "All-Null Columns", "Result": sum(df[c].isnull().all() for c in df.columns), "Status": "❌ Issue" if any(df[c].isnull().all() for c in df.columns) else "✅ OK"})

        quality_df = pd.DataFrame(quality_data)
        st.dataframe(quality_df, use_container_width=True)
        st.download_button(
            label="⬇️ Download Quality Report",
            data=quality_df.to_csv(index=False),
            file_name="quality_report.csv",
            mime="text/csv"
        )
