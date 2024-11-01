#!/usr/bin/env python3

import argparse
import logging
import os
from typing import Optional

from datasets import Dataset, DatasetDict, load_dataset

from swebench.harness.constants import (
    MAP_REPO_VERSION_TO_SPECS,
    MAP_REPO_TO_REQS_PATHS,
)

from swebench.harness.utils import (
    get_requirements_by_commit,
)

from swebench.harness.test_spec import (
    replace_uninstallable_packages_requirements_txt,
)

from utils import Repo

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_instance(
    example: dict, organization: str
) -> dict:
    """Convert a SWE-bench instance to the commit0 form."""
    setup = dict()
    raw_info = MAP_REPO_VERSION_TO_SPECS[example["repo"]][example["version"]]
    setup["python"] = raw_info["python"]
    setup["install"] = raw_info["install"]
    setup["specification"] = ""
    if "pre_install" in raw_info:
        setup["pre_install"] = raw_info["pre_install"]
        setup["pre_install"] = []
        for one in raw_info["pre_install"]:
            if 'apt' in one:
                setup["pre_install"].append(one)
            else:
                setup["install"] = f"{one}; {setup['install']}"
    if "packages" in raw_info:
        if raw_info["packages"] == "requirements.txt":
            packages = replace_uninstallable_packages_requirements_txt(
                get_requirements_by_commit(example["repo"], example["environment_setup_commit"])
                )
            setup["packages"] = [one.split('#')[0].strip().split(';')[0].strip() for one in packages.split('\n') if one.strip() != '']
            setup["packages"] = [f"\"{one}\"" for one in setup["packages"] if 'win32' not in one]
            setup["packages"] = ' '.join(setup["packages"])
        elif raw_info["packages"] == "environment.yml":
            pass
        else:
            setup["packages"] = raw_info["packages"]
    if "pip_packages" in raw_info:
        setup["pip_packages"] = raw_info["pip_packages"]
    owner, repo = example["repo"].split("/")
    if repo == "matplotlib":
        test_cmd = "pytest"
        test_dir = "lib/matplotlib/tests"
        src_dir = "lib/matplotlib"
        if not "pre_install" in setup:
            setup["pre_install"] = []
        setup["pre_install"] += ["apt-get update", "apt-get install clang"]
    elif repo == "pylint":
        test_cmd = "pytest"
        test_dir = "tests/"
        src_dir = "pylint/"
    elif repo == "sympy":
        test_cmd = "pytest"
        test_dir = "sympy/"
        src_dir = "sympy/"
    elif repo == "seaborn":
        test_cmd = "pytest -n auto"
        test_dir = "tests/"
        src_dir = "seaborn/"
    elif repo == "flask":
        test_cmd = "pytest"
        test_dir = "tests/"
        src_dir = "src/flask/"
    elif repo == "astropy":
        test_cmd = "pytest"
        test_dir = "astropy/"
        src_dir = "astropy"
        if not "pre_install" in setup:
            setup["pre_install"] = []
        setup["pre_install"] += ["apt-get update", "apt-get install clang"]
    elif repo == "requests":
        test_cmd = "pytest"
        test_dir = "tests/"
        src_dir = "src/requests/"
    elif repo == "xarray":
        test_cmd = "pytest -n auto"
        test_dir = "tests/"
        src_dir = "xarray/"
    elif repo == "pytest":
        test_cmd = "pytest"
        test_dir = "testing/"
        src_dir = "src/"
    elif repo == "sphinx":
        test_cmd = "pytest"
        test_dir = "tests/"
        src_dir = "sphinx/"
    elif repo == "django":
        test_cmd = "PYTHONWARNINGS=always pytest --capture=no"
        test_dir = "tests/"
        src_dir = "django"
        if not "pre_install" in setup:
            setup["pre_install"] = []
        setup["pre_install"] += ["apt-get update", "apt-get install clang"]
    elif repo == "scikit-learn":
        test_cmd = "pytest"
        test_dir = "sklearn/"
        src_dir = "sklearn/"
        if not "pre_install" in setup:
            setup["pre_install"] = []
        setup["pre_install"] += ["apt-get update", "apt-get install clang"]
        setup["install"] = "python setup.py install"
    return {
        "instance_id": example["instance_id"],
        "repo": f"{organization}/{repo}",
        "original_repo": f"{owner}/{repo}",
        "base_commit": example["base_commit"],
        "reference_commit": example["environment_setup_commit"],
        "setup": setup,
        "test": {"test_cmd": test_cmd, "test_dir": test_dir, "PASS_TO_PASS": example["PASS_TO_PASS"], "FAIL_TO_PASS": example["FAIL_TO_PASS"], "patch": example["patch"], "test_patch": example["test_patch"]},
        "src_dir": src_dir,
    }


def main(
    dataset: str,
    organization: str,
    token: Optional[str] = None,
) -> None:
    """Main thread for creating task instances from existing repositories

    Args:
    ----
        dataset (str): SWE-bench dataset to build
        organization (str): under which organization to fork repos to
        token (str): GitHub token

    """
    if token is None:
        # Get GitHub token from environment variable if not provided
        token = os.environ.get("GITHUB_TOKEN")

    examples = []
    ds = load_dataset(dataset, split="test")
    for example in ds:
        logger.info(f"Working on {example['repo']}")
        head = example["environment_setup_commit"]
        owner, repo = example["repo"].split("/")
        #repo = Repo(owner, repo, organization=organization, head=head, token=token)
        # Create task instance
        instance = create_instance(example, organization)
        examples.append(instance)
    ds = Dataset.from_list(examples)
    ds = DatasetDict({"test": ds})
    hf_name = f"wentingzhao/{dataset.split('/')[-1]}"
    ds.push_to_hub(hf_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=str, help="SWE-bench dataset to build")
    parser.add_argument(
        "--organization",
        type=str,
        default="commit-0",
        help="under which organization to fork repos to",
    )
    parser.add_argument("--token", type=str, help="GitHub token")
    args = parser.parse_args()
    main(**vars(args))
