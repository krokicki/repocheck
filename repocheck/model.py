from pydantic import BaseModel, Field
from typing import Optional

class Prerequisite(BaseModel):
    description: str = Field(description="A brief description of the prerequisite")
    url: str = Field(description="The URL to the full documentation for installing the prerequisite")

class ShellCommand(BaseModel):
    description: str = Field(description="A brief description of the command")
    command: str = Field(description="The shell command, as it would be typed in the terminal")

class ReadmeAnalysis(BaseModel):
    github_commit_hash: Optional[str] = Field(description="The commit hash for the code (AI should leave this blank)")
    project_name: str = Field(description="The full name of the project")
    prerequisites: list[Prerequisite] = Field(description="The prerequisites for running the setup steps")
    setup_steps: list[ShellCommand] = Field(description="The shell commands which build/install/run the project")
    setup_completeness: int = Field(min_value=1, max_value=5, description="How complete the setup steps are")
    documentation_quality: int = Field(min_value=1, max_value=5, description="How well the README is written")
    docs_url: str = Field(description="The URL to the full documentation for the project, if it exists")

class LicenseAnalysis(BaseModel):
    github_commit_hash: Optional[str] = Field(description="The commit hash for the code (AI should leave this blank)")
    is_bsd3clause: bool = Field(description="Is the license a BSD 3-clause license?")
    is_copyright_hhmi: bool = Field(description="Is the license a copyright notice for HHMI?")
    is_current_year: bool = Field(description="Is the license current for the current year?")
    
class CodeDocumentationAnalysis(BaseModel):
    github_commit_hash: Optional[str] = Field(description="The commit hash for the code (AI should leave this blank)")
    api_documentation_score: int = Field(min_value=1, max_value=5, description="How well the code is documented for external users")
    code_comments_score: int = Field(min_value=1, max_value=5, description="How well the code is commented for developers")
    explanation: str = Field(description="A very brief explanation for the scores")

class GlobalQualityScores(BaseModel):
    readme: float = Field(description="The score for the README")
    license: float = Field(description="The score for the license")
    api_documentation: float = Field(description="The average API documentation score for all files")
    code_comments: float = Field(description="The average code comments score for all files")
    overall: float = Field(description="The overall quality score for the project")

class GithubMetadata(BaseModel):
    repo_name: str = Field(description="The name of the GitHub repository")
    repo_url: str = Field(description="The URL of the GitHub repository")
    description: Optional[str] = Field(description="The description of the GitHub repository")
    stars: int = Field(description="The number of stars for the GitHub repository")
    forks: int = Field(description="The number of forks for the GitHub repository")

class ProjectAnalysis(BaseModel):
    github_metadata: GithubMetadata = Field(description="Metadata about the GitHub repository")
    last_commit_date: str = Field(description="The date of the last commit to the repository")
    readme_analysis: ReadmeAnalysis = Field(description="The analysis of the README file")
    license_analysis: LicenseAnalysis = Field(description="The analysis of the LICENSE file")
    code_analysis: dict[str, CodeDocumentationAnalysis] = Field(description="The analysis of the code")
    global_scores: GlobalQualityScores = Field(description="The overall quality scores computed for the project")