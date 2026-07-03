"""
streamlit demo for the SOC Co-pilot agent.
run with: streamlit run src/app.py
"""

import sys
import os

# streamlit doesn't add the repo root to the python path automatically,
# so we do it manually here — this lets "from src.agent..." imports work
# no matter which folder you launch streamlit from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from src.agent.graph import triage_graph

st.set_page_config(page_title="SOC Co-pilot", page_icon="🛡️", layout="centered")

st.title("🛡️ SOC Co-pilot")
st.caption("LLM-assisted alert triage — paste alert fields, get a verdict")

st.subheader("alert fields")

col1, col2 = st.columns(2)
with col1:
    category = st.text_input("Category", placeholder="e.g. InitialAccess")
    entity_type = st.text_input("EntityType", placeholder="e.g. User")
    mitre_technique = st.text_input("MitreTechniques", placeholder="e.g. T1078")
with col2:
    title = st.text_input("Title", placeholder="alert title / summary")
    evidence = st.text_area("EvidenceRole / details", placeholder="any extra context")

if st.button("run triage", type="primary"):
    raw_alert = {
        "Category": category,
        "EntityType": entity_type,
        "MitreTechniques": mitre_technique,
        "Title": title,
        "Evidence": evidence,
    }

    with st.spinner("running agent..."):
        result = triage_graph.invoke({"raw_alert": raw_alert})

    st.divider()
    st.subheader("result")

    verdict = result.get("predicted_label", "unknown")
    confidence = result.get("confidence", "unknown")
    needs_review = result.get("needs_human_review", False)

    verdict_colors = {
        "TruePositive": "🔴",
        "BenignPositive": "🟡",
        "FalsePositive": "🟢",
    }
    icon = verdict_colors.get(verdict, "⚪")

    c1, c2, c3 = st.columns(3)
    c1.metric("verdict", f"{icon} {verdict}")
    c2.metric("confidence", confidence)
    c3.metric("human review needed", "yes" if needs_review else "no")

    st.write("**reasoning:**")
    st.write(result.get("reasoning", "n/a"))

    if result.get("mitre_context"):
        st.write("**MITRE ATT&CK context used:**")
        st.info(result["mitre_context"])

    if needs_review:
        st.warning("this alert was flagged for human review because confidence was not high.")

    with st.expander("raw agent state"):
        st.json(result)