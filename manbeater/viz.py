"""Charts, an example play, and an interactive comparison tool."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .data import KEYS

POS_COLOR = {"WR": "#2a78d6", "TE": "#eb6834", "RB": "#1baf7a", "FB": "#1baf7a"}
INK, INK2, GRID, AXIS, BG = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "axes.edgecolor": AXIS,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 22,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "font.size": 10.5, "legend.frameon": False,
})


def _sub(ax, text):
    ax.text(0, 1.015, text, transform=ax.transAxes, fontsize=9.5, color=INK2, va="bottom")


def leaderboard_chart(L: pd.DataFrame, path: str, top: int = 15):
    d = L.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    cols = d["position"].map(POS_COLOR)
    ax.barh(d["player"], d["man_beater_score"], color=cols, height=0.62)
    ax.errorbar(d["man_beater_score"], d["player"], xerr=[d["man_beater_score"] - d["ci_low"], d["ci_high"] - d["man_beater_score"]],
                fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
    for y, (_, r) in enumerate(d.iterrows()):
        ax.text(max(r["ci_high"], r["man_beater_score"]) + 0.03, y, f"{r['man_beater_score']:+.2f}  ({r['man_routes']} routes)",
                va="center", fontsize=8.5, color=INK2)
    ax.axvline(0, color=AXIS, lw=1)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(min(-0.1, d["ci_low"].min() - 0.05), d["ci_high"].max() + 0.55)
    ax.set_xlabel("yards more open than normal when the ball is thrown (0 = average)")
    ax.set_title("These receivers get the most open against man coverage")
    _sub(ax, "2021, first 8 weeks · receivers covered one-on-one at least 40 times · lines show the likely range")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=POS_COLOR[p], label=p) for p in ["WR", "TE", "RB"]],
              loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def why_it_matters_chart(v: dict, path: str):
    cb = v["catch_rate_by_bin"].reset_index()
    tq = pd.Series(v["target_rate_by_quartile"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6))
    a1.bar(cb["bin"].astype(str), cb["mean"] * 100, color="#2a78d6", width=0.6)
    for i, r in cb.iterrows():
        a1.annotate(f"{r['mean']:.0%}\n(n={int(r['size'])})", (i, r["mean"] * 100), xytext=(0, 4),
                    textcoords="offset points", ha="center", va="bottom", fontsize=9, color=INK2)
    a1.set_ylim(0, 100)
    a1.set_ylabel("share of throws that were caught (%)")
    a1.set_xlabel("how much more open than normal the receiver was")
    a1.set_title("Receivers who get more open catch more passes")
    _sub(a1, f"throws against man coverage · the pattern holds after accounting for how deep the pass was · {v['logit_n']} throws")
    a2.bar(tq.index.astype(str), tq.values * 100, color="#2a78d6", width=0.6)
    for i, val in enumerate(tq.values):
        a2.annotate(f"{val:.0%}", (i, val * 100), xytext=(0, 4), textcoords="offset points", ha="center",
                    va="bottom", fontsize=9, color=INK2)
    a2.set_ylim(0, max(tq.values) * 100 * 1.3)
    a2.set_ylabel("share of routes the ball was thrown to (%)")
    a2.set_xlabel("receivers grouped from least open to most open")
    a2.set_title("Quarterbacks throw to the more open receivers more often")
    _sub(a2, "how often the receiver was thrown the ball")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def example_play(D: dict, m: pd.DataFrame, player: str, path: str):
    """Draw the play where `player` beat man coverage by the most and caught the ball."""
    cand = m[(m["player"] == player) & (m["targeted"] == 1) & (m["complete"] == 1)]
    if cand.empty:
        cand = m[m["player"] == player]
    r = cand.sort_values("soe", ascending=False).iloc[0]
    t = D["track"]
    pl = t[(t["gameId"] == r["gameId"]) & (t["playId"] == r["playId"])]
    pl = pl[(pl["frameId"] >= r["f_snap"]) & (pl["frameId"] <= r["f_throw"])]
    rec = pl[pl["nflId"] == r["nflId"]].sort_values("frameId")
    end = rec.iloc[-1]
    de = pl[(pl["pff_role"] == "Coverage") & (pl["frameId"] == end["frameId"])].copy()
    de["d"] = np.hypot(de["x"] - end["x"], de["y"] - end["y"])
    did = de.sort_values("d").iloc[0]["nflId"]
    dpath = pl[pl["nflId"] == did].sort_values("frameId")
    los = rec["x"].iloc[0]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.set_facecolor("#eef3ea")
    for yl in range(10, 111, 5):
        ax.axvline(yl, color="#d5dccd", lw=0.8 if yl % 10 else 1.3, zorder=0)
    ax.axvline(los, color=INK2, lw=1, ls="--", zorder=1)
    ax.plot(rec["x"], rec["y"], color=POS_COLOR.get(r["position"], "#2a78d6"), lw=2.4, label=f"{player} (where he ran)")
    ax.plot(dpath["x"], dpath["y"], color="#52514e", lw=1.8, ls=(0, (4, 3)), label="closest defender")
    ax.scatter([rec["x"].iloc[-1]], [rec["y"].iloc[-1]], s=70, color=POS_COLOR.get(r["position"], "#2a78d6"), zorder=4)
    ax.scatter([dpath["x"].iloc[-1]], [dpath["y"].iloc[-1]], s=60, color="#52514e", zorder=4)
    ax.plot([rec["x"].iloc[-1], dpath["x"].iloc[-1]], [rec["y"].iloc[-1], dpath["y"].iloc[-1]], color="#c0392b", lw=1.2)
    mx, my = (rec["x"].iloc[-1] + dpath["x"].iloc[-1]) / 2, (rec["y"].iloc[-1] + dpath["y"].iloc[-1]) / 2
    ax.annotate(f"{r['sep_throw']:.1f} yards of space at the throw\n(usually about {r['exp_sep']:.1f})", (mx, my), xytext=(0, -34),
                textcoords="offset points", ha="center", fontsize=9.5, color=INK)
    xs = pd.concat([rec["x"], dpath["x"]]); ys = pd.concat([rec["y"], dpath["y"]])
    ax.set_xlim(xs.min() - 4, xs.max() + 8); ax.set_ylim(max(0, ys.min() - 5), min(53.3, ys.max() + 5))
    ax.set_aspect("equal"); ax.grid(False)
    ax.set_xlabel("yards down the field (play moving →)"); ax.set_ylabel("yards across the field")
    ax.set_title(f"{player} getting open: from the snap to the throw")
    _sub(ax, f"he had {r['sep_throw']:.1f} yards of space, about {r['soe']:+.1f} more than normal · "
             f"the ball came out {r['time_to_throw']:.1f} seconds after the snap · he caught it")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return r


def comparison_tool(L: pd.DataFrame, m: pd.DataFrame, path: str):
    """Interactive HTML: every qualified player, filter by position, hover for details, plus a full table."""
    fig = make_subplots(rows=2, cols=1, row_heights=[0.62, 0.38], vertical_spacing=0.08,
                        specs=[[{"type": "scatter"}], [{"type": "table"}]])
    for pos in ["WR", "TE", "RB"]:
        d = L[L["position"] == pos]
        fig.add_trace(go.Scatter(
            x=d["avg_sep_at_throw"], y=d["man_beater_score"], mode="markers", name=pos,
            marker=dict(size=np.clip(d["man_routes"] / 4, 8, 26), color=POS_COLOR[pos], line=dict(width=1.5, color="white")),
            customdata=np.stack([d["player"], d["man_routes"], d["ci_low"], d["ci_high"], d["targets_vs_man"],
                                 d["catch_rate_vs_man"]], axis=-1),
            hovertemplate="<b>%{customdata[0]}</b><br>Yards more open than normal: %{y:+.2f} "
                          "(likely range %{customdata[2]:+.2f} to %{customdata[3]:+.2f})<br>"
                          "Average space when the ball is thrown: %{x:.2f} yd<br>"
                          "Times covered one-on-one: %{customdata[1]}<br>"
                          "Times thrown to: %{customdata[4]} · caught %{customdata[5]:.0%}<extra>" + pos + "</extra>"),
            row=1, col=1)
    fig.add_hline(y=0, line_color="#c3c2b7", row=1, col=1)
    t = L.copy()
    fig.add_trace(go.Table(
        header=dict(values=["Rank", "Player", "Position", "Times covered one-on-one", "Yards more open than normal",
                            "Likely range", "Average space at throw", "Times thrown to", "Catch rate"],
                    fill_color="#eef4fc", align="left"),
        cells=dict(values=[t.index + 1, t["player"], t["position"], t["man_routes"], t["man_beater_score"].round(2),
                           [f"{a:+.2f} to {b:+.2f}" for a, b in zip(t["ci_low"], t["ci_high"])],
                           t["avg_sep_at_throw"].round(2), t["targets_vs_man"],
                           (t["catch_rate_vs_man"] * 100).round(0).astype("Int64").astype(str) + "%"],
                   align="left", height=24)), row=2, col=1)
    fig.update_xaxes(title_text="average yards of space when the ball is thrown (raw distance)", row=1, col=1)
    fig.update_yaxes(title_text="yards more open than normal (0 = average)", row=1, col=1)
    fig.update_layout(
        title=dict(text="<b>Who gets open against man coverage</b><br><sup>How open each receiver gets compared with "
                        "normal · 2021, first 8 weeks · click a position in the legend to show or hide it · "
                        "hover over a dot for details</sup>"),
        height=1100, template="plotly_white", legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
        font=dict(family="Inter, Arial, sans-serif"))
    fig.write_html(path, include_plotlyjs=True)


SCHEME_MARKER = {"Cover-0": "o", "Cover-1": "s", "2-Man": "^"}
SCHEME_LABEL = {"Cover-0": "all-out blitz, no deep help", "Cover-1": "one deep safety",
                "2-Man": "two deep safeties, tight coverage"}


def coverage_chart(players: pd.DataFrame, league: pd.DataFrame, overall: pd.DataFrame, path: str, top: int = 15):
    """Dot plot: top 15 players (by overall Man-Beater Score) with their score vs each man scheme on one row each."""
    order = overall.set_index("player")["man_beater_score"]
    d = players.copy()
    d["overall"] = d["player"].map(order)
    d = d.dropna(subset=["overall"]).sort_values("overall", ascending=False).head(top).iloc[::-1].reset_index(drop=True)

    schemes = ["Cover-0", "Cover-1", "2-Man"]
    scheme_color = {"Cover-0": "#c0392b", "Cover-1": "#2a78d6", "2-Man": "#eb6834"}
    fig, ax = plt.subplots(figsize=(9.5, 7))
    ax.axvline(0, color=INK2, lw=1, zorder=1)
    for y, (_, r) in enumerate(d.iterrows()):
        vals = [r[f"score_{s}"] for s in schemes]
        xs = [v for v in vals if pd.notna(v)]
        if xs:
            ax.plot([min(xs), max(xs)], [y, y], color=GRID, lw=1.4, zorder=1)
        for s in schemes:
            v = r[f"score_{s}"]
            if pd.notna(v):
                ax.scatter(v, y, marker=SCHEME_MARKER[s], s=70, color=scheme_color[s],
                           edgecolor="white", linewidth=0.8, zorder=3)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d["player"])
    ax.set_xlabel("yards more open than normal (0 = average), for each type of coverage")
    ax.set_title("The same receiver beats different coverages by different amounts")
    c1 = league.set_index("scheme")["mean_soe"]
    _sub(ax, "2021, first 8 weeks · top 15 receivers · one row per receiver, one marker per type of coverage")
    from matplotlib.lines import Line2D
    handles = [Line2D([0], [0], marker=SCHEME_MARKER[s], color="white", markerfacecolor=scheme_color[s],
                      markeredgecolor="white", markersize=9, label=SCHEME_LABEL[s]) for s in schemes]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.0, 1.0), title="type of coverage")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def head_to_head(L: pd.DataFrame, m: pd.DataFrame, path: str,
                 default_a: str = "Mark Andrews", default_b: str = "Darren Waller"):
    """Self-contained HTML: pick two players, compare their cards and overlay their per-route soe histograms."""
    import plotly.offline

    order = L.sort_values("man_beater_score", ascending=False)
    players = {}
    soe_by_player = m.groupby("player")["soe"].apply(lambda s: [round(float(v), 4) for v in s]).to_dict()
    for r in order.itertuples():
        players[r.player] = {
            "player": r.player,
            "position": r.position,
            "man_routes": int(r.man_routes),
            "score": round(float(r.man_beater_score), 2),
            "ci_low": round(float(r.ci_low), 2),
            "ci_high": round(float(r.ci_high), 2),
            "avg_sep": round(float(r.avg_sep_at_throw), 2),
            "targets": int(r.targets_vs_man),
            "catch_rate": None if pd.isna(r.catch_rate_vs_man) else round(float(r.catch_rate_vs_man), 3),
            "soe": soe_by_player.get(r.player, []),
        }
    names = list(players.keys())
    if default_a not in players:
        default_a = names[0]
    if default_b not in players:
        default_b = names[1] if len(names) > 1 else names[0]

    pos_color = {"WR": "#2a78d6", "TE": "#eb6834", "RB": "#1baf7a", "FB": "#1baf7a"}
    payload = {"players": players, "order": names, "defaultA": default_a, "defaultB": default_b,
               "colorA": "#2a78d6", "colorB": "#eb6834", "posColor": pos_color}
    plotly_js = plotly.offline.get_plotlyjs()
    data_json = json.dumps(payload)

    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Who gets open — compare two receivers</title>
<script type="text/javascript">__PLOTLY_JS__</script>
<style>
  :root { --ink:#0b0b0b; --ink2:#52514e; --grid:#e1e0d9; --bg:#fcfcfb; --a:#2a78d6; --b:#eb6834; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
  .wrap { max-width:1060px; margin:0 auto; padding:24px 20px 40px; }
  h1 { font-size:22px; margin:0 0 2px; }
  .sub { color:var(--ink2); font-size:13px; margin:0 0 20px; }
  .pickers { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px; }
  .picker { display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--ink2); }
  .picker.b label { color:var(--b); }
  .picker.a label { color:var(--a); }
  select { font-size:14px; padding:7px 10px; border:1px solid var(--grid); border-radius:8px;
    background:#fff; color:var(--ink); min-width:220px; }
  .cards { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:22px; }
  @media (max-width:720px){ .cards { grid-template-columns:1fr; } }
  .card { border:1px solid var(--grid); border-radius:12px; padding:16px 18px; background:#fff; }
  .card.a { border-top:4px solid var(--a); }
  .card.b { border-top:4px solid var(--b); }
  .card .name { font-size:18px; font-weight:700; }
  .card .pos { display:inline-block; font-size:11px; font-weight:700; color:#fff;
    padding:2px 8px; border-radius:999px; margin-left:8px; vertical-align:middle; }
  .score { font-size:30px; font-weight:800; margin:10px 0 2px; }
  .score small { font-size:13px; font-weight:600; color:var(--ink2); }
  .ci { font-size:12px; color:var(--ink2); margin-bottom:12px; }
  .stats { display:grid; grid-template-columns:1fr 1fr; gap:10px 16px; }
  .stat .k { font-size:11px; color:var(--ink2); text-transform:uppercase; letter-spacing:.03em; }
  .stat .v { font-size:17px; font-weight:700; }
  #hist { border:1px solid var(--grid); border-radius:12px; background:#fff; padding:6px; }
  .note { color:var(--ink2); font-size:12px; margin-top:10px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Who gets open: compare two receivers</h1>
  <p class="sub">How open each receiver gets against man coverage, compared with normal · 2021, first 8 weeks · pick any two players</p>
  <div class="pickers">
    <div class="picker a"><label for="selA">Player A</label><select id="selA"></select></div>
    <div class="picker b"><label for="selB">Player B</label><select id="selB"></select></div>
  </div>
  <div class="cards">
    <div class="card a" id="cardA"></div>
    <div class="card b" id="cardB"></div>
  </div>
  <div id="hist"></div>
  <p class="note">The chart shows, route by route, how much more or less open each receiver was than normal. Bars to the right of 0 mean more open than usual. The dashed lines mark each receiver's average.</p>
</div>
<script type="text/javascript">
const DATA = __DATA_JSON__;
const P = DATA.players, A = DATA.colorA, B = DATA.colorB;

function fmtSigned(x){ return (x>=0?"+":"") + x.toFixed(2); }
function fmtPct(x){ return x==null ? "—" : Math.round(x*100) + "%"; }

function fill(sel){
  for(const name of DATA.order){
    const o = document.createElement("option");
    o.value = name; o.textContent = name + "  (" + fmtSigned(P[name].score) + ")";
    sel.appendChild(o);
  }
}

function card(elId, name, color){
  const p = P[name];
  const pc = DATA.posColor[p.position] || "#52514e";
  document.getElementById(elId).innerHTML =
    '<div><span class="name">' + p.player + '</span>' +
    '<span class="pos" style="background:' + pc + '">' + p.position + '</span></div>' +
    '<div class="score" style="color:' + color + '">' + fmtSigned(p.score) +
      ' <small>yards more open than normal</small></div>' +
    '<div class="ci">likely range ' + fmtSigned(p.ci_low) + ' to ' + fmtSigned(p.ci_high) + '</div>' +
    '<div class="stats">' +
      stat("Times covered one-on-one", p.man_routes) +
      stat("Average space at throw", p.avg_sep.toFixed(2) + " yd") +
      stat("Times thrown to", p.targets) +
      stat("Catch rate", fmtPct(p.catch_rate)) +
    '</div>';
}
function stat(k, v){ return '<div class="stat"><div class="k">' + k + '</div><div class="v">' + v + '</div></div>'; }

function mean(a){ return a.length ? a.reduce((s,x)=>s+x,0)/a.length : 0; }

function draw(){
  const na = document.getElementById("selA").value;
  const nb = document.getElementById("selB").value;
  card("cardA", na, A);
  card("cardB", nb, B);
  const sa = P[na].soe, sb = P[nb].soe;
  const start = -5, end = 6, size = 0.5;
  const traces = [
    {type:"histogram", x:sa, name:na, marker:{color:A}, opacity:0.55,
     xbins:{start:start,end:end,size:size}, histnorm:"probability density"},
    {type:"histogram", x:sb, name:nb, marker:{color:B}, opacity:0.55,
     xbins:{start:start,end:end,size:size}, histnorm:"probability density"}
  ];
  const ma = mean(sa), mb = mean(sb);
  const layout = {
    barmode:"overlay", bargap:0.04,
    title:{text:"How open each receiver was, route by route", font:{size:15}},
    xaxis:{title:"yards more open than normal on the route (0 = average)", zeroline:true,
           zerolinecolor:"#c3c2b7", range:[start,end]},
    yaxis:{title:"how often"},
    legend:{orientation:"h", y:1.08, x:1, xanchor:"right"},
    template:"plotly_white", height:420, margin:{t:60,r:20,b:55,l:60},
    font:{family:"Inter, Arial, sans-serif"},
    shapes:[
      {type:"line", x0:ma, x1:ma, yref:"paper", y0:0, y1:1, line:{color:A, dash:"dash", width:2}},
      {type:"line", x0:mb, x1:mb, yref:"paper", y0:0, y1:1, line:{color:B, dash:"dash", width:2}}
    ],
    annotations:[
      {x:ma, yref:"paper", y:1.0, text:"mean "+fmtSigned(ma), showarrow:false, font:{color:A, size:11}, xanchor:"left", xshift:4},
      {x:mb, yref:"paper", y:0.93, text:"mean "+fmtSigned(mb), showarrow:false, font:{color:B, size:11}, xanchor:"left", xshift:4}
    ]
  };
  Plotly.react("hist", traces, layout, {displayModeBar:false, responsive:true});
}

(function init(){
  const selA = document.getElementById("selA"), selB = document.getElementById("selB");
  fill(selA); fill(selB);
  selA.value = DATA.defaultA; selB.value = DATA.defaultB;
  selA.addEventListener("change", draw);
  selB.addEventListener("change", draw);
  draw();
})();
</script>
</body>
</html>
"""
    html = html.replace("__PLOTLY_JS__", plotly_js).replace("__DATA_JSON__", data_json)
    with open(path, "w") as fh:
        fh.write(html)


def time_to_open_chart(per_player: pd.DataFrame, summary: dict, path: str, top: int = 15):
    """Two panels: fastest-open route runners, and whether getting open earlier means more targets."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 5.6), gridspec_kw={"width_ratios": [1.15, 1]})

    d = per_player.sort_values("median_sec_to_open").head(top).iloc[::-1]
    cols = d["position"].map(POS_COLOR)
    a1.barh(d["player"], d["median_sec_to_open"], color=cols, height=0.64)
    for y, (_, r) in enumerate(d.iterrows()):
        a1.text(r["median_sec_to_open"] + 0.02, y,
                f"{r['median_sec_to_open']:.2f}s · never got clear {r['never_open_rate']:.0%} of the time",
                va="center", fontsize=8, color=INK2)
    a1.set_xlim(0, d["median_sec_to_open"].max() + 0.7)
    a1.grid(axis="y", visible=False)
    a1.set_xlabel("seconds to pull two yards clear of the defender (lower is faster)")
    a1.set_title("These receivers shake their defender the fastest")
    _sub(a1, f"covered one-on-one at least {int(per_player['man_routes'].min())} times · label: typical time · how often he never got clear")
    from matplotlib.patches import Patch
    a1.legend(handles=[Patch(color=POS_COLOR[p], label=p) for p in ["WR", "TE", "RB"]],
              loc="upper left", bbox_to_anchor=(1.0, 1.0))

    # does getting clear relate to being thrown to?
    labels = ["got clear\nquickly", "got clear\nlater", "never got\nclear"]
    tr = [summary["target_rate_early"], summary["target_rate_late"], summary["target_rate_never"]]
    a2.bar(labels, [x * 100 for x in tr], color=["#1baf7a", "#2a78d6", "#c3c2b7"], width=0.62)
    for i, x in enumerate(tr):
        a2.annotate(f"{x:.0%}", (i, x * 100), xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9.5, color=INK2)
    a2.set_ylim(0, max(tr) * 100 * 1.35)
    a2.set_ylabel("share of routes the ball was thrown to (%)")
    a2.set_title("Receivers who get clear get thrown to more")
    _sub(a2, f"across {summary['n_routes']:,} routes · 'quickly' and 'later' split at the typical time of {summary['median_split_sec']:.2f}s")

    fig.suptitle("Only about 1 route in 9 breaks clear of its defender — and those get thrown to more often",
                 fontsize=14, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def open_but_ignored_chart(per_team: pd.DataFrame, summary: dict, path: str):
    """Two panels: what happens when the open man is ignored, and which teams ignore him most."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.5, 6.4), gridspec_kw={"width_ratios": [0.82, 1.18]})

    cr_t = summary["catch_rate_when_open_targeted"]
    cr_i = summary["catch_rate_when_open_ignored"]
    a1.bar(["threw to the\nmost open man", "threw to\nsomeone else"], [cr_t * 100, cr_i * 100],
           color=["#1baf7a", "#c0392b"], width=0.6)
    for i, (x, n) in enumerate([(cr_t, summary["n_targeted"]), (cr_i, summary["n_ignored"])]):
        a1.annotate(f"{x:.0%}\n({n:,} throws)", (i, x * 100), xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9.5, color=INK2)
    a1.set_ylim(0, 100)
    a1.set_ylabel("share of throws that were caught")
    a1.set_title("Throwing to the most open man completes more")
    _sub(a1, f"{summary['n_plays']:,} man-coverage plays · "
             f"{summary['yards_when_open_targeted']:.1f} vs {summary['yards_when_open_ignored']:.1f} yards gained")

    d = per_team.sort_values("missed_open_rate").iloc[::-1]
    a2.barh(d["possessionTeam"], d["missed_open_rate"] * 100, color="#2a78d6", height=0.72)
    lg = summary["missed_open_rate"] * 100
    a2.axvline(lg, color=INK2, lw=1, ls="--")
    a2.text(lg, len(d) - 0.3, f" league average {lg:.0f}%", color=INK2, fontsize=8.5, va="top")
    for y, (_, r) in enumerate(d.iterrows()):
        a2.text(r["missed_open_rate"] * 100 + 0.4, y, f"{r['missed_open_rate']:.0%} ({int(r['man_plays'])} plays)",
                va="center", fontsize=7.6, color=INK2)
    a2.set_xlim(0, d["missed_open_rate"].max() * 100 + 11)
    a2.grid(axis="y", visible=False)
    a2.set_xlabel("how often the team threw to someone other than its most open man")
    a2.set_title("How often each team passed up its most open receiver")
    _sub(a2, "each team on offense · label: the rate and how many plays")

    fig.suptitle("Teams passed up their most open receiver on most man plays — and those throws worked less well",
                 fontsize=14, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
