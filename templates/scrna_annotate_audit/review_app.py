#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import anndata as ad
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = APP_DIR if (APP_DIR / "annotation_audit.json").exists() else APP_DIR / "results"
TABLES_DIR = RESULTS_DIR / "tables"
RUN_DIR = RESULTS_DIR.parent
CONFIG_DIR = RUN_DIR / "config"
FINAL_DECISIONS_PATH = CONFIG_DIR / "final_annotation_decisions.csv"
FINAL_H5AD_PATH = RESULTS_DIR / "adata.final_annotated.h5ad"
PREFIX = "scrna_annotate_audit"


@st.cache_data(show_spinner=False)
def load_json(path: str) -> dict | list:
    return json.loads(Path(path).read_text())


@st.cache_data(show_spinner=False)
def load_table(path: str) -> pd.DataFrame:
    return pd.read_csv(path).astype({"cluster_id": str})


@st.cache_data(show_spinner=False)
def available_umaps(input_h5ad: str) -> list[str]:
    adata = ad.read_h5ad(input_h5ad, backed="r")
    try:
        keys = []
        for key in adata.obsm.keys():
            coords = adata.obsm[key]
            if "umap" in str(key).lower() and len(coords.shape) == 2 and coords.shape[1] >= 2:
                keys.append(str(key))
        return sorted(keys, key=lambda key: (0 if key == "X_umap" else 1, key))
    finally:
        try:
            adata.file.close()
        except Exception:
            pass


@st.cache_data(show_spinner=True)
def load_umap(input_h5ad: str, cluster_key: str, sample_key: str, embedding_key: str) -> pd.DataFrame:
    adata = ad.read_h5ad(input_h5ad, backed="r")
    try:
        coords = adata.obsm[embedding_key]
        return pd.DataFrame(
            {
                "UMAP1": coords[:, 0],
                "UMAP2": coords[:, 1],
                "cluster_id": adata.obs[cluster_key].astype(str).values,
                "sample": adata.obs[sample_key].astype(str).values if sample_key and sample_key in adata.obs else "all",
            }
        )
    finally:
        try:
            adata.file.close()
        except Exception:
            pass


def cluster_sort_key(value: object) -> tuple[int, int | str]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def card_by_cluster(cards: list[dict]) -> dict[str, dict]:
    return {str(card.get("cluster_id")): card for card in cards}


def provider_rows(card: dict) -> pd.DataFrame:
    rows = []
    for provider, record in (card.get("methods") or {}).items():
        rows.append(
            {
                "provider": provider,
                "annotation": record.get("label") or "",
                "broad_label": record.get("broad_label") or "",
                "confidence": record.get("confidence") or "",
            }
        )
    return pd.DataFrame(rows)


def decision_defaults(card: dict, decisions: pd.DataFrame) -> dict[str, str]:
    cluster_id = str(card.get("cluster_id"))
    row = decisions[decisions["cluster_id"].astype(str) == cluster_id]
    if len(row):
        item = row.iloc[0].to_dict()
    else:
        item = {}
    final = card.get("final") or {}
    return {
        "final_label": str(item.get("final_label") or final.get("label") or card.get("suggested_label") or ""),
        "review_status": str(item.get("review_status") or final.get("review_status") or "not_reviewed"),
        "reviewer_note": str(item.get("reviewer_note") or final.get("reviewer_note") or ""),
    }


def update_decision(decisions: pd.DataFrame, card: dict, values: dict[str, str]) -> pd.DataFrame:
    cluster_id = str(card.get("cluster_id"))
    updated = decisions.copy()
    if cluster_id not in set(updated["cluster_id"].astype(str)):
        updated.loc[len(updated)] = {
            "cluster_id": cluster_id,
            "suggested_label": card.get("suggested_label") or "",
            "suggested_broad_label": card.get("suggested_broad_label") or "",
            "decision": card.get("decision") or "",
            "confidence": card.get("confidence") or "",
            "agreement_level": card.get("agreement_level") or "",
            "review_priority": card.get("review_priority") or "",
            "review_status": "not_reviewed",
            "final_label": "",
            "reviewer_note": "",
        }
    mask = updated["cluster_id"].astype(str) == cluster_id
    for key, value in values.items():
        updated.loc[mask, key] = value
    return updated


def write_final_h5ad(input_h5ad: str, cluster_key: str, cards: list[dict], decisions: pd.DataFrame, output_h5ad: Path) -> None:
    adata = ad.read_h5ad(input_h5ad)
    if cluster_key not in adata.obs:
        raise ValueError(f"cluster_key '{cluster_key}' was not found in input h5ad")
    decision_lookup = {str(row["cluster_id"]): row for row in decisions.to_dict(orient="records")}
    card_lookup = card_by_cluster(cards)
    clusters = adata.obs[cluster_key].astype(str)

    final_labels = []
    review_statuses = []
    label_sources = []
    suggested_labels = []
    agreement_levels = []
    confidences = []
    for cluster_id in clusters:
        card = card_lookup.get(cluster_id, {})
        row = decision_lookup.get(cluster_id, {})
        final_label = str(row.get("final_label") or card.get("suggested_label") or "Unknown")
        review_status = str(row.get("review_status") or "not_reviewed")
        final_labels.append(final_label)
        review_statuses.append(review_status)
        if review_status in {"accepted", "changed"}:
            label_sources.append("reviewed")
        elif review_status == "bulk_filled":
            label_sources.append("bulk_fill")
        else:
            label_sources.append("user_table_fallback")
        suggested_labels.append(str(card.get("suggested_label") or "Unknown"))
        agreement_levels.append(str(card.get("agreement_level") or "insufficient_evidence"))
        confidences.append(str(card.get("confidence") or "unknown"))

    adata.obs[f"{PREFIX}_final_label"] = pd.Categorical(final_labels)
    adata.obs[f"{PREFIX}_review_status"] = pd.Categorical(review_statuses)
    adata.obs[f"{PREFIX}_label_source"] = pd.Categorical(label_sources)
    adata.obs[f"{PREFIX}_suggested_label"] = pd.Categorical(suggested_labels)
    adata.obs[f"{PREFIX}_agreement_level"] = pd.Categorical(agreement_levels)
    adata.obs[f"{PREFIX}_confidence"] = pd.Categorical(confidences)
    adata.uns[PREFIX] = {
        "schema_version": "izkf_annotation_audit.v1",
        "source": "streamlit_review_app",
        "cluster_key": cluster_key,
    }
    output_h5ad.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(output_h5ad)


def render_umap(umap: pd.DataFrame, cards: list[dict], decisions: pd.DataFrame, facet_by_sample: bool) -> go.Figure:
    labels = []
    decision_lookup = {str(row["cluster_id"]): row for row in decisions.to_dict(orient="records")}
    card_lookup = card_by_cluster(cards)
    for cluster_id in umap["cluster_id"].astype(str):
        row = decision_lookup.get(cluster_id, {})
        card = card_lookup.get(cluster_id, {})
        labels.append(str(row.get("final_label") or (card.get("final") or {}).get("label") or card.get("suggested_label") or "Unknown"))
    plot_df = umap.copy()
    plot_df["final_label"] = labels
    facet_col = "sample" if facet_by_sample and "sample" in plot_df and plot_df["sample"].nunique() > 1 else None
    fig = px.scatter(
        plot_df,
        x="UMAP1",
        y="UMAP2",
        color="final_label",
        facet_col=facet_col,
        facet_col_wrap=3 if facet_col else 0,
        hover_data={"cluster_id": True, "sample": True, "UMAP1": False, "UMAP2": False},
        render_mode="webgl",
    )
    fig.update_traces(marker={"size": 3, "opacity": 0.75})
    fig.update_layout(
        height=620,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        legend={"orientation": "h", "y": 1.02},
    )
    fig.update_xaxes(visible=False, constrain="domain")
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1, constrain="domain")
    return fig


def main() -> None:
    st.set_page_config(page_title="Annotation Audit Review", layout="wide")
    st.title("Annotation Audit Review")

    payload = load_json(str(RESULTS_DIR / "annotation_audit.json"))
    cards = load_json(str(RESULTS_DIR / "annotation_audit_cards.json"))
    draft = load_table(str(TABLES_DIR / "final_annotation_decisions_draft.csv"))
    source_decisions = load_table(str(FINAL_DECISIONS_PATH)) if FINAL_DECISIONS_PATH.exists() else draft
    if "decisions" not in st.session_state:
        st.session_state.decisions = source_decisions.copy()

    input_h5ad = payload.get("input", {}).get("h5ad") or ""
    cluster_key = payload.get("input", {}).get("cluster_key") or ""
    sample_key = payload.get("input", {}).get("sample_key") or ""
    cards_by_cluster = card_by_cluster(cards)
    clusters = sorted(cards_by_cluster, key=cluster_sort_key)
    priority_clusters = [
        cluster for cluster in clusters
        if str(cards_by_cluster[cluster].get("review_priority")) in {"high", "medium"}
    ]

    with st.sidebar:
        st.header("Review")
        only_priority = st.checkbox("Show priority clusters first", value=True)
        options = priority_clusters + [c for c in clusters if c not in set(priority_clusters)] if only_priority else clusters
        cluster_id = st.selectbox("Cluster", options, format_func=lambda c: f"Cluster {c}")
        st.divider()
        if st.button("Save decisions CSV", type="primary"):
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            st.session_state.decisions.to_csv(FINAL_DECISIONS_PATH, index=False)
            st.success(f"Saved {FINAL_DECISIONS_PATH}")
        if st.button("Write final h5ad"):
            try:
                write_final_h5ad(input_h5ad, cluster_key, cards, st.session_state.decisions, FINAL_H5AD_PATH)
                st.success(f"Wrote {FINAL_H5AD_PATH}")
            except Exception as exc:
                st.error(f"Could not write final h5ad: {exc}")

    card = cards_by_cluster[str(cluster_id)]
    defaults = decision_defaults(card, st.session_state.decisions)
    providers = provider_rows(card)
    provider_labels = [label for label in providers["annotation"].astype(str).tolist() if label]
    label_options = [card.get("suggested_label") or ""] + provider_labels + ["Custom"]
    label_options = [x for i, x in enumerate(label_options) if x and x not in label_options[:i]]

    left, right = st.columns([1.25, 1.0], gap="large")
    with left:
        st.subheader(f"Cluster {cluster_id}")
        st.caption(
            f"{card.get('n_cells', '')} cells | {card.get('review_priority', '')} priority | "
            f"{card.get('decision', '')} | {card.get('agreement_level', '')}"
        )
        st.dataframe(providers[["provider", "annotation", "confidence"]], hide_index=True, use_container_width=True)

        st.markdown("#### Final annotation")
        selected_label = st.selectbox("Select from suggested/provider labels", label_options, index=0)
        initial_label = defaults["final_label"] if selected_label == "Custom" else selected_label
        final_label = st.text_input("Final label", value=initial_label)
        review_status = st.selectbox(
            "Review status",
            ["accepted", "changed", "bulk_filled", "uncertain", "not_reviewed"],
            index=["accepted", "changed", "bulk_filled", "uncertain", "not_reviewed"].index(defaults["review_status"])
            if defaults["review_status"] in {"accepted", "changed", "bulk_filled", "uncertain", "not_reviewed"} else 4,
        )
        reviewer_note = st.text_area("Reviewer note", value=defaults["reviewer_note"], height=90)
        if st.button("Save this cluster"):
            st.session_state.decisions = update_decision(
                st.session_state.decisions,
                card,
                {
                    "final_label": final_label,
                    "review_status": review_status,
                    "reviewer_note": reviewer_note,
                },
            )
            st.success(f"Saved cluster {cluster_id} in this session")

    with right:
        st.subheader("Final-label UMAP")
        try:
            embeddings = available_umaps(input_h5ad)
            embedding_key = st.selectbox("Embedding", embeddings, index=0)
            facet_by_sample = st.checkbox("Facet by sample", value=True)
            umap = load_umap(input_h5ad, cluster_key, sample_key, embedding_key)
            st.plotly_chart(render_umap(umap, cards, st.session_state.decisions, facet_by_sample), use_container_width=True)
        except Exception as exc:
            st.info(f"UMAP unavailable: {exc}")


if __name__ == "__main__":
    main()
