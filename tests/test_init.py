from __future__ import annotations

from pathlib import Path

import pytest

from portfolio.config import load_config
from portfolio.mutations import ValidationError, init_config


HEADER = "date,ticker,action,quantity,price,currency\n"


def _seed_existing(tmp_path: Path, with_categories: bool, with_tx_rows: bool) -> tuple[Path, Path]:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    if with_categories:
        cfg.write_text(
            "base_currency: EUR\n"
            "categories:\n"
            "  old:\n"
            "    target_weight: 1.0\n"
            "    tickers: []\n"
            "cash_balance_eur: 0.0\n"
        )
    else:
        cfg.write_text(
            "base_currency: EUR\n"
            "categories: {}\n"
            "cash_balance_eur: 0.0\n"
        )
    if with_tx_rows:
        tx.write_text(HEADER + "2026-04-01,X.DE,buy,1,1,EUR\n")
    else:
        tx.write_text(HEADER)
    return cfg, tx


def test_init_config_happy_path(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    init_config(
        config_path=cfg,
        tx_path=tx,
        cash_balance_eur=1500.0,
        categories=[("global-equity", 0.7), ("us-equity", 0.15), ("bonds", 0.1), ("cash", 0.05)],
    )
    loaded = load_config(cfg)
    assert loaded.cash_balance_eur == 1500.0
    assert set(loaded.categories.keys()) == {"global-equity", "us-equity", "bonds", "cash"}
    assert loaded.categories["global-equity"].target_weight == pytest.approx(0.7)
    for c in loaded.categories.values():
        assert c.tickers == ()
    assert tx.read_text() == HEADER


def test_init_config_refuses_when_config_has_categories_without_force(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=True, with_tx_rows=False)
    with pytest.raises(ValidationError, match="config"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 1.0)],
        )


def test_init_config_refuses_when_csv_has_rows_without_force(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=True)
    with pytest.raises(ValidationError, match="transactions"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 1.0)],
        )


def test_init_config_force_writes_bak_files(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=True, with_tx_rows=True)
    original_cfg = cfg.read_text()
    original_tx = tx.read_text()

    init_config(
        config_path=cfg,
        tx_path=tx,
        cash_balance_eur=42.0,
        categories=[("a", 1.0)],
        force=True,
    )

    assert (cfg.parent / "config.yaml.bak").read_text() == original_cfg
    assert (tx.parent / "transactions.csv.bak").read_text() == original_tx
    loaded = load_config(cfg)
    assert loaded.cash_balance_eur == 42.0
    assert tx.read_text() == HEADER


def test_init_config_validates_weight_sum(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="sum"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 0.5), ("b", 0.4)],
        )


def test_init_config_rejects_negative_cash(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="cash"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=-1.0,
            categories=[("a", 1.0)],
        )


def test_init_config_rejects_duplicate_categories(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="duplicate"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 0.5), ("a", 0.5)],
        )


def test_init_config_rejects_empty_categories(tmp_path: Path) -> None:
    cfg, tx = _seed_existing(tmp_path, with_categories=False, with_tx_rows=False)
    with pytest.raises(ValidationError, match="at least one"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[],
        )


def test_init_config_handles_missing_files(tmp_path: Path) -> None:
    """Truly fresh repo: no config.yaml or transactions.csv exists yet."""
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    init_config(
        config_path=cfg,
        tx_path=tx,
        cash_balance_eur=100.0,
        categories=[("only", 1.0)],
    )
    assert load_config(cfg).cash_balance_eur == 100.0
    assert tx.read_text() == HEADER


def test_init_config_refuses_config_without_categories_key(tmp_path: Path) -> None:
    """A user-edited config that lost its 'categories' key must require --force."""
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text("base_currency: EUR\ncash_balance_eur: 999.0\n")  # no categories key
    tx.write_text(HEADER)

    with pytest.raises(ValidationError, match="categories"):
        init_config(
            config_path=cfg,
            tx_path=tx,
            cash_balance_eur=0.0,
            categories=[("a", 1.0)],
        )


from portfolio import cli


def _scripted_input(answers: list[str]):
    it = iter(answers)
    return lambda _prompt="": next(it)


def test_prompt_init_inputs_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = [
        "1500",         # cash
        "global-equity",  # category 1
        "us-equity",      # category 2
        "",               # end of categories
        "70",             # weight 1
        "30",             # weight 2
    ]
    monkeypatch.setattr("builtins.input", _scripted_input(answers))

    cash, cats = cli._prompt_init_inputs()
    assert cash == 1500.0
    assert cats == [("global-equity", 0.7), ("us-equity", 0.3)]


def test_prompt_init_inputs_reprompts_on_bad_weight_sum(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    answers = [
        "0",            # cash
        "a", "b", "",   # categories
        "60", "30",     # first attempt sums to 90 → reprompt
        "60", "40",     # second attempt sums to 100 → accepted
    ]
    monkeypatch.setattr("builtins.input", _scripted_input(answers))

    cash, cats = cli._prompt_init_inputs()
    assert cash == 0.0
    assert cats == [("a", 0.6), ("b", 0.4)]
    err = capsys.readouterr().err
    assert "90" in err  # informed the user about the bad sum


def test_prompt_init_inputs_reprompts_on_negative_cash(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = ["-5", "100", "only", "", "100"]
    monkeypatch.setattr("builtins.input", _scripted_input(answers))

    cash, cats = cli._prompt_init_inputs()
    assert cash == 100.0
    assert cats == [("only", 1.0)]


def test_prompt_init_inputs_rejects_duplicate_category(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = ["0", "a", "a", "b", "", "50", "50"]
    monkeypatch.setattr("builtins.input", _scripted_input(answers))

    cash, cats = cli._prompt_init_inputs()
    assert [n for n, _ in cats] == ["a", "b"]


def test_init_cli_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text("base_currency: EUR\ncategories: {}\ncash_balance_eur: 0.0\n")
    tx.write_text(HEADER)

    answers = [
        "y",         # confirmation
        "100",       # cash
        "only", "",  # categories
        "100",       # weight
    ]
    monkeypatch.setattr("builtins.input", _scripted_input(answers))

    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "init"])
    assert rc == 0
    assert load_config(cfg).cash_balance_eur == 100.0


def test_init_cli_aborts_on_no_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text("base_currency: EUR\ncategories: {}\ncash_balance_eur: 0.0\n")
    tx.write_text(HEADER)
    original = cfg.read_text()

    monkeypatch.setattr("builtins.input", _scripted_input(["n"]))
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "init"])

    assert rc == 0  # graceful abort, not an error
    assert cfg.read_text() == original  # untouched


def test_init_cli_preflight_refuses_before_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Existing categories + no --force → refuse after confirmation, no further prompts consumed."""
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n"
        "  old:\n"
        "    target_weight: 1.0\n"
        "    tickers: []\n"
        "cash_balance_eur: 0.0\n"
    )
    tx.write_text(HEADER)

    # Only one input (the 'y'); if pre-flight works, no input is consumed beyond it.
    monkeypatch.setattr("builtins.input", _scripted_input(["y"]))

    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "init"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "categor" in err.lower()
    assert "--force" in err


def test_dashboard_passes_unknown_options_through(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def fake_call(cmd: list[str]) -> int:
        captured.append(list(cmd))
        return 0

    monkeypatch.setattr("subprocess.call", fake_call)

    rc = cli.main(["dashboard", "--server.port", "8765", "--server.headless", "true"])
    assert rc == 0
    assert len(captured) == 1
    cmd = captured[0]
    assert "--server.port" in cmd
    assert "8765" in cmd
    assert "--server.headless" in cmd
    assert "true" in cmd


def test_dashboard_extras_appear_before_app_py(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streamlit options only take effect when they PRECEDE the script path."""
    captured: list[list[str]] = []

    def fake_call(cmd: list[str]) -> int:
        captured.append(list(cmd))
        return 0

    monkeypatch.setattr("subprocess.call", fake_call)

    rc = cli.main(["dashboard", "--server.port", "8765"])
    assert rc == 0
    cmd = captured[0]
    run_idx = cmd.index("run")
    port_idx = cmd.index("--server.port")
    app_idx = next(i for i, x in enumerate(cmd) if str(x).endswith("app.py"))
    assert run_idx < port_idx < app_idx, f"expected run < --server.port < app.py, got {cmd}"
