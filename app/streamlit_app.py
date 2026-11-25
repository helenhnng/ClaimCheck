"""ClaimCheck demo screen.

    streamlit run app/streamlit_app.py

The biller uploads a CSV of unsubmitted claims. The file is cleaned and checked
on the spot against each payer's rules, using the EVV visits, authorizations
and adjudicated claims already on file. Nothing is pre-computed, and the screen
never edits or submits a claim.
"""
from __future__ import annotations

import io
import time

import pandas as pd
import streamlit as st

from claimcheck import paths
from claimcheck.data import CLAIM_COLUMNS, DataError, load_auths, load_claims, load_evv
from claimcheck.predict import PREDICTION_COLUMNS, check_claims

CODE_MEANINGS = {
    "D01": "No verified EVV visit for the date of service",
    "D02": "Units exceed the authorization's remaining units",
    "D03": "Claim received after the payer's timely filing limit",
    "D04": "Missing or invalid modifier",
    "D05": "Duplicate claim",
    "D06": "Daily unit maximum exceeded",
    "D07": "Prior authorization number missing",
    "D08": "Authorization not valid for this patient, service or date of service",
    "D09": "Billed units exceed the EVV-verified time",
    "D10": "Payer contract-specific denial",
}
PAYER_NAMES = {"PY01": "Northwind Health Plan", "PY02": "Harbor Medicaid Plan", "PY03": "Summit Care Partners"}
ACTION_LABELS = {
    "submit": "Submit",
    "fix_then_submit": "Fix, then submit",
    "hold": "Hold",
    "review": "Needs a person",
}
ACTION_HELP = {
    "submit": "No rule broken. Ready to send.",
    "fix_then_submit": "A rule is broken. The suggested fix is below.",
    "hold": "The visit record is awaiting verification. Wait; do not write it off.",
    "review": "The checker is less sure here. A person should decide.",
}


@st.cache_data(show_spinner=False)
def reference_data() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Data already on file: EVV visits, authorizations and the count of past claims."""
    return load_evv(), load_auths(), len(load_claims("history"))


@st.cache_data(show_spinner=False)
def run_check(file_bytes: bytes) -> tuple[pd.DataFrame, pd.DataFrame, dict, float]:
    """Clean and check an uploaded file. Cached per file content, so filters do not recompute."""
    started = time.perf_counter()
    raw = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    claims, detailed, report = check_claims(raw)
    merged = claims.merge(detailed.drop(columns=["payer_id"]), on="claim_id", validate="one_to_one")
    return merged, detailed, report, time.perf_counter() - started


def upload_panel(n_visits: int, n_auths: int, n_history: int) -> tuple[str, bytes] | None:
    """The landing section: pick a file. Returns ``(name, bytes)``, or ``None`` if none yet.

    Removing the file from the uploader clears the results. (``claims_file`` in the
    session state is only a hook for the automated tests, which cannot click "Browse".)
    """
    uploaded = st.file_uploader("Upload unsubmitted claims (.csv)", type=["csv"])
    current = (uploaded.name, uploaded.getvalue()) if uploaded is not None else st.session_state.get("claims_file")
    if current is None:
        st.info(
            "Upload a CSV of claims that have not been submitted yet. Each claim is checked when you "
            "upload it; nothing is stored or sent to a payer."
        )
        left, right = st.columns(2)
        with left:
            st.markdown("**What the file needs**")
            st.markdown("One row per claim, with these columns:")
            st.code(", ".join(CLAIM_COLUMNS), language=None)
            st.caption(
                "Payer names, dates in either YYYY-MM-DD or MM/DD/YYYY, and stray spaces are tidied "
                "automatically. A value that cannot be read stops the check with a message naming it."
            )
        with right:
            st.markdown("**What each claim is checked against**")
            st.markdown(
                f"- {n_visits:,} EVV visit records on file\n"
                f"- {n_auths:,} payer authorizations on file\n"
                f"- {n_history:,} claims already decided by the payers (for duplicates, units used "
                "on each authorization, and daily totals)\n"
                "- The rules in the three payers' manuals and bulletins"
            )
        return None
    return current


def cleaning_note(report: dict, seconds: float, name: str) -> None:
    tidy = []
    if report["payer_names_mapped"]:
        tidy.append(f"{report['payer_names_mapped']} payer names standardised")
    us_dates = sum(report["us_format_dates"].values())
    if us_dates:
        tidy.append(f"{us_dates} dates converted from MM/DD/YYYY")
    spaces = report["service_codes_normalised"] + report["modifiers_normalised"]
    if spaces:
        tidy.append(f"{spaces} codes or modifiers trimmed")
    if report["exact_duplicate_rows_dropped"]:
        tidy.append(f"{report['exact_duplicate_rows_dropped']} repeated rows removed")
    st.success(
        f"Checked **{report['rows_out']} claims** from `{name}` in {seconds:.1f} seconds."
        + (" Tidied on the way in: " + "; ".join(tidy) + "." if tidy else "")
    )


def downloads(detailed: pd.DataFrame) -> None:
    left, right, _ = st.columns([1, 1, 3])
    left.download_button(
        "Download predictions.csv", detailed[PREDICTION_COLUMNS].to_csv(index=False),
        file_name="predictions.csv", mime="text/csv",
    )
    right.download_button(
        "Download with reasons and fixes", detailed.to_csv(index=False),
        file_name="predictions_detailed.csv", mime="text/csv",
    )


def summary(df: pd.DataFrame) -> None:
    cols = st.columns(5)
    cols[0].metric("Claims checked", len(df))
    cols[1].metric("Submit", int((df["action"] == "submit").sum()))
    cols[2].metric("Fix, then submit", int((df["action"] == "fix_then_submit").sum()))
    cols[3].metric("Hold", int((df["action"] == "hold").sum()))
    cols[4].metric("Needs a person", int((df["action"] == "review").sum()))
    at_risk = df.loc[df["status"] == "denied", "billed_amount"].sum()
    st.caption(
        f"{int((df['status'] == 'denied').sum())} of {len(df)} claims are predicted to be denied "
        f"if sent as they are, worth ${at_risk:,.0f} of ${df['billed_amount'].sum():,.0f} billed."
    )
    denied = df[df["status"] == "denied"]
    if not denied.empty:
        by_code = (
            denied.groupby("denial_code").agg(claims=("claim_id", "count"), billed=("billed_amount", "sum"))
            .reset_index()
        )
        by_code["meaning"] = by_code["denial_code"].map(CODE_MEANINGS)
        left, right = st.columns([2, 3])
        left.bar_chart(by_code.set_index("denial_code")["claims"], height=260)
        right.dataframe(
            by_code[["denial_code", "meaning", "claims", "billed"]].rename(columns={
                "denial_code": "Code", "meaning": "Meaning", "claims": "Claims", "billed": "Billed ($)"}),
            hide_index=True, width="stretch",
            column_config={"Billed ($)": st.column_config.NumberColumn(format="%.0f")},
        )


def filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filter claims")
    payers = st.sidebar.multiselect("Payer", sorted(df["payer_id"].unique()),
                                    format_func=lambda p: f"{p} {PAYER_NAMES[p]}")
    actions = st.sidebar.multiselect("Action", list(ACTION_LABELS), format_func=ACTION_LABELS.get)
    codes = st.sidebar.multiselect("Denial code", sorted(c for c in df["denial_code"].unique() if c),
                                   format_func=lambda c: f"{c} {CODE_MEANINGS[c]}")
    agencies = st.sidebar.multiselect("Agency", sorted(df["agency_id"].unique()))
    out = df
    if payers:
        out = out[out["payer_id"].isin(payers)]
    if actions:
        out = out[out["action"].isin(actions)]
    if codes:
        out = out[out["denial_code"].isin(codes)]
    if agencies:
        out = out[out["agency_id"].isin(agencies)]
    return out


def claim_table(df: pd.DataFrame) -> None:
    view = df.assign(action=df["action"].map(ACTION_LABELS))[[
        "claim_id", "agency_id", "payer_id", "patient_id", "service_code", "date_of_service",
        "units", "billed_amount", "status", "denial_code", "action", "fix",
    ]].rename(columns={
        "claim_id": "Claim", "agency_id": "Agency", "payer_id": "Payer", "patient_id": "Patient",
        "service_code": "Service", "date_of_service": "Date of service", "units": "Units",
        "billed_amount": "Billed ($)", "status": "Prediction", "denial_code": "Code",
        "action": "Action", "fix": "Suggested fix",
    })
    st.dataframe(view, hide_index=True, width="stretch", height=300)


def claim_detail(row: pd.Series, evv: pd.DataFrame, auths: pd.DataFrame) -> None:
    denied = row["status"] == "denied"
    left, right = st.columns([3, 2])
    with left:
        label = ACTION_LABELS[row["action"]]
        if row["action"] == "submit":
            st.success(f"**{label}.** {ACTION_HELP['submit']}")
        elif row["action"] == "fix_then_submit":
            st.error(f"**{label}.** Predicted denial **{row['denial_code']}**: {CODE_MEANINGS[row['denial_code']]}.")
        elif row["action"] == "hold":
            st.warning(f"**{label}.** {ACTION_HELP['hold']}")
        else:
            verdict = (f"Predicted denial **{row['denial_code']}**: {CODE_MEANINGS[row['denial_code']]}."
                       if denied else "Predicted to be paid.")
            st.warning(f"**{label}.** {verdict}")
        if denied:
            st.markdown(f"**Rule broken:** {row['message']}")
            st.markdown(f"**Source:** {row['citation']}")
            st.markdown(f"**Suggested fix:** {row['fix']}")
            others = [c for c in row["all_hits"].split("|") if c and c != row["denial_code"]]
            if others:
                st.markdown(
                    "**Also broken:** " + ", ".join(f"{c} ({CODE_MEANINGS[c]})" for c in others)
                    + ". The payer reports one code only; fix these too before resubmitting."
                )
        if row["needs_review"]:
            st.info(f"**Why a person should look:** {row['review_reason']}")
    with right:
        st.markdown("**Claim**")
        st.dataframe(pd.DataFrame({
            "Field": ["Agency", "Payer", "Patient", "Service", "Modifier", "Date of service",
                      "Submitted", "Units", "Billed ($)", "Authorization", "Claim type"],
            "Value": [row["agency_id"], f"{row['payer_id']} {PAYER_NAMES[row['payer_id']]}", row["patient_id"],
                      row["service_code"], row["modifier"] or "none",
                      f"{row['date_of_service']:%a %d %b %Y}", f"{row['submitted_date']:%a %d %b %Y}",
                      str(row["units"]), f"{row['billed_amount']:.2f}", row["auth_id"] or "none",
                      "Corrected claim for " + str(row["original_claim_id"]) if row["frequency_code"] == 7
                      else "New claim"],
        }), hide_index=True, width="stretch")

    st.markdown("**Evidence behind the decision**")
    evv_col, auth_col = st.columns(2)
    with evv_col:
        st.caption("EVV visits for this patient, service and date (a visit counts on its clock-in date)")
        same_day = evv[(evv["patient_id"] == row["patient_id"]) & (evv["service_code"] == row["service_code"])]
        same_day = same_day[[t.date() == row["date_of_service"] for t in same_day["clock_in"]]]
        if same_day.empty:
            st.write("No visit recorded.")
        else:
            minutes = [int((o - i).total_seconds() // 60) for i, o in zip(same_day["clock_in"], same_day["clock_out"])]
            st.dataframe(pd.DataFrame({
                "Visit": same_day["visit_id"].to_list(),
                "Clock in": [f"{t:%d %b %H:%M}" for t in same_day["clock_in"]],
                "Clock out": [f"{t:%d %b %H:%M}" for t in same_day["clock_out"]],
                "Minutes": minutes,
                "Status": same_day["verification_status"].to_list(),
            }), hide_index=True, width="stretch")
    with auth_col:
        st.caption("Authorization quoted on the claim")
        auth = auths[auths["auth_id"] == row["auth_id"]] if row["auth_id"] else auths.iloc[0:0]
        if auth.empty:
            st.write("No authorization number on the claim." if not row["auth_id"] else "Not on file.")
        else:
            a = auth.iloc[0]
            remaining = row["auth_remaining_before"]
            st.dataframe(pd.DataFrame({
                "Field": ["Authorization", "Patient", "Payer", "Service", "Valid", "Units authorized",
                          "Units left before this claim"],
                "Value": [a["auth_id"], a["patient_id"], a["payer_id"], a["service_code"],
                          f"{a['start_date']:%d %b %Y} to {a['end_date']:%d %b %Y}", str(a["units_authorized"]),
                          "n/a" if remaining == "" or pd.isna(remaining) else str(int(float(remaining)))],
            }), hide_index=True, width="stretch")


def main() -> None:
    st.set_page_config(page_title="ClaimCheck", layout="wide")
    st.title("ClaimCheck")
    st.caption(
        "Checks unsubmitted claims against each payer's rules and predicts paid or denied. "
        "It recommends; the biller decides. Nothing is changed or submitted from this screen."
    )
    evv, auths, n_history = reference_data()

    upload = upload_panel(len(evv), len(auths), n_history)
    if upload is None:
        accuracy_panel()
        return

    try:
        with st.spinner("Checking claims against the payer rules..."):
            df, detailed, report, seconds = run_check(upload[1])
    except (DataError, pd.errors.ParserError, UnicodeDecodeError) as problem:
        st.error(f"This file could not be checked. {problem}")
        st.caption("Nothing was guessed or skipped. Correct the file and upload it again.")
        return

    cleaning_note(report, seconds, upload[0])
    downloads(detailed)
    summary(df)
    st.divider()

    filtered = filters(df)
    st.subheader(f"Claims ({len(filtered)} of {len(df)})")
    if filtered.empty:
        st.write("No claims match the filters.")
        return
    claim_table(filtered)

    st.subheader("Claim detail")
    order = filtered.sort_values(["status", "claim_id"]).set_index("claim_id")  # denied first
    chosen = st.selectbox(
        "Choose a claim", order.index,
        format_func=lambda c: (
            f"{c}  |  {order.loc[c, 'payer_id']}  |  {ACTION_LABELS[order.loc[c, 'action']]}"
            + (f"  |  {order.loc[c, 'denial_code']}" if order.loc[c, 'denial_code'] else "")
        ),
    )
    claim_detail(df.set_index("claim_id", drop=False).loc[chosen], evv, auths)

    st.divider()
    accuracy_panel()


def accuracy_panel() -> None:
    with st.expander("How accurate is it? (held-back test set of past claims, scored once)"):
        metrics_path = paths.OUTPUTS_DIR / "metrics_test.md"
        if metrics_path.is_file():
            st.markdown(metrics_path.read_text(encoding="utf-8").split("## Confusion matrix")[0])
            st.caption("D99 ('contact payer' / 'under review') cannot be predicted and is never predicted.")
        else:
            st.write("Run `python -m claimcheck.evaluate --split test` to produce the test metrics.")


main()
