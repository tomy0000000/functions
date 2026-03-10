"""
GitHub Issues to Project

Finds unassigned open issues across specified repos, assigns them to the
authenticated user, and adds them to a GitHub Projects v2 board.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated, Optional

import requests
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markup import escape
from typer_config.decorators import use_toml_config

app = typer.Typer()
console = Console()
err_console = Console(stderr=True)

REST_BASE = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"


# ── Auth / Session ──────────────────────────────────────────────────────────


def load_token(env_file: Optional[Path]) -> str:
    if env_file:
        load_dotenv(env_file, override=True)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        err_console.print(
            "[bold red]Error:[/] GITHUB_TOKEN not found. Set it in the environment or use --env-file."
        )
        raise typer.Exit(code=1)
    return token


def make_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


# ── GitHub GraphQL ───────────────────────────────────────────────────────────


def graphql(session: requests.Session, query: str, variables: dict) -> dict:
    resp = session.post(GRAPHQL_URL, json={"query": query, "variables": variables})
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data


# ── GitHub REST helpers ──────────────────────────────────────────────────────


def get_authenticated_user(session: requests.Session) -> dict:
    resp = session.get(f"{REST_BASE}/user")
    resp.raise_for_status()
    return resp.json()


def get_unassigned_issues(
    session: requests.Session, owner: str, repo: str
) -> list[dict]:
    issues = []
    url = f"{REST_BASE}/repos/{owner}/{repo}/issues"
    params: dict = {"state": "open", "assignee": "none", "per_page": 100}

    while url:
        resp = session.get(url, params=params)
        if resp.status_code == 404:
            err_console.print(
                f"  [yellow]Warning:[/] {owner}/{repo} not found or no access — skipping."
            )
            return []
        resp.raise_for_status()
        page = [i for i in resp.json() if "pull_request" not in i]
        issues.extend(page)
        url = resp.links.get("next", {}).get("url")
        params = {}

    return issues


# ── GitHub Projects v2 ───────────────────────────────────────────────────────

_GET_PROJECT_QUERY = """
query GetProject($login: String!, $number: Int!) {
  user(login: $login) {
    projectV2(number: $number) { id title }
  }
}
"""

_GET_ORG_PROJECT_QUERY = """
query GetOrgProject($login: String!, $number: Int!) {
  organization(login: $login) {
    projectV2(number: $number) { id title }
  }
}
"""

_ASSIGN_AND_ADD_MUTATION = """
mutation AssignAndAdd($projectId: ID!, $issueId: ID!, $assigneeIds: [ID!]!) {
  updateIssue(input: {id: $issueId, assigneeIds: $assigneeIds}) {
    issue { number }
  }
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $issueId}) {
    item { id }
  }
}
"""


def get_project_node_id(session: requests.Session, login: str, project: int) -> str:
    data = graphql(session, _GET_PROJECT_QUERY, {"login": login, "number": project})
    project = data["data"]["user"]["projectV2"]
    if project:
        console.print(f'Found project: [bold green]"{project["title"]}"[/]')
        return project["id"]

    err_console.print(
        f"[bold red]Error:[/] Project [cyan]#{project}[/] not found under user [cyan]'{login}'[/]. "
        "If it belongs to an org, pass the org login via --org."
    )
    raise typer.Exit(code=1)


def get_org_project_node_id(session: requests.Session, org: str, project: int) -> str:
    data = graphql(session, _GET_ORG_PROJECT_QUERY, {"login": org, "number": project})
    project = data["data"]["organization"]["projectV2"]
    if project:
        console.print(f'Found project: [bold green]"{project["title"]}"[/]')
        return project["id"]

    err_console.print(
        f"[bold red]Error:[/] Project [cyan]#{project}[/] not found under org [cyan]'{org}'[/]."
    )
    raise typer.Exit(code=1)


def assign_and_add_to_project(
    session: requests.Session,
    project_id: str,
    issue_node_id: str,
    user_node_id: str,
    dry_run: bool,
) -> None:
    if dry_run:
        console.print(
            "    [bold yellow][[DRY RUN][/] Would assign and add issue to project"
        )
        return
    graphql(
        session,
        _ASSIGN_AND_ADD_MUTATION,
        {
            "projectId": project_id,
            "issueId": issue_node_id,
            "assigneeIds": [user_node_id],
        },
    )


def process_repo(
    token: str,
    repo_str: str,
    project_id: str,
    user_node_id: str,
    dry_run: bool,
) -> int:
    if "/" not in repo_str:
        err_console.print(
            f"  [yellow]Warning:[/] '{repo_str}' is not in owner/repo format — skipping."
        )
        return 0

    session = make_session(token)
    owner, repo_name = repo_str.split("/", 1)
    issues = get_unassigned_issues(session, owner, repo_name)

    console.print(
        f"[bold cyan]{escape(f'[{owner}/{repo_name}]')}[/] {len(issues)} unassigned open issue(s)"
    )
    count = 0
    for issue in issues:
        console.print(f"  [dim]->[/] [yellow]#{issue['number']}[/]: {issue['title']}")
        assign_and_add_to_project(
            session, project_id, issue["node_id"], user_node_id, dry_run
        )
        count += 1

    return count


# ── CLI ──────────────────────────────────────────────────────────────────────


@app.command()
@use_toml_config()
def main(
    repos: Annotated[
        list[str],
        typer.Option("--repo", "-r", help="Repo in owner/repo format. Repeatable."),
    ],
    project: Annotated[
        int,
        typer.Option(
            "--project", "-p", help="Projects v2 number (from the project URL)."
        ),
    ],
    env_file: Annotated[
        Optional[Path],
        typer.Option(
            "--env-file",
            help="Path to a .env file containing GITHUB_TOKEN.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    org: Annotated[
        Optional[str],
        typer.Option(
            "--org",
            help="Org login if the project is org-owned rather than user-owned.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print actions without making any changes."),
    ] = False,
) -> None:
    """Assign unassigned GitHub issues to yourself and add them to a project."""

    token = load_token(env_file)
    session = make_session(token)

    user = get_authenticated_user(session)
    login: str = user["login"]
    user_node_id: str = user["node_id"]
    console.print(f"Authenticated as: [bold green]{login}[/]")

    if org:
        project_id = get_org_project_node_id(session, org, project)
    else:
        project_id = get_project_node_id(session, login, project)

    total = 0
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                process_repo, token, repo_str, project_id, user_node_id, dry_run
            ): repo_str
            for repo_str in repos
        }
        for future in as_completed(futures):
            total += future.result()

    label = "[bold yellow][[DRY RUN][/] " if dry_run else ""
    console.print(f"\n{label}[bold green]Done.[/] Processed {total} issue(s).")


if __name__ == "__main__":
    app()
