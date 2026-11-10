"""Per route-runner features from snap to throw."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import FPS, KEYS

SKILL = {"WR", "TE", "RB", "FB"}


def _nearest_defender(frame_rows: pd.DataFrame, defenders: pd.DataFrame) -> pd.Series:
    m = frame_rows.merge(defenders, on=KEYS + ["frameId"], suffixes=("", "_d"))
    m["d"] = np.hypot(m["x"] - m["x_d"], m["y"] - m["y_d"])
    return m.groupby(KEYS + ["nflId"])["d"].min()


def route_runner_table(D: dict) -> pd.DataFrame:
    t, p, players, pff = D["track"], D["plays"], D["players"], D["pff"]
    pos = players.set_index("nflId")["officialPosition"]
    t = t.merge(p[KEYS + ["f_snap", "f_throw"]], on=KEYS)
    t = t[(t["frameId"] >= t["f_snap"]) & (t["frameId"] <= t["f_throw"])]
    off = t[t["pff_role"].eq("Pass Route") & t["nflId"].map(pos).isin(SKILL)]
    de = t[t["pff_role"].eq("Coverage")][KEYS + ["frameId", "x", "y"]]

    g = off.sort_values("frameId").groupby(KEYS + ["nflId"])
    f = pd.DataFrame({
        "x_snap": g["x"].first(),
        "x_throw": g["x"].last(),
        "max_speed_mph": g["s"].max() * 2.04545,
    })
    snap_rows = off[off["frameId"] == off["f_snap"]][KEYS + ["frameId", "nflId", "x", "y"]]
    throw_rows = off[off["frameId"] == off["f_throw"]][KEYS + ["frameId", "nflId", "x", "y"]]
    f["sep_snap"] = _nearest_defender(snap_rows, de)          # cushion the defender gave at the snap
    f["sep_throw"] = _nearest_defender(throw_rows, de)        # separation when the ball leaves the QB's hand
    f = f.reset_index().dropna(subset=["sep_snap", "sep_throw"])
    f["depth_at_throw"] = f["x_throw"] - f["x_snap"]

    f = f.merge(p[KEYS + ["f_snap", "f_throw", "targetId", "passResult", "prePenaltyPlayResult", "down", "yardsToGo",
                          "pff_passCoverage", "pff_passCoverageType", "week", "possessionTeam"]], on=KEYS)
    f["time_to_throw"] = (f["f_throw"] - f["f_snap"]) / FPS
    f["targeted"] = (f["nflId"] == f["targetId"]).astype(int)
    f["yards_gained"] = f["prePenaltyPlayResult"]
    f["complete"] = np.where(f["passResult"].eq("C"), 1.0, np.where(f["passResult"].isin(["I", "IN"]), 0.0, np.nan))
    f = f.merge(pff[KEYS + ["nflId", "pff_positionLinedUp"]], on=KEYS + ["nflId"], how="left")
    f["alignment"] = f["pff_positionLinedUp"].astype(str).str.replace(r"^[LR]", "", regex=True)
    f["position"] = f["nflId"].map(pos)
    f["player"] = f["nflId"].map(players.set_index("nflId")["displayName"])
    return f
