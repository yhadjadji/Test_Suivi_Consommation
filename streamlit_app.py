import streamlit as st
import pandas as pd
from datetime import datetime, date

# Configuration de la page et style simple
st.set_page_config(page_title="Suivi Stock & Consommation", layout="wide")
st.markdown(
    """
    <style>
    .stMetric { text-align: center; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialisation de l'état de session
st.session_state.setdefault("start_time", datetime.now())
st.session_state.setdefault("live_records", [])
st.session_state.setdefault("catalog", None)
st.session_state.setdefault("show_add_form", False)


def process_scan():
    """Traite un scan de code-barres."""
    code = st.session_state["scan_input"].strip()
    st.session_state["last_scan_error"] = None
    st.session_state["last_scan_message"] = None
    try:
        if st.session_state["catalog"] is None:
            raise ValueError("Pas de catalogue chargé.")
        df_cat = st.session_state["catalog"]
        match = df_cat[df_cat["code_carton"] == code]
        if match.empty:
            match = df_cat[df_cat["code_carton"].apply(lambda x: code.endswith(x))]
        if match.empty:
            st.session_state["show_add_form"] = True
            raise ValueError(f"Code-barres '{code}' non trouvé dans le catalogue.")
        info = match.iloc[0]
        record = {
            "timestamp": datetime.now(),
            "scan_code": code,
            "code_carton": info["code_carton"],
            "nom_produit": info["nom_produit"],
            "quantite_par_carton": int(info["quantite_par_carton"]),
            "consommation": int(info["quantite_par_carton"]),
        }
        st.session_state["live_records"].append(record)
        st.session_state["last_scan_message"] = f"✅ Scanné : {code}"
    except Exception as exc:  # pylint: disable=broad-except
        st.session_state["last_scan_error"] = str(exc)
    finally:
        st.session_state["scan_input"] = ""


# --- TITRE & MÉTRIQUES ---
st.title("📦 Outil de Gestion de Stock & Consommation")
now = datetime.now()
duration = now - st.session_state["start_time"]
col1, col2, col3 = st.columns(3)
col1.metric(
    "⏱️ Durée session",
    f"{duration.seconds // 3600}h {(duration.seconds % 3600) // 60}m {duration.seconds % 60}s",
)
col2.metric("📑 Total scans", len(st.session_state["live_records"]))
if st.session_state["live_records"]:
    df_tmp = pd.DataFrame(st.session_state["live_records"])
    start_month = pd.Timestamp(date.today().replace(day=1))
    total_monthly_scans = df_tmp[df_tmp["timestamp"] >= start_month].shape[0]
else:
    total_monthly_scans = 0
col3.metric("📆 Total mensuel", int(total_monthly_scans))
st.markdown("---")

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("🔧 Configuration")
catalog_file = st.sidebar.file_uploader("Catalogue produits (CSV)", type=["csv"])
if catalog_file:
    cat = pd.read_csv(catalog_file, dtype={"code_carton": str})
    cat["code_carton"] = cat["code_carton"].str.strip()
    st.session_state["catalog"] = cat
    st.sidebar.success("📦 Catalogue chargé")

scan_code = st.sidebar.text_input(
    "Scannez un code-barres :", key="scan_input", on_change=process_scan
)
if st.session_state.get("last_scan_message"):
    st.sidebar.success(st.session_state.pop("last_scan_message"))
if st.session_state.get("last_scan_error"):
    st.sidebar.error(st.session_state.pop("last_scan_error"))

if st.session_state["show_add_form"]:
    st.sidebar.markdown("---")
    st.sidebar.warning("Produit inconnu ! Veuillez l'ajouter au catalogue.")
    with st.sidebar.form(key="add_product"):
        new_code = st.text_input("Code carton", value=scan_code or "")
        new_name = st.text_input("Nom produit")
        new_qty = st.number_input("Quantité par carton", min_value=1, value=1)
        if st.form_submit_button("Ajouter au catalogue"):
            new_entry = {
                "code_carton": new_code.strip(),
                "nom_produit": new_name.strip(),
                "quantite_par_carton": int(new_qty),
            }
            st.session_state["catalog"] = pd.concat(
                [st.session_state["catalog"], pd.DataFrame([new_entry])],
                ignore_index=True,
            )
            st.sidebar.success(f"Produit '{new_name}' ajouté.")
            st.session_state["show_add_form"] = False


# --- AFFICHAGE DES SCANS LIVE ---
st.subheader("📋 Scans en direct")
if st.session_state["live_records"]:
    df_live = pd.DataFrame(st.session_state["live_records"])
    df_live["date"] = df_live["timestamp"].dt.date
    st.dataframe(
        df_live[[
            "timestamp",
            "code_carton",
            "nom_produit",
            "quantite_par_carton",
            "consommation",
        ]],
        use_container_width=True,
    )
    daily = df_live[df_live["date"] == date.today()]["consommation"].sum()
    monthly = df_live[df_live["timestamp"] >= pd.Timestamp(date.today().replace(day=1))]["consommation"].sum()
    c1, c2 = st.columns(2)
    c1.metric("📅 Cumul quotidien", int(daily))
    c2.metric("📆 Cumul mensuel", int(monthly))

    st.subheader("📈 Récapitulatif mensuel par produit")
    recap = df_live[df_live["timestamp"] >= pd.Timestamp(date.today().replace(day=1))]
    recap = (
        recap.groupby("nom_produit")
        .agg(cartons=("scan_code", "count"), total_consommation=("consommation", "sum"))
        .reset_index()
    )
    st.dataframe(recap, use_container_width=True)

    csv = df_live.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Exporter live (CSV)", data=csv, file_name="scans_live.csv", mime="text/csv"
    )
else:
    st.info("🤖 Aucune entrée de scan pour le moment.")

# --- IMPORT MULTI-BATCH ---
st.sidebar.markdown("---")
st.sidebar.header("📂 Import batch scans (multiple)")
batch_files = st.sidebar.file_uploader(
    "Sélectionner un ou plusieurs fichiers scans CSV", type=["csv"], accept_multiple_files=True
)
if batch_files:
    if st.session_state["catalog"] is None:
        st.sidebar.error("Erreur: pas de catalogue chargé.")
    else:
        enriched = []
        for bf in batch_files:
            df_batch = pd.read_csv(
                bf, parse_dates=["timestamp"], dtype={"scan_code": str}, dayfirst=True
            )
            for _, r in df_batch.iterrows():
                val = r["scan_code"].strip()
                df_cat = st.session_state["catalog"]
                m = df_cat[df_cat["code_carton"] == val]
                if m.empty:
                    m = df_cat[df_cat["code_carton"].apply(lambda x: val.endswith(x))]
                if m.empty:
                    continue
                info = m.iloc[0]
                enriched.append(
                    {
                        "timestamp": r["timestamp"],
                        "scan_code": val,
                        "code_carton": info["code_carton"],
                        "nom_produit": info["nom_produit"],
                        "quantite_par_carton": int(info["quantite_par_carton"]),
                        "consommation": int(info["quantite_par_carton"]),
                    }
                )
        df_en = pd.DataFrame(enriched)
        df_en["mois"] = df_en["timestamp"].dt.to_period("M").dt.to_timestamp()
        st.subheader("📑 Détail Batch Multi-Fichiers")
        st.dataframe(
            df_en[[
                "timestamp",
                "code_carton",
                "nom_produit",
                "quantite_par_carton",
                "consommation",
            ]],
            use_container_width=True,
        )
        synth = (
            df_en.groupby(["mois", "nom_produit"])
            .agg(cartons=("scan_code", "count"), total_consommation=("consommation", "sum"))
            .reset_index()
        )
        st.subheader("📊 Synthèse mensuelle batch")
        st.dataframe(synth, use_container_width=True)
        st.subheader("📈 Évolution mensuelle")
        pivot = synth.pivot(index="mois", columns="nom_produit", values="total_consommation").fillna(0)
        st.line_chart(pivot, use_container_width=True)

# --- FOOTER ---
st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Catalogue requis :** code_carton, nom_produit, quantite_par_carton"
)
st.sidebar.markdown("[📖 Documentation](https://example.com/docs)")
