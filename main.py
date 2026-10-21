import streamlit as st
import pandas as pd
import plotly.express as px
import io

# --- Page Configuration ---
st.set_page_config(page_title="Data Analyzer Pro", layout="wide")

# --- Reusable Functions ---
@st.cache_data
def load_data(uploaded_file):
    """Loads data based on file extension with error handling."""
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        elif uploaded_file.name.endswith('.json'):
            df = pd.read_json(uploaded_file)
        else:
            return None, "Unsupported file format."
        return df, None
    except Exception as e:
        return None, f"Error loading file: {e}"

def clean_data(df):
    """Preprocess data: force numeric columns, clean currency, and set categories."""
    df_cleaned = df.drop_duplicates().copy()
    
    # 1. Explicitly force known numeric columns to float, turning text like 'unknown' to NaN
    numeric_targets = ['Sales', 'Quantity', 'Discount', 'Profit']
    for col in numeric_targets:
        if col in df_cleaned.columns:
            # Strip $ and commas, then coerce to numeric
            cleaned_str = df_cleaned[col].astype(str).str.replace(r'[$,]', '', regex=True)
            df_cleaned[col] = pd.to_numeric(cleaned_str, errors='coerce')
            # Fill the resulting NaNs with 0
            df_cleaned[col] = df_cleaned[col].fillna(0)

    # 2. Convert remaining object (text) columns to categorical
    cat_cols = df_cleaned.select_dtypes(include=['object']).columns
    for col in cat_cols:
        df_cleaned[col] = df_cleaned[col].fillna('Unknown').astype('category')
        
    return df_cleaned

def remove_outliers(df, columns):
    """Removes outliers from specified columns using the IQR method."""
    df_out = df.copy()
    for col in columns:
        # Check if the column exists and is numeric
        if col in df_out.columns and pd.api.types.is_numeric_dtype(df_out[col]):
            Q1 = df_out[col].quantile(0.25)
            Q3 = df_out[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            # Keep only the rows within the normal range
            df_out = df_out[(df_out[col] >= lower_bound) & (df_out[col] <= upper_bound)]
    return df_out

def calculate_kpis(df):
    """Calculates the 5 required KPIs, forcing numeric types to prevent string errors."""
    sales_col = 'Sales' if 'Sales' in df.columns else df.columns[0]
    profit_col = 'Profit' if 'Profit' in df.columns else df.columns[1]
    qty_col = 'Quantity' if 'Quantity' in df.columns else df.columns[2]
    order_col = 'Order ID' if 'Order ID' in df.columns else df.columns[3]

    # Forcefully convert to numeric, turning stubborn text into NaN (which sums to 0)
    total_sales = pd.to_numeric(df[sales_col].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce').sum()
    total_profit = pd.to_numeric(df[profit_col].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce').sum()
    total_qty = pd.to_numeric(df[qty_col].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce').sum()
    total_orders = df[order_col].nunique()

    # Calculate margin safely
    profit_margin = (total_profit / total_sales * 100) if total_sales != 0 else 0

    return total_sales, total_profit, total_orders, total_qty, profit_margin

# --- Main App Interface ---
st.title("📊 Interactive Data Analysis Dashboard")
st.write("Upload your dataset (like `experiment10_raw_dataset.csv`) to validate, clean, and visualize the data.")

# 1. Data Upload and Validation
uploaded_file = st.file_uploader("Upload CSV, Excel, or JSON file", type=['csv', 'xlsx', 'json'])

if uploaded_file is not None:
    df_raw, error = load_data(uploaded_file)
    
    if error:
        st.error(error)
    else:
        st.header("1. Data Validation & Overview")
        col1, col2, col3 = st.columns(3)
        col1.metric("Rows & Columns", f"{df_raw.shape[0]} x {df_raw.shape[1]}")
        col2.metric("Missing Values", df_raw.isna().sum().sum())
        col3.metric("Duplicate Records", df_raw.duplicated().sum())
        
        with st.expander("View Column Names and Data Types"):
            st.write(df_raw.dtypes)

        # 2. Data Preprocessing and Analysis
        st.header("2. Data Preprocessing")
        df_clean = clean_data(df_raw)
        st.success("Data cleaned: Duplicates removed and missing values handled.")
        
        with st.expander("View Statistical Summary"):
            st.write(df_clean.describe())

        # 3. Interactive Filters
        st.header("3. Filters & KPIs")
        st.sidebar.header("Interactive Filters")
        
        # We dynamically grab categorical columns for filtering
        cat_cols = df_clean.select_dtypes(include=['object', 'category']).columns.tolist()
        
        if len(cat_cols) >= 2:
            filter1_col = cat_cols[0]
            filter2_col = cat_cols[1]
            
            filter1_val = st.sidebar.multiselect(f"Filter by {filter1_col}", options=df_clean[filter1_col].unique(), default=df_clean[filter1_col].unique())
            filter2_val = st.sidebar.multiselect(f"Filter by {filter2_col}", options=df_clean[filter2_col].unique(), default=df_clean[filter2_col].unique())
            
            # Apply filters
            df_filtered = df_clean[df_clean[filter1_col].isin(filter1_val) & df_clean[filter2_col].isin(filter2_val)]
        else:
            st.sidebar.warning("Not enough categorical columns for standard filters.")
            df_filtered = df_clean
            
        # Optional: Numeric Slider Filter
        num_cols = df_clean.select_dtypes(include=['number']).columns.tolist()
        if num_cols:
            filter3_col = num_cols[0]
            min_val, max_val = float(df_clean[filter3_col].min()), float(df_clean[filter3_col].max())
            filter3_val = st.sidebar.slider(f"Filter by {filter3_col} range", min_value=min_val, max_value=max_val, value=(min_val, max_val))
            df_filtered = df_filtered[(df_filtered[filter3_col] >= filter3_val[0]) & (df_filtered[filter3_col] <= filter3_val[1])]

        # --- Add this right below your existing sidebar filters ---
        st.sidebar.markdown("---")
        apply_outlier_filter = st.sidebar.checkbox("Remove Outliers (IQR)", help="Strips extreme values from numerical columns to improve chart scaling.")

        # Apply the outlier filter if the user checked the box
        if apply_outlier_filter and len(num_cols) > 0:
            df_filtered = remove_outliers(df_filtered, num_cols)
            st.success("Outliers removed! Visualizations will now scale better.")
        # ----------------------------------------------------------
        
        # Calculate and Display KPIs (this remains the same)
        sales, profit, orders, qty, margin = calculate_kpis(df_filtered)

        # Calculate and Display KPIs
        sales, profit, orders, qty, margin = calculate_kpis(df_filtered)
        
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Total Sales", f"${sales:,.2f}")
        kpi2.metric("Total Profit", f"${profit:,.2f}")
        kpi3.metric("Total Orders", f"{orders:,}")
        kpi4.metric("Total Quantity", f"{qty:,}")
        kpi5.metric("Profit Margin", f"{margin:.2f}%")

        # 4. Interactive Visualization
        st.header("4. Interactive Visualizations")
        
        if len(cat_cols) > 0 and len(num_cols) > 0:
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.subheader(f"Sales Distribution by {cat_cols[0]}")
                # Grouping data for the chart
                bar_data = df_filtered.groupby(cat_cols[0])[num_cols[0]].sum().reset_index()
                fig_bar = px.bar(bar_data, x=cat_cols[0], y=num_cols[0], template="plotly_white")
                st.plotly_chart(fig_bar, use_container_width=True)
                
            with chart_col2:
                st.subheader(f"Proportion by {cat_cols[-1]}")
                pie_data = df_filtered.groupby(cat_cols[-1])[num_cols[0]].sum().reset_index()
                fig_pie = px.pie(pie_data, names=cat_cols[-1], values=num_cols[0], template="plotly_white")
                st.plotly_chart(fig_pie, use_container_width=True)
                
            st.subheader(f"Scatter Plot: {num_cols[0]} vs {num_cols[1] if len(num_cols) > 1 else num_cols[0]}")
            y_axis_col = num_cols[1] if len(num_cols) > 1 else num_cols[0]
            fig_scatter = px.scatter(df_filtered, x=num_cols[0], y=y_axis_col, color=cat_cols[0], template="plotly_white")
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.warning("The dataset needs at least one categorical and numeric column for visualizations.")