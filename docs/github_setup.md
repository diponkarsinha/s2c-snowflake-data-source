# Setup: from zip to a running pipeline

About 45 minutes the first time. Commands are for macOS / Linux / Git Bash; Windows PowerShell differences are noted.

## 0. Prerequisites

- Git, Python 3.10-3.12, a GitHub account, a Snowflake account where you can use ACCOUNTADMIN (a trial is fine)
- Optional: GitHub CLI (`gh`) and `make`

## 1. Unzip and generate the data

```bash
unzip s2c-snowflake-data-source.zip && cd s2c-snowflake-data-source
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python generator/generate_data.py --clean   # rebuilds data/initial, pending/ (waves) and answer_key/
python generator/build_docs.py              # refreshes the data dictionary and drop plan
```

The generator is seeded, so the output is identical every time. It must run once on your machine because it also writes the Parquet files (needs `pyarrow`).

## 2. Snowflake: account setup (Snowsight, once)

1. Open Snowsight → **Projects → Worksheets → + SQL worksheet**, role **ACCOUNTADMIN**.
2. Paste and run `snowflake/01_account_setup.sql`.

## 3. Key pair for the GitHub service user

```bash
mkdir -p ~/.ssh/snowflake && cd ~/.ssh/snowflake
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
cat rsa_key.pub          # copy the text BETWEEN the BEGIN/END lines
cd -                     # back to the repo
```

In Snowsight (ACCOUNTADMIN):

```sql
ALTER USER S2C_INGEST_SVC SET RSA_PUBLIC_KEY = 'MIIBIjANBgkq...';   -- one line, no BEGIN/END
DESC USER S2C_INGEST_SVC;                                              -- RSA_PUBLIC_KEY_FP is now set
```

Never commit `rsa_key.p8`. `.gitignore` already blocks `*.p8`.

## 4. Snowflake: create all objects

Option A (Snowsight): run `snowflake/02_...sql` to `snowflake/11_...sql` in order, role **S2C_ADMIN**.

Option B (terminal):

```bash
cp .env.example .env          # fill in SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and one login method (your own user)
python scripts/run_sql.py --setup         # or: make setup
```

Check: `SHOW TASKS IN DATABASE S2C_DEV;` lists 4 suspended tasks; `SELECT COUNT(*) FROM S2C_DEV.AUDIT.DQ_RULES;` returns 27.

## 5. Create the GitHub repo

Web: **github.com → New repository** → name `s2c-snowflake-data-source`, Private or Public, **no** README / .gitignore / license (the repo already has them).

Or with the CLI:

```bash
gh repo create s2c-snowflake-data-source --private
```

## 6. Add the secrets

**Repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `SNOWFLAKE_ACCOUNT` | Account identifier, e.g. `abc12345.west-europe.azure` or `ORG-ACCOUNT` |
| `SNOWFLAKE_USER` | `S2C_INGEST_SVC` |
| `SNOWFLAKE_PRIVATE_KEY` | Full content of `rsa_key.p8`, including the BEGIN/END lines |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Leave unset (key has no passphrase) |

Or with the CLI:

```bash
gh secret set SNOWFLAKE_ACCOUNT --body "abc12345.west-europe.azure"
gh secret set SNOWFLAKE_USER --body "S2C_INGEST_SVC"
gh secret set SNOWFLAKE_PRIVATE_KEY < ~/.ssh/snowflake/rsa_key.p8
```

Optional variable (not secret): `SNOWFLAKE_DATABASE` = `S2C_DEV`.

## 7. First push: commit in steps (a readable history)

The workflow only runs when `data/` changes, so push the code first and the data last.

```bash
git init -b main
git remote add origin https://github.com/<your-user>/s2c-snowflake-data-source.git

git add .gitignore .env.example requirements.txt Makefile README.md
git commit -m "chore: project skeleton"

git add snowflake/
git commit -m "feat(snowflake): roles, stages, RAW tables, audit layer, stream, tasks"

git add scripts/ .github/
git commit -m "feat(ingest): uploader with pre-load checks and GitHub Action"

git add generator/ answer_key/ docs/
git commit -m "docs: architecture, catalog, dictionary, DQ rules, drop plan"

git push -u origin main

git add data/
git commit -m "data: initial load (Jan-Oct 2026)"
git push
```

Open the **Actions** tab: "Ingest to Snowflake" uploads the initial files (about 1 minute).

## 8. Load and check

```sql
-- Snowsight, role S2C_ADMIN
-- run snowflake/ops/run_now.sql      (loads now)
-- run snowflake/ops/resume_tasks.sql (keeps loading every 10 minutes)
-- run snowflake/ops/check_status.sql (see everything)
```

You should see 14 files in `V_FILE_LINEAGE` with `LOAD_STATUS = Loaded`, and the gate `PASS`.

## 9. Drop the waves

```bash
python scripts/drop_wave.py --list
python scripts/drop_wave.py 1 --push      # or: make wave N=1
```

Wait for the Action (and up to 10 minutes for the batch task, about 1 minute for stream files), then run `check_status.sql` and read `pending/wave_01/WAVE.md` for what should have happened. After all 12:

```bash
python scripts/check_planted.py     # every planted audit / stream issue should be "caught"
```

When you stop for the day: `snowflake/ops/suspend_tasks.sql`.

## Branching and pull requests (once the basics run)

- `main` is protected: **Settings → Branches → Add rule → Require a pull request before merging**
- Work on `feature/<name>`, open a PR, merge with "Squash and merge"
- Data drops go straight to `main` (they simulate a source system, not a code change)
- Commit messages: `feat:`, `fix:`, `docs:`, `data:`, `chore:` (Conventional Commits)
