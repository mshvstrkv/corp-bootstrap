from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class MergeResult:
    ok: bool
    conflicts: list[str]
    message: str = ""


@dataclass(frozen=True)
class GitClient:
    logger: logging.Logger

    def _run(self, args: list[str], cwd: Path | None = None) -> str:
        command = ["git", *args]
        display_command = " ".join(redact_command(command))
        self.logger.debug("Running command: %s", display_command)
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise GitError(f"Unable to run git: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise GitError(f"Git command failed: {display_command}\n{redact_text(detail)}")
        return completed.stdout.strip()

    def clone(self, url: str, destination: Path) -> None:
        if destination.exists():
            if any(destination.iterdir()):
                raise GitError(f"Clone destination is not empty: {destination}")
            shutil.rmtree(destination)
        self._run(["clone", url, str(destination)])

    def fetch(self, repo: Path, remote: str = "origin") -> None:
        self._run(["fetch", "--prune", remote], cwd=repo)

    def is_git_repository(self, repo: Path) -> bool:
        try:
            output = self._run(["rev-parse", "--is-inside-work-tree"], cwd=repo)
        except GitError:
            return False
        return output == "true"

    def remote_head_branches(self, repo: Path, remote: str = "origin") -> list[str]:
        heads = self.remote_heads(repo, remote)
        branches = sorted(heads)
        if not branches:
            raise GitError("No remote branches were found in GitVerse repository")
        return branches

    def remote_heads(self, repo: Path, remote: str) -> dict[str, str]:
        output = self._run(["ls-remote", "--heads", remote], cwd=repo)
        heads: dict[str, str] = {}
        for raw in output.splitlines():
            parts = raw.strip().split()
            if len(parts) != 2:
                continue
            commit, ref = parts
            if ref.startswith("refs/heads/"):
                heads[ref.removeprefix("refs/heads/")] = commit
        return heads

    def remote_branches(self, repo: Path) -> list[str]:
        output = self._run(["branch", "-r"], cwd=repo)
        branches: list[str] = []
        for raw in output.splitlines():
            branch = raw.strip()
            if "->" in branch:
                continue
            if branch.startswith("origin/"):
                branches.append(branch.removeprefix("origin/"))
        unique = sorted(set(branches))
        if not unique:
            raise GitError("No remote branches were found in GitVerse repository")
        return unique

    def checkout(self, repo: Path, branch: str) -> None:
        self._run(["check-ref-format", "--branch", branch], cwd=repo)
        self._run(["checkout", "-B", branch, f"refs/remotes/origin/{branch}"], cwd=repo)

    def checkout_existing(self, repo: Path, branch: str) -> None:
        self._run(["check-ref-format", "--branch", branch], cwd=repo)
        self._run(["rev-parse", "--verify", f"refs/heads/{branch}"], cwd=repo)
        self._run(["checkout", branch], cwd=repo)

    def checkout_target_branch(self, repo: Path, branch: str, remote: str = "bitbucket") -> None:
        self._run(["check-ref-format", "--branch", branch], cwd=repo)
        remote_ref = f"refs/remotes/{remote}/{branch}"
        if self.local_branch_exists(repo, branch):
            self._run(["checkout", branch], cwd=repo)
            self._run(["rev-parse", "--verify", remote_ref], cwd=repo)
            self._run(["reset", "--hard", f"{remote}/{branch}"], cwd=repo)
            return
        self._run(["rev-parse", "--verify", remote_ref], cwd=repo)
        self._run(["checkout", "-b", branch, f"{remote}/{branch}"], cwd=repo)

    def local_branch_exists(self, repo: Path, branch: str) -> bool:
        try:
            self._run(["check-ref-format", "--branch", branch], cwd=repo)
            self._run(["rev-parse", "--verify", f"refs/heads/{branch}"], cwd=repo)
        except GitError:
            return False
        return True

    def remote_tracking_branch_exists(self, repo: Path, remote: str, branch: str) -> bool:
        try:
            self._run(["check-ref-format", "--branch", branch], cwd=repo)
            self._run(["rev-parse", "--verify", f"refs/remotes/{remote}/{branch}"], cwd=repo)
        except GitError:
            return False
        return True

    def local_branches(self, repo: Path) -> list[str]:
        output = self._run(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=repo)
        return sorted(line.strip() for line in output.splitlines() if line.strip())

    def remote_tracking_branches(self, repo: Path, remote: str) -> list[str]:
        output = self._run(["for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}"], cwd=repo)
        prefix = f"{remote}/"
        branches: list[str] = []
        for raw in output.splitlines():
            ref = raw.strip()
            if not ref.startswith(prefix) or "->" in ref:
                continue
            branches.append(ref.removeprefix(prefix))
        return sorted(set(branches))

    def commits_ahead(self, repo: Path, source_ref: str, target_ref: str) -> int:
        output = self._run(["rev-list", "--count", f"{target_ref}..{source_ref}"], cwd=repo)
        return int(output or "0")

    def merge(self, repo: Path, source_ref: str, message: str) -> MergeResult:
        command = ["git", "merge", source_ref, "-m", message]
        display_command = " ".join(redact_command(command))
        self.logger.debug("Running command: %s", display_command)
        try:
            completed = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
        except OSError as exc:
            raise GitError(f"Unable to run git: {exc}") from exc
        if completed.returncode == 0:
            return MergeResult(ok=True, conflicts=[])
        conflicts = self.conflicted_files(repo)
        if conflicts:
            detail = completed.stderr.strip() or completed.stdout.strip()
            return MergeResult(ok=False, conflicts=conflicts, message=redact_text(detail))
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise GitError(f"Git command failed: {display_command}\n{redact_text(detail)}")

    def conflicted_files(self, repo: Path) -> list[str]:
        output = self._run(["diff", "--name-only", "--diff-filter=U"], cwd=repo)
        return [line.strip() for line in output.splitlines() if line.strip()]

    def added_root_src_files(self, repo: Path) -> list[str]:
        output = self._run(["status", "--porcelain"], cwd=repo)
        files: list[str] = []
        for line in output.splitlines():
            if len(line) < 4:
                continue
            status = line[:2]
            path = line[3:].strip()
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1]
            if "A" not in status and status != "??":
                continue
            if path.startswith("src/"):
                files.append(path)
        return files

    def verify_local_branch(self, repo: Path, branch: str) -> None:
        self._run(["check-ref-format", "--branch", branch], cwd=repo)
        self._run(["rev-parse", "--verify", f"refs/heads/{branch}"], cwd=repo)

    def add_or_set_remote(self, repo: Path, name: str, url: str) -> None:
        remotes = self._run(["remote"], cwd=repo).splitlines()
        if name in remotes:
            self._run(["remote", "set-url", name, url], cwd=repo)
        else:
            self._run(["remote", "add", name, url], cwd=repo)

    def push_branch(self, repo: Path, remote: str, local_branch: str, remote_branch: str | None = None) -> None:
        destination = remote_branch or local_branch
        self._run(["check-ref-format", "--branch", local_branch], cwd=repo)
        self._run(["check-ref-format", "--branch", destination], cwd=repo)
        self._run(["push", remote, f"refs/heads/{local_branch}:refs/heads/{destination}"], cwd=repo)

    def push_current_branch(self, repo: Path, remote: str, branch: str) -> None:
        self._run(["check-ref-format", "--branch", branch], cwd=repo)
        self._run(["push", remote, f"refs/heads/{branch}:refs/heads/{branch}"], cwd=repo)

    def push_remote_branch(self, repo: Path, remote: str, source_remote: str, branch: str) -> None:
        self._run(["check-ref-format", "--branch", branch], cwd=repo)
        self._run(["push", remote, f"refs/remotes/{source_remote}/{branch}:refs/heads/{branch}"], cwd=repo)

    def delete_remote_branch(self, repo: Path, remote: str, branch: str) -> None:
        self._run(["push", remote, "--delete", branch], cwd=repo)

    def create_branch(self, repo: Path, branch: str) -> None:
        self._run(["check-ref-format", "--branch", branch], cwd=repo)
        self._run(["checkout", "-B", branch], cwd=repo)

    def delete_local_branch(self, repo: Path, branch: str, fallback_branch: str | None = None) -> None:
        current = self._run(["branch", "--show-current"], cwd=repo)
        if current == branch:
            if not fallback_branch:
                raise GitError(f"Cannot delete current branch {branch} without a fallback branch")
            self._run(["checkout", fallback_branch], cwd=repo)
        self._run(["branch", "-D", branch], cwd=repo)

    def restore_worktree(self, repo: Path) -> None:
        self._run(["reset", "--hard", "HEAD"], cwd=repo)
        self._run(["clean", "-fd"], cwd=repo)

    def has_changes(self, repo: Path) -> bool:
        return bool(self._run(["status", "--porcelain"], cwd=repo))

    def changed_files(self, repo: Path) -> list[str]:
        output = self._run(["status", "--porcelain"], cwd=repo)
        files: list[str] = []
        for line in output.splitlines():
            if not line:
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1]
            files.append(path)
        return files

    def current_branch(self, repo: Path) -> str:
        branch = self._run(["branch", "--show-current"], cwd=repo)
        if not branch:
            raise GitError("Unable to determine current branch")
        return branch

    def remotes(self, repo: Path) -> list[str]:
        output = self._run(["remote"], cwd=repo)
        return [line.strip() for line in output.splitlines() if line.strip()]

    def commit(self, repo: Path, message: str) -> bool:
        if not self.has_changes(repo):
            return False
        self._run(["add", "-A"], cwd=repo)
        self._run(["commit", "-m", message], cwd=repo)
        return True


def redact_command(command: list[str]) -> list[str]:
    return [redact_text(part) for part in command]


def redact_text(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.scheme and parsed.netloc and "@" in parsed.netloc:
        host = parsed.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parsed.scheme, f"***@{host}", parsed.path, parsed.query, parsed.fragment))
    return value
