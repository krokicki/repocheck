#!/usr/bin/env python

import os
import sys
import json
import random
from datetime import datetime

from git import Repo
from openai import OpenAI
from github import Github, Auth, Repository
from loguru import logger

from repocheck.model import *


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


def clone_or_update_repo(repo_url, local_path):
    # Clone the repo if not already cached locally
    if not os.path.exists(local_path):
        logger.debug(f"Cloning repository from {repo_url} to {local_path}...")
        repo = Repo.clone_from(repo_url, local_path)
        changed = True
    else:
        # Pull latest updates if it already exists locally
        logger.debug(f"Updating repository at {local_path}...")
        repo = Repo(local_path)
        before_pull_commit = repo.head.commit
        repo.remotes.origin.pull()
        changed = repo.head.commit != before_pull_commit

    logger.debug(f"Repository at {local_path} is up to date")
    
    last_commit_date = repo.head.commit.committed_datetime
    logger.info(f"Last commit date: {last_commit_date}")
    
    return changed, last_commit_date


def get_commit_hash(repo_path, relative_path):
    repo = Repo(repo_path)
    commit_hash = repo.git.rev_list("-1", "HEAD", "--", relative_path)
    return commit_hash


def read_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            return f.read()


def collect_content(local_path):
    readme = None, ""
    license = None, ""
    code = {}
    for root, _, files in os.walk(local_path):
        for file in files:
            file_path = os.path.join(root, file)
            real_path = os.path.relpath(file_path, local_path)

            if "/" not in real_path:
                if file in ("README", "README.mdown", "README.md"):
                    readme = (file, read_file(file_path))
                    logger.debug(f"Found readme at {root}/{file}")
                elif file in ("LICENSE", "LICENSE.mdown", "LICENSE.md"):
                    license = (file, read_file(file_path))
                    logger.debug(f"Found license at {root}/{file}")

            elif file.endswith(".py"):
                try:
                    code[real_path] = read_file(file_path)
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")

    return readme, license, code


def analyze_file_content(client, filepath, file_content, system_prompt, user_prompt, response_format):
    
    CHAR_LIMIT = 100000
    if len(file_content) > CHAR_LIMIT:
        logger.warning(f"File {filepath} exceeds the token limit and will be truncated.")
        file_content = file_content[:CHAR_LIMIT]

    try:
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


def calculate_completion_cost(completion):
    prompt_tokens = completion.usage.prompt_tokens
    output_tokens = completion.usage.completion_tokens
    total_cost = (prompt_tokens * COST_PER_INPUT_TOKEN[OPENAI_MODEL]
                    + output_tokens * COST_PER_OUTPUT_TOKEN[OPENAI_MODEL])
    return total_cost


def analyze_readme(root_path, readme):
    file, content = readme

    system_prompt = """
    You are an expert at analyzing Markdown files from GitHub repositories and extracting structured information about the project.
    Given the content of a README file, you extract the shell commands which are necessary to setup the project and run a basic example.
    Please break multiline commands into separate steps.
    Do not include commands which are optional or not relevant to setting up the project for a minimal example.
    If commands are repeated multiple times with different example arguments, you should output those command only once, choosing the best example.
    If you can't find any setup commands, please output an empty list.
    """

    user_prompt = f"""
    Given the README content below, extract only the shell commands which are necessary to setup the project and run a basic example:

    {content}
    """

    client = OpenAI()
    completion, cost = analyze_file_content(client, f"{root_path}/{file}", content, system_prompt, user_prompt, ReadmeAnalysis)
    if completion is None:
        return None, cost

    message = completion.choices[0].message
    if message.parsed:
        result = message.parsed
        # Populate the commit hash
        result.github_commit_hash = get_commit_hash(root_path, file) if file else None
        #logger.info(message.parsed.model_dump_json(indent=4))
        return result, cost
    
    elif message.refusal:
        logger.info(f"[ERROR] refused to analyze README {root_path}/{file}: {message.refusal}")
    
    return None, cost
    

def analyze_license(root_path, license):
    file, content = license

    analysis = LicenseAnalysis(
        github_commit_hash=get_commit_hash(root_path, file) if file else None,
        is_bsd3clause="BSD 3-Clause License" in content,
        is_copyright_hhmi="Howard Hughes Medical Institute" in content,
        is_current_year=str(datetime.now().year) in content,
    )
    return analysis


def analyze_code(root_path, code):
    client = OpenAI()
    results = {}
    total_cost = 0
    c = 0

    if len(code) <= MAX_CODE_FILES:
        sampled_code = code
    else:
        sampled_code = dict(random.sample(list(code.items()), MAX_CODE_FILES))
        logger.warning(f"Too many files to analyze. Analyzing {len(sampled_code)} random code files: {list(sampled_code.keys())}")

    for filepath, file_content in sampled_code.items():

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

        completion, cost = analyze_file_content(client, f"{root_path}/{filepath}", file_content, system_prompt, user_prompt, CodeDocumentationAnalysis)
        if completion is None:
            continue

        total_cost += cost

        message = completion.choices[0].message
        if message.parsed:
            if message.parsed.github_commit_hash:
                logger.warning(f"AI returned a commit hash for {filepath}: {message.parsed.github_commit_hash}")
            
            # Populate the commit hash
            message.parsed.github_commit_hash = get_commit_hash(root_path, filepath)

            results[filepath] = message.parsed
            c += 1
        
        elif message.refusal:
            logger.info(f"[ERROR] refused to analyze code {root_path}/{filepath}: {message.refusal}")

        if c > 10:
            logger.info(f"Analyzed {c} code files")
            return results, total_cost

    return results, total_cost


def process_github_repo(repo: Repository):

    logger.info("=" * 80)
    logger.info(f"Processing {repo.full_name}")
    logger.info(f"Repo URL: {repo.html_url}")
    logger.info(f"Repo Description: {repo.description}")

    project_cache_path = f"repo_cache/{repo.full_name}"
    local_repo_path = f"{project_cache_path}/repo"

    changed, last_commit_date = clone_or_update_repo(repo.ssh_url, local_repo_path)

    if not changed and os.path.exists(f"{project_cache_path}/analysis.json"):
        logger.info(f"Skipping {repo.full_name} because it hasn't changed since last analysis")
        return

    readme, license, code = collect_content(local_repo_path)
    readme_result, readme_cost = analyze_readme(local_repo_path, readme)

    if readme_result.setup_steps:
        logger.info("Setup Steps:")
        for step in readme_result.setup_steps:
            logger.info(f"  $ {step.command}")
    else:
        logger.info("Setup Steps: none found")

    logger.info(f"README Quality Score: {readme_result.documentation_quality}")
    logger.info(f"Setup Completeness Score: {readme_result.setup_completeness}")

    license_result = analyze_license(local_repo_path, license)
    if ANALYZE_CODE:
        code_result, code_cost = analyze_code(local_repo_path, code)
    else:
        code_result, code_cost = {}, 0

    total_lines = sum(len([line for line in content.splitlines() if line.strip()]) for content in code.values())
    global_api_doc_score = 0
    global_code_comments_score = 0

    for filepath, analysis in code_result.items():
        file_lines = len(code[filepath].splitlines())
        weight = file_lines / total_lines
        global_api_doc_score += analysis.api_documentation_score * weight
        global_code_comments_score += analysis.code_comments_score * weight
    
    logger.info(f"API Documentation Score: {global_api_doc_score:.2f}")
    logger.info(f"Code Comments Score: {global_code_comments_score:.2f}")

    license_score = 0
    if license:
        license_score += 1
        if license_result.is_bsd3clause:
            license_score += 1
        if license_result.is_copyright_hhmi:
            license_score += 1
        if license_result.is_current_year:
            license_score += 1
    logger.info(f"License Score: {license_score}")

    overall_score = 0.5 * readme_result.setup_completeness \
                  + 0.4 * readme_result.documentation_quality \
                  + 0.1 * license_score \
                  + 0.3 * global_api_doc_score \
                  + 0.2 * global_code_comments_score
    logger.info(f"Overall Score: {overall_score:.2f}")

    total_cost = readme_cost + code_cost
    logger.info(f"Total cost: ${total_cost:.4f}")

    metadata = GithubMetadata(
        repo_name=repo.full_name,
        repo_url=repo.html_url,
        description=repo.description,
        stars=repo.stargazers_count,
        forks=repo.forks_count,
    )

    analysis = ProjectAnalysis(
        github_metadata=metadata,
        last_commit_date=last_commit_date.isoformat(),
        readme_analysis=readme_result,
        license_analysis=license_result,
        code_analysis=code_result,
        global_scores=GlobalQualityScores(
            readme=readme_result.documentation_quality, 
            license=license_score, 
            api_documentation=global_api_doc_score, 
            code_comments=global_code_comments_score, 
            overall=overall_score),
    )

    output_file = f"{project_cache_path}/analysis.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis.model_dump(), f, indent=4)
    
    logger.info(f"Analysis saved to {output_file}")
    return analysis


def process_repo_from_url(repo_url):
    if repo_url.startswith("git@"):
        # SSH URL
        org_repo = repo_url.split(":")[1].replace(".git", "")
    elif repo_url.startswith("https://"):
        # HTTPS URL
        org_repo = repo_url.split("github.com/")[1].replace(".git", "")
    else:
        raise ValueError("Unsupported URL format")

    org_name, repo_name = org_repo.split("/")
    g = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))
    repo = g.get_repo(f"{org_name}/{repo_name}")
    return process_github_repo(repo)


def process_all_repos_in_org(org_name):
    logger.info(f"Fetching repositories in {org_name} organization...")
    g = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")))
    repos = list(g.get_organization(org_name).get_repos(type='public'))
    for repo in repos:
        process_github_repo(repo)


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level=LOG_LEVEL)
    process_all_repos_in_org("JaneliaSciComp")
    #process_repo_from_url("https://github.com/JaneliaSciComp/zarrcade")
    #process_repo_from_url("https://github.com/JaneliaSciComp/colormipsearch")
    #process_repo_from_url("git@github.com:JaneliaSciComp/FL-web.git")
    #process_repo_from_url("https://github.com/JaneliaSciComp/G4_Display_Tools")

