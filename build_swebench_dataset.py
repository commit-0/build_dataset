#!/usr/bin/env python3

import argparse
import logging
import os
from typing import Optional

from datasets import Dataset, DatasetDict, load_dataset

from swebench.harness.constants import (
    MAP_REPO_VERSION_TO_SPECS
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
    if "packages" in raw_info:
        setup["packages"] = raw_info["packages"]
    if "pip_packages" in raw_info:
        setup["pip_packages"] = raw_info["pip_packages"]
    owner, repo = example["repo"].split("/")
    if repo == "matplotlib":
        test_cmd = "pytest"
        test_dir = "lib/matplotlib/tests"
        src_dir = "lib/matplotlib"
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
        test_dir = "astropy/tests/"
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
    elif repo == "scikit-learn":
        test_cmd = "pytest"
        test_dir = "sklearn/"
        src_dir = "sklearn/"
    return {
        "instance_id": example["instance_id"],
        "repo": f"{organization}/{repo}",
        "original_repo": f"{owner}/{repo}",
        "base_commit": example["base_commit"],
        "reference_commit": example["environment_setup_commit"],
        "setup": setup,
        "test": {"test_cmd": test_cmd, "test_dir": test_dir},
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
        # Create task instance
        instance = create_instance(example, organization)
        examples.append(instance)
    ds = Dataset.from_list(examples)
    ds = DatasetDict({"test": ds})
    hf_name = f"wentingzhao/{dataset.split('/')[-1]}_commit0"
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
