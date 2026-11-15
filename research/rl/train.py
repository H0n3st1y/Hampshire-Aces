"""Train tabular Q-learning policies and evaluate them on held-out seeds.

From the repository root (uses the backend venv; no extra packages):
    backend/.venv/Scripts/python -m research.rl.train            # full run
    backend/.venv/Scripts/python -m research.rl.train --quick    # smoke run, writes nothing

Protocol (fixed before looking at results):
- 5 training runs, run seeds 0..4; training episode seeds run*1_000_000 + i.
- Held-out evaluation episode seeds 900_000_000 + i, disjoint from training.
- The deployed artifact is the run-seed-0 policy, chosen in advance (not the best run).
- Every policy is evaluated through strategy.propose (the real integration path)
  with identical episodes, gate, costs, and execution.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import time
from pathlib import Path

from backend.agents import rl_policy, strategy
from backend.agents._common import held_quantity, metric, normalize_observation

from .env import DRIFT, HEADLINE_MATCH_PROB, SIGMAS, Episode

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "research" / "artifacts"
RESULTS_DIR = ROOT / "research" / "results"

CONFIG = {
    "episodes_per_run": 6000,
    "episode_length": 8,
    "gamma": 0.9,
    "alpha_min": 0.02,
    "epsilon_start": 1.0,
    "epsilon_end": 0.05,
    "downside_penalty": 0.5,
    "reward_scale": 100.0,
    "run_seeds": [0, 1, 2, 3, 4],
    "deployed_run_seed": 0,
    "eval_episodes": 400,
    "eval_seed_base": 900_000_000,
}


def reward(before: int, after: int, cfg: dict) -> float:
    """Next-step simulated return after costs (costs already inside the adapter's
    end value, counted once) minus a penalty on negative returns. The penalty shapes
    behaviour; it does not bound losses."""
    ret = (after - before) / before
    return cfg["reward_scale"] * (ret - cfg["downside_penalty"] * max(0.0, -ret))


def features(obs: dict, sent: dict) -> tuple[str, list[str], dict]:
    norm, _ = normalize_observation(obs)
    key = rl_policy.state_key(
        sent["sentiment_label"], metric(norm, "daily_volatility"), metric(norm, "position_weight_before"),
        norm["cash_cents"], norm["total_value_cents"],
    )
    held = held_quantity(norm, norm["focus_symbol"])
    return key, rl_policy.feasible_actions(held, norm["permitted_actions"]), norm


def proposal_for(action: str, norm: dict) -> dict:
    """Same mapping as strategy._rl_proposal: fixed permitted quantity, sell capped at holdings."""
    if action == "hold":
        return {"type": "hold", "symbol": None, "quantity": 0, "reason": "training"}
    symbol, qty = norm["focus_symbol"], norm["action_quantity"]
    if action == "sell":
        qty = min(qty, held_quantity(norm, symbol))
    return {"type": action, "symbol": symbol, "quantity": qty, "reason": "training"}


def train_run(run_seed: int, cfg: dict) -> dict:
    rng = random.Random(run_seed)
    table: dict[str, dict] = {}

    def entry(key):
        return table.setdefault(key, {"q": [0.0] * len(rl_policy.ACTIONS), "visits": [0] * len(rl_policy.ACTIONS)})

    n = cfg["episodes_per_run"]
    for i in range(n):
        eps = cfg["epsilon_start"] + (cfg["epsilon_end"] - cfg["epsilon_start"]) * i / max(n - 1, 1)
        env = Episode(seed=run_seed * 1_000_000 + i, length=cfg["episode_length"])
        obs, sent = env.observe()
        key, feasible, norm = features(obs, sent)
        while True:
            e = entry(key)
            if rng.random() < eps:
                action = rng.choice(feasible)
            else:
                action = max(feasible, key=lambda a: (e["q"][rl_policy.ACTIONS.index(a)], -rl_policy.ACTIONS.index(a)))
            res = env.step(proposal_for(action, norm))
            r = reward(res.value_before, res.value_after, cfg)
            if env.done:
                target = r
            else:
                obs, sent = env.observe()
                next_key, next_feasible, norm = features(obs, sent)
                ne = entry(next_key)
                target = r + cfg["gamma"] * max(ne["q"][rl_policy.ACTIONS.index(a)] for a in next_feasible)
            ai = rl_policy.ACTIONS.index(action)
            e["visits"][ai] += 1
            alpha = max(cfg["alpha_min"], 1.0 / e["visits"][ai])
            e["q"][ai] += alpha * (target - e["q"][ai])
            if env.done:
                break
            key, feasible = next_key, next_feasible
    return {
        "format": rl_policy.ARTIFACT_FORMAT,
        "artifact_id": f"q_policy_seed{run_seed}",
        "actions": list(rl_policy.ACTIONS),
        "min_state_visits": rl_policy.MIN_STATE_VISITS,
        "q_table": {k: {"q": [round(x, 6) for x in v["q"]], "visits": v["visits"]} for k, v in sorted(table.items())},
        "training": {"run_seed": run_seed, "config": cfg, "env": {"sigmas": SIGMAS, "drift": DRIFT, "headline_match_prob": HEADLINE_MATCH_PROB}},
    }


def max_drawdown(values: list[int]) -> float:
    peak, worst = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        worst = max(worst, (peak - v) / peak)
    return worst


def evaluate(policy: str, cfg: dict, artifact_path: Path | None = None) -> dict:
    env_vars = {"AGENTS_MODEL_ENABLED": "0", "AGENTS_POLICY": "rl" if policy == "rl" else "rule_based"}
    if artifact_path:
        env_vars["AGENTS_RL_ARTIFACT"] = str(artifact_path)
    saved = {k: os.environ.get(k) for k in env_vars}
    os.environ.update(env_vars)
    try:
        rets, dds, trades, shares, blocked, fallbacks, decisions = [], [], [], [], 0, 0, 0
        for i in range(cfg["eval_episodes"]):
            env = Episode(seed=cfg["eval_seed_base"] + i, length=cfg["episode_length"])
            values = [env.portfolio.total_value_cents]
            n_trades = n_shares = 0
            while not env.done:
                obs, sent = env.observe()
                if policy == "hold":
                    proposal = {"type": "hold", "symbol": None, "quantity": 0, "reason": "baseline"}
                else:
                    out = strategy.propose(obs, sent)
                    proposal = out["proposal"]
                    if policy == "rl" and out["policy_mode"] != "rl":
                        fallbacks += 1
                decisions += 1
                res = env.step(proposal)
                blocked += res.gate_status == "blocked"
                n_trades += res.executed_trade
                n_shares += res.shares_traded
                values.append(res.value_after)
            rets.append(values[-1] / values[0] - 1)
            dds.append(max_drawdown(values))
            trades.append(n_trades)
            shares.append(n_shares)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    rets_sorted = sorted(rets)
    return {
        "policy": policy,
        "episodes": len(rets),
        "decisions": decisions,
        "mean_return": statistics.fmean(rets),
        "median_return": statistics.median(rets),
        "p10_return": rets_sorted[len(rets) // 10],
        "mean_max_drawdown": statistics.fmean(dds),
        "worst_max_drawdown": max(dds),
        "mean_trades_per_episode": statistics.fmean(trades),
        "mean_shares_traded_per_episode": statistics.fmean(shares),
        "blocked_proposals": blocked,
        "rl_fallback_decisions": fallbacks if policy == "rl" else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="tiny smoke run; writes nothing")
    args = ap.parse_args()
    cfg = dict(CONFIG)
    if args.quick:
        cfg.update(episodes_per_run=60, eval_episodes=20, run_seeds=[0])
    t0 = time.time()
    tmp_dir = ARTIFACT_DIR / "runs"
    if not args.quick:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    runs = []
    for seed in cfg["run_seeds"]:
        art = train_run(seed, cfg)
        path = (tmp_dir / f"q_policy_seed{seed}.json") if not args.quick else (Path(os.environ.get("TEMP", ".")) / "q_quick.json")
        path.write_text(json.dumps(art, indent=1), encoding="utf-8")
        ev = evaluate("rl", cfg, path)
        ev["run_seed"] = seed
        ev["states_learned"] = len(art["q_table"])
        runs.append(ev)
        print(f"run seed {seed}: mean_return={ev['mean_return']:.4%} dd={ev['mean_max_drawdown']:.4%} "
              f"trades={ev['mean_trades_per_episode']:.2f} blocked={ev['blocked_proposals']} fallbacks={ev['rl_fallback_decisions']}")
        if seed == cfg["deployed_run_seed"] and not args.quick:
            art["artifact_id"] = "q_policy_v1"
            (ARTIFACT_DIR / "q_policy_v1.json").write_text(json.dumps(art, indent=1), encoding="utf-8")

    baselines = [evaluate("rule", cfg), evaluate("hold", cfg)]
    for b in baselines:
        print(f"{b['policy']}: mean_return={b['mean_return']:.4%} dd={b['mean_max_drawdown']:.4%} "
              f"trades={b['mean_trades_per_episode']:.2f} blocked={b['blocked_proposals']}")

    report = {
        "config": cfg,
        "rl_runs": runs,
        "rl_mean_return_range": [min(r["mean_return"] for r in runs), max(r["mean_return"] for r in runs)],
        "baselines": baselines,
        "deployed_artifact": "research/artifacts/q_policy_v1.json (run seed 0, chosen before evaluation)",
        "seconds": round(time.time() - t0, 1),
    }
    if not args.quick:
        (RESULTS_DIR / "rl_eval_v1.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"done in {report['seconds']}s")


if __name__ == "__main__":
    main()
