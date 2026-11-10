"""Man-Beater Score: separation over expected against man coverage, and checks that it matters."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold, cross_val_predict

from .data import FPS, KEYS

CONTEXT = ["depth_at_throw", "time_to_throw", "sep_snap", "down", "yardsToGo"]
CATEGORICAL = ["position", "alignment"]

OPEN_YD = 2.0          # "open" = this many yards of separation created over the tightest point in the route


def expected_separation(df: pd.DataFrame) -> pd.Series:
    """Out-of-fold prediction of separation at the throw from context the receiver doesn't control."""
    X = pd.get_dummies(df[CONTEXT + CATEGORICAL], columns=CATEGORICAL, dtype=float).fillna(0)
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=0)
    # folds grouped by game so a player's own plays in a game never predict each other
    return pd.Series(cross_val_predict(model, X, df["sep_throw"], groups=df["gameId"], cv=GroupKFold(5)),
                     index=df.index)


def man_beater(rr: pd.DataFrame) -> pd.DataFrame:
    m = rr[rr["pff_passCoverageType"].eq("Man")].copy()
    m["exp_sep"] = expected_separation(m)
    m["soe"] = m["sep_throw"] - m["exp_sep"]          # + = more open than expected
    return m


def leaderboard(m: pd.DataFrame, min_routes: int = 40, n_boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for (nid, name, pos), g in m.groupby(["nflId", "player", "position"]):
        if len(g) < min_routes:
            continue
        v = g["soe"].to_numpy()
        boots = rng.choice(v, (n_boot, len(v))).mean(axis=1)
        tg = g[g["targeted"] == 1]
        rows.append({"player": name, "position": pos, "man_routes": len(v),
                     "man_beater_score": v.mean(), "ci_low": np.percentile(boots, 5), "ci_high": np.percentile(boots, 95),
                     "avg_sep_at_throw": g["sep_throw"].mean(), "targets_vs_man": len(tg),
                     "catch_rate_vs_man": tg["complete"].mean()})
    return pd.DataFrame(rows).sort_values("man_beater_score", ascending=False).reset_index(drop=True)


def validate(m: pd.DataFrame) -> dict:
    out = {}
    # depth of the targeted receiver at the throw stands in for pass depth (deeper throws are harder)
    tg = m[(m["targeted"] == 1) & m["complete"].notna()]
    fit = smf.logit("complete ~ soe + depth_at_throw", data=tg).fit(disp=0)
    out["logit_soe_coef"] = fit.params["soe"]
    out["logit_soe_p"] = fit.pvalues["soe"]
    out["logit_n"] = int(fit.nobs)
    # completion probability at average target depth, for -1 / 0 / +1 / +2 yd over expected
    base = tg["depth_at_throw"].mean()
    pred = fit.predict(pd.DataFrame({"soe": [-1.0, 0.0, 1.0, 2.0], "depth_at_throw": base}))
    out["p_complete_at_soe"] = dict(zip([-1, 0, 1, 2], pred.round(3)))
    # repeatable skill? weeks 1-4 vs 5-8
    a = m[m["week"] <= 4].groupby("nflId")["soe"].agg(["mean", "size"])
    b = m[m["week"] > 4].groupby("nflId")["soe"].agg(["mean", "size"])
    j = a.join(b, lsuffix="_1", rsuffix="_2")
    j = j[(j["size_1"] >= 15) & (j["size_2"] >= 15)]
    out["split_half_rho"] = j["mean_1"].corr(j["mean_2"], method="spearman")
    out["split_half_players"] = len(j)
    # do QBs throw to it?
    m = m.assign(q=pd.qcut(m["soe"], 4, labels=["least open", "below average", "above average", "most open"]))
    out["target_rate_by_quartile"] = m.groupby("q", observed=False)["targeted"].mean().round(3).to_dict()
    tg = tg.assign(bin=pd.cut(tg["soe"], [-99, -1, 0, 1, 99],
                              labels=["more covered\nthan usual", "a bit covered", "a bit open", "more open\nthan usual"]))
    out["catch_rate_by_bin"] = tg.groupby("bin", observed=False)["complete"].agg(["mean", "size"]).round(3)
    out["yards_by_bin"] = tg.groupby("bin", observed=False)["yards_gained"].mean().round(2).to_dict()
    return out


SCHEMES = ["Cover-0", "Cover-1", "2-Man"]


def coverage_split(m: pd.DataFrame, min_routes: int = 15) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-player mean soe by man-coverage scheme, plus league-wide mean soe and catch rate by scheme.

    Keeps players with at least `min_routes` routes vs Cover-1 and at least 8 routes in one other scheme.
    Returns (players, league):
      players  one row per qualified player with score_<scheme> and n_<scheme> columns, sorted by Cover-1 score.
      league   one row per scheme with mean soe, route count, catch rate (targeted==1) and target count.
    """
    s = m[m["pff_passCoverage"].isin(SCHEMES)].copy()

    # per-player mean soe and route count in each scheme
    agg = s.groupby(["nflId", "player", "position", "pff_passCoverage"])["soe"].agg(["mean", "size"])
    score = agg["mean"].unstack("pff_passCoverage").reindex(columns=SCHEMES)
    counts = agg["size"].unstack("pff_passCoverage").reindex(columns=SCHEMES).fillna(0).astype(int)
    score.columns = [f"score_{c}" for c in score.columns]
    counts.columns = [f"n_{c}" for c in counts.columns]
    players = score.join(counts).reset_index()

    n1 = players["n_Cover-1"]
    other = players[["n_Cover-0", "n_2-Man"]].max(axis=1)
    players = players[(n1 >= min_routes) & (other >= 8)]
    players = players.sort_values("score_Cover-1", ascending=False).reset_index(drop=True)

    # league-wide mean soe and catch rate (targeted rows only) by scheme
    rows = []
    for scheme in SCHEMES:
        g = s[s["pff_passCoverage"] == scheme]
        tg = g[g["targeted"] == 1]
        rows.append({"scheme": scheme, "mean_soe": g["soe"].mean(), "routes": len(g),
                     "catch_rate": tg["complete"].mean(), "targets": int(tg["complete"].notna().sum())})
    league = pd.DataFrame(rows)
    return players, league


def _frame_separation(D: dict, m: pd.DataFrame) -> pd.DataFrame:
    """Nearest-coverage-defender distance at every frame from snap to throw, for each man-coverage route in m.

    Same nearest-defender logic as features.py (min Euclidean distance to any Coverage player on that frame),
    computed per frame instead of only at snap/throw. Returns one row per (gameId, playId, nflId, frameId).
    """
    t = D["track"]
    routes = m[KEYS + ["nflId", "f_snap", "f_throw"]].drop_duplicates()

    # route-runner positions within the snap->throw window
    rr = t.merge(routes, on=KEYS + ["nflId"])
    rr = rr[(rr["frameId"] >= rr["f_snap"]) & (rr["frameId"] <= rr["f_throw"])]
    rr = rr[[*KEYS, "nflId", "frameId", "f_snap", "x", "y"]]

    # coverage defenders on the same plays/frames
    play_window = routes.groupby(KEYS)[["f_snap", "f_throw"]].first().reset_index()
    de = t[t["pff_role"].eq("Coverage")].merge(play_window, on=KEYS)
    de = de[(de["frameId"] >= de["f_snap"]) & (de["frameId"] <= de["f_throw"])]
    de = de[[*KEYS, "frameId", "x", "y"]]

    mrg = rr.merge(de, on=KEYS + ["frameId"], suffixes=("", "_d"))
    mrg["d"] = np.hypot(mrg["x"] - mrg["x_d"], mrg["y"] - mrg["y_d"])
    sep = mrg.groupby(KEYS + ["nflId", "frameId", "f_snap"])["d"].min().reset_index()
    return sep


def time_to_open(D: dict, m: pd.DataFrame, min_routes: int = 40) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """First moment after the snap a route runner *creates* OPEN_YD of separation, vs man coverage.

    "Open" is defined relative to the tightest the nearest coverage defender got on the route so far, not an
    absolute distance: 91% of receivers already sit 2+ yd from the nearest coverage man at the snap (that is
    pre-snap spacing, not beating a man), so we instead ask when a receiver pulls OPEN_YD clear of the closest
    point the defender had reached since the snap. That isolates the act of getting open during the route.

    Returns (per_route, per_player, summary):
      per_route   one row per man-coverage route with t_open (seconds; NaN if he never created the cushion
                  before the throw) and got_open (bool), joined to targeted/complete/yards_gained/soe from m.
      per_player  median t_open among routes where he got open, and never_open_rate, for players with >= min_routes.
      summary     league medians and the target/catch relationship between getting open earlier and outcomes.
    """
    sep = _frame_separation(D, m).sort_values(KEYS + ["nflId", "frameId"])
    sep["t"] = (sep["frameId"] - sep["f_snap"]) / FPS
    # running tightest separation since the snap, then separation gained over that closest point
    grp = sep.groupby(KEYS + ["nflId"], sort=False)
    sep["min_so_far"] = grp["d"].cummin()
    sep["gained"] = sep["d"] - sep["min_so_far"]
    opened = sep[sep["gained"] >= OPEN_YD].groupby(KEYS + ["nflId"])["t"].min()

    base = m[KEYS + ["nflId", "player", "position", "targeted", "complete", "yards_gained", "soe"]].copy()
    per_route = base.merge(opened.rename("t_open"), on=KEYS + ["nflId"], how="left")
    per_route["got_open"] = per_route["t_open"].notna()

    g = per_route.groupby(["nflId", "player", "position"])
    per_player = pd.DataFrame({
        "man_routes": g.size(),
        "median_sec_to_open": g["t_open"].median(),
        "never_open_rate": g["got_open"].apply(lambda s: 1.0 - s.mean()),
    }).reset_index()
    per_player = per_player[per_player["man_routes"] >= min_routes]
    per_player = per_player.sort_values("median_sec_to_open").reset_index(drop=True)

    # does getting open earlier relate to being targeted and caught?
    summary = {}
    summary["open_rate"] = float(per_route["got_open"].mean())
    summary["median_sec_to_open_league"] = float(per_route["t_open"].median())
    summary["target_rate_open"] = float(per_route[per_route["got_open"]]["targeted"].mean())
    summary["target_rate_never"] = float(per_route[~per_route["got_open"]]["targeted"].mean())

    # early vs late among routes that did get open (split at the median time)
    opn = per_route[per_route["got_open"]].copy()
    med = opn["t_open"].median()
    early, late = opn[opn["t_open"] <= med], opn[opn["t_open"] > med]
    summary["median_split_sec"] = float(med)
    summary["target_rate_early"] = float(early["targeted"].mean())
    summary["target_rate_late"] = float(late["targeted"].mean())
    tg_e = early[early["targeted"] == 1]["complete"]
    tg_l = late[late["targeted"] == 1]["complete"]
    summary["catch_rate_early"] = float(tg_e.mean()) if tg_e.notna().any() else float("nan")
    summary["catch_rate_late"] = float(tg_l.mean()) if tg_l.notna().any() else float("nan")
    summary["n_early_targets"] = int(tg_e.notna().sum())
    summary["n_late_targets"] = int(tg_l.notna().sum())
    # honest correlation check: per-route time-to-open vs whether targeted
    o = per_route.dropna(subset=["t_open"])
    summary["corr_topen_targeted"] = float(o["t_open"].corr(o["targeted"]))
    summary["n_routes"] = int(len(per_route))
    summary["n_open_routes"] = int(per_route["got_open"].sum())
    return per_route, per_player, summary


def open_but_ignored(m: pd.DataFrame, min_plays: int = 60) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """On each man play, the route runner with the highest Man-Beater Score — was he the target?

    Returns (per_play, per_team, summary):
      per_play   one row per man-coverage pass play: the most-open route runner, his soe, whether he was
                 targeted, and the actual play outcome (target's catch/yards).
      per_team   missed-open-receiver rate per possessionTeam (share of plays where the most-open man was
                 not the target), for teams with >= min_plays man plays.
      summary    outcome split: catch rate and yards when the most-open man was targeted vs when he wasn't.
    """
    # need a known target on the play to say whether the open man was ignored
    plays = m[m["targeted"].notna() if "targeted" in m else slice(None)].copy()
    # most-open route runner per play
    idx = m.groupby(KEYS)["soe"].idxmax()
    top = m.loc[idx, KEYS + ["nflId", "player", "position", "soe", "targeted", "possessionTeam"]].copy()
    top = top.rename(columns={"nflId": "open_nflId", "player": "open_player", "soe": "open_soe",
                              "targeted": "open_targeted"})

    # did this play have any identified target among its route runners?
    has_target = m.groupby(KEYS)["targeted"].max().rename("play_has_target")
    # the actual target's outcome on the play (if any)
    tg = m[m["targeted"] == 1].groupby(KEYS)[["complete", "yards_gained"]].first()
    per_play = top.merge(has_target, on=KEYS).merge(tg, on=KEYS, how="left")
    # only plays where we actually know who was targeted can be judged
    per_play = per_play[per_play["play_has_target"] == 1].copy()
    per_play["open_was_target"] = per_play["open_targeted"].astype(int)
    per_play["missed_open"] = 1 - per_play["open_was_target"]

    per_team = per_play.groupby("possessionTeam").agg(
        man_plays=("missed_open", "size"),
        missed_open_rate=("missed_open", "mean"),
        avg_open_soe=("open_soe", "mean"),
    ).reset_index()
    per_team = per_team[per_team["man_plays"] >= min_plays]
    per_team = per_team.sort_values("missed_open_rate", ascending=False).reset_index(drop=True)

    tgt = per_play[per_play["open_was_target"] == 1]
    ign = per_play[per_play["open_was_target"] == 0]
    summary = {
        "n_plays": int(len(per_play)),
        "missed_open_rate": float(per_play["missed_open"].mean()),
        "catch_rate_when_open_targeted": float(tgt["complete"].mean()) if tgt["complete"].notna().any() else float("nan"),
        "catch_rate_when_open_ignored": float(ign["complete"].mean()) if ign["complete"].notna().any() else float("nan"),
        "yards_when_open_targeted": float(tgt["yards_gained"].mean()),
        "yards_when_open_ignored": float(ign["yards_gained"].mean()),
        "n_targeted": int(tgt["complete"].notna().sum()),
        "n_ignored": int(ign["complete"].notna().sum()),
        "avg_open_soe": float(per_play["open_soe"].mean()),
    }
    return per_play, per_team, summary
