import streamlit as st
import pandas as pd

st.title("CSV File Upload Dashboard 📁")
st.write("Upload any CSV file and see instant dashboard!")

# ---- FILE UPLOAD ----
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    # CSV read karo
    df = pd.read_csv(uploaded_file)

    st.success("File uploaded successfully! ✅")

    # ---- BASIC INFO ----
    st.subheader("Data Overview 🔢")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Rows", df.shape[0])
    col2.metric("Total Columns", df.shape[1])
    col3.metric("Departments", df["Department"].nunique())

    # ---- DATA TABLE ----
    st.subheader("Full Data 📋")
    st.dataframe(df)

    # ---- FILTER BY DEPARTMENT ----
    st.subheader("Filter by Department 🔍")
    departments = df["Department"].unique()
    selected_dept = st.selectbox("Select Department:", departments)
    filtered_df = df[df["Department"] == selected_dept]
    st.dataframe(filtered_df)

    # ---- SALARY BAR CHART ----
    st.subheader("Salary Chart 📊")
    st.bar_chart(df.set_index("Name")["Salary"])

    # ---- DEPARTMENT COUNT ----
    st.subheader("Employees per Department 📈")
    dept_count = df["Department"].value_counts()
    st.bar_chart(dept_count)

else:
    st.info("👆 Please upload a CSV file to see the dashboard!")
