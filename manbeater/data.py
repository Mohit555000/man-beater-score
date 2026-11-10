"""Load the provided event dataset into tidy tables (provided files only, no outside data)."""
from __future__ import annotations

import glob
import os
import re

import numpy as np
import pandas as pd

FPS = 10
FIELD_LEN, FIELD_WID = 120.0, 53.3
KEYS = ["gameId", "playId"]
TRACK_COLS = ["gameId", "playId", "nflId", "frameId", "playDirection", "x", "y", "s", "event"]
SUFFIXES = {"Jr.", "Jr", "Sr.", "II", "III", "IV", "V"}


def load_tracking(data_dir: str, roles: pd.DataFrame) -> pd.DataFrame:
    """Read every game, keep only route runners + coverage defenders, flip plays to go left->right."""
    keep = roles[roles["pff_role"].isin(["Pass Route", "Coverage"])][KEYS + ["nflId", "pff_role"]]
    parts = []
    for f in sorted(glob.glob(os.path.join(data_dir, "tracking", "tracking_*.csv"))):
        t = pd.read_csv(f, usecols=TRACK_COLS)
        parts.append(t.merge(keep, on=KEYS + ["nflId"], how="inner"))
    t = pd.concat(parts, ignore_index=True)
    left = t["playDirection"].eq("left")
    t.loc[left, "x"] = FIELD_LEN - t.loc[left, "x"]
    t.loc[left, "y"] = FIELD_WID - t.loc[left, "y"]
    t["event"] = t["event"].replace("None", np.nan)
    return t


def play_frames(t: pd.DataFrame) -> pd.DataFrame:
    """Snap and throw frame for every play."""
    ev = t.dropna(subset=["event"])
    snap = ev[ev["event"].isin(["ball_snap", "autoevent_ballsnap"])].groupby(KEYS)["frameId"].min()
    throw = ev[ev["event"].isin(["pass_forward", "autoevent_passforward"])].groupby(KEYS)["frameId"].min()
    return pd.DataFrame({"f_snap": snap, "f_throw": throw}).dropna().astype(int).reset_index()


def _name_variants(display_name: str) -> set:
    """'Amon-Ra St. Brown' -> {'A.St. Brown', 'Am.St. Brown', 'A.Brown', ...} as written in play descriptions."""
    t = [w for w in str(display_name).replace("'", "").split() if w not in SUFFIXES]
    if len(t) < 2:
        return set()
    first, rest, last = t[0], " ".join(t[1:]), t[-1]
    return {f"{first[0]}.{rest}", f"{first[0]}.{last}", f"{first[:2]}.{rest}", f"{first[:2]}.{last}"}


def targets_from_description(plays: pd.DataFrame, pff: pd.DataFrame, players: pd.DataFrame) -> pd.Series:
    """Targeted receiver per play, read from playDescription ('... pass short left to C.Godwin ...')
    and matched to that play's route runners."""
    rr = pff[pff["pff_role"].eq("Pass Route")][KEYS + ["nflId"]].merge(
        players[["nflId", "displayName"]], on="nflId")
    rr["variants"] = rr["displayName"].map(_name_variants)
    desc = plays.set_index(KEYS)["playDescription"].astype(str).str.replace("'", "", regex=False)
    pattern = re.compile(r"pass .*?(?: to | for )(.*)")

    def pick(g):
        m = pattern.search(desc.get(g.name, ""))
        if not m:
            return np.nan
        tail = m.group(1)
        hits = [r.nflId for r in g.itertuples() if any(tail.startswith(v) for v in r.variants)]
        return hits[0] if len(hits) == 1 else np.nan

    return rr.groupby(KEYS).apply(pick, include_groups=False).rename("targetId")


def load_all(data_dir: str) -> dict:
    plays = pd.read_csv(os.path.join(data_dir, "plays.csv"))
    players = pd.read_csv(os.path.join(data_dir, "players.csv"))
    games = pd.read_csv(os.path.join(data_dir, "games.csv"))
    pff = pd.read_csv(os.path.join(data_dir, "pffScoutingData.csv"),
                      usecols=KEYS + ["nflId", "pff_role", "pff_positionLinedUp"])
    t = load_tracking(data_dir, pff)
    frames = play_frames(t)
    plays = plays.merge(targets_from_description(plays, pff, players).reset_index(), on=KEYS, how="left")
    plays = plays.merge(frames, on=KEYS, how="inner")          # plays with a snap and a throw
    plays["week"] = plays["gameId"].map(games.set_index("gameId")["week"])
    return {"track": t, "plays": plays, "players": players, "pff": pff, "games": games}
