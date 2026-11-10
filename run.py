"""
Man-Beater Score — run everything.

    python run.py --data <path to the event data folder containing tracking/, plays.csv, ...>

Writes to outputs/: leaderboard.csv, man_beater_routes.csv, summary.md, leaderboard.png,
why_it_matters.png, example_play.png, compare_tool.html
"""
import argparse
import json
import os
import time
import warnings

warnings.filterwarnings("ignore")

from manbeater.data import load_all
from manbeater.features import route_runner_table
from manbeater.score import (coverage_split, leaderboard, man_beater, open_but_ignored,
                             time_to_open, validate)
from manbeater import viz

ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True, help="folder with tracking/, plays.csv, players.csv, games.csv, pffScoutingData.csv")
ap.add_argument("--out", default="outputs")
ap.add_argument("--min-routes", type=int, default=40)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

t0 = time.time()
D = load_all(a.data)
print(f"loaded {len(D['plays']):,} pass plays in {time.time() - t0:.0f}s")
rr = route_runner_table(D)
m = man_beater(rr)
L = leaderboard(m, min_routes=a.min_routes)
v = validate(m)
cov_players, cov_league = coverage_split(m)
tto_routes, tto_players, tto = time_to_open(D, m, min_routes=a.min_routes)
obi_plays, obi_teams, obi = open_but_ignored(m)

L.to_csv(os.path.join(a.out, "leaderboard.csv"), index=False)
m[["gameId", "playId", "nflId", "player", "position", "pff_passCoverage", "sep_snap", "depth_at_throw",
   "time_to_throw", "sep_throw", "exp_sep", "soe", "targeted", "complete", "yards_gained"]] \
    .to_csv(os.path.join(a.out, "man_beater_routes.csv"), index=False)
viz.leaderboard_chart(L, os.path.join(a.out, "leaderboard.png"))
viz.why_it_matters_chart(v, os.path.join(a.out, "why_it_matters.png"))
ex = viz.example_play(D, m, L.iloc[0]["player"], os.path.join(a.out, "example_play.png"))
viz.comparison_tool(L, m, os.path.join(a.out, "compare_tool.html"))
cov_players.to_csv(os.path.join(a.out, "coverage_split.csv"), index=False)
viz.coverage_chart(cov_players, cov_league, L, os.path.join(a.out, "coverage_split.png"))
viz.head_to_head(L, m, os.path.join(a.out, "head_to_head.html"))
tto_players.to_csv(os.path.join(a.out, "time_to_open.csv"), index=False)
obi_teams.to_csv(os.path.join(a.out, "open_but_ignored.csv"), index=False)
viz.time_to_open_chart(tto_players, tto, os.path.join(a.out, "time_to_open.png"))
viz.open_but_ignored_chart(obi_teams, obi, os.path.join(a.out, "open_but_ignored.png"))

cb = v["catch_rate_by_bin"]
cb_disp = cb.copy()
cb_disp.index = [str(k).replace("\n", " ") for k in cb_disp.index]
yb_disp = {str(k).replace("\n", " "): x for k, x in v['yards_by_bin'].items()}
summary = f"""# Results, in plain words

Everything below is about receivers covered one-on-one ("man coverage"). "More open than normal" means
they had more space than a receiver usually gets on that kind of play. 0 means an average amount of space.

- How many plays: we looked at {len(m):,} one-on-one routes run by {m['nflId'].nunique()} receivers; {len(L)} of them were covered this way at least {a.min_routes} times.
- Getting open leads to catches: when a receiver is about average, {v['p_complete_at_soe'][0]:.0%} of throws to him are caught. With one extra yard of space the catch rate climbs to {v['p_complete_at_soe'][1]:.0%}, and with two it reaches {v['p_complete_at_soe'][2]:.0%}. This pattern is very unlikely to be luck (based on {v['logit_n']} throws).
- Catch rate by how open the receiver was: {', '.join(f"{k}: {r['mean']:.0%} ({int(r['size'])} throws)" for k, r in cb_disp.iterrows())}
- Yards gained, by how open the receiver was: {', '.join(f"{k}: {x:.1f}" for k, x in yb_disp.items())}
- Quarterbacks throw to the more open receivers more often: {', '.join(f"{k}: {x:.0%}" for k, x in v['target_rate_by_quartile'].items())}
- Is it a repeatable skill? A receiver's first-four-weeks number and his next-four-weeks number move together, but only loosely (across {v['split_half_players']} players). So it's a real skill, with real week-to-week noise.
- Against different one-on-one looks (the league averages near 0 by design): {', '.join(f"{r.scheme}: caught {r.catch_rate:.0%} of {r.targets} throws across {r.routes} routes" for r in cov_league.itertuples())}
- The best at getting open: {', '.join(f"{r.player} ({r.position}) {r.man_beater_score:+.2f}" for r in L.head(5).itertuples())}
- A clear example: {ex['player']} had {ex['sep_throw']:.1f} yards of space, about {ex['exp_sep']:.1f} is normal (game {ex['gameId']}, play {ex['playId']})

## Getting open: how fast?

- What "getting open" means here: most receivers already stand a couple yards off the nearest defender at the snap because of where they line up, so that isn't beating anyone. We instead count the moment a receiver pulls two yards clear of the closest the defender had gotten to him.
- How many manage it: {tto['open_rate']:.0%} of {tto['n_routes']:,} one-on-one routes break clear before the throw, and it takes about {tto['median_sec_to_open_league']:.1f} seconds on average.
- Getting clear draws the ball: receivers thrown to {tto['target_rate_early']:.0%} of the time when they got clear quickly, {tto['target_rate_late']:.0%} when they got clear later, and {tto['target_rate_never']:.0%} when they never got clear.
- But breaking free earlier is not clearly better than later: when thrown to, catch rate was {tto['catch_rate_early']:.0%} ({tto['n_early_targets']} throws) for the quick ones vs {tto['catch_rate_late']:.0%} ({tto['n_late_targets']} throws) for the later ones. Honestly, the link between how fast a receiver gets open and whether he's thrown to is weak; the real story is that getting open at all draws the ball.

## Did the open man get the ball?

- On {obi['n_plays']:,} one-on-one plays, the receiver who got the most open was NOT the one thrown to {obi['missed_open_rate']:.0%} of the time.
- Passing him up cost something: throws to the most open man were caught {obi['catch_rate_when_open_targeted']:.0%} of the time for {obi['yards_when_open_targeted']:.1f} yards ({obi['n_targeted']} throws); throws to someone else were caught {obi['catch_rate_when_open_ignored']:.0%} of the time for {obi['yards_when_open_ignored']:.1f} yards ({obi['n_ignored']} throws).
- One fair caveat: we judge "most open" at the moment the ball is thrown, but the quarterback decides a little earlier, so some of these are timing and reads rather than clear mistakes.
"""
open(os.path.join(a.out, "summary.md"), "w").write(summary)
print(summary)
print(f"done in {time.time() - t0:.0f}s → {a.out}/")
