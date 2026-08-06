# docs/paper/figures/generate_figures.py
# Regenerates the paper's data-driven figures directly from committed
# experiments/results/*.json -- run from the repo root:
#   python3 -m docs.paper.figures.generate_figures
# or: python3 docs/paper/figures/generate_figures.py
#
# Figure (b): benign-vs-injection score distribution, soc_domain_eval_results.json (PROGRESS.md T2b)
# Figure (c): throughput vs worker count by mode, week7_scalability_benchmark.json (PROGRESS.md T2c)

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = REPO_ROOT / "experiments" / "results"
FIGURES_DIR = Path(__file__).resolve().parent

# First three slots of the validated categorical palette (dataviz skill,
# references/palette.md) -- these three clear the all-pairs CVD/contrast
# floors in both light and dark mode, unlike slots 4+.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"

MUTED = "#898781"
GRIDLINE = "#e1e0d9"
AXIS = "#c3c2b7"
PRIMARY_INK = "#0b0b0b"


def _style_axes(ax):
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(AXIS)
    ax.tick_params(colors=PRIMARY_INK, labelsize=8)
    ax.xaxis.label.set_color(PRIMARY_INK)
    ax.yaxis.label.set_color(PRIMARY_INK)


def figure_b_score_distribution():
    data = json.loads((RESULTS_DIR / "soc_domain_eval_results.json").read_text())
    rows = data["per_row"]
    benign = [r["score"] for r in rows if r["label"] == "benign"]
    injection = [r["score"] for r in rows if r["label"] == "injection"]

    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=200)
    rng_seed = 42
    import random
    rnd = random.Random(rng_seed)

    for y, (scores, color, name) in enumerate(
        [(injection, ORANGE, "injection (n=20)"), (benign, BLUE, "benign (n=20)")]
    ):
        jitter = [y + rnd.uniform(-0.18, 0.18) for _ in scores]
        ax.scatter(scores, jitter, s=26, color=color, alpha=0.85, edgecolors="white", linewidths=0.5, label=name, zorder=3)

    ax.axvline(0.5, color=MUTED, linestyle="--", linewidth=1, zorder=1)
    ax.text(0.5, 1.55, "default\nthreshold\n(0.5)", ha="center", va="bottom", fontsize=6.5, color=MUTED)
    ax.axvline(0.7, color=MUTED, linestyle=":", linewidth=1, zorder=1)
    ax.text(0.7, 1.55, "best-accuracy\nthreshold\n(0.7)", ha="center", va="bottom", fontsize=6.5, color=MUTED)

    ax.set_yticks([0, 1])
    ax.set_yticklabels(["injection", "benign"], fontsize=8)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.6, 2.1)
    ax.set_xlabel("classifier score (post index-bug fix)", fontsize=8)
    ax.grid(axis="x", color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    _style_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)

    fig.suptitle(
        "SOC-domain eval: no score threshold separates the two classes",
        fontsize=9.5, fontweight="bold", x=0.02, ha="left", color=PRIMARY_INK,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    out = FIGURES_DIR / "score_distribution.png"
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")


def figure_c_throughput_scaling():
    data = json.loads((RESULTS_DIR / "week7_scalability_benchmark.json").read_text())
    results = data["results"]

    modes = ["llm", "rf", "hybrid"]
    mode_titles = {"llm": "LLM-only", "rf": "RF-only", "hybrid": "Hybrid (context-richness router)"}
    prompt_counts = [30, 60, 120]
    colors = {30: BLUE, 60: ORANGE, 120: AQUA}

    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.6), dpi=200, sharex=True)

    for ax, mode in zip(axes, modes):
        for pc in prompt_counts:
            rows = sorted(
                (r for r in results if r["mode"] == mode and r["prompt_count"] == pc),
                key=lambda r: r["workers"],
            )
            workers = [r["workers"] for r in rows]
            throughput = [r["throughput_alerts_per_second"] for r in rows]
            ax.plot(
                workers, throughput, marker="o", markersize=4.5, linewidth=2,
                color=colors[pc], label=f"{pc} prompts",
            )
        ax.set_title(mode_titles[mode], fontsize=8.5, color=PRIMARY_INK)
        ax.set_xticks([1, 4])
        ax.set_xlim(0.5, 4.5)
        ax.set_xlabel("workers", fontsize=8)
        ax.set_yscale("log")
        ax.grid(axis="y", which="both", color=GRIDLINE, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        _style_axes(ax)

    axes[0].set_ylabel("throughput (alerts/s, log scale)", fontsize=8)

    fig.suptitle(
        "Throughput vs. worker count, by pipeline mode\n(note: each panel has its own y-scale)",
        fontsize=9.5, fontweight="bold", y=0.99, color=PRIMARY_INK,
    )
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", ncol=3, frameon=False,
        bbox_to_anchor=(0.5, 0.85), fontsize=8,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.78])
    out = FIGURES_DIR / "throughput_scaling.png"
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    figure_b_score_distribution()
    figure_c_throughput_scaling()
