"""Assemble an Engine + Session from a scenario argument.

One place that does this, shared by the terminal and web front ends, so
they can't drift into building the engine two different ways.
"""
from __future__ import annotations

from pathlib import Path

from src.cast import load_scenario, resolve_scenario
from src.config import load_config
from src.engine import Engine
from src.policy import load_policy
from src.provider import get_client
from src.session import Session, attachments_dir, session_path


def build_engine(scenario_arg: str | None, fresh: bool) -> tuple[Engine, Session, Path]:
    cfg = load_config()
    scenario_path = resolve_scenario(cfg, scenario_arg)
    policy = load_policy(cfg)
    scenario = load_scenario(scenario_path)

    save_path = session_path(cfg, scenario_path)
    session = Session() if fresh else Session.load(save_path, policy.history_strategy)

    engine = Engine(
        scenario=scenario,
        cfg=cfg,
        policy=policy,
        client=get_client(cfg),
        history=session.history,
        state=session.state,
        last_speaker=session.last_speaker,
        attachments_dir=attachments_dir(save_path),
    )
    for name, value in session.debt.items():
        if name in engine.selector.debt:
            engine.selector.debt[name] = value

    return engine, session, save_path


def save_session(engine: Engine, session: Session, save_path: Path) -> None:
    session.history = engine.history
    session.state = engine.state
    session.debt = engine.selector.debt
    session.last_speaker = engine.last_speaker
    session.save(save_path)
