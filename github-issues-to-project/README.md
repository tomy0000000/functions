# Github Issues to Project

Scans a list of GitHub repos for unassigned open issues, assigns them to you, and adds them to a GitHub Projects v2 board — all in parallel.

## Requirements

- Python 3.13+
- A GitHub Personal access tokens (classic) with scopes: `repo`, `project`.

## Setup

```bash
uv sync
```

Set your GitHub token in the environment or in a `.env` file:

```bash
echo "GITHUB_TOKEN=ghp_..." > .env
```

## Usage

```bash
uv run main.py --config config.toml
```

All flags can be provided via a TOML config file (passed with `--config`) or directly on the command line.

### Options

| Flag         | Short | Description                                                   |
| ------------ | ----- | ------------------------------------------------------------- |
| `--repo`     | `-r`  | Repo in `owner/repo` format. Repeatable.                      |
| `--project`  | `-p`  | Projects v2 number (from the project URL).                    |
| `--env-file` |       | Path to a `.env` file containing `GITHUB_TOKEN`.              |
| `--org`      |       | Org login if the project is org-owned rather than user-owned. |
| `--dry-run`  |       | Print actions without making any changes.                     |
| `--config`   |       | Path to a TOML config file.                                   |

### Config file

```toml
# config.toml
project = 9
env_file = ".env"

repos = [
    "owner/repo-a",
    "owner/repo-b",
]
```

### CLI example

```bash
# Single repo, explicit flags
uv run main.py --repo owner/repo --project 9 --env-file .env

# Dry run
uv run main.py --config config.toml --dry-run

# Org-owned project
uv run main.py --config config.toml --org my-org
```
