import os
import git
from pydantic import BaseModel, Field
from openai import OpenAI
from pprint import pprint
from devtools import debug
from datetime import datetime

def clone_or_update_repo(repo_url, local_path):
    # Clone the repo if not already cached locally
    if not os.path.exists(local_path):
        print(f"Cloning repository from {repo_url} to {local_path}")
        git.Repo.clone_from(repo_url, local_path)
    else:
        # Pull latest updates if it already exists locally
        print(f"Updating repository at {local_path}...")
        repo = git.Repo(local_path)
        repo.remotes.origin.pull()


def read_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def collect_content(local_path):
    readme = ""
    license = ""
    code = {}
    for root, _, files in os.walk(local_path):
        for file in files:
            file_path = os.path.join(root, file)
            real_path = os.path.relpath(file_path, local_path)
            
            if "/" not in real_path:
                if file in ("README", "README.mdown", "README.md"):
                    readme = read_file(file_path)
                    print(f"Found readme at {root}/{file}")
                elif file in ("LICENSE", "LICENSE.mdown", "LICENSE.md"):
                    license = read_file(file_path)
                    print(f"Found license at {root}/{file}")

            elif file.endswith(".py"):
                code[real_path] = read_file(file_path)

    return readme, license, code


def save_code_to_file(all_code, output_file="all_python_code.txt"):
    with open(output_file, "w", encoding="utf-8") as f:
        for filepath in all_code:
            code = all_code[filepath]
            output = f"# File: {filepath}\n\n{code}\n\n{'#' * 80}\n\n"
            f.write(output)
    print(f"Saved code saved to {output_file}")


class Prerequisite(BaseModel):
    description: str = Field(description="A brief description of the prerequisite")
    url: str = Field(description="The URL to the full documentation for installing the prerequisite")

class ShellCommand(BaseModel):
    description: str = Field(description="A brief description of the command")
    command: str = Field(description="The shell command, as it would be typed in the terminal")

class ReadmeAnalysis(BaseModel):
    project_name: str = Field(description="The full name of the project")
    prerequisites: list[Prerequisite] = Field(description="The prerequisites for running the setup steps")
    setup_steps: list[ShellCommand] = Field(description="The shell commands which build/install/run the project")
    setup_completeness: int = Field(min_value=1, max_value=5, description="How complete the setup steps are")
    documentation_quality: int = Field(min_value=1, max_value=5, description="How well the README is written")
    docs_url: str = Field(description="The URL to the full documentation for the project")


def analyze_readme(content):

    system_prompt = """
    You are an expert at analyzing README.md files from GitHub repositories and extracting information about the project.
    You are given the content of a README.md file in Markdown format.
    
    First, extract the shell commands which build/install/run the project and output them as `setup_steps`. 
    You should ignore commands which are optional or not relevant to setting up the project. 
    For example, do not include commands to run tests or other developer commands.
    If commands are repeated multiple times with different example arguments, you should output those command only once, choosing the best example.
    If you can't find any setup commands, output an empty `setup_steps` list.
    
    Next, extract any `prerequisites` which are needed before running the setup commands.
    
    Next, output the `setup_completeness` which should be a number between 1 and 5, representing how complete the setup instructions are.
    
    Finally, output the `docs_url` which should be the URL to the full documentation for the project, empty string if not found.
    """

    user_prompt = """
    Please analyze the content below:
    """ + content

    client = OpenAI()
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=ReadmeAnalysis,
    )

    message = completion.choices[0].message
    if message.parsed:
        #debug(message.parsed)
        print(message.parsed.model_dump_json(indent=4))
        return message.parsed
    elif message.refusal:
        # handle refusal
        print(message.refusal)
    
    return None
    
def analyze_license(license):

    class LicenseAnalysis(BaseModel):
        is_bsd3clause: bool = Field(description="Is the license a BSD 3-clause license?")
        is_copyright_hhmi: bool = Field(description="Is the license a copyright notice for HHMI?")
        is_current_year: bool = Field(description="Is the license current for the current year?")
        
    analysis = LicenseAnalysis(
        is_bsd3clause="BSD 3-Clause License" in license,
        is_copyright_hhmi="Howard Hughes Medical Institute" in license,
        is_current_year=str(datetime.now().year) in license,
    )
    return analysis


def analyze_code(code):
    client = OpenAI()
    results = {}

    class CodeDocumentationAnalysis(BaseModel):
        api_documentation_score: int = Field(min_value=1, max_value=5, description="How well the code is documented for external users")
        code_comments_score: int = Field(min_value=1, max_value=5, description="How well the code is commented for developers")
        explanation: str = Field(description="A very brief explanation for the scores")
        
    
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

        completion = client.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=CodeDocumentationAnalysis,
        )

        message = completion.choices[0].message
        if message.parsed:
            results[filepath] = message.parsed
        elif message.refusal:
            results[filepath] = {"error": "Refusal to analyze"}

    return results


def process_github_repo(repo_url):
    local_path = f"repo_cache/{repo_url.split('/')[-1]}"
    clone_or_update_repo(repo_url, local_path)
    readme, license, code = collect_content(local_path)
    readme_result = analyze_readme(readme)
    code_result = analyze_code(code)
    license_result = analyze_license(license)
    total_lines = sum(len([line for line in content.splitlines() if line.strip()]) for content in code.values())
    global_api_doc_score = 0
    global_code_comments_score = 0

    for filepath, analysis in code_result.items():
        file_lines = len(code[filepath].splitlines())
        weight = file_lines / total_lines
        global_api_doc_score += analysis.api_documentation_score * weight
        global_code_comments_score += analysis.code_comments_score * weight
    
    print("=" * 80)
    print(f"README Quality: {readme_result.documentation_quality}")
    print(f"Setup Completeness: {readme_result.setup_completeness}")
    
    license_score = 0
    if license:
        license_score += 1
        if license_result.is_bsd3clause:
            license_score += 1
        if license_result.is_copyright_hhmi:
            license_score += 1
        if license_result.is_current_year:
            license_score += 1

    print(f"License Score: {license_score}")
    print(f"API Documentation Score: {global_api_doc_score:.2f}")
    print(f"Code Comments Score: {global_code_comments_score:.2f}")


process_github_repo("https://github.com/JaneliaSciComp/zarrcade")
#process_github_repo("https://github.com/JaneliaSciComp/colormipsearch")
#process_github_repo("https://github.com/JaneliaSciComp/FL-web")
#process_github_repo("https://github.com/JaneliaSciComp/G4_Display_Tools")
