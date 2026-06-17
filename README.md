# Secondary → Main: Challenge Assignment Agent

An automated agent that assigns personalised challenges to SECONDARY bank customers to drive their conversion to MAIN status.

## What the agent does

**MAIN customer** = incoming credit ≥ 15,000 CZK + at least 3 transactions in a calendar month.

Each month the agent processes all SECONDARY customers and assigns each one up to 3 personalised challenges ranked by priority:

| Code | Challenge |
|---|---|
| C1 | Receive 15,000 CZK into the account |
| C2 | Pay 10 times with the bank's card in a month |
| C3 | Set up a standing order for energy or telecom bills |
| C4 | Set up a recurring payment for an online subscription (Netflix, Spotify…) |
| C5 | Transfer 10,000 CZK into investments |

Challenges are selected based on behavioural data (income, transactions, balance, card activity) and demographic data (age, gender, city, tenure). C1 is always included when the customer does not meet the income threshold — it is the primary condition for MAIN status.

## Data sources

| File | Content |
|---|---|
| `VSE_Data_6M.xlsx` | 6-month product and transaction data (~10,000 customers) |
| `VSE_Data_LABELY.xlsx` | Behavioural labels (salary estimate, utility payments, subscriber flag) |
| `VSE_Data_DEMO.xlsx` | Demographic data (age, gender, city, citizenship) |

Place files in the `data/` folder. Source data is not included in the repository.

## Installation

**Step 1 — clone the repository**

```bash
git clone https://github.com/husd03/Data-project-team-A.git
cd Data-project-team-A
```

**Step 2 — install dependencies**

On Windows, double-click `instalation.bat` — it installs everything automatically.

Alternatively from the command line:

```bash
python -m pip install -r requirements.txt
```

**Step 3 — add source data**

Copy the three source Excel files into the `data/` folder:

```
data/VSE_Data_6M.xlsx
data/VSE_Data_LABELY.xlsx
data/VSE_Data_DEMO.xlsx
```

## Running the agent

### Double-click (Windows)

Copy `spustit_agenta.bat` into the project folder and double-click it.

### Command line

```bash
python agent/run_agent.py
```

### Custom parameters

```bash
python agent/run_agent.py \
    --data-6m     data/VSE_Data_6M.xlsx \
    --data-labels data/VSE_Data_LABELY.xlsx \
    --data-demo   data/VSE_Data_DEMO.xlsx \
    --output-dir  agent/output \
    --run-date    2026-06-01 \
    --config      config/config.yaml
```

`--config` lets you point at an alternative configuration file — useful for
testing threshold changes side-by-side without overwriting the live config
(e.g. `--config config/config_test.yaml`).

### Scheduled monthly execution (Linux/Mac)

```
0 6 1 * * cd /opt/Data-project-team-A && python agent/run_agent.py >> logs/agent.log 2>&1
```

## Output files

The agent generates three files named by run date (e.g. `odmeny_20260601`):

| File | Description |
|---|---|
| `odmeny_YYYYMMDD.xlsx` | Excel for relationship managers — 3 sheets (all customers, HIGH priority, summary) |
| `odmeny_YYYYMMDD.csv` | CRM import / data warehouse |
| `summary_YYYYMMDD.json` | Statistics for system logs and monitoring |

### Output columns

| Column | Description |
|---|---|
| `ID zákazníka` | Customer identifier |
| `Priorita` | HIGH / MEDIUM / LOW based on conversion score |
| `Skóre konverze` | 0–100, higher = greater chance of becoming MAIN |
| `Byl MAIN` | Customer previously held MAIN status |
| `Výzva 1 (kód)` | Code of the top challenge (C1–C5) |
| `Výzva 1` | Challenge name |
| `Výzva 1 — důvod` | Why this challenge was chosen for this customer |
| `Výzva 2`, `Výzva 3` | Second and third challenges (if applicable) |
| `Příjem splněn (podíl)` | Share of months with income ≥ 15,000 CZK (e.g. 0.67 = 4 of 6) |
| `Transakce splněny (podíl)` | Share of months with ≥ 3 transactions |
| `Avg příjem (Kč)` | Average incoming credit, last 3 months |
| `Avg transakce` | Average transaction count, last 3 months |

## Configuration

All thresholds, scoring weights, normalizers, and challenge names are
externalized in **[config/config.yaml](config/config.yaml)** — no values are
hardcoded in Python. This means a non-developer can tune the agent's
behaviour by editing one YAML file.

```
config/config.yaml
├── main_status        # MAIN definition: income threshold, transaction
│                       # threshold, how many months to average over
├── agent               # max_challenges per customer
├── conversion_score    # weights, normalizers, HIGH/MEDIUM/LOW boundaries
└── challenges          # C1-C5: display names, point values, thresholds
```

The engine computes a relevance score for each challenge (C1-C5) and assigns
the top three (configurable via `agent.max_challenges`). Summary of the
default scoring logic — exact numbers live in `config.yaml`:

```
C1 — Receive 15,000 CZK
     base points (if not met) + proximity bonus (closer to threshold = more points)
     bonus if previously MAIN, bonus if transactions already meet the threshold

C2 — 10 card payments
     points if average usage below target, extra points if close to target

C3 — Energy / telecom standing order
     points if no utility payment through the bank, plus bonuses for
     balance and age (likely pays household bills)

C4 — Subscription payment
     points if no subscription set up, plus bonuses for younger age and
     active card usage

C5 — Investments
     points if no investment product, plus bonuses for high salary,
     high balance, term deposits, and younger age
```

C1 is always included when the customer does not meet the income threshold,
regardless of its score relative to other challenges — this is a structural
rule in `agent/reward_engine.py`, not a config value.

If `config.yaml` is missing, malformed, or missing required keys, the agent
prints a clear Czech error message explaining what's wrong and how to fix it
(including `git checkout config/config.yaml` to restore the last working
version).

## Results on current data

| Metric | Value |
|---|---|
| SECONDARY customers scored | 2,785 |
| HIGH priority (score ≥ 55) | 720 |
| MEDIUM priority (score 25–54) | 941 |
| LOW priority (score < 25) | 1,124 |
| Customers who previously held MAIN | 864 |

Challenge distribution (a customer can receive multiple):

| Challenge | Customers |
|---|---|
| C1 — Receive 15,000 CZK | 2,251 |
| C3 — Energy / telecom | 2,065 |
| C2 — 10 card payments | 1,685 |
| C5 — Investments | 1,297 |
| C4 — Subscription | 857 |

## Key findings from the analysis

- **94% of MAIN-to-SECONDARY drops** are caused by a single factor — incoming credit falling below 15,000 CZK
- Age 50 is a clear behavioural breakpoint: younger customers are more active with cards, older customers hold higher balances
- Female SECONDARY customers hold 3× higher average balances than male customers (24,137 CZK vs 7,907 CZK)
- 864 customers previously held MAIN status and lost it — the easiest targets for re-conversion
- Prague and Brno customers hold higher balances than other regions

## Testing

The scoring logic, configuration loader, and pre-flight checks are covered
by 45 unit tests using synthetic data — no bank data files are required to
run them.

### Double-click (Windows)

Run `spustit_testy.bat`.

### Command line

```bash
python -m pytest tests/ -v
```

`test_reward_engine.py` (26 tests) checks: which challenges get assigned for
different customer profiles, the C1 override rule, conversion score
boundaries, priority tier thresholds, and the overall output shape. These
tests load the real `config/config.yaml`, so they also catch accidental
breaking changes to the config file.

`test_config_loader.py` (12 tests) checks that `config.yaml` loads
correctly, and that missing files, invalid YAML, missing sections, or
missing keys produce clear error messages rather than cryptic Python
tracebacks.

`test_checks.py` (7 tests) checks the pre-flight error messages for missing
dependencies and missing/corrupted data files.

Run all of these after any change to `reward_engine.py`, `config.yaml`, or
`checks.py` to catch regressions.

## Friendly error messages

Before doing any real work, the agent runs three pre-flight checks
(`agent/checks.py`) and prints a plain-language Czech message — not a Python
traceback — if something is wrong:

| Problem | What you'll see |
|---|---|
| `instalation.bat` was never run | "Chybí potřebné Python knihovny" + which packages, and tells you to run `instalation.bat` |
| Data files not copied into `data/` | "Chybí zdrojová data" + lists exactly which of the 3 files are missing and where they should go |
| Data file is empty, corrupted, or open in Excel | "Soubor s daty se nepodařilo otevřít" + which file and the underlying error |

This means a non-technical user who forgets a setup step gets a message
telling them exactly what to do, instead of a `FileNotFoundError` traceback.

## Customizing the scoring rules with AI

The scoring logic is written as simple, readable `if`/`+=` rules so that
anyone can ask an AI assistant (Claude, ChatGPT, GitHub Copilot, etc.) to
adjust thresholds, weights, or add new challenges — without needing to
understand the full codebase.

See **[VIBECODING.md](VIBECODING.md)** for ready-to-use prompts, e.g.
"increase the weight of high balance in the investment challenge" or
"add a new challenge for opening a savings account."

## Project structure

```
Data-project-team-A/
├── data/                        # source data (not in repository)
├── config/
│   └── config.yaml               # ALL thresholds, weights, and challenge
│                                  # names — edit this to change behaviour
├── agent/
│   ├── run_agent.py              # main entry point — run this monthly
│   ├── reward_engine.py          # challenge assignment LOGIC (reads config.yaml)
│   ├── config_loader.py          # loads + validates config.yaml
│   ├── data_loader.py            # data loading and merging
│   ├── report_generator.py       # Excel / CSV / JSON report generation
│   └── checks.py                 # pre-flight checks with friendly error messages
├── src/
│   ├── features.py              # feature engineering for ML model
│   ├── train.py                 # XGBoost training (future use)
│   └── predict.py               # ML inference (future use)
├── notebooks/
│   └── model_walkthrough.ipynb  # exploratory analysis
├── agent/output/                # generated reports (not in repository)
├── logs/                        # agent logs (not in repository)
├── tests/
│   ├── test_reward_engine.py    # unit tests for challenge scoring (26 tests)
│   ├── test_config_loader.py    # unit tests for config loading/validation (12 tests)
│   └── test_checks.py           # unit tests for pre-flight checks (7 tests)
├── instalation.bat              # Windows one-click dependency installer
├── spustit_agenta.bat            # Windows one-click agent launcher
├── spustit_testy.bat             # Windows one-click test runner
├── requirements.txt
├── VIBECODING.md                 # guide for customizing rules with AI
└── README.md
```

## Future improvements

- [ ] A/B test — measure which challenges actually drive conversion and retrain the model on real outcomes
- [ ] REST API — FastAPI wrapper for real-time scoring from the bank's core systems
- [ ] Churn model — predict which MAIN customers are at risk of falling back to SECONDARY
- [ ] Monitoring — track monthly drift in segments and challenge effectiveness
