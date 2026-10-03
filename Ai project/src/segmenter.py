import numpy as np
import pandas as pd


class AdaptiveBoundarySegmenter:
    """
    Splits a user's 24-hour consumption profile into 4 adaptive,
    behavior-driven segments, subject to hard duration constraints:

        - exactly 4 segments
        - each segment between MIN_SEGMENT_HOURS and MAX_SEGMENT_HOURS
        - segments are contiguous and cover the full 24-hour day

    Public API (unchanged from the previous version, consumed by
    DatasetBuilder, Predictor, daily_actual_writer, prediction_service):

        build_hour_profile(user_df)   -> pd.Series (index 0..23)
        smooth_profile(profile)       -> pd.Series (index 0..23)
        detect_peak(profile)          -> (peak_hour: int, peak_value: float)
        find_boundaries(profile)      -> [b1, b2, b3]
        create_segments(boundaries)   -> {seg_id: {"start": int, "end": int}}
        extract_segment_features(...) -> {seg_id: {...}}
        fit_user(user_df)             -> dict (same keys as before)

    New public helper:

        validate_segmentation(segments) -> raises ValueError if invalid
    """

    MIN_SEGMENT_HOURS = 4
    MAX_SEGMENT_HOURS = 7
    N_SEGMENTS = 4

    # Exponential recency decay used when combining multiple days into
    # one representative 24h profile. 1.0 = every day weighted equally.
    DAY_RECENCY_DECAY = 0.97

    def __init__(self):
        # Populated by build_hour_profile(); consumed by find_boundaries()
        # to score boundaries using cross-day persistence. These are
        # per-call scratch state (overwritten on every build_hour_profile
        # call) - NOT a cache keyed by user, so they stay correct even
        # though a single segmenter instance is reused across many users.
        self._last_day_matrix = None
        self._last_day_weights = None

    # ==========================================
    # Step 1: representative multi-day profile
    # ==========================================

    def build_hour_profile(self, user_df: pd.DataFrame) -> pd.Series:
        """
        Build a robust, recency-weighted 24-hour consumption profile.

        If `user_df` spans multiple days (a "day" column, or a
        "timestamp" column from which a day can be derived), each day
        contributes a per-hour value and the profile is the
        recency-weighted *median* across days per hour - this keeps one
        abnormal day from moving the profile as much as a plain mean
        would, while still letting genuinely recent behavior dominate.

        If only a single day of data is available (no day/timestamp
        column, or only one distinct day), falls back to the original
        plain per-hour mean, exactly as before.
        """

        if user_df is None or len(user_df) == 0:
            raise ValueError("user_df is empty; cannot build an hourly profile")

        if "hour" not in user_df.columns or "consumption_kwh" not in user_df.columns:
            raise ValueError(
                "user_df must contain 'hour' and 'consumption_kwh' columns"
            )

        df = user_df.copy()

        if "day" in df.columns:
            day_col = "day"
        elif "timestamp" in df.columns:
            df["_derived_day"] = pd.to_datetime(df["timestamp"]).dt.date
            day_col = "_derived_day"
        else:
            day_col = None

        if day_col is None:
            profile = (
                df.groupby("hour")["consumption_kwh"].mean().reindex(range(24))
            )
            profile = profile.fillna(profile.mean())
            self._last_day_matrix = None
            self._last_day_weights = None
            return profile

        pivot = (
            df.groupby([day_col, "hour"])["consumption_kwh"]
            .mean()
            .unstack("hour")
            .reindex(columns=range(24))
        )
        pivot = pivot.loc[sorted(pivot.index.tolist())]

        if len(pivot) <= 1:
            profile = (
                df.groupby("hour")["consumption_kwh"].mean().reindex(range(24))
            )
            profile = profile.fillna(profile.mean())
            if len(pivot) == 1:
                self._last_day_matrix = pivot.values.astype(float)
                self._last_day_weights = np.array([1.0])
            else:
                self._last_day_matrix = None
                self._last_day_weights = None
            return profile

        weights = self._compute_day_weights(len(pivot))

        hour_values = np.full(24, np.nan)
        for h in range(24):
            col = pivot[h].to_numpy(dtype=float)
            mask = ~np.isnan(col)
            if not mask.any():
                continue
            hour_values[h] = self._weighted_median(col[mask], weights[mask])

        profile = pd.Series(hour_values, index=range(24))
        if profile.isna().any():
            fallback = profile.mean()
            if pd.isna(fallback):
                fallback = float(np.nanmean(pivot.to_numpy(dtype=float)))
            profile = profile.fillna(fallback)

        # Stash per-day data for the persistence scoring in find_boundaries().
        self._last_day_matrix = pivot.to_numpy(dtype=float)
        self._last_day_weights = weights

        return profile

    @staticmethod
    def _compute_day_weights(n_days: int, decay: float = None) -> np.ndarray:
        """Weight[i] is largest for the most recent day (last row, since
        pivot index is sorted ascending) and decays geometrically going
        back in time. Normalized to sum to 1."""

        decay = AdaptiveBoundarySegmenter.DAY_RECENCY_DECAY if decay is None else decay
        ranks_from_recent = (n_days - 1) - np.arange(n_days)
        weights = np.power(decay, ranks_from_recent)
        return weights / weights.sum()

    @staticmethod
    def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
        order = np.argsort(values)
        values_sorted = values[order]
        weights_sorted = weights[order]
        cum_weights = np.cumsum(weights_sorted)
        cutoff = weights_sorted.sum() / 2.0
        idx = int(np.searchsorted(cum_weights, cutoff))
        idx = min(idx, len(values_sorted) - 1)
        return float(values_sorted[idx])

    # ==========================================
    # Step 2: light smoothing (noise reduction)
    # ==========================================

    def smooth_profile(self, profile: pd.Series) -> pd.Series:
        """
        Small centered rolling average (window=3). Uses min_periods=1 so
        the first/last hours aren't artificially pulled down by implicit
        zero-padding (the previous np.convolve(..., mode="same")
        implementation did this at the edges). The window stays small on
        purpose - aggressive smoothing would erase real peaks/transitions.
        """

        return profile.rolling(window=3, center=True, min_periods=1).mean()

    # ==========================================
    # Step 3: peak detection (single hour - unchanged)
    # ==========================================

    def detect_peak(self, profile: pd.Series):
        peak_hour = int(profile.idxmax())
        peak_value = float(profile.max())
        return peak_hour, peak_value

    # ==========================================
    # Step 5: constrained boundary search
    # ==========================================

    def find_boundaries(self, profile: pd.Series):
        """
        Search over every 4-segment partition (b1, b2, b3) of the 24h
        day that satisfies the hard 4-7 hour constraint on all four
        segments, score each COMPLETE valid partition - not three
        independently-chosen boundary locations - and return the
        boundaries of the best-scoring one.

        The PRIMARY signal is now a genuine whole-partition regime-fit
        objective: each of the four segments is scored by how well a
        single local trend line explains it (`_segment_linear_fit_rss`),
        and the partition's fitted variance fraction (`plfvf`, see
        `_score_partition`) only rewards a boundary when it actually
        improves how well the *whole day* is explained by four coherent
        regimes - not by however "different" the few hours immediately
        around a candidate cut happen to look in isolation. A smooth,
        constant-slope ramp is fit almost perfectly by a single line, so
        it is already fit almost perfectly by any 4-way split of that
        same line; `plfvf` therefore stays close to its already-near-1
        ceiling for every candidate partition and does not reward
        slicing a ramp at an arbitrary point.

        Real, persistent, noise-normalized transitions at the chosen
        boundary hours (`_score_candidate_boundaries`) are kept as a
        secondary, confirmatory term: among partitions with similar
        regime-fit quality, prefer the one whose cuts coincide with an
        actual, repeatable behavioral change rather than an arbitrary
        tie-break.

        There is deliberately no separate "peak region" heuristic here:
        a broad, persistent high-consumption plateau is allowed to
        remain one coherent segment, but if the start or end of that
        plateau is itself a strong, persistent transition, the search
        is free to place a boundary there - the transition evidence
        decides this per-profile, rather than a hand-tuned region rule.

        Invalid partitions (any segment <4h or >7h) are never generated
        in the first place - the constraint is baked into the loop
        bounds, not applied as a post-hoc filter.
        """

        if profile is None or len(profile) != 24:
            raise ValueError("profile must be a 24-value pd.Series (hours 0-23)")

        smooth = self.smooth_profile(profile)
        values = smooth.to_numpy(dtype=float)

        day_matrix = self._last_day_matrix
        day_weights = self._last_day_weights
        use_persistence = (
            day_matrix is not None
            and day_weights is not None
            and day_matrix.shape[0] > 1
            and day_matrix.shape[1] == 24
        )

        change_evidence = self._score_candidate_boundaries(
            values, day_matrix, day_weights, use_persistence
        )

        # Noise floor is anchored only to hours that could ever actually
        # be chosen as a boundary given the hard 4-7h/4-segment
        # constraint (derived from the constants, not hardcoded) -
        # candidate hours near the very edges of the day (e.g. hour 1 or
        # 23) can never be a real boundary here, have the noisiest local
        # window estimates (heavily truncated), and should not be
        # allowed to distort the percentile threshold used against hours
        # that genuinely can be chosen.
        feasible_hours = sorted(self._feasible_boundary_hours())
        feasible_scores = np.array(
            [change_evidence[b]["score"] for b in feasible_hours if b in change_evidence]
        )
        noise_floor = float(np.percentile(feasible_scores, 25)) if feasible_scores.size else 0.0

        min_h = self.MIN_SEGMENT_HOURS
        max_h = self.MAX_SEGMENT_HOURS

        best_score = -np.inf
        best_boundaries = None

        for b1 in range(min_h, max_h + 1):
            for b2 in range(b1 + min_h, b1 + max_h + 1):
                for b3 in range(b2 + min_h, b2 + max_h + 1):
                    last_len = 24 - b3
                    if last_len < min_h or last_len > max_h:
                        continue

                    boundaries = (b1, b2, b3)
                    total = self._score_partition(
                        boundaries,
                        values,
                        change_evidence,
                        noise_floor,
                    )

                    if total > best_score:
                        best_score = total
                        best_boundaries = [int(b1), int(b2), int(b3)]

        if best_boundaries is None:
            # Mathematically unreachable given 4<=each<=7 and total=24,
            # but fail loudly rather than silently returning nothing.
            raise RuntimeError(
                "No valid 4-7 hour segmentation exists for this profile"
            )

        self._validate_boundaries(best_boundaries)
        return best_boundaries

    def _feasible_boundary_hours(self):
        """
        Every hour that occurs as *some* boundary in at least one valid
        4-segment, 4-7h partition of a 24h day. Derived generically from
        MIN_SEGMENT_HOURS/MAX_SEGMENT_HOURS/N_SEGMENTS (never a
        hardcoded hour), so it stays correct if those constants ever
        change. Used to keep statistics like the noise floor anchored to
        positions that could actually be selected.
        """

        min_h, max_h = self.MIN_SEGMENT_HOURS, self.MAX_SEGMENT_HOURS
        feasible = set()
        for b1 in range(min_h, max_h + 1):
            for b2 in range(b1 + min_h, b1 + max_h + 1):
                for b3 in range(b2 + min_h, b2 + max_h + 1):
                    if min_h <= 24 - b3 <= max_h:
                        feasible.update((b1, b2, b3))
        return feasible

    def _score_candidate_boundaries(
        self, values, day_matrix, day_weights, use_persistence
    ):
        """
        Per-hour-position "real transition" evidence, evaluated using the
        behavior immediately on both sides of each candidate boundary -
        kept as a secondary, confirmatory signal in `_score_partition`
        (the primary signal is the whole-partition regime fit, see
        `find_boundaries`).

        For every candidate boundary b (1..23):
          1. local_level_diff  - difference between the local mean just
             before b and just after b (small window, not single-hour).
          2. local_slope_diff  - difference between the local slope just
             before b and just after b (a real kink/change-point, not
             just "values differ").
          3. change_point_strength - (1)+(2) expressed in units of the
             profile's own background *curvature/jitter* scale (see
             `noise_scale` below), so a transition only scores as
             "strong" when it stands out from ordinary hour-to-hour
             variability.
          4. persistence - a recency- AND magnitude-weighted fraction of
             recent days whose own local shift at this hour agrees in
             direction with the aggregate profile's shift. A day whose
             own local change at this hour is negligible compared to
             its own noise contributes almost no vote either way,
             instead of a full vote based on an essentially arbitrary
             sign.

        Why noise_scale uses SECOND differences, not first differences:
        on a smooth, constant-slope ramp, first differences are
        dominated by the slope itself (diff ~= slope, not noise), so a
        first-difference-based noise scale mistakes trend size for
        noise and silently normalizes every hour's change-point
        strength down to a deceptively "moderate but non-zero" value
        even though there is no real transition anywhere. Second
        differences of a constant-slope ramp are ~0 (a linear trend has
        no curvature), so they isolate actual curvature/jitter instead
        of conflating it with trend magnitude - this is what lets
        `local_level_diff`/`local_slope_diff` correctly normalize to
        ~0 everywhere on a pure ramp, rather than to a spuriously
        uniform, nonzero value.
        """

        window = 3
        n = len(values)

        # Robust, trend-insensitive estimate of ordinary background
        # curvature/jitter in this profile (median absolute *second*
        # difference). See docstring above for why first differences
        # are not appropriate here.
        if n >= 3:
            second_diffs = np.abs(np.diff(values, n=2))
            noise_scale = float(np.median(second_diffs)) if second_diffs.size else 0.0
        else:
            noise_scale = 0.0

        # Floor relative to the profile's own value range, not a fixed
        # tiny absolute constant: perfectly clean/deterministic data
        # (e.g. a noiseless synthetic ramp) has second differences of
        # *exactly* zero, and dividing by an absolute epsilon like 1e-6
        # would blow change_point_strength up to a meaningless,
        # astronomically large magnitude for ordinary kWh-scale values.
        # An absolute 1e-6 is only reached as a last resort, for the
        # degenerate case of an entirely constant (zero-range) profile.
        value_range = float(np.max(values) - np.min(values)) if n else 0.0
        noise_scale = max(noise_scale, 1e-3 * value_range, 1e-6)

        def local_stats(arr, b):
            left = arr[max(0, b - window):b]
            right = arr[b:min(n, b + window)]
            left_mean = float(left.mean())
            right_mean = float(right.mean())
            left_slope = float((left[-1] - left[0]) / (len(left) - 1)) if len(left) >= 2 else 0.0
            right_slope = float((right[-1] - right[0]) / (len(right) - 1)) if len(right) >= 2 else 0.0
            return left_mean, right_mean, left_slope, right_slope

        def row_noise_scale(row):
            row_range = float(np.nanmax(row) - np.nanmin(row)) if len(row) else 0.0
            row_floor = max(1e-3 * row_range, 1e-6)
            if len(row) < 3:
                return max(noise_scale, row_floor)
            rd2 = np.abs(np.diff(row, n=2))
            rd2 = rd2[~np.isnan(rd2)]
            if not rd2.size:
                return max(noise_scale, row_floor)
            return max(float(np.median(rd2)), row_floor)

        evidence = {}

        for b in range(1, n):
            left_mean, right_mean, left_slope, right_slope = local_stats(values, b)

            local_level_diff = abs(right_mean - left_mean)
            local_slope_diff = abs(right_slope - left_slope)

            change_point_strength = (local_level_diff + local_slope_diff) / noise_scale

            agreement = 0.5  # neutral default when persistence can't be computed
            if use_persistence:
                day_diffs = []
                day_strengths = []
                for row in day_matrix:
                    # NaN check is *local to this boundary's window* -
                    # a day missing an unrelated hour elsewhere in the
                    # day should not be discarded wholesale from every
                    # boundary's persistence vote, only from boundaries
                    # whose own window actually touches the missing hour.
                    win_l = row[max(0, b - window):b]
                    win_r = row[b:min(n, b + window)]
                    if np.isnan(win_l).any() or np.isnan(win_r).any():
                        day_diffs.append(np.nan)
                        day_strengths.append(np.nan)
                        continue
                    dl, dr, _, _ = local_stats(row, b)
                    diff = dr - dl
                    day_diffs.append(diff)
                    # This day's own change, in units of *its own*
                    # background noise, capped so one extreme day can't
                    # single-handedly dominate the vote.
                    day_strengths.append(min(abs(diff) / row_noise_scale(row), 3.0))

                day_diffs = np.asarray(day_diffs, dtype=float)
                day_strengths = np.asarray(day_strengths, dtype=float)
                valid = ~np.isnan(day_diffs)

                if valid.any():
                    w_dir = day_weights[valid]
                    d = day_diffs[valid]
                    agg_sign = np.sign(np.average(d, weights=w_dir))

                    # Evidence-weighted vote: a day's influence on
                    # "does this transition persist" is proportional to
                    # both recency (day_weights) and how large that
                    # day's own local change actually was relative to
                    # its own noise (day_strengths) - a day that is
                    # essentially flat at hour b carries ~no vote in
                    # either direction, rather than a full vote decided
                    # by an arbitrary sign of a near-zero number.
                    vote_w = w_dir * day_strengths[valid]
                    if agg_sign == 0 or vote_w.sum() < 1e-9:
                        agreement = 0.5
                    else:
                        signs = np.sign(d)
                        agree_mask = (signs == agg_sign).astype(float)
                        agreement = float(np.sum(agree_mask * vote_w) / vote_w.sum())

            # One-off spikes (agreement -> 0) are halved rather than
            # zeroed out - they still get some weight, just less than a
            # transition repeated across many days (agreement -> 1).
            persistence_multiplier = 0.5 + 0.5 * agreement

            evidence[b] = {
                "local_level_diff": local_level_diff,
                "local_slope_diff": local_slope_diff,
                "change_point_strength": change_point_strength,
                "persistence": agreement,
                "score": change_point_strength * persistence_multiplier,
            }

        return evidence

    @staticmethod
    def _segment_linear_fit_rss(values, start, end):
        """
        Residual sum of squares of the best-fit straight line over
        values[start:end]. A single line is a superset of "flat"
        (slope can fit to ~0), so this scores a segment as coherent
        whether it is a plateau OR a smooth, steady ramp - it only
        penalizes a segment that actually contains a bend or jump that
        one line cannot follow. This is what lets the whole-partition
        objective in `_score_partition` tell a genuine change-point
        apart from an arbitrary cut through a smooth trend: slicing a
        pure ramp anywhere still leaves every resulting piece
        (itself a line) with ~0 residual, so no slicing of a pure trend
        is rewarded over any other.
        """

        seg = values[start:end]
        length = len(seg)
        if length < 2:
            return 0.0

        x = np.arange(length, dtype=float)
        xbar = x.mean()
        ybar = seg.mean()
        sxx = float(np.sum((x - xbar) ** 2))
        if sxx < 1e-12:
            return float(np.sum((seg - ybar) ** 2))

        sxy = float(np.sum((x - xbar) * (seg - ybar)))
        slope = sxy / sxx
        intercept = ybar - slope * xbar
        fitted = intercept + slope * x
        return float(np.sum((seg - fitted) ** 2))

    def _score_partition(
        self,
        boundaries,
        values,
        change_evidence,
        noise_floor,
    ):
        """
        Score one COMPLETE 4-segment partition:

            WHOLE-PARTITION REGIME FIT (primary)
            + REAL, PERSISTENT TRANSITIONS AT THE CHOSEN CUTS (secondary)
            - ARBITRARY / UNEVIDENCED CUTS
            + BETWEEN-SEGMENT SEPARATION (minor tie-break)

        The dominant term is `plfvf`: how much of the day's total
        variance is explained once each of the four segments is allowed
        its own best-fit trend line, versus one line for the whole day.
        Because this depends on all four segments jointly (not on any
        one boundary in isolation), a partition can only score well by
        being a genuinely good *complete* description of the day - a
        boundary set made of three locally-flashy but mutually
        unrelated hours will not, in general, also produce four
        internally coherent segments.

        The per-boundary transition evidence from
        `_score_candidate_boundaries` is kept as a smaller, secondary
        term: it breaks ties between partitions of similar regime-fit
        quality in favor of the one whose cuts land on real, persistent
        behavioral changes rather than an arbitrary equally-good split.
        """

        b1, b2, b3 = boundaries
        borders = (0, b1, b2, b3, 24)

        total_rss = sum(
            self._segment_linear_fit_rss(values, borders[i], borders[i + 1])
            for i in range(4)
        )

        overall_mean = values.mean()
        total_sq_dev = float(np.sum((values - overall_mean) ** 2))

        # Fraction of variance explained by a *piecewise-linear* fit
        # (one trend line per segment) rather than a piecewise-constant
        # one - the primary, whole-partition signal.
        plfvf = 1.0 - (total_rss / total_sq_dev) if total_sq_dev > 1e-9 else 0.0

        seg_slices = [values[borders[i]:borders[i + 1]] for i in range(4)]
        seg_means = np.array([s.mean() for s in seg_slices])

        # Normalized against the profile's own overall variability (not
        # the residual noise), so a partition that happens to fit almost
        # perfectly (e.g. a deterministic ramp) doesn't cause this term
        # to blow up from dividing by a near-zero residual.
        profile_scale = max(float(np.std(values)), 1e-6)
        adjacent_separation = float(
            sum(abs(seg_means[i + 1] - seg_means[i]) for i in range(3)) / profile_scale
        )

        # Secondary signal: real, persistence-weighted, noise-normalized
        # transition strength at exactly the chosen boundary hours.
        change_score = sum(change_evidence[b]["score"] for b in boundaries)

        # Penalize boundaries with little real evidence of a transition
        # (below the profile's own 25th-percentile of change-point
        # strength among feasible boundary hours) - i.e. cuts placed
        # only because they help the regime fit marginally, without any
        # real change-point behind them.
        instability_penalty = sum(
            max(0.0, noise_floor - change_evidence[b]["score"]) for b in boundaries
        )

        return (
            4.0 * plfvf
            + 1.5 * change_score
            - 1.5 * instability_penalty
            + 0.25 * adjacent_separation
        )


    def _validate_boundaries(self, boundaries):
        if len(boundaries) != self.N_SEGMENTS - 1:
            raise ValueError(f"Expected 3 boundaries, got {len(boundaries)}")

        b1, b2, b3 = boundaries
        if not (0 < b1 < b2 < b3 < 24):
            raise ValueError(f"Boundaries must be strictly increasing in (0,24): {boundaries}")

        durations = [b1, b2 - b1, b3 - b2, 24 - b3]
        for d in durations:
            if not (self.MIN_SEGMENT_HOURS <= d <= self.MAX_SEGMENT_HOURS):
                raise ValueError(
                    f"Segment duration {d}h violates the "
                    f"{self.MIN_SEGMENT_HOURS}-{self.MAX_SEGMENT_HOURS}h "
                    f"constraint: boundaries={boundaries}"
                )
        if sum(durations) != 24:
            raise ValueError(f"Segment durations {durations} do not sum to 24")

    # ==========================================
    # Step 6: boundaries -> segment dict (unchanged shape)
    # ==========================================

    def create_segments(self, boundaries):
        self._validate_boundaries(boundaries)

        borders = [0] + list(boundaries) + [24]
        segments = {}

        for i in range(self.N_SEGMENTS):
            start_hour = borders[i]
            end_hour = borders[i + 1] - 1
            segments[i] = {"start": int(start_hour), "end": int(end_hour)}

        self.validate_segmentation(segments)
        return segments

    def validate_segmentation(self, segments: dict) -> None:
        """
        Strict validation of a finished segmentation. Raises ValueError
        (never returns a partial/silent failure) if any condition is
        violated:
            - exactly N_SEGMENTS segments
            - contiguous, no gaps/overlaps
            - covers the full 0-23 range
            - every segment duration in [MIN_SEGMENT_HOURS, MAX_SEGMENT_HOURS]
            - total duration == 24
        """

        if len(segments) != self.N_SEGMENTS:
            raise ValueError(f"Expected {self.N_SEGMENTS} segments, got {len(segments)}")

        ordered = [segments[i] for i in sorted(segments.keys())]

        expected_start = 0
        total_hours = 0
        for seg in ordered:
            start, end = seg["start"], seg["end"]
            if end < start:
                raise ValueError(f"Segment has end before start: {seg}")
            duration = end - start + 1
            if start != expected_start:
                raise ValueError(
                    f"Segments are not contiguous: expected start {expected_start}, got {start}"
                )
            if not (self.MIN_SEGMENT_HOURS <= duration <= self.MAX_SEGMENT_HOURS):
                raise ValueError(
                    f"Segment duration {duration}h out of "
                    f"[{self.MIN_SEGMENT_HOURS},{self.MAX_SEGMENT_HOURS}] range: {seg}"
                )
            total_hours += duration
            expected_start = end + 1

        if expected_start != 24:
            raise ValueError(f"Segments do not cover the full day (ended at hour {expected_start})")
        if total_hours != 24:
            raise ValueError(f"Segment durations sum to {total_hours}, expected 24")

    # ==========================================
    # ویژگی هر Segment (unchanged)
    # ==========================================

    def extract_segment_features(self, profile: pd.Series, segments: dict):
        result = {}

        for seg_id, seg in segments.items():
            start_hour = seg["start"]
            end_hour = seg["end"]
            hours = list(range(start_hour, end_hour + 1))
            values = profile.loc[hours]

            result[seg_id] = {
                "mean": float(values.mean()),
                "max": float(values.max()),
                "min": float(values.min()),
                "std": float(values.std()),
                "total": float(values.sum()),
            }

        return result

    # ==========================================
    # Full pipeline for one user (unchanged interface)
    # ==========================================

    def fit_user(self, user_df: pd.DataFrame):
        profile = self.build_hour_profile(user_df)
        peak_hour, peak_value = self.detect_peak(profile)
        boundaries = self.find_boundaries(profile)
        segments = self.create_segments(boundaries)
        self.validate_segmentation(segments)
        features = self.extract_segment_features(profile, segments)

        return {
            "peak_hour": peak_hour,
            "peak_value": peak_value,
            "boundaries": boundaries,
            "segments": segments,
            "segment_features": features,
            "profile": profile,
        }
