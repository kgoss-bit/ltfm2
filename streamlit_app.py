import streamlit as st
import pandas as pd
import numpy as np

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(layout="wide", page_title="Charter Group 10-Year Financial Model")
st.title("Charter Network: 10-Year Financial Scenario Planner")

# --- 2. THE SIDEBAR (LEADERSHIP CONTROLS) ---
st.sidebar.header("Scenario Drivers")

# Global Assumptions
cola_rate = st.sidebar.slider("Annual COLA (Revenue Growth)", 0.0, 5.0, 2.5, 0.1) / 100
salary_growth = st.sidebar.slider("Annual Salary Step Increase", 0.0, 5.0, 3.0, 0.1) / 100
mgmt_fee_pct = st.sidebar.slider("Management Fee %", 10.0, 20.0, 15.0, 0.5) / 100

st.sidebar.markdown("---")
st.sidebar.header("Growth & Structure")
activate_growth = st.sidebar.checkbox("Activate Growth (CWB LEA)?", value=False)
growth_join_og = st.sidebar.checkbox("Growth Joins Obligated Group?", value=False)
og_smoothing_active = st.sidebar.checkbox("Active OG Rent Smoothing?", value=True)

# --- 3. THE LOGIC ENGINE (CLASSES) ---

class School:
    def __init__(self, name, start_enrollment, is_og, is_growth=False):
        self.name = name
        self.enrollment = start_enrollment
        self.is_og = is_og
        self.is_growth = is_growth
        # Base Financials (Simplified for Demo)
        self.base_ppr = 14000  # Per Pupil Revenue
        self.base_personnel_cost = 9000 # Per Pupil Personnel Cost
        self.fixed_cost = 200000 # Local fixed costs (utilities, supplies)
        self.debt_service = 600000 if is_og else 400000 # Higher debt for OG schools (owned) vs Leased
        
    def forecast(self, years=10):
        # Creates a 10-year DataFrame for this specific school
        data = []
        current_enrollment = self.enrollment
        current_ppr = self.base_ppr
        current_personnel = self.base_personnel_cost
        
        for year in range(1, years + 1):
            # Growth Logic: Growth schools ramp up, Legacy schools stay flat (simplified)
            if self.is_growth:
                current_enrollment += 100 # Add 100 kids/year
            
            # Revenue Calculation
            gross_revenue = current_enrollment * current_ppr
            
            # The Fee Calculation (The 15% Rule)
            mgmt_fee = gross_revenue * mgmt_fee_pct
            net_revenue = gross_revenue - mgmt_fee
            
            # Expense Calculation
            personnel = current_enrollment * current_personnel
            # Rent is calculated LATER during the "Smoothing" phase
            
            data.append({
                "Year": year,
                "School": self.name,
                "Enrollment": current_enrollment,
                "Gross Revenue": gross_revenue,
                "Mgmt Fee": mgmt_fee,
                "Personnel": personnel,
                "Fixed Ops": self.fixed_cost,
                "Base Rent Obligation": self.debt_service, 
                "Net Income": 0 # Placeholder
            })
            
            # Inflate for next year
            current_ppr *= (1 + cola_rate)
            current_personnel *= (1 + salary_growth)
            self.fixed_cost *= 1.02 # 2% inflation on fixed goods
            
        return pd.DataFrame(data)

# --- 4. BUILDING THE FLEET ---
schools = []

# The Legacy 7
legacy_names = ["School A (OG)", "School B (OG)", "School C (OG)", "School D (OG)", "School E (OG)", "School F (Lease)", "School G (Lease)"]
for i, name in enumerate(legacy_names):
    is_og = "(OG)" in name
    schools.append(School(name, 500, is_og))

# The Growth Vehicle (CWB)
if activate_growth:
    # Modeled as one large LEA ramping up
    schools.append(School("Growth CWB (New)", 150, is_og=growth_join_og, is_growth=True))

# --- 5. THE SIMULATION RUN ---
# Generate raw data for all schools
all_data = pd.DataFrame()
for s in schools:
    all_data = pd.concat([all_data, s.forecast()])

# --- 6. THE SMOOTHING LOGIC (THE MAGIC) ---
# We need to process year-by-year to smooth rent across the Obligated Group
final_frames = []

for year in range(1, 11):
    year_slice = all_data[all_data["Year"] == year].copy()
    
    # Identify OG members for this year
    og_members = year_slice[year_slice["School"].str.contains("\(OG\)") | 
                           (year_slice["School"].str.contains("CWB") & (growth_join_og))]
    
    if og_smoothing_active and not og_members.empty:
        total_og_debt = og_members["Base Rent Obligation"].sum()
        total_og_enrollment = og_members["Enrollment"].sum()
        
        # Calculate "Smoothed Rent" per student
        rent_per_student = total_og_debt / total_og_enrollment
        
        # Apply back to the rows
        for index, row in og_members.iterrows():
            year_slice.at[index, "Final Rent"] = row["Enrollment"] * rent_per_student
            year_slice.at[index, "Rent Note"] = "Smoothed"
    else:
        # No smoothing, everyone pays their own base obligation
        year_slice["Final Rent"] = year_slice["Base Rent Obligation"]
        year_slice["Rent Note"] = "Fixed"

    # Handle Non-OG Schools (Lease)
    non_og_mask = ~year_slice.index.isin(og_members.index)
    year_slice.loc[non_og_mask, "Final Rent"] = year_slice.loc[non_og_mask, "Base Rent Obligation"]
    year_slice.loc[non_og_mask, "Rent Note"] = "Lease"

    # Final Net Income Calc
    year_slice["Net Income"] = year_slice["Gross Revenue"] - year_slice["Mgmt Fee"] - year_slice["Personnel"] - year_slice["Fixed Ops"] - year_slice["Final Rent"]
    year_slice["Margin %"] = (year_slice["Net Income"] / year_slice["Gross Revenue"]) * 100
    
    final_frames.append(year_slice)

full_forecast = pd.concat(final_frames)

# --- 7. THE DASHBOARD DISPLAY ---

# A. Home Office View
st.subheader("🏛️ Home Office Consolidated View")
ho_revenue = full_forecast.groupby("Year")["Mgmt Fee"].sum()
st.line_chart(ho_revenue)
st.caption(f"Projected Year 10 Home Office Revenue: ${ho_revenue.iloc[-1]:,.0f}")

# B. The Obligated Group Health (Covenant Check)
st.subheader("🛡️ Obligated Group (OG) Health")
og_data = full_forecast[full_forecast["Rent Note"] == "Smoothed"]
if not og_data.empty:
    og_stats = og_data.groupby("Year")[["Net Income", "Base Rent Obligation"]].sum()
    # DSCR proxy: (Net Income + Rent) / Rent. 
    # (Real DSCR is more complex, but this is the 'Vibe' proxy)
    og_stats["DSCR Proxy"] = (og_stats["Net Income"] + og_stats["Base Rent Obligation"]) / og_stats["Base Rent Obligation"]
    
    col1, col2 = st.columns(2)
    col1.line_chart(og_stats["DSCR Proxy"])
    col1.caption("Debt Service Coverage Ratio (Goal > 1.2x)")
    
    # Show the table for details
    col2.dataframe(og_stats.style.format("{:,.2f}"))
else:
    st.warning("Obligated Group Smoothing is OFF or No Schools in OG.")

# C. School-Level Traffic Light
st.subheader("🏫 Individual School Health (Year 5 Snapshot)")
y5 = full_forecast[full_forecast["Year"] == 5].set_index("School")
display_cols = ["Enrollment", "Gross Revenue", "Mgmt Fee", "Final Rent", "Net Income", "Margin %"]

def color_margin(val):
    color = 'red' if val < 0 else 'orange' if val < 3 else 'green'
    return f'color: {color}'

st.dataframe(y5[display_cols].style.applymap(color_margin, subset=['Margin %']).format({
    "Gross Revenue": "${:,.0f}",
    "Mgmt Fee": "${:,.0f}",
    "Final Rent": "${:,.0f}", 
    "Net Income": "${:,.0f}",
    "Margin %": "{:.1f}%"
}))