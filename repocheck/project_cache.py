import os
import json

from git import Repo
from loguru import logger
from pydantic import ValidationError

from repocheck.model import ProjectAnalysis

ANALYSIS_FILE = "analysis.json"

class ProjectCache:
    """
    A class that manages the file cache for a single project.
    """

    def __init__(self, cache_dir: str, repo_full_name: str):
        self.cache_dir = cache_dir
        self.repo_full_name = repo_full_name
        self.project_cache_dir = self.get_project_cache_dir(repo_full_name)
        self.repo_path = self.get_repo_path(repo_full_name)


    def get_project_cache_dir(self, repo_full_name: str):
        """
        Get the cache directory for the given repository.
        """
        return f"{self.cache_dir}/{repo_full_name}"


    def get_repo_path(self, repo_full_name: str):
        """
        Get the path to the cached repository.
        """
        return f"{self.cache_dir}/{repo_full_name}/repo"


    def clone_or_update_repo(self, repo_url: str):
        """
        Clone the repository if not already cached locally, 
        or pull the latest updates if it already exists locally.
        """
        # Clone the repo if not already cached locally
        if not os.path.exists(self.repo_path):
            logger.debug(f"Cloning repository from {repo_url} to {self.repo_path}...")
            repo = Repo.clone_from(repo_url, self.repo_path)
            changed = True
        else:
            # Pull latest updates if it already exists locally
            logger.debug(f"Updating repository at {self.repo_path}...")
            repo = Repo(self.repo_path)
            before_pull_commit = repo.head.commit
            repo.remotes.origin.pull()
            changed = repo.head.commit != before_pull_commit

        logger.debug(f"Repository at {self.repo_path} is up to date")
        return changed

    
    def get_commit_hash(self, relative_path: str):
        """
        Get the commit hash for the given relative path in the repository.
        """
        repo = Repo(self.repo_path)
        commit_hash = repo.git.rev_list("-1", "HEAD", "--", relative_path)
        return commit_hash
    

    def get_path_in_repo(self, relative_path: str):
        """
        Get the path to the given relative path in the repository.
        """
        return os.path.join(self.repo_path, relative_path)


    def save_analysis_to_file(self, analysis: ProjectAnalysis):
        """
        Save the given analysis to the project's cache directory.
        """
        # Create the project cache directory if necessary
        os.makedirs(self.project_cache_dir, exist_ok=True)
        # Dump the formatted analysis to the analysis file
        output_file = os.path.join(self.project_cache_dir, ANALYSIS_FILE)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(analysis.model_dump(), f, indent=4)
            logger.info(f"Analysis saved to {output_file}")


    def analysis_exists(self) -> bool:
        """
        Check if the analysis file exists in the project's cache directory.
        """
        return os.path.exists(os.path.join(self.project_cache_dir, ANALYSIS_FILE))


    def remove_existing_analysis(self):
        """
        Remove the existing analysis file in the project's cache directory, if it exists.
        """
        if self.analysis_exists():
            logger.info(f"Removing existing analysis for repo {self.project_cache_dir}")
            output_file = os.path.join(self.project_cache_dir, ANALYSIS_FILE)
            os.remove(output_file)


def load_analysis_from_cache(cache_dir: str) -> list[ProjectAnalysis]:
    """
    Load all of the analyses from the cache directory and return them as a list.
    """
    analyses = []
    for root, _, files in os.walk(cache_dir):
        for file in files:
            if file == ANALYSIS_FILE:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        analysis = ProjectAnalysis(**data)
                        analyses.append(analysis)
                except (json.JSONDecodeError, ValidationError) as e:
                    print(f"Failed to load {file_path}: {e}")
    return analyses

