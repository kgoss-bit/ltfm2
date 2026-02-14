import streamlit as st
import pandas as pd
import numpy as np

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Charter Group Forecast v2.0")
st.title("Charter Network: 10-Year Strategic Model")
st.markdown("### v2.0: Including Shared Specialists & CWB Growth")

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

# Staffing Toggles (The "Value Prop" Check)
st.sidebar.subheader("Shared Specialists (Allocated)")
num_psychs = st.sidebar.number_input("# of Shared Psychologists", 0, 10, 2)
num_coaches = st.sidebar.number_input("# of Shared Math Coaches", 0, 10, 1)
avg_specialist_salary = 95000

# Home Office Core (Fee-Funded)
st.sidebar.subheader("Home Office Core")
ho_salary_base = st.sidebar.number_input("Total HO Salaries (CEO/Fin/HR)", 500000, 5000000, 1200000)

# --- 3. THE LOGIC ENGINE ---

# Helper function to grow a value over time
def grow(value, rate, years):
    return [value * ((1 + rate) ** i) for i in range(years)]

# A. SCHOOL CLASS
class School:
    def __init__(self, name, start_enrollment, is_og, is_growth=False):
        self.name = name
        self.enrollment = start_enrollment
        self.is_og = is_og
        self.is_growth = is_growth
        
        # Base Financials (Year 1)
        self.base_ppr = 14000 # Per Pupil Revenue (State + Federal Block)
        self.base_teacher_cost = 4500 # Direct Classroom Cost per pupil
        self.base_fixed = 250000 # Utilities, insurance, etc.
        self.base_rent = 550000 if is_og else 350000 # Higher if owned (debt service)
        
    def generate_projection(self, years=10):
        # Create empty DataFrame
        df = pd.DataFrame({"Year": range(1, years + 1)})
        df["School"] = self.name
        df["Is_OG"] = self.is_og
        
        # Enrollment Ramp
        if self.is_growth:
            # Linear ramp to target
            ramp = np.linspace(100, cwb_target_enrollment, 5) # 5 year ramp
            full = [cwb_target_enrollment] * (years - 5)
            enrollment_curve = np.concatenate([ramp, full])
            df["Enrollment"] = enrollment_curve
        else:
            # Mature schools stay flat
            df["Enrollment"] = self.enrollment

        # Revenue
        ppr_curve = grow(self.base_ppr, cola_rate, years)
        df["Gross Revenue"] = df["Enrollment"] * ppr_curve
        
        # Management Fee (The 15% Cut)
        df["Mgmt Fee"] = df["Gross Revenue"] * mgmt_fee_pct
        
        # Direct Expenses
        teacher_cost_curve = grow(self.base_teacher_cost, salary_growth, years)
        df["Direct Instruction"] = df["Enrollment"] * teacher_cost_curve * (1 + benefit_rate)
        
        fixed_cost_curve = grow(self.base_fixed, inflation, years)
        df["School Fixed Ops"] = fixed_cost_curve
        
        # Base Rent (Before Smoothing)
        df["Base Rent Obligation"] = self.base_rent # Simplified flat debt service
        
        return df

# --- 4. RUNNING THE SIMULATION ---

# Initialize Schools
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

# Combine all data
all_data = pd.DataFrame()
for s in schools:
    all_data = pd.concat([all_data, s.generate_projection()])

# --- 5. THE ALLOCATION LAYER (Rent & Specialists) ---

final_years = []

for year in range(1, 11):
    year_slice = all_data[all_data["Year"] == year].copy()
    
    # A. SHARED SPECIALIST ALLOCATION
    # Calculate Total Cost of Specialists for this year
    specialist_salary_inflated = avg_specialist_salary * ((1 + salary_growth) ** (year - 1))
    total_specialist_cost = (num_psychs + num_coaches) * specialist_salary_inflated * (1 + benefit_rate)
    
    # Allocate based on Enrollment %
    total_enrollment = year_slice["Enrollment"].sum()
    year_slice["Allocated Staff Costs"] = (year_slice["Enrollment"] / total_enrollment) * total_specialist_cost
    
    # B. RENT SMOOTHING
    og_mask = year_slice["Is_OG"] == True
    
    if og_smoothing_active and year_slice[og_mask].shape[0] > 0:
        total_og_debt = year_slice.loc[og_mask, "Base Rent Obligation"].sum()
        total_og_enrollment = year_slice.loc[og_mask, "Enrollment"].sum()
        
        # The Smoothing Calculation
        smoothed_rate = total_og_debt / total_og_enrollment
        year_slice.loc[og_mask, "Final Rent"] = year_slice.loc[og_mask, "Enrollment"] * smoothed_rate
        year_slice.loc[og_mask, "Rent Note"] = "Smoothed"
    else:
        year_slice.loc[og_mask, "Final Rent"] = year_slice.loc[og_mask, "Base Rent Obligation"]
        year_slice.loc[og_mask, "Rent Note"] = "Fixed"
        
    # Non-OG always pays base
    year_slice.loc[~og_mask, "Final Rent"] = year_slice.loc[~og_mask, "Base Rent Obligation"]
    year_slice.loc[~og_mask, "Rent Note"] = "Lease"

    # C. FINAL NET INCOME
    year_slice["Total Expenses"] = (year_slice["Mgmt Fee"] + 
                                   year_slice["Direct Instruction"] + 
                                   year_slice["School Fixed Ops"] + 
                                   year_slice["Allocated Staff Costs"] + 
                                   year_slice["Final Rent"])
                                   
    year_slice["Net Income"] = year_slice["Gross Revenue"] - year_slice["Total Expenses"]
    year_slice["Margin"] = year_slice["Net Income"] / year_slice["Gross Revenue"]