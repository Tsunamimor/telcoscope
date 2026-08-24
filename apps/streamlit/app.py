"""telcoscope Incident Inspector — Streamlit drill-down for individual anomalies.

Run locally:

    streamlit run apps/streamlit/app.py

This is the v1 skeleton. The full implementation lands in Week 5.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="telcoscope — Incident Inspector",
    page_icon="📡",
    layout="wide",
)

st.title("📡 telcoscope — Incident Inspector")
st.caption("Drill-down view for individual anomalies and their RCA hypotheses.")

# --- Sidebar: incident selection ---
with st.sidebar:
    st.header("Select incident")
    st.info("Once the detection layer is wired up (Week 3+), this list will "
            "be populated from the `incidents` table.")
    incident_id = st.text_input("Incident UID", value="")
    st.divider()
    st.subheader("Filters")
    st.selectbox("KPI", options=["(all)", "rrc_conn_setup_sr", "erab_setup_sr",
                                 "erab_drop_rate", "intra_lte_ho_sr",
                                 "dl_user_throughput_kbps",
                                 "cell_availability_pct"])
    st.selectbox("Severity", options=["(all)", "critical", "major", "minor"])

# --- Main panel ---
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("KPI timeline")
    st.info("Plotly chart of the affected KPI ± baseline ± anomaly markers "
            "will render here once data flows.")

    st.subheader("Concurrent alarms")
    st.info("Timeline of FM alarms on the same eNB / region within the "
            "incident window.")

with col_right:
    st.subheader("RCA hypotheses")
    st.info("Ranked list of matching RCA rules with confidence scores.")

    st.subheader("LLM narrative")
    st.info("Human-readable incident summary from the narrator service.")

st.divider()
st.caption("v0.1 scaffold — apps/streamlit/app.py")
