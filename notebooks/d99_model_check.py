"""Dev-only experiment: can a learned model find the denials the rules miss (D99)?

Run: .venv/bin/python notebooks/d99_model_check.py
Takes dev claims where no rule fires, and asks two standard models to tell the
ones the payer denied anyway from the ones it paid, with 5-fold cross-validation.
An AUC near 0.5 means "no better than chance".
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from claimcheck.data import load_auths, load_claims, load_evv
from claimcheck.predict import load_timeline, predict_claims
from claimcheck.split import attach_split

history = attach_split(load_claims("history"))
dev = history[history["split"] == "dev"]
timeline, known = load_timeline()
predicted = predict_claims(timeline, load_evv(), load_auths(), known_status=known)
clean = dev.merge(predicted[["claim_id", "all_hits"]], on="claim_id")
clean = clean[clean["all_hits"] == ""].reset_index(drop=True)
y = (clean["status"] == "denied").astype(int).to_numpy()
print(f"dev claims with no rule broken: {len(clean)} | denied anyway: {y.sum()} "
      f"{clean['denial_code'].value_counts().to_dict()}")

numeric = pd.DataFrame({
    "units": clean["units"], "billed": clean["billed_amount"], "units_mod4": clean["units"] % 4,
    "lag_days": [(s - d).days for s, d in zip(clean["submitted_date"], clean["date_of_service"])],
    "dos_month": [d.month for d in clean["date_of_service"]],
    "dos_weekday": [d.weekday() for d in clean["date_of_service"]],
    "sub_month": [d.month for d in clean["submitted_date"]],
    "sub_weekday": [d.weekday() for d in clean["submitted_date"]],
})
X = pd.concat([
    numeric,
    pd.get_dummies(clean[["payer_id", "agency_id", "service_code"]]),
    pd.get_dummies(clean["modifier"].fillna("none"), prefix="mod"),
], axis=1).astype(float)

folds = StratifiedKFold(5, shuffle=True, random_state=42)
models = {
    "gradient boosting": GradientBoostingClassifier(random_state=42),
    "logistic regression": LogisticRegression(max_iter=5000, class_weight="balanced"),
}
for name, model in models.items():
    prob = cross_val_predict(model, X, y, cv=folds, method="predict_proba")[:, 1]
    top50 = np.argsort(-prob)[:50]
    print(f"{name}: AUC {roc_auc_score(y, prob):.3f} | average precision "
          f"{average_precision_score(y, prob):.3f} (base rate {y.mean():.3f}) | "
          f"denied among the 50 highest-risk claims: {y[top50].sum()} (chance: {50 * y.mean():.1f})")
