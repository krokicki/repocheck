#!/usr/bin/env python

import os
import sys
import random
from datetime import datetime
import argparse

from openai import OpenAI
from github import Github, Auth, Repository
from loguru import logger
from nbconvert import PythonExporter
import nbformat

from repocheck.model import *
from repocheck.project_cache import ProjectCache

# Use consistent seed so that we sample the same files each time
random.seed(42)

LOG_LEVEL = "INFO"
ANALYZE_CODE = True
MAX_CODE_FILES = 10
OPENAI_MODEL = "gpt-4o-mini-2024-07-18"

COST_PER_INPUT_TOKEN = {
    "gpt-4o": 2.50 / 1_000_000,
    "gpt-4o-mini": 0.15 / 1_000_000,
    "gpt-4o-mini-2024-07-18": 0.15 / 1_000_000,
}

COST_PER_OUTPUT_TOKEN = {
    "gpt-4o": 10.00 / 1_000_000,
    "gpt-4o-mini": 0.60 / 1_000_000,
    "gpt-4o-mini-2024-07-18": 0.60 / 1_000_000,
}


def read_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            return f.read()

       
def collect_content(project_cache: ProjectCache):
    readme = None, ""
    license = None, ""
    code_files = []
    code = {}
    local_path = project_cache.repo_path

    for root, _, files in os.walk(local_path):

        for file in files:
            file_path = os.path.join(root, file)
            real_path = os.path.relpath(file_path, local_path)

            if "/" not in real_path:
                if file.lower() in ("readme", "readme.mdown", "readme.md", "readme.txt"):
                    readme = (file, read_file(file_path))
                    logger.debug(f"Found readme at {root}/{file}")
                elif file.lower() in ("license", "license.mdown", "license.md", "license.txt"):
                    license = (file, read_file(file_path))
                    logger.debug(f"Found license at {root}/{file}")

            if file.endswith(".py") or file.endswith(".ipynb"):
                code_files.append(file_path)

    # Randomly select from code_files if we have more files than the limit
    if len(code_files) > MAX_CODE_FILES:
        code_files = random.sample(code_files, MAX_CODE_FILES)
        logger.debug(f"Randomly selected {MAX_CODE_FILES} files to analyze.")

    for file_path in code_files:
        real_path = os.path.relpath(file_path, local_path)
        if real_path.endswith(".py"):
            try:
                code[real_path] = read_file(file_path)
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {e}")

        elif real_path.endswith(".ipynb"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    notebook = nbformat.read(f, as_version=4)
                exporter = PythonExporter()
                code_content, _ = exporter.from_notebook_node(notebook)
                code[real_path] = code_content
            except Exception as e:
                logger.warning(f"Failed to read notebook file {file_path}: {e}")

    return readme, license, code


def calculate_completion_cost(completion):
    prompt_tokens = completion.usage.prompt_tokens
    output_tokens = completion.usage.completion_tokens
    total_cost = (prompt_tokens * COST_PER_INPUT_TOKEN[OPENAI_MODEL]
                    + output_tokens * COST_PER_OUTPUT_TOKEN[OPENAI_MODEL])
    return total_cost


def analyze_file_content(client, filepath, file_content, system_prompt, user_prompt, response_format):
    
    CHAR_LIMIT = 100000
    if len(file_content) > CHAR_LIMIT:
        logger.warning(f"File {filepath} exceeds the token limit and will be truncated.")
        file_content = file_content[:CHAR_LIMIT]

    try:
        # Using beta API so that we can structured output
        completion = client.beta.chat.completions.parse(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_format,
        )
                
        cost = calculate_completion_cost(completion)
        return completion, cost
    
    except Exception as e:
        logger.error(f"Failed to analyze code {filepath}: {e}")
        return None, 0


def analyze_readme(project_cache: ProjectCache, readme):
    file, content = readme

    system_prompt = """
    You are an expert at analyzing Markdown files from GitHub repositories and extracting structured information about the project.
    Given the content of a README file, you extract the shell (CLI) commands which are necessary to setup the project and run a basic example.
    Break multiline commands into separate steps.
    Do NOT include commands which are optional or not relevant to setting up the project for a minimal example.
    If commands are repeated multiple times with different example arguments, you should output those command only once, choosing the best example.
    If you can't find any setup commands, please output an empty list.
    """

    user_prompt = f"""
    Given the README content below, extract ONLY the shell commands which are necessary to setup the project and run a basic example:

    {content}
    """

    client = OpenAI()
    completion, cost = analyze_file_content(client, project_cache.get_path_in_repo(file), content, system_prompt, user_prompt, ReadmeAnalysis)
    if completion is None:
        return None, cost

    message = completion.choices[0].message
    if message.parsed:
        result = message.parsed
        result.github_commit_hash = project_cache.get_commit_hash(file) if file else None
        return result, cost
    
    elif message.refusal:
        logger.info(f"[ERROR] refused to analyze README {project_cache.get_path_in_repo(file)}: {message.refusal}")
    
    return None, cost
    

def analyze_license(project_cache: ProjectCache, license):
    file, content = license

    is_copyright_hhmi = any(
        line.strip().startswith("Copyright") and 
        ("HHMI" in line.strip() or "Howard Hughes Medical Institute" in line.strip())
        for line in content.splitlines()
    )

    analysis = LicenseAnalysis(
        github_commit_hash=project_cache.get_commit_hash(file) if file else None,
        is_bsd3clause="BSD 3-Clause License" in content,
        is_copyright_hhmi=is_copyright_hhmi,
        is_current_year=str(datetime.now().year) in content,
    )
    return analysis


def analyze_code(project_cache: ProjectCache, code):
    client = OpenAI()
    results = {}
    total_cost = 0
    c = 0

    for filepath, file_content in code.items():

        system_prompt = """
        You are an expert in evaluating Python code for API documentation and internal comments.
        You will be given the content of a Python file.
        
        Please rate the quality of the API documentation and internal comments on a scale from 1 to 5.
        Provide a very brief (two sentences max) explanation for your rating.
        """

        user_prompt = f"""
        Please analyze the following Python file:
        {file_content}
        """

        fullpath = project_cache.get_path_in_repo(filepath)
        completion, cost = analyze_file_content(client, fullpath, file_content, system_prompt, user_prompt, CodeDocumentationAnalysis)
        if completion is None:
            continue

        total_cost += cost

        message = completion.choices[0].message
        if message.parsed:
            if message.parsed.github_commit_hash:
                logger.warning(f"AI returned a commit hash for {filepath}: {message.parsed.github_commit_hash}")
            
            message.parsed.github_commit_hash = project_cache.get_commit_hash(filepath)

            results[filepath] = message.parsed
            c += 1
        
        elif message.refusal:
            logger.info(f"[ERROR] refused to analyze code {fullpath}: {message.refusal}")

        if c > 10:
            logger.info(f"Analyzed {c} code files")
            return results, total_cost

    return results, total_cost


def process_github_repo(repo: Repository, cache_dir: str, force: bool = False):

    project_cache = ProjectCache(cache_dir, repo.full_name)

    logger.info("=" * 80)
    logger.info(f"Processing {repo.full_name}")
    logger.info(f"Repo URL: {repo.html_url}")
    logger.info(f"Repo Description: {repo.description}")
    logger.info(f"Language: {repo.language}")
    logger.info(f"Pushed at: {repo.pushed_at}")

    if repo.fork or repo.archived:
        reason = "fork" if repo.fork else "archived"
        logger.info(f"Skipping {repo.full_name} because it is a {reason}")
        project_cache.remove_existing_analysis()
        return

    # Get the contributors
    contributors = repo.get_contributors()
    logger.info("Contributors:")    
    for contributor in contributors:
        logger.info(f"  {contributor.login} ({contributor.contributions} contributions)")

    # Fetch changes to the repo
    changed = project_cache.clone_or_update_repo(repo.ssh_url)
    if not changed and project_cache.analysis_exists() and not force:
        logger.info(f"Skipping {repo.full_name} because it hasn't changed since last analysis")
        return

    readme, license, code = collect_content(project_cache)
    readme_result, readme_cost = analyze_readme(project_cache, readme)

    if readme_result.setup_steps:
        logger.info("Setup Steps:")
        for step in readme_result.setup_steps:
            logger.info(f"  $ {step.command}")
    else:
        logger.info("Setup Steps: N/A")

    logger.info(f"Setup Completeness Score: {readme_result.setup_completeness}")
    logger.info(f"README Quality Score: {readme_result.readme_quality}")

    license_result = analyze_license(project_cache, license)
    
    if ANALYZE_CODE:
        code_result, code_cost = analyze_code(project_cache, code)
    else:
        code_result, code_cost = {}, 0

    total_lines = sum(len([line for line in content.splitlines() if line.strip()]) for content in code.values())
    global_api_doc_score = 0
    global_code_comments_score = 0

    for filepath, analysis in code_result.items():
        file_lines = len([line for line in code[filepath].splitlines() if line.strip()])
        weight = file_lines / total_lines
        global_api_doc_score += analysis.api_documentation_score * weight
        global_code_comments_score += analysis.code_comments_score * weight
    
    logger.info(f"API Docs Score: {global_api_doc_score:.2f}")
    logger.info(f"Code Comments Score: {global_code_comments_score:.2f}")

    license_score = 0
    if license_result.github_commit_hash:
        license_score += 2
        if license_result.is_bsd3clause:
            license_score += 1
        if license_result.is_copyright_hhmi:
            license_score += 1
        if license_result.is_current_year:
            license_score += 1
    logger.info(f"License Score: {license_score}")

    scores = {
        "setup_completeness": readme_result.setup_completeness,
        "readme_quality": readme_result.readme_quality,
        "license": license_score,
        "api_documentation": global_api_doc_score,
        "code_comments": global_code_comments_score,
    }

    weights = {
        "setup_completeness": 0.5,
        "readme_quality": 0.4,
        "license": 0.1,
        "api_documentation": 0.3,
        "code_comments": 0.2,
    }

    overall_score = sum(weights[key] * scores[key] for key in scores)
    logger.info(f"Overall Score: {overall_score:.2f}")

    # Normalize the overall score to a 0 to 5 range
    def normalize_score(overall_score, weights):
        theoretical_min = sum(weights[key] * 1 for key in weights)
        theoretical_max = sum(weights[key] * 5 for key in weights)
        normalized_score = 5 * ((overall_score - theoretical_min) / (theoretical_max - theoretical_min))
        normalized_score = min(5, max(0, normalized_score))  # Clamp between 0-5
        return normalized_score
    
    normalized_score = normalize_score(overall_score, weights)
    logger.info(f"Normalized Overall Score: {normalized_score:.2f}")

    analysis_cost = readme_cost + code_cost
    logger.info(f"Analysis cost: ${analysis_cost:.4f}")

    metadata = GithubMetadata(
        repo_name=repo.full_name,
        repo_url=repo.html_url,
        description=repo.description,
        stars=repo.stargazers_count,
        forks=repo.forks_count,
        language=repo.language,
        contributors=[contributor.login for contributor in contributors],
    )

    analysis = ProjectAnalysis(
        github_metadata=metadata,
        last_commit_date=repo.pushed_at.isoformat(),
        analysis_date=datetime.now().isoformat(),
        readme_analysis=readme_result,
        license_analysis=license_result,
        code_analysis=code_result,
        global_scores=GlobalQualityScores(
            setup_completeness=readme_result.setup_completeness,
            readme_quality=readme_result.readme_quality, 
            license=license_score, 
            api_documentation=global_api_doc_score, 
            code_comments=global_code_comments_score, 
            overall=normalized_score),
    )

    project_cache.save_analysis_to_file(analysis)
    return analysis


def process_repo_from_url(repo_url, cache_dir="cache", force=False):
    if repo_url.startswith("git@"):
        # SSH URL
        org_repo = repo_url.split(":")[1].replace(".git", "")
    elif repo_url.startswith("https://"):
        # HTTPS URL
        org_repo = repo_url.split("github.com/")[1].replace(".git", "")
    else:
        org_repo = repo_url

    org_name, repo_name = org_repo.split("/")
    g = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))
    repo = g.get_repo(f"{org_name}/{repo_name}")
    return process_github_repo(repo, cache_dir, force)


def process_all_repos_in_org(org_name, start_repo=None, cache_dir="cache", force=False):
    logger.info(f"Fetching repositories in {org_name} organization...")
    g = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))
    repos = list(g.get_organization(org_name).get_repos(type='public'))
    
    start_processing = start_repo is None
    for repo in repos:
        if not start_processing:
            if repo.full_name == start_repo:
                start_processing = True
            else:
                continue
        
        process_github_repo(repo, cache_dir, force)


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL)
    
    parser = argparse.ArgumentParser(description="Process GitHub repositories.")
    parser.add_argument("--single", type=str, help="Process a single repository")
    parser.add_argument("--start", type=str, help="Restart processing from this repository name (full name, e.g. JaneliaSciComp/colormipsearch)")
    parser.add_argument("--force", action="store_true", help="Force re-analysis even if existing analysis exists")
    parser.add_argument("--org", type=str, help="Process all repositories in this organization", default="JaneliaSciComp")
    parser.add_argument("--cache-dir", type=str, help="Directory to store analysis cache files", default="cache")
    args = parser.parse_args()

    if args.single:
        process_repo_from_url(args.single, cache_dir=args.cache_dir, force=args.force)
    else:
        process_all_repos_in_org(args.org, start_repo=args.start, cache_dir=args.cache_dir, force=args.force)
