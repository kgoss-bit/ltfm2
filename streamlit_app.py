import streamlit as st
import pandas as pd
import numpy as np

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Charter Group Forecast v2.1")
st.title("Charter Network: 10-Year Strategic Model (v2.1)")

# --- 2. GLOBAL ASSUMPTIONS (SIDEBAR) ---
st.sidebar.header("Global Assumptions")

# Economic Drivers
cola_rate = st.sidebar.slider("Annual Revenue COLA %", 0.0, 5.0, 2.5, 0.1) / 100
salary_growth = st.sidebar.slider("Annual Salary Step %", 0.0, 5.0, 3.0, 0.1) / 100
benefit_rate = st.sidebar.slider("Benefit Load %", 20, 40, 25, 1) / 100
inflation = 0.02 # General inflation

st.sidebar.markdown("---")
st.sidebar.header("Network Structure")
mgmt_fee_pct = st.sidebar.slider("Management Fee %", 10.0, 20.0, 15.0, 0.5) / 100
og_smoothing_active = st.sidebar.checkbox("Active OG Rent Smoothing?", value=True)

# Growth Toggles
st.sidebar.subheader("Growth Scenarios")
launch_cwb = st.sidebar.checkbox("Launch CWB (Growth LEA)?", value=False)
cwb_join_og = st.sidebar.checkbox("CWB Joins Obligated Group?", value=False)
cwb_target_enrollment = st.sidebar.number_input("CWB Target Enrollment (Year 5)", 100, 2000, 500)

# Staffing Toggles
st.sidebar.subheader("Shared Specialists (Allocated)")
num_psychs = st.sidebar.number_input("# of Shared Psychologists", 0, 10, 2)
num_coaches = st.sidebar.number_input("# of Shared Math Coaches", 0, 10, 1)
avg_specialist_salary = 95000

# Home Office Core
st.sidebar.subheader("Home Office Core")
ho_salary_base = st.sidebar.number_input("Total HO Salaries (CEO/Fin/HR)", 500000, 5000000, 1200000)

# --- 3. THE LOGIC ENGINE ---

def grow(value, rate, years):
    return [value * ((1 + rate) ** i) for i in range(years)]

class School:
    def __init__(self, name, start_enrollment, is_og, is_growth=False):
        self.name = name
        self.enrollment = start_enrollment
        self.is_og = is_og
        self.is_growth = is_growth
        
        self.base_ppr = 14000 
        self.base_teacher_cost = 4500 
        self.base_fixed = 250000 
        self.base_rent = 550000 if is_og else 350000 
        
    def generate_projection(self, years=10):
        df = pd.DataFrame({"Year": range(1, years + 1)})
        df["School"] = self.name
        df["Is_OG"] = self.is_og
        
        if self.is_growth:
            ramp = np.linspace(100, cwb_target_enrollment, 5)
            full = [cwb_target_enrollment] * (years - 5)
            enrollment_curve = np.concatenate([ramp, full])
            df["Enrollment"] = enrollment_curve
        else:
            df["Enrollment"] = self.enrollment

        ppr_curve = grow(self.base_ppr, cola_rate, years)
        df["Gross Revenue"] = df["Enrollment"] * ppr_curve
        df["Mgmt Fee"] = df["Gross Revenue"] * mgmt_fee_pct
        
        teacher_cost_curve = grow(self.base_teacher_cost, salary_growth, years)
        df["Direct Instruction"] = df["Enrollment"] * teacher_cost_curve * (1 + benefit_rate)
        
        fixed_cost_curve = grow(self.base_fixed, inflation, years)
        df["School Fixed Ops"] = fixed_cost_curve
        
        df["Base Rent Obligation"] = self.base_rent
        
        return df

# --- 4. RUNNING THE SIMULATION ---

schools = []
legacy_configs = [
    ("School A (OG)", 500, True), ("School B (OG)", 480, True), 
    ("School C (OG)", 520, True), ("School D (OG)", 450, True), 
    ("School E (OG)", 600, True), ("School F (Ext)", 350, False), 
    ("School G (Ext)", 380, False)
]

for name, enr, og in legacy_configs:
    schools.append(School(name, enr, og))

if launch_cwb:
    schools.append(School("Growth CWB (New)", 100, is_og=cwb_join_og, is_growth=True))

all_data = pd.DataFrame()
for s in schools:
    all_data = pd.concat([all_data, s.generate_projection()])

# --- 5. THE ALLOCATION LAYER ---

final_years = []

for year in range(1, 11):
    year_slice = all_data[all_data["Year"] == year].copy()
    
    # Specialist Allocation
    specialist_salary_inflated = avg_specialist_salary * ((1 + salary_growth) ** (year - 1))
    total_specialist_cost = (num_psychs + num_coaches) * specialist_salary_inflated * (1 + benefit_rate)
    total_enrollment = year_slice["Enrollment"].sum()
    year_slice["Allocated Staff Costs"] = (year_slice["Enrollment"] / total_enrollment) * total_specialist_cost
    
    # Rent Smoothing
    og_mask = year_slice["Is_OG"] == True
    
    if og_smoothing_active and year_slice[og_mask].shape[0] > 0:
        total_og_debt = year_slice.loc[og_mask, "Base Rent Obligation"].sum()
        total_og_enrollment = year_slice.loc[og_mask, "Enrollment"].sum()
        smoothed_rate = total_og_debt / total_og_enrollment
        year_slice.loc[og_mask, "Final Rent"] = year_slice.loc[og_mask, "Enrollment"] * smoothed_rate
        year_slice.loc[og_mask, "Rent Note"] = "Smoothed"
    else:
        year_slice.loc[og_mask, "Final Rent"] = year_slice.loc[og_mask, "Base Rent Obligation"]
        year_slice.loc[og_mask, "Rent Note"] = "Fixed"
        
    year_slice.loc[~og_mask, "Final Rent"] = year_slice.loc[~og_mask, "Base Rent Obligation"]
    year_slice.loc[~og_mask, "Rent Note"] = "Lease"

    year_slice["Total Expenses"] = (year_slice["Mgmt Fee"] + 
                                   year_slice["Direct Instruction"] + 
                                   year_slice["School Fixed Ops"] + 
                                   year_slice["Allocated Staff Costs"] + 
                                   year_slice["Final Rent"])
                                   
    year_slice["Net Income"] = year_slice["Gross Revenue"] - year_slice["Total Expenses"]
    year_slice["Margin"] = year_slice["Net Income"] / year_slice["Gross Revenue"]
    
    final_years.append(year_slice)

forecast = pd.concat(final_years)

# --- 6. HOME OFFICE P&L ---
ho_data = []
for year in range(1, 11):
    ys = forecast[forecast["Year"] == year]
    total_fees = ys["Mgmt Fee"].sum()
    core_cost = ho_salary_base * ((1 + salary_growth) ** (year - 1)) * (1 + benefit_rate)
    net_ho = total_fees - core_cost
    ho_data.append({
        "Year": year,
        "Total Fee Revenue": total_fees,
        "Core HO Expense": core_cost,
        "HO Net Income": net_ho,
        "HO Margin": net_ho / total_fees
    })

ho_df = pd.DataFrame(ho_data)

# --- 7. DASHBOARD VISUALS (SAFE MODE) ---

tab1, tab2, tab3 = st.tabs(["🏛️ Network Health", "🏫 School Details", "📈 Growth Impact"])

with tab1:
    st.subheader("Home Office Financial Stability")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.metric("Year 10 HO Revenue", f"${ho_df.iloc[-1]['Total Fee Revenue']:,.0f}")
        st.metric("Year 10 HO Expense", f"${ho_df.iloc[-1]['Core HO Expense']:,.0f}")
        st.metric("Year 10 Margin", f"{ho_df.iloc[-1]['HO Margin']:.1%}")

    with col2:
        st.line_chart(ho_df.set_index("Year")[["Total Fee Revenue", "Core HO Expense"]])
        st.caption("Blue: Revenue | Red: Expenses")

with tab2:
    st.subheader("Individual School Viability (Year 5)")
    y5 = forecast[forecast["Year"] == 5].copy()
    
    # Simplified Dataframe (No complex styling)
    display_cols = ["School", "Enrollment", "Gross Revenue", "Mgmt Fee", "Allocated Staff Costs", "Final Rent", "Net Income", "Margin"]
    
    # Format numbers for cleaner display
    y5_clean = y5[display_cols].copy()
    y5_clean["Margin"] = y5_clean["Margin"].apply(lambda x: f"{x:.1%}")
    y5_clean["Net Income"] = y5_clean["Net Income"].apply(lambda x: f"${x:,.0f}")
    
    st.dataframe(y5_clean)
    st.info("💡 Note: Positive Margins are safe.