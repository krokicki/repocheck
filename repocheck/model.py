from pydantic import BaseModel, Field
from typing import Optional


class Prerequisite(BaseModel):
    """ A prerequisite dependency for running the setup steps
    """
    description: str = Field(description="A brief description of the prerequisite")
    url: str = Field(description="The URL to the full documentation for installing the prerequisite")


class ShellCommand(BaseModel):
    """ A shell command to be run in the terminal
    """
    description: str = Field(description="A brief description of the command")
    command: str = Field(description="The shell command, as it would be typed in the terminal")


class ReadmeAnalysis(BaseModel):
    """ Analysis of the README file
    """
    github_commit_hash: Optional[str] = Field(description="The commit hash for the code (AI should leave this blank)")
    project_name: str = Field(description="The full name of the project")
    prerequisites: list[Prerequisite] = Field(description="The prerequisites for running the setup steps")
    setup_steps: list[ShellCommand] = Field(description="The shell commands which build/install/run the project")
    setup_completeness: int = Field(min_value=0, max_value=5, description="Score for how complete the setup steps are")
    readme_quality: int = Field(min_value=0, max_value=5, description="Score for how well the README is written")
    docs_url: Optional[str] = Field(description="The URL to the full documentation for the project. Blank if it doesn't exist.")


class LicenseAnalysis(BaseModel):
    """ Analysis of the LICENSE file
    """
    github_commit_hash: Optional[str] = Field(description="The commit hash for the code (AI should leave this blank)")
    is_bsd3clause: bool = Field(description="Is the license a BSD 3-clause license?")
    is_copyright_hhmi: bool = Field(description="Is the license a copyright notice for HHMI?")
    is_current_year: bool = Field(description="Is the license current for the current year?")
    

class FunctionAnalysis(BaseModel):
    """ Analysis of a function
    """
    function_name: str = Field(description="The function being analyzed")
    clear_name: bool = Field(description="Does the function have a clear name?")
    type_annotations: bool = Field(description="Does the function have type annotations?")
    api_documentation: bool = Field(description="Does the function have good API documentation?")
    code_comments: bool = Field(description="Does the function have good comments?")
    explanation: str = Field(description="A very brief explanation for the scores")


class CodeDocumentationAnalysis(BaseModel):
    """ Analysis of a code file
    """
    filepath: str = Field(description="The relative path to the file in the codebase that is being analyzed")
    github_commit_hash: Optional[str] = Field(description="The commit hash for the code (AI should leave this blank)")
    high_level_documentation: bool = Field(description="Does the file have high-level documentation?")
    code_factored: bool = Field(description="Is the code appropriately factored into multiple functions?")
    function_analysis: list[FunctionAnalysis] = Field(description="The analysis of the functions in the file")


class GlobalQualityScores(BaseModel):
    """ The overall quality scores computed for the project
    """
    setup_completeness: float = Field(description="The score for the setup completeness")
    readme_quality: float = Field(description="The score for the README")


class GithubMetadata(BaseModel):
    """ Metadata about the GitHub repository
    """
    repo_name: str = Field(description="The name of the GitHub repository")
    repo_url: str = Field(description="The URL of the GitHub repository")
    description: Optional[str] = Field(description="Repository description")
    stars: int = Field(description="Number of stars")
    forks: int = Field(description="Number of forks")
    language: Optional[str] = Field(description="Main programming language")
    contributors: list[str] = Field(description="The list of contributing users")


class ProjectAnalysis(BaseModel):
    """ The analysis of a project
    """
    github_metadata: GithubMetadata = Field(description="Metadata about the GitHub repository")
    last_commit_date: str = Field(description="The date of the last commit to the repository")
    analysis_date: str = Field(description="The date of the analysis")
    readme_analysis: ReadmeAnalysis = Field(description="The analysis of the README file")
    license_analysis: LicenseAnalysis = Field(description="The analysis of the LICENSE file")
    code_analysis: list[CodeDocumentationAnalysis] = Field(description="The analysis of the code")
    global_scores: GlobalQualityScores = Field(description="The overall quality scores computed for the project")