import os
import csv
import argparse
from jinja2 import Environment, FileSystemLoader

from repocheck.model import *
from repocheck.project_cache import load_analysis_from_cache

CSV_OUTPUT = False

def remove_empty_lines(html_content):
    return "\n".join([line for line in html_content.split("\n") if line.strip() != ""])


def build_row(analysis):
    row = {}
    row["Repo"] = analysis.github_metadata.repo_name
    row["URL"] = analysis.github_metadata.repo_url
    row["Language"] = analysis.github_metadata.language
    row["Contributors"] = ",".join(analysis.github_metadata.contributors)
    
    scores = analysis.global_scores
    row["Overall Score"] = scores.overall
    row["Setup Score"] = scores.setup_completeness
    row["README Score"] = scores.readme_quality
    row["License Score"] = scores.license
    row["API Docs Score"] = scores.api_documentation
    row["Code Comments Score"] = scores.code_comments
    
    row["Has License"] = analysis.license_analysis.github_commit_hash is not None
    if row["Has License"]:
        row["License is BSD 3-clause"] = analysis.license_analysis.is_bsd3clause
        row["License is Copyright HHMI"] = analysis.license_analysis.is_copyright_hhmi
        row["License is Current Year"] = analysis.license_analysis.is_current_year
    else:
        row["License is BSD 3-clause"] = False
        row["License is Copyright HHMI"] = False
        row["License is Current Year"] = False

    row["Last Commit Date"] = analysis.last_commit_date
    row["Stars"] = analysis.github_metadata.stars
    row["Forks"] = analysis.github_metadata.forks

    return row


def get_score_color(score):
    if score >= 4:
        return "green"
    elif score >= 2:
        return "#F88017"
    else:
        return "red"


def generate_csv_output(data, output_dir):
    # Write CSV output
    output_csv_file = os.path.join(output_dir, "analysis.csv")
    with open(output_csv_file, "w", newline='', encoding="utf-8") as csvfile:
        fieldnames = data[0].keys() if data else []
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for row in data:
            writer.writerow(row)

        print(f"Data has been written to {output_csv_file}")

    # Generate CSV with raw code analysis scores
    code_scores_file = os.path.join(output_dir, "code_scores.csv")
    with open(code_scores_file, "w", newline='', encoding="utf-8") as csvfile:
        fieldnames = ["Repo", "File", "API Documentation Score", "Code Comments Score", "Explanation"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for analysis in analyses:
            repo_name = analysis.github_metadata.repo_name
            if analysis.code_analysis:
                for filepath, file_analysis in analysis.code_analysis.items():
                    row = {
                        "Repo": repo_name,
                        "File": filepath,
                        "API Documentation Score": file_analysis.api_documentation_score,
                        "Code Comments Score": file_analysis.code_comments_score,
                        "Explanation": file_analysis.explanation
                    }
                    writer.writerow(row)
    
        print(f"Generated code analysis scores at {code_scores_file}")


def generate_html_output(analyses, data, output_dir, get_score_color):
    # Generate individual repo HTML files
    safe_name_map = {}
    env = Environment(loader=FileSystemLoader('.'))
    repo_template = env.get_template('templates/repo.html')
    for analysis in analyses:
        repo_html = repo_template.render(analysis=analysis, get_score_color=get_score_color)
        repo_html = remove_empty_lines(repo_html)
        
        # Create safe filename from repo name
        safe_name = analysis.github_metadata.repo_name.replace('/', '_')
        output_repo_file = os.path.join(output_dir, f"{safe_name}.html")
        safe_name_map[analysis.github_metadata.repo_name] = safe_name
        
        with open(output_repo_file, "w", encoding="utf-8") as htmlfile:
            htmlfile.write(repo_html)
        print(f"Generated report for {analysis.github_metadata.repo_name} at {output_repo_file}")

    # Post-process data for display in the index table
    for row in data:

        # Split comma-separated contributors into a list
        if "Contributors" in row:
            row["Contributors"] = row["Contributors"].split(',')
    
        # Add HTML links to the URL field using safe_name mapping
        if "Repo" in row:
            repo_name = row["Repo"]
            if repo_name in safe_name_map:
                row["Repo"] = f'{safe_name_map[repo_name]}.html'

    # Generate the index table
    columns = data[0].keys() if data else []
    column_unique_values = {
        col: [""] + sorted({
            item for row in data 
            for item in ([row.get(col)] if not isinstance(row.get(col), list) else row.get(col))
            if item is not None and item != ""
        })
        for col in columns
    }
    
    # Render the index table
    index_template = env.get_template('templates/index.html')
    html_content = index_template.render(columns=columns, column_unique_values=column_unique_values, data=data, safe_name_map=safe_name_map)
    html_content = remove_empty_lines(html_content)
    output_html_file = os.path.join(args.output_dir, "index.html")
    with open(output_html_file, "w", encoding="utf-8") as htmlfile:
        htmlfile.write(html_content)
    print(f"Generated index table at {output_html_file}")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate analysis output files.")
    parser.add_argument("--cache-dir", type=str, help="Directory to store analysis cache files", default="cache")
    parser.add_argument("--output-dir", type=str, default="output", help="Directory to write output files")
    parser.add_argument("--csv", dest="csv", action="store_true", help="Do not generate CSV output")
    parser.add_argument("--no-csv", dest="csv", action="store_false", help="Do not generate CSV output (default)")
    parser.add_argument("--html", dest="html", action="store_true", help="Generate HTML output (default)")
    parser.add_argument("--no-html", dest="html", action="store_false", help="Do not generate HTML output")
    parser.set_defaults(csv=False, html=True)

    args = parser.parse_args()

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    # Load analyses from cache
    analyses = load_analysis_from_cache(args.cache_dir)    

    data = [build_row(analysis) for analysis in analyses]

    if args.csv:
        generate_csv_output(data, args.output_dir)

    if args.html:
        generate_html_output(analyses, data, args.output_dir, get_score_color)
