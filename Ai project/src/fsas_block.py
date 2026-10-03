# ============================================================================
# FSAS - Forecast-aware, Stable Adaptive Segmentation  (proposed method)
# ============================================================================
# Design decisions come from the London (real data) benchmark:
#   * rolling boundaries (Adaptive, Standard-rolling) were 2.5-4.6 % WORSE than
#     Fixed (CI excludes 0) -> boundaries must be FROZEN after fitting on TRAIN.
#   * frozen homogeneity-only boundaries (Adaptive-static, Standard) ~ Fixed
#     -> homogeneity (Jenks/SSE) is not the right criterion for forecasting.
# FSAS therefore (1) selects ONE frozen boundary set per device from ALL valid
# candidates (4 segments, 4-7 h each -> only 31 candidates) using the
# hourly-reconstruction error of a cheap causal forecaster on TRAIN days
# (forecast-aware), and (2) shrinks towards a population / cluster reference
# boundary with strength lambda (stability / noise control).
# lambda is chosen on a tuning block carved from the END OF TRAIN - the test
# period is never touched.

FSAS_LAMBDA_GRID = (0.0, 0.002, 0.005, 0.01, 0.02, 0.05, float("inf"))
FSAS_K = 7            # proxy forecaster: mean of the previous K days, per segment
FSAS_VAL_DAYS = 56    # selection window length (days)
FSAS_TUNE_DAYS = 28   # tuning block length (days) used only to choose lambda


def fsas_candidates(n_seg: int = 4, min_len: int = 4, max_len: int = 7, day_len: int = 24) -> np.ndarray:
    """All boundary triples (b1,b2,b3) whose segment lengths are in [min_len, max_len]."""
    out = []
    for l1 in range(min_len, max_len + 1):
        for l2 in range(min_len, max_len + 1):
            for l3 in range(min_len, max_len + 1):
                l4 = day_len - l1 - l2 - l3
                if min_len <= l4 <= max_len:
                    out.append((l1, l1 + l2, l1 + l2 + l3))
    return np.array(out, dtype=int)


def _fsas_proxy_err(mat: np.ndarray, cand: np.ndarray, start: int, end: int, k: int = FSAS_K) -> np.ndarray:
    """Hourly MAE of a causal proxy forecaster for every candidate boundary set.

    mat: (D,24) hourly kWh of ONE device (TRAIN days only).  Days t in [start,end) are
    scored.  Forecast of segment sums = mean of the previous k days; spread to hours with
    the mean hourly shape of days [0,start) (causal).  Returns (n_cand,).
    """
    prof = mat[:start].mean(axis=0)
    hours = np.arange(24)
    errs = np.empty(len(cand))
    cs_h = np.concatenate([np.zeros((mat.shape[0], 1)), np.cumsum(mat, axis=1)], axis=1)   # (D,25)
    for ci, b in enumerate(cand):
        edges = np.array([0, b[0], b[1], b[2], 24])
        S = np.diff(cs_h[:, edges], axis=1)                                   # (D,4)
        cs = np.concatenate([np.zeros((1, 4)), np.cumsum(S, axis=0)], axis=0)  # (D+1,4)
        t = np.arange(start, end)
        F = (cs[t] - cs[t - k]) / k                                           # (T,4)
        seg_id = (hours >= b[0]).astype(int) + (hours >= b[1]) + (hours >= b[2])
        psum = np.array([prof[seg_id == s].sum() for s in range(4)])
        ln = np.array([(seg_id == s).sum() for s in range(4)], dtype=float)
        share = np.where(psum[seg_id] > 1e-12, prof / np.where(psum[seg_id] > 1e-12, psum[seg_id], 1.0),
                         1.0 / ln[seg_id])
        pred = F[:, seg_id] * share[None, :]
        errs[ci] = np.abs(mat[start:end] - pred).mean()
    return errs


def _fsas_choose(err: np.ndarray, cand: np.ndarray, b_ref: np.ndarray, lam: float) -> int:
    """argmin_c  rel_err[c] + lam * ||cand[c]-b_ref||_1   (lam=inf -> reference boundaries)."""
    dist = np.abs(cand - b_ref[None, :]).sum(axis=1).astype(float)
    if np.isinf(lam):
        return int(np.argmin(dist))
    rel = err / max(err.min(), 1e-12) - 1.0
    return int(np.argmin(rel + lam * dist))


def _fsas_reference(errs: list[np.ndarray], cand: np.ndarray) -> np.ndarray:
    """Population/cluster reference: candidate with the lowest mean normalised error."""
    if not errs:
        return cand[0]
    rel = np.mean([e / max(e.mean(), 1e-12) for e in errs], axis=0)
    return cand[int(np.argmin(rel))]


def fsas_fit(mats: dict[int, np.ndarray], n_train: dict[int, int], fallback_b: np.ndarray,
             groups: dict[int, int] | None = None, lam_grid=FSAS_LAMBDA_GRID,
             tune_days: int = FSAS_TUNE_DAYS, val_days: int = FSAS_VAL_DAYS,
             k: int = FSAS_K) -> tuple[dict[int, np.ndarray], dict]:
    """Return ({device: frozen (3,) boundaries}, info).  Uses TRAIN days only.

    groups: optional {device: cluster id} -> reference boundaries per cluster (FSAS-KM).
    """
    cand = fsas_candidates()
    need = k + tune_days + 14
    ok = [d for d in mats if n_train[d] >= need]
    g = groups or {d: 0 for d in mats}
    errA, errT, errF = {}, {}, {}
    for d in ok:
        m, n = mats[d][:n_train[d]], n_train[d]
        sel_end = n - tune_days
        errA[d] = _fsas_proxy_err(m[:sel_end], cand, max(k, sel_end - val_days), sel_end, k)      # selection (phase A)
        errT[d] = _fsas_proxy_err(m, cand, sel_end, n, k)                                        # tuning block
        errF[d] = _fsas_proxy_err(m, cand, max(k, n - val_days), n, k)                           # final selection
    info = {"n_fitted": len(ok), "n_fallback": len(mats) - len(ok), "lambda": None, "tune_curve": {}}
    if not ok:
        return {d: np.asarray(fallback_b) for d in mats}, info

    def refs(err):
        return {gid: _fsas_reference([err[d] for d in ok if g[d] == gid], cand) for gid in set(g[d] for d in ok)}

    refA = refs(errA)
    curve = {}
    for lam in lam_grid:
        tot = []
        for d in ok:
            c = _fsas_choose(errA[d], cand, refA[g[d]], lam)
            tot.append(errT[d][c] / max(errT[d].mean(), 1e-12))
        curve[lam] = float(np.mean(tot))
    best_val = min(curve.values())
    tied = [L for L in curve if curve[L] <= best_val * 1.0005]      # within 0.05 % of the best
    best_lam = max(tied)                                            # tie -> most stable (largest lambda)
    info["lambda"], info["tune_curve"] = best_lam, curve
    refF = refs(errF)
    out = {}
    for d in mats:
        if d in errF:
            out[d] = cand[_fsas_choose(errF[d], cand, refF[g[d]], best_lam)]
        else:
            out[d] = np.asarray(fallback_b)
    info["share_equal_reference"] = float(np.mean([np.array_equal(out[d], refF[g[d]]) for d in ok]))
    return out, info


def _fsas_groups(mats: dict[int, np.ndarray], n_train: dict[int, int], n_clusters: int, seed: int) -> dict[int, int]:
    """K-Means on each device's TRAIN mean 24 h profile (shape-normalised)."""
    from sklearn.cluster import KMeans
    devs = [d for d in mats if n_train[d] > 0]
    P = np.array([mats[d][:n_train[d]].mean(axis=0) for d in devs])
    P = P / np.maximum(P.sum(axis=1, keepdims=True), 1e-12)
    k = max(1, min(n_clusters, len(devs)))
    lab = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(P) if k > 1 else np.zeros(len(devs), int)
    return {d: int(l) for d, l in zip(devs, lab)} | {d: 0 for d in mats if d not in devs}


