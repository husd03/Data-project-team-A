# Customizing the agent (vibecoding)

Most adjustments to this agent are now just **editing numbers in a YAML
file** — no Python knowledge needed at all. For structural changes (adding
a new challenge, changing how a condition is evaluated), this guide also
includes prompts for an AI assistant (Claude, ChatGPT, GitHub Copilot, etc.).

---

## Quick start — most common changes need NO code or AI

Open **[config/config.yaml](config/config.yaml)**. Every threshold, scoring
weight, normalizer, and challenge name lives there. Edit the number, save,
then:

```bash
python -m pytest tests/ -v      # or double-click spustit_testy.bat
python agent/run_agent.py        # or double-click spustit_agenta.bat
```

If the tests pass and the new challenge distribution in
`agent/output/odmeny_*.xlsx` (Souhrn sheet) still looks reasonable, you're done.

---

## Config changes you can make directly (no AI needed)

### Change the MAIN income threshold

```yaml
main_status:
  income_threshold_czk: 15000   # change to 20000, etc.
```

### Change the MAIN transaction threshold

```yaml
main_status:
  transaction_threshold: 3      # change to 5, etc.
```

### Change how many months are used for rolling averages

```yaml
main_status:
  history_months: 3             # change to 6 to use all available months
```

### Change how many challenges each customer gets

```yaml
agent:
  max_challenges: 3              # change to 2, etc.
```

### Adjust the weight of any scoring signal

Every challenge has a `points` section. For example, to make "high balance"
worth more for the investment challenge (C5):

```yaml
challenges:
  C5:
    points:
      high_balance_bonus: 25    # change to 40
```

### Rename a challenge

```yaml
challenges:
  C5:
    name: "Vložit 10 000 Kč do investic"   # edit this text freely
```

### Change priority tier boundaries

```yaml
conversion_score:
  priority_tiers:
    high_min: 55      # conversion_score >= 55 -> HIGH
    medium_min: 25    # 25-54 -> MEDIUM, below 25 -> LOW
```

### Translate challenge names and reasons to another language

The `name` fields in `config/config.yaml` can be edited directly. The
"reason" text templates (e.g. `"příjem {avg_cr:,.0f} Kč/měs."`) are in
`agent/reward_engine.py` — for these, use the AI prompts below.

---

## Testing a config change before committing to it

Copy `config/config.yaml` to `config/config_test.yaml`, edit the copy, and
run the agent with `--config`:

```bash
cp config/config.yaml config/config_test.yaml
# edit config_test.yaml
python agent/run_agent.py --config config/config_test.yaml --output-dir agent/output_test
```

Compare `agent/output_test/odmeny_*.xlsx` against your normal output before
replacing `config/config.yaml`.

---

## Changes that need an AI assistant

These involve changing the LOGIC in `agent/reward_engine.py`, not just
numbers. Open `agent/reward_engine.py` and `config/config.yaml`, paste both
into Claude or ChatGPT, then use one of these prompts.

### Add a brand new challenge (C6)

> "Add a new challenge C6: 'Open a savings account'. It should score
> high for customers who have no savings account (BALANCE_SA_ASSET = 0
> across all months) and a balance above 20,000 CZK.
>
> 1. Add a C6 section to config/config.yaml with a 'name' and 'points'/
>    'thresholds' similar to the C5 section.
> 2. Add the scoring logic for C6 to _score_one() in reward_engine.py,
>    following the same pattern as the C5 block.
> 3. Update REQUIRED_CHALLENGES in agent/config_loader.py to include 'C6'.
> 4. Update the docstring at the top of reward_engine.py."

### Remove a challenge

> "Remove challenge C4 (subscription payment) entirely:
> 1. Remove the C4 section from config/config.yaml
> 2. Remove the C4 scoring block from _score_one() in reward_engine.py
> 3. Remove 'C4' from REQUIRED_CHALLENGES in agent/config_loader.py
> 4. Update the docstring at the top of reward_engine.py
> 5. Update tests/test_reward_engine.py and tests/test_config_loader.py
>    to remove references to C4."

### Change which customers count as 'previously MAIN'

> "Currently `was_main` in reward_engine.py checks if PACTSEG_CODE was
> 'MAIN' in ANY of the available months. Change it to only count as
> 'previously MAIN' if the customer was MAIN in at least 2 of the last
> 3 months. Keep this as a constant in config.yaml under main_status
> (e.g. 'was_main_lookback_months' and 'was_main_min_occurrences') so
> it stays configurable."

### Translate reason text templates

> "All the f-string reason templates in _score_one() in reward_engine.py
> are in Czech (e.g. 'příjem {avg_cr:,.0f} Kč/měs., chybí {gap_cr:,.0f} Kč').
> Translate them to [your language], keeping the {variable} placeholders
> and all variable/dict-key names unchanged."

### Add a new data source / column

> "I want to add a new signal from [describe your data]. Here's a sample
> of the column: [paste a few rows]. Add a new average/flag feature in
> score_customers() following the pattern of avg_cr/has_inv, and use it
> in one of the challenge scoring blocks in _score_one()."

---

## After any change

Always run the test suite:

```bash
python -m pytest tests/ -v
```

`tests/test_config_loader.py` will catch a malformed `config.yaml`
(missing keys, bad YAML syntax) with a clear error message before you
even run the agent. If a test fails, paste the error message back to the
AI along with the changed file and ask it to fix the failing test — either
by adjusting the code/config or explaining if the test itself needs
updating because the rule intentionally changed.

If `config.yaml` ever gets into a broken state, restore the last working
version from Git:

```bash
git checkout config/config.yaml
```

---

## What NOT to change without care

- **`agent/data_loader.py`** — column name detection. Only change this if
  your source Excel files have different column names than
  `VSE_Data_6M.xlsx`.
- **`agent/report_generator.py`** — output formatting. Safe to ask for new
  columns, but be careful with Excel styling code (colors, widths).
- **File names and paths** — `run_agent.py` expects specific file names in
  `data/`. If you rename source files, update the `--data-*` defaults too.
- **`agent/config_loader.py` `REQUIRED_*` lists** — these define what
  `config.yaml` MUST contain. Keep them in sync if you add/remove
  challenges or sections.
