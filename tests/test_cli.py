from __future__ import annotations

from pathlib import Path

import pytest

from portfolio import cli

CONFIG_YAML = """\
base_currency: EUR
categories:
  equity:
    target_weight: 0.7
    tickers:
      - VWCE.DE
  cash:
    target_weight: 0.3
    tickers: []
cash_balance_eur: 1000.0
"""
HEADER = "date,ticker,action,quantity,price,currency\n"


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text(CONFIG_YAML)
    tx.write_text(HEADER + "2026-01-15,VWCE.DE,buy,10,98.50,EUR\n")
    return cfg, tx


def _argv(cfg: Path, tx: Path, *rest: str) -> list[str]:
    return ["--config", str(cfg), "--transactions", str(tx), *rest]


# --- dispatch / arg parsing ---------------------------------------------------

def test_main_rejects_unknown_args(repo: tuple[Path, Path]) -> None:
    cfg, tx = repo
    with pytest.raises(SystemExit):
        cli.main(_argv(cfg, tx, "show", "--bogus"))


# --- add-buy / add-sell -------------------------------------------------------

def test_main_add_buy_success(repo: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    cfg, tx = repo
    rc = cli.main(_argv(cfg, tx, "add-buy", "VWCE.DE", "5", "100.0"))
    assert rc == 0
    assert "appended" in capsys.readouterr().out
    assert len(tx.read_text().strip().splitlines()) == 3  # header + seed + new


def test_main_add_buy_unknown_ticker_returns_1(
    repo: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, tx = repo
    rc = cli.main(_argv(cfg, tx, "add-buy", "NOPE.DE", "5", "100.0"))
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_main_add_sell_within_holding(
    repo: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    cfg, tx = repo
    rc = cli.main(_argv(cfg, tx, "add-sell", "VWCE.DE", "3", "120.0"))
    assert rc == 0
    assert "appended" in capsys.readouterr().out


# --- check --------------------------------------------------------------------

def test_main_check_ok(repo: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    cfg, tx = repo
    rc = cli.main(_argv(cfg, tx, "check"))
    assert rc == 0
    assert "ok:" in capsys.readouterr().out


def test_main_check_orphan_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text(CONFIG_YAML)
    tx.write_text(HEADER + "2026-01-15,ORPHAN.DE,buy,10,98.50,EUR\n")
    rc = cli.main(_argv(cfg, tx, "check"))
    assert rc == 1
    assert "not in config" in capsys.readouterr().err


# --- show (network fetchers stubbed) -----------------------------------------

def test_main_show_renders_table(
    repo: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, tx = repo
    monkeypatch.setattr(cli, "fetch_historical_fx_eur", lambda cur, d: 1.0)
    monkeypatch.setattr(cli, "fetch_prices", lambda tickers: {"VWCE.DE": 150.0})
    monkeypatch.setattr(cli, "fetch_fx_eur", lambda currencies: {"EUR": 1.0})
    monkeypatch.setattr(cli, "fetch_dividend_yields", lambda tickers, **kw: {"VWCE.DE": 0.02})

    rc = cli.main(_argv(cfg, tx, "show"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "VWCE.DE" in out
    assert "CATEGORY" in out


def test_main_show_includes_income_summary(
    repo: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, tx = repo
    _stub_income_fetchers(monkeypatch, {"VWCE.DE": 0.02})

    rc = cli.main(_argv(cfg, tx, "show"))
    out = capsys.readouterr().out
    assert rc == 0
    # one-line income run-rate summary folded into show
    assert "INCOME" in out
    assert "30.00" in out  # annual economic run-rate


# --- income (network fetchers stubbed) ---------------------------------------

def _stub_income_fetchers(monkeypatch: pytest.MonkeyPatch, yields: dict[str, float]) -> None:
    monkeypatch.setattr(cli, "fetch_historical_fx_eur", lambda cur, d: 1.0)
    monkeypatch.setattr(cli, "fetch_prices", lambda tickers: {"VWCE.DE": 150.0})
    monkeypatch.setattr(cli, "fetch_fx_eur", lambda currencies: {"EUR": 1.0})
    monkeypatch.setattr(cli, "fetch_dividend_yields", lambda tickers, **kw: yields)
    monkeypatch.setattr(cli, "fetch_names", lambda tickers: {"VWCE.DE": "Vanguard FTSE All-World"})


def test_main_income_renders(
    repo: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, tx = repo
    _stub_income_fetchers(monkeypatch, {"VWCE.DE": 0.02})  # 10 sh × 150 = 1500 mv → 30/yr

    rc = cli.main(_argv(cfg, tx, "income"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "VWCE.DE" in out
    assert "Vanguard FTSE All-World" in out  # friendly company name
    assert "30.00" in out   # annual economic income
    assert "TOTAL" in out


def test_main_income_net_applies_tax(
    repo: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, tx = repo
    _stub_income_fetchers(monkeypatch, {"VWCE.DE": 0.02})  # gross economic = 30.00

    rc = cli.main(_argv(cfg, tx, "income", "--net"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "net" in out.lower()
    # equity-fund default: 30 * (1 - 0.26375*0.70) = 24.46
    assert "24.46" in out
    assert "30.00" not in out  # gross figure should not appear in net mode


def test_main_income_warns_on_unresolved(
    repo: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg, tx = repo
    _stub_income_fetchers(monkeypatch, {"VWCE.DE": float("nan")})

    rc = cli.main(_argv(cfg, tx, "income"))
    captured = capsys.readouterr()
    assert rc == 0
    assert "n/a" in captured.out
    assert "warning" in captured.err.lower()
    assert "VWCE.DE" in captured.err


def test_main_show_orphan_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    cfg.write_text(CONFIG_YAML)
    tx.write_text(HEADER + "2026-01-15,ORPHAN.DE,buy,10,98.50,EUR\n")
    rc = cli.main(_argv(cfg, tx, "show"))
    assert rc == 1
    assert "not in config" in capsys.readouterr().err


# --- init ---------------------------------------------------------------------

def test_main_init_aborts_on_no(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    monkeypatch.setattr("builtins.input", lambda _="": "n")
    rc = cli.main(_argv(cfg, tx, "init"))
    assert rc == 0
    assert "aborted" in capsys.readouterr().err


def test_main_init_refuses_clobber_without_force(
    repo: tuple[Path, Path], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg, tx = repo  # already has categories
    monkeypatch.setattr("builtins.input", lambda _="": "y")
    rc = cli.main(_argv(cfg, tx, "init"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "error:" in err
    assert "--force" in err


def test_main_init_success_on_fresh_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.yaml"
    tx = tmp_path / "transactions.csv"
    # confirm, cash, one category, blank-to-finish, its weight
    answers = iter(["y", "1500", "equity", "", "100"])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    rc = cli.main(_argv(cfg, tx, "init"))
    assert rc == 0
    assert cfg.exists() and tx.read_text() == HEADER
    assert "wrote" in capsys.readouterr().out


# --- dashboard ----------------------------------------------------------------

def test_main_dashboard_app_not_found(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_find_app_py", lambda: None)
    rc = cli.main(["dashboard"])
    assert rc == 1
    assert "app.py not found" in capsys.readouterr().err


def test_main_dashboard_invokes_streamlit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_call(cmd: list[str]) -> int:
        captured["cmd"] = cmd
        return 0

    monkeypatch.setattr(cli, "_find_app_py", lambda: tmp_path / "app.py")
    monkeypatch.setattr(cli.subprocess, "call", fake_call)

    rc = cli.main(["dashboard", "--server.port", "8502"])
    assert rc == 0
    assert "streamlit" in captured["cmd"]
    assert "--server.port" in captured["cmd"]


def test_find_app_py_prefers_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "app.py").write_text("# app")
    monkeypatch.chdir(tmp_path)
    assert cli._find_app_py() == (tmp_path / "app.py").resolve()


def test_find_app_py_returns_none_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Isolate both lookup paths: empty cwd, and a module location whose parents
    # contain no app.py + pyproject.toml pair.
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "__file__", str(nested / "cli.py"))
    assert cli._find_app_py() is None


# --- interactive prompt helpers ----------------------------------------------

def test_prompt_cash_reprompts_on_bad_then_negative(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter(["abc", "-5", "100"])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    assert cli._prompt_cash() == 100.0
    err = capsys.readouterr().err
    assert "not a number" in err
    assert "must be >= 0" in err


def test_prompt_categories_rejects_empty_and_duplicate(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter(["", "equity", "equity", ""])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    assert cli._prompt_categories() == ["equity"]
    err = capsys.readouterr().err
    assert "at least one" in err
    assert "duplicate" in err


def test_prompt_weights_reprompts_on_bad_then_negative(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter(["x", "-1", "60"])
    monkeypatch.setattr("builtins.input", lambda _="": next(answers))
    assert cli._prompt_weights(["equity"]) == {"equity": 60.0}
    err = capsys.readouterr().err
    assert "not a number" in err
    assert "must be >= 0" in err


# --- import -------------------------------------------------------------------

import builtins


def _feed_inputs(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda *a, **k: next(it))


def _write_csv(path, body):
    path.write_text(body)


def test_import_full_flow_writes_tx_and_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: []\n"
        "cash_balance_eur: 0.0\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text("date,ticker,action,quantity,price,currency\n")
    csv = tmp_path / "tr.csv"
    csv.write_text(
        "Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n"
        "19.04.2026,IE00X,Kauf,\"2,5\",\"1.234,56\",EUR\n"
        "20.04.2026,IE00X,Kauf,\"1\",\"1.000,00\",EUR\n"
    )
    # Profile setup answers: date col=0, isin=1, action=2, qty=3, price=4, currency=5,
    # decimal default (blank -> suggested 'comma'), date_format blank->auto,
    # action 'Kauf'->buy. Then ISIN prompt: ticker, category index 0. Then confirm 'y'.
    answers = [
        "0", "1", "2", "3", "4", "5",   # columns
        "", "",                          # decimal (suggested), date_format (auto)
        "buy",                           # classify 'Kauf'
        "WEBG.DE", "0",                  # ISIN IE00X -> ticker, category 0
        "y",                             # confirm append
    ]
    _feed_inputs(monkeypatch, answers)
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv)])
    assert rc == 0
    rows = [l for l in tx.read_text().splitlines()[1:] if l.strip()]
    assert len(rows) == 2
    assert all(r.split(",")[1] == "WEBG.DE" for r in rows)
    import yaml
    data = yaml.safe_load(cfg.read_text())
    assert data["isin_map"]["IE00X"] == "WEBG.DE"
    assert "WEBG.DE" in data["categories"]["core"]["tickers"]
    assert data["import_profile"]["actions"] == {"kauf": "buy"}


def test_import_reimport_skips_duplicates(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: [WEBG.DE]\n"
        "cash_balance_eur: 0.0\n"
        "import_profile:\n"
        "  columns: {date: Datum, isin: ISIN, action: Typ, quantity: Anzahl, price: Kurs, currency: Waehrung}\n"
        "  decimal: comma\n  date_format: auto\n  actions: {kauf: buy}\n"
        "isin_map: {IE00X: WEBG.DE}\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text(
        "date,ticker,action,quantity,price,currency\n"
        "2026-04-19,WEBG.DE,buy,2.5,1234.56,EUR\n"
    )
    csv = tmp_path / "tr.csv"
    csv.write_text(
        "Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n"
        "19.04.2026,IE00X,Kauf,\"2,5\",\"1.234,56\",EUR\n"   # dup of existing
        "20.04.2026,IE00X,Kauf,\"1\",\"1.000,00\",EUR\n"     # new
    )
    _feed_inputs(monkeypatch, ["y"])  # only the confirm prompt
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv)])
    assert rc == 0
    rows = [l for l in tx.read_text().splitlines()[1:] if l.strip()]
    assert len(rows) == 2  # 1 existing + 1 new (dup skipped)


def test_import_dry_run_appends_nothing(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: [WEBG.DE]\n"
        "cash_balance_eur: 0.0\n"
        "import_profile:\n"
        "  columns: {date: Datum, isin: ISIN, action: Typ, quantity: Anzahl, price: Kurs, currency: Waehrung}\n"
        "  decimal: comma\n  date_format: auto\n  actions: {kauf: buy}\n"
        "isin_map: {IE00X: WEBG.DE}\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text("date,ticker,action,quantity,price,currency\n")
    csv = tmp_path / "tr.csv"
    csv.write_text("Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n20.04.2026,IE00X,Kauf,\"1\",\"1.000,00\",EUR\n")
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv), "--dry-run"])
    assert rc == 0
    assert [l for l in tx.read_text().splitlines()[1:] if l.strip()] == []


def test_import_unknown_isin_with_yes_errors(tmp_path, capsys):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: []\n"
        "cash_balance_eur: 0.0\n"
        "import_profile:\n"
        "  columns: {date: Datum, isin: ISIN, action: Typ, quantity: Anzahl, price: Kurs, currency: Waehrung}\n"
        "  decimal: comma\n  date_format: auto\n  actions: {kauf: buy}\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text("date,ticker,action,quantity,price,currency\n")
    csv = tmp_path / "tr.csv"
    csv.write_text("Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n20.04.2026,IE00X,Kauf,\"1\",\"1.000,00\",EUR\n")
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv), "--yes"])
    assert rc == 1
    assert "unmapped ISIN" in capsys.readouterr().err


def test_import_sell_exceeds_holdings_aborts(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: [WEBG.DE]\n"
        "cash_balance_eur: 0.0\n"
        "import_profile:\n"
        "  columns: {date: Datum, isin: ISIN, action: Typ, quantity: Anzahl, price: Kurs, currency: Waehrung}\n"
        "  decimal: comma\n  date_format: auto\n  actions: {kauf: buy, verkauf: sell}\n"
        "isin_map: {IE00X: WEBG.DE}\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text("date,ticker,action,quantity,price,currency\n")
    csv = tmp_path / "tr.csv"
    csv.write_text(
        "Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n"
        "20.04.2026,IE00X,Verkauf,\"5\",\"1.000,00\",EUR\n"  # sell with no holdings
    )
    _feed_inputs(monkeypatch, ["y"])
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv)])
    assert rc == 1
    assert [l for l in tx.read_text().splitlines()[1:] if l.strip()] == []


def test_import_same_day_buy_before_sell_ok(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: [WEBG.DE]\n"
        "cash_balance_eur: 0.0\n"
        "import_profile:\n"
        "  columns: {date: Datum, isin: ISIN, action: Typ, quantity: Anzahl, price: Kurs, currency: Waehrung}\n"
        "  decimal: comma\n  date_format: auto\n  actions: {kauf: buy, verkauf: sell}\n"
        "isin_map: {IE00X: WEBG.DE}\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text("date,ticker,action,quantity,price,currency\n")
    csv = tmp_path / "tr.csv"
    csv.write_text(
        "Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n"
        "19.04.2026,IE00X,Verkauf,\"5\",\"100,00\",EUR\n"   # sell listed first
        "19.04.2026,IE00X,Kauf,\"10\",\"100,00\",EUR\n"     # buy same day
    )
    _feed_inputs(monkeypatch, ["y"])
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv)])
    assert rc == 0
    rows = [l for l in tx.read_text().splitlines()[1:] if l.strip()]
    assert len(rows) == 2


def test_import_yes_happy_path_no_prompt(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: [WEBG.DE]\n"
        "cash_balance_eur: 0.0\n"
        "import_profile:\n"
        "  columns: {date: Datum, isin: ISIN, action: Typ, quantity: Anzahl, price: Kurs, currency: Waehrung}\n"
        "  decimal: comma\n  date_format: auto\n  actions: {kauf: buy}\n"
        "isin_map: {IE00X: WEBG.DE}\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text("date,ticker,action,quantity,price,currency\n")
    csv = tmp_path / "tr.csv"
    csv.write_text("Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n20.04.2026,IE00X,Kauf,\"1\",\"1.000,00\",EUR\n")
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv), "--yes"])
    assert rc == 0
    rows = [l for l in tx.read_text().splitlines()[1:] if l.strip()]
    assert len(rows) == 1


def test_import_parse_error_aborts(tmp_path, capsys):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "base_currency: EUR\n"
        "categories:\n  core:\n    target_weight: 1.0\n    tickers: [WEBG.DE]\n"
        "cash_balance_eur: 0.0\n"
        "import_profile:\n"
        "  columns: {date: Datum, isin: ISIN, action: Typ, quantity: Anzahl, price: Kurs, currency: Waehrung}\n"
        "  decimal: comma\n  date_format: auto\n  actions: {kauf: buy}\n"
        "isin_map: {IE00X: WEBG.DE}\n"
    )
    tx = tmp_path / "transactions.csv"
    tx.write_text("date,ticker,action,quantity,price,currency\n")
    csv = tmp_path / "tr.csv"
    csv.write_text("Datum,ISIN,Typ,Anzahl,Kurs,Waehrung\n20.04.2026,IE00X,Dividende,\"1\",\"1.000,00\",EUR\n")
    rc = cli.main(["--config", str(cfg), "--transactions", str(tx), "import", str(csv)])
    assert rc == 1
    assert "unknown action" in capsys.readouterr().err
    assert [l for l in tx.read_text().splitlines()[1:] if l.strip()] == []
