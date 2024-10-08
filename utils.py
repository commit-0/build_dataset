import asyncio
import logging
import os
import shutil
import time
from glob import glob
from typing import Callable, Optional

import ast
import git
from ghapi.core import GhApi
from fastcore.net import HTTP404NotFoundError, HTTP403ForbiddenError

from scrape_pdf import scrape_spec

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Repo:
    def __init__(
        self,
        owner: str,
        name: str,
        organization: str,
        head: str,
        token: Optional[str] = None,
    ):
        """Init to retrieve target repository and create ghapi tool

        Args:
        ----
            owner (str): owner of target repository
            name (str): name of target repository
            org (str): under which organization to fork repos to
            head (str): which head to set the repo to
            setup (list[str]): a list of setup steps
            token (str): github token

        """
        self.name = name
        self.owner = organization
        self.token = token
        self.api = GhApi(token=token)
        self.repo = self.call_api(self.api.repos.get, owner=organization, repo=name)
        if self.repo is None:
            self.repo = self.call_api(
                self.api.repos.create_fork,
                owner=owner,
                repo=name,
                organization=organization,
            )
            # The API call returns immediately when the fork isn't complete. Needed to wait for a few seconds to finish.
            time.sleep(2)
        self.cwd = os.getcwd()
        if head.startswith("tags/"):
            self.commit = self.get_commit_by_tag(head)
        else:
            self.commit = head
        logger.info("Setting up a local copy of the repository.")
        self.clone_dir = os.path.abspath(os.path.join("tmp", self.name))
        self.local_repo = clone_repo(self.repo.clone_url, self.clone_dir, self.commit)

    def call_api(self, func: Callable, **kwargs) -> dict | None:
        """API call wrapper with rate limit handling (checks every 5 minutes if rate limit is reset)

        Args:
        ----
            func (callable): API function to call
            **kwargs: keyword arguments to pass to API function
        Return:
            values (dict): response object of `func`

        """
        while True:
            try:
                values = func(**kwargs)
                return values
            except HTTP403ForbiddenError:
                while True:
                    rl = self.api.rate_limit.get()
                    logger.info(
                        f"[{self.owner}/{self.name}] Rate limit exceeded for token {self.token[:10]}, "
                        f"waiting for 5 minutes, remaining calls: {rl.resources.core.remaining}"
                    )
                    if rl.resources.core.remaining > 0:
                        break
                    time.sleep(60 * 5)
            except HTTP404NotFoundError:
                logger.info(f"[{self.owner}/{self.name}] Resource not found {kwargs}")
                return None

    def get_commit_by_tag(self, tag: str) -> str:
        """Get commit sha for a tag

        Args:
        ----
            tag (str): to retrieve the commit of which tag
        Return:
            commit (str): sha of the commit

        """
        tag_ref = self.call_api(
            self.api.git.get_ref, owner=self.owner, repo=self.name, ref=tag
        )
        return tag_ref.object.sha


class RemoveMethod(ast.NodeTransformer):
    """Class to replace method code or remove function definitions based on method type"""

    def __init__(self, removal_method):
        self.removal_method = removal_method

    def visit_FunctionDef(self, node):
        transform = node

        # Don't modify Python's special functions (like __init__, __str__, etc.)
        if node.name.startswith('__') and node.name.endswith('__'):
            return node  # Leave special methods unchanged

        # Check if the first statement is a docstring
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            docstring_node = node.body[0]
        else:
            docstring_node = None

        # Create a pass node
        pass_node = ast.Pass()

        if self.removal_method == "all":
            # Replace body with pass, keeping docstring if present
            if docstring_node:
                node.body = [docstring_node, pass_node]
            else:
                node.body = [pass_node]
        elif self.removal_method == "docstring":
            # Only replace body with pass if there is a docstring, otherwise leave function unchanged
            if docstring_node:
                node.body = [docstring_node, pass_node]
        elif self.removal_method == "combined":
            # For combined: keep functions with docstrings, replace their body with pass,
            # remove functions without docstrings
            if docstring_node:
                node.body = [docstring_node, pass_node]
            else:
                # Return None to remove the function entirely
                return None
        else:
            raise NotImplementedError(
                f"Removal method {self.removal_method} is not implemented"
            )
        return ast.copy_location(transform, node)

    def visit_AsyncFunctionDef(self, node):
        # Handle async functions the same way as regular functions
        return self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        # Visit all the body of the class to apply transformations
        self.generic_visit(node)

        # Check if the class is left with only a `Pass` or is entirely empty
        if not node.body or all(isinstance(child, ast.Pass) for child in node.body):
            node.body = [ast.Pass()]  # Replace the body with a single `Pass` statement

        return node


def clone_repo(clone_url, clone_dir, commit) -> None:
    """Clone repo into a temporary directory

    Return:
    ------
        None

    """
    # cleanup if the repo already exists
    remove_local_repo(clone_dir)
    logger.info(f"cloning {clone_url} into {clone_dir}")
    try:
        repo = git.Repo.clone_from(clone_url, clone_dir)
    except git.exc.GitCommandError as e:
        raise RuntimeError(f"Failed to clone repository: {e}")
    logger.info(f"checking out {commit}")
    try:
        repo.git.checkout(commit)
    except git.exc.GitCommandError as e:
        raise RuntimeError(f"Failed to check out {commit}: {e}")
    return repo


def remove_local_repo(clone_dir) -> None:
    """Remove the cloned repository directory from the local filesystem."""
    if os.path.exists(clone_dir):
        try:
            shutil.rmtree(clone_dir)
        except OSError:
            os.system(f"rm -rf {clone_dir}")
        logger.info(f"Cleaned up the cloned repository at {clone_dir}")

def collect_test_files(directory):
    # List to store all the filenames
    test_files = []
    subdirs = []

    # Walk through the directory
    for root, dirs, files in os.walk(directory):
        if root.endswith("/"):
            root = root[:-1]
        # Check if 'test' is part of the folder name
        if 'test' in os.path.basename(root).lower() or os.path.basename(root) in subdirs:
            for file in files:
                # Process only Python files
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    test_files.append(file_path)
            for d in dirs:
                subdirs.append(d)

    return test_files


def collect_python_files(directory):
    # List to store all the .py filenames
    python_files = []

    # Walk through the directory recursively
    for root, _, files in os.walk(directory):
        for file in files:
            # Check if the file ends with '.py'
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                python_files.append(file_path)

    return python_files


def _find_files_to_edit(base_dir: str, src_dir: str, test_dir: str) -> list[str]:
    """Identify files to remove content by heuristics.
    We assume source code is under [lib]/[lib] or [lib]/src.
    We exclude test code. This function would not work
    if test code doesn't have its own directory.

    Args:
    ----
        base_dir (str): the path to local library.

    Return:
    ------
        files (list[str]): a list of files to be edited.

    """
    files = collect_python_files(os.path.join(base_dir, src_dir))
    test_files = collect_test_files(os.path.join(base_dir, test_dir))
    files = list(set(files) - set(test_files))

    # don't edit __init__ files
    files = [f for f in files if "__init__" not in f]
    # don't edit __main__ files
    files = [f for f in files if "__main__" not in f]
    # don't edit confest.py files
    files = [f for f in files if "conftest.py" not in f]
    return files


def generate_base_commit(
    repo: Repo,
    src_dir: str,
    test_dir: str,
    spec_url: str,
    base_branch_name: str = "commit0",
    removal: str = "all",
    spec_cache_dir: str = "pdfs",
) -> str:
    """Generate a base commit by removing all function contents

    Args:
    ----
        repo (Repo): from which repo to generate the base commit
        base_branch_name (str): base of the branch name of the base commit
        spec_cache_dir (str): where spec is cache to
    Return:
        collected_tests (list[str]): a list of test function names

    """
    # check if base commit has already been generated
    remote = repo.local_repo.remote()
    remote.fetch()
    exists = False
    branch_name = f"{base_branch_name}_{removal}"
    for ref in repo.local_repo.refs:
        if ref.name.endswith(f"/{branch_name}"):
            branch_name = ref.name
            exists = True
            break
    if exists:
        branch = repo.local_repo.refs[branch_name]
        if branch.commit.message == "Commit 0":
            logger.info("Commit 0 has already been created.")
            return branch.commit.hexsha
        else:
            raise ValueError(f"{branch_name} exists but it's not commit 0")
    else:
        logger.info("Creating commit 0")
        repo.local_repo.git.checkout("-b", branch_name)
        files = _find_files_to_edit(repo.clone_dir, src_dir, test_dir)
        for f in files:
            tree = ast.parse(open(f, "r").read())
            tree = RemoveMethod(removal).visit(tree)
            open(f, "w").write(ast.unparse(tree))
            try:
                repo.local_repo.git.add(f)
            except git.exc.GitCommandError as e:
                if "paths are ignored by one of your .gitignore files" in e.stderr:
                    logger.warning(
                        f"File {f} is ignored due to .gitignore rules and won't be added."
                    )
                elif "is in submodule" in e.stderr:
                    logger.warning(f"File {f} is in a submodule and won't be added.")
                else:
                    raise

        # check if function body has actually been removed
        diff = repo.local_repo.index.diff("HEAD", create_patch=True, staged=True)
        additions = 0
        deletions = 0
        for blob in diff:
            for line in blob.diff.decode("utf-8").splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
        if additions == 0 or deletions == 0:
            raise Exception(
                f"Removal is not working! 0 added lines or 0 deleted lines. Files found: {files}"
            )
        logger.info(f"Lines added: {additions}")
        logger.info(f"Lines removed: {deletions}")

        spec_path = os.path.join(spec_cache_dir, f"{repo.name}.pdf.bz2")
        if os.path.exists(spec_path):
            logger.info(f"Found spec PDF at {spec_path}")
        else:
            logger.info(f"Scraping spec PDF at {spec_url}")
            asyncio.get_event_loop().run_until_complete(
                scrape_spec(spec_url, "pdfs", repo.name)
            )
        # github does not allow file > 100 MB
        file_size = os.path.getsize(spec_path)
        if file_size >= 100 * 1_048_576:
            raise ValueError(f"{spec_path} is too large to be pushed to github")
        try:
            shutil.copy(spec_path, f"{repo.clone_dir}/spec.pdf.bz2")
        except IOError as e:
            raise IOError(f"Unable to copy file. {e}")
        except Exception as e:
            raise Exception(f"Unexpected error: {e}")
        repo.local_repo.git.add(f"{repo.clone_dir}/spec.pdf.bz2")

        base_commit = repo.local_repo.index.commit("Commit 0")
        origin = repo.local_repo.remote(name="origin")
        origin.push(branch_name)
        # go back to the starting commit
        repo.local_repo.git.checkout(repo.commit)
        return base_commit.hexsha
