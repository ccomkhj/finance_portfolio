# Public Launch Notes

This project is best launched as a local-first open-source tool, not as a hosted
robo-advisor or broker-connected SaaS.

## Positioning

- Privacy-first portfolio tracker for EU self-directed investors.
- Plain-text CSV/YAML data that can be backed up and audited with Git.
- CLI plus Streamlit dashboard.
- Rebalancing against user-defined target categories, not generated investment
  advice.
- No broker login, no hosted account, no tracking.

## Public Release Checklist

- Replace all bundled data with synthetic demo data.
- Check Git history before publishing. If real portfolio data was committed,
  publish from a clean repository or rewrite history before making it public.
- Keep `DISCLAIMER.md` linked from the README.
- Deploy `streamlit_app.py` for public demos. It sets `PORTFOLIO_READ_ONLY=1`
  and hides mutation forms.
- Keep personal broker exports out of the repo. Use `.gitignore` or a private
  data directory for real local use.
- Choose a unique package name before publishing to PyPI. The current import
  package and CLI can stay `portfolio`, but the distribution name should not be
  the generic `portfolio`.
- Add a simple CI workflow before inviting contributions.

## Demo Deployment

For Streamlit Community Cloud, deploy:

- Repository: this public repo.
- Branch: `main` or the release branch.
- Entrypoint: `streamlit_app.py`.
- Python: 3.12 or a supported newer version that has passed tests.

The demo should remain read-only. Public users should clone/fork the project and
run the full app locally for their own data.

## Revenue Paths

Start with revenue around convenience and support rather than hosted custody of
personal financial data:

- GitHub Sponsors for one-time and monthly support.
- Paid setup calls for importing a user's broker export and configuring targets.
- Paid broker import packs for Trade Republic, Scalable Capital, Interactive
  Brokers, and other common EU brokers.
- Paid report templates, tax/income presets, and portfolio review workbooks.
- A hosted SaaS only after validation, and only with proper auth, per-user
  storage, privacy policy, licensed data, and regulatory review.

## Risk Boundaries

- Do not present generated target weights or specific instruments as suitable
  personal recommendations unless you have reviewed the regulatory requirements.
- Keep the default product language focused on tracking, visualization, and
  arithmetic from user-defined targets.
- `yfinance`/Yahoo data is useful for local personal tooling, but commercial
  use should be reviewed against provider terms and replaced with licensed data
  if needed.
