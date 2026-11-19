"""RealBasket dashboard. All source data and calculations are fetched from MCP (no local data access)."""
from __future__ import annotations

import base64

import pandas as pd
import plotly.express as px
import streamlit as st

from real_basket.mcp_server.client import call_tool, url

st.set_page_config(page_title="RealBasket – MCP", page_icon="🧺", layout="wide")


def de(value, digits=2):
    return f"{float(value):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(ttl=90, show_spinner="Lade validierte Werte über MCP …")
def snapshot():
    return call_tool("get_dashboard_snapshot")


st.title("🧺 RealBasket")
st.caption("Streamlit → Strands-Agent → MCP-Server → validierter Rechenkern / SQLite / Weaviate")
st.sidebar.header("🔌 MCP-Verbindung")
st.sidebar.code(url(), language="text")
try:
    data = snapshot()
    if "error" in data:
        raise RuntimeError(data["error"])
except Exception as exc:
    import traceback

    st.error("MCP-Abfrage fehlgeschlagen")
    st.code(
        "".join(traceback.format_exception(exc)),
        language="text"
    )
    st.info("Starte die Dienste mit `docker compose up --build -d` und prüfe `docker compose logs realbasket-mcp`.")
    if st.button("Erneut verbinden"):
        snapshot.clear()
        st.rerun()
    st.stop()

st.sidebar.success("MCP verbunden")
st.sidebar.caption(str(data["data_basis"]))
if st.sidebar.button("Daten neu laden"):
    snapshot.clear()
    st.rerun()

st.sidebar.header("📄 Referenzberichte")
try:
    refs = call_tool("list_reference_pdfs")["files"]
    for ref in refs:
        if st.sidebar.button("Laden: " + ref["filename"], key="ref_" + ref["filename"]):
            payload = call_tool("get_reference_pdf", filename=ref["filename"])
            st.session_state["download_pdf"] = (payload["filename"], base64.b64decode(payload["content_base64"]))
    if "download_pdf" in st.session_state:
        name, raw = st.session_state["download_pdf"]
        st.sidebar.download_button("⬇️ " + name, data=raw, file_name=name, mime="application/pdf")
    if st.sidebar.button("Auswertungsberichte generieren"):
        st.session_state["reports"] = call_tool("generate_reports")
    for filename, pdf64 in st.session_state.get("reports", {}).items():
        st.sidebar.download_button(filename, data=base64.b64decode(pdf64), file_name=filename,
                                   mime="application/pdf", key="generated_" + filename)
except Exception as exc:
    st.sidebar.warning(f"PDF-Funktionen nicht verfügbar: {exc}")

breakdown = data["breakdown"]
comparison = pd.DataFrame(data["comparison"])
prices = pd.DataFrame(data["prices"])
cities = pd.DataFrame(data["cities"])
category_names = {"food": "Lebensmittel", "housing_energy": "Wohnen / Energie",
                  "mobility": "Mobilität", "health": "Gesundheit", "communication": "Kommunikation"}

c1, c2, c3, c4 = st.columns(4)
c1.metric("ECLI ggü. Vorjahr", f"{de(breakdown['essential_yoy_pct'])} %")
c2.metric("VPI ggü. Vorjahr", f"{de(breakdown['cpi_yoy_pct'])} %")
c3.metric("Abweichung", f"{de(breakdown['deviation_pp'])} PP")
driver = breakdown["categories"][0]
c4.metric("Größter Einflussfaktor", category_names.get(driver["category"], driver["category"]),
          f"{de(driver['gap_pp'])} PP")
st.info("**Datenbasis:** " + data["note"] + " Eine Abweichung zum VPI bedeutet nicht, dass der VPI falsch ist.")

view_index, view_drivers, view_rent, view_rag, view_agent = st.tabs(
    ["📈 Index vs. VPI", "🧩 Einflussfaktoren", "🏠 Stadtmieten", "📚 PDF-Suche (Weaviate)", "🤖 MCP-Agent"])

with view_index:
    left, right = st.columns(2)
    with left:
        st.plotly_chart(px.line(comparison, x="period", y=["essential_index", "cpi_index"],
                                title="Index (Basis: November 2024 = 100)", labels={"value": "Index"}),
                        use_container_width=True)
    with right:
        st.plotly_chart(px.line(comparison, x="period", y=["essential_yoy_pct", "cpi_yoy_pct"],
                                title="Jährliche Veränderung", labels={"value": "%"}),
                        use_container_width=True)
    st.subheader("Modellierte Grundbedarfskosten in Euro")
    if not prices.empty:
        monthly = prices.pivot_table(index="period", columns="category", values="eur", aggfunc="sum")
        monthly = monthly.rename(columns=category_names)
        st.plotly_chart(px.area(monthly, title="Monatliche Ausgaben des Referenzwarenkorbs (€/Monat)"),
                        use_container_width=True)
        st.dataframe(monthly, use_container_width=True)

with view_drivers:
    st.caption("Deterministische Kategorienbeiträge aus dem MCP-Rechenkern.")
    drivers = pd.DataFrame(breakdown["categories"])
    drivers["Kategorie"] = drivers["category"].map(category_names)
    st.plotly_chart(px.bar(drivers, x="Kategorie", y="gap_pp", color="gap_pp",
                           title="Beiträge zur ECLI-VPI-Abweichung in Prozentpunkten"),
                    use_container_width=True)
    st.dataframe(drivers, use_container_width=True)
    with st.expander("Quelle und Datenprüfungen"):
        st.dataframe(pd.DataFrame(data["checks"]), use_container_width=True)
        st.dataframe(pd.DataFrame(data["base_amounts"]), use_container_width=True)
        st.write("PDF-Quellen:", ", ".join(data["documents"]))

with view_rent:
    st.caption("Veröffentlichte Angebotskaltmieten, keine repräsentativen Bestandsmieten oder Landesmieten.")
    if cities.empty:
        st.warning("Keine belegten Stadtmieten verfügbar.")
    else:
        st.dataframe(cities, use_container_width=True)
        st.plotly_chart(px.bar(cities.sort_values("rent_oct_eur_m2", ascending=False),
                               x="city", y="rent_oct_eur_m2", title="Miete Oktober 2026 in €/m²"),
                        use_container_width=True)
    st.subheader("Bundesländer – Datenabdeckung")
    st.info(data["state_note"])
    st.dataframe(pd.DataFrame(data["states"]), use_container_width=True)

with view_rag:
    st.caption("Semantische Suche ausschließlich via WeaviateVectorStore hinter dem MCP-Server. "
               "Für die Indizes werden keine Zahlen aus RAG übernommen.")
    query = st.text_input("PDF-Methodik durchsuchen", placeholder="Wie wird Wohnen / Energie berechnet?")
    if st.button("Weaviate durchsuchen") and query:
        try:
            found = call_tool("search_documents", query=query, top_k=5)
            if not found.get("passages"):
                st.info("Keine Treffer. Wurde die Weaviate-Ingestion bereits ausgeführt?")
            for passage in found.get("passages", []):
                st.markdown(f"**{passage.get('source_file', '?')} · S. {passage.get('page', '?')}**")
                st.write(passage.get("text", ""))
        except Exception as exc:
            st.error(f"Weaviate-Suche nicht verfügbar: {exc}. Bitte Embeddings konfigurieren und indexieren.")

with view_agent:
    st.caption("Der Strands-Agent lädt seine Tools über FastMCP. Er hat keine direkten lokalen Datentools.")
    st.session_state.setdefault("chat_history", [])
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("tools"):
                st.caption("MCP: " + " → ".join(msg["tools"]))
    question = st.chat_input("Wie hat sich der ECLI gegenüber dem VPI entwickelt?")
    if question:
        previous = st.session_state.chat_history[:]
        st.session_state.chat_history.append({"role": "user", "content": question})
        st.chat_message("user").write(question)
        with st.chat_message("assistant"), st.spinner("MCP-Tools werden aufgerufen …"):
            try:
                from real_basket.mcp_server.agent import ask
                answer, invoked = ask(question, previous)
            except Exception as exc:
                answer, invoked = f"Agenten- oder MCP-Fehler: {exc}", []
            st.write(answer)
            if invoked:
                st.caption("MCP: " + " → ".join(invoked))
        st.session_state.chat_history.append({"role": "assistant", "content": answer, "tools": invoked})
    if st.button("Neuer Chat"):
        st.session_state.chat_history = []
        st.rerun()
