import os
import csv
import argparse
from jinja2 import Environment, FileSystemLoader

from repocheck.model import *
from repocheck.project_cache import load_analysis_from_cache

CSV_OUTPUT = False

def remove_empty_lines(html_content):
    return "\n".join([line for line in html_content.split("\n") if line.strip() != ""])


def get_license_score(license_analysis: LicenseAnalysis):
    license_score = 0
    if license_analysis.github_commit_hash:
        license_score += 2
        if license_analysis.is_bsd3clause:
            license_score += 1
        if license_analysis.is_copyright_hhmi:
            license_score += 1
        if license_analysis.is_current_year:
            license_score += 1
    return license_score


def score_bool(value):
    return 1 if value else 0


def compute_scores(analysis: ProjectAnalysis):
    
    global_scores = analysis.global_scores
    license_score = get_license_score(analysis.license_analysis)

    global_api_doc_score = 0.0
    global_api_doc_score_divisor = 0.0
    global_code_comments_score = 0.0
    global_code_comments_score_divisor = 0.0
    
    for file_analysis in analysis.code_analysis:
        global_api_doc_score += score_bool(file_analysis.high_level_documentation)
        global_api_doc_score_divisor += 1
        
        # TODO: included code factored score
    
        for function_analysis in file_analysis.function_analysis:
            global_api_doc_score += score_bool(function_analysis.api_documentation)
            global_api_doc_score_divisor += 1
            global_code_comments_score += score_bool(function_analysis.code_comments)
            global_code_comments_score_divisor += 1

    scores = {
        "setup_completeness": global_scores.setup_completeness,
        "readme_quality": global_scores.readme_quality,
        "api_documentation": 5 * (global_api_doc_score / global_api_doc_score_divisor),
        "code_comments": 5 * (global_code_comments_score / global_code_comments_score_divisor),
        "license": license_score,
    }

    weights = {
        "setup_completeness": 5,
        "readme_quality": 4,
        "api_documentation": 4,
        "code_comments": 2,
        "license": 1,
    }

    overall_score = sum(weights[key] * scores[key] for key in scores)
    scores["overall"] = overall_score

    # Normalize the overall score to a 0 to 5 range
    def normalize_score(overall_score, weights):
        theoretical_min = sum(weights[key] * 1 for key in weights)
        theoretical_max = sum(weights[key] * 5 for key in weights)
        normalized_score = 5 * ((overall_score - theoretical_min) / (theoretical_max - theoretical_min))
        normalized_score = min(5, max(0, normalized_score))  # Clamp between 0-5
        return normalized_score
    
    normalized_score = normalize_score(overall_score, weights)
    scores["normalized"] = normalized_score

    return scores


# Create safe filename from repo name
def generate_filename(repo_name):
    return repo_name.replace('/', '_') + ".html"


def build_report(analysis):

    scores = compute_scores(analysis)

    report = {
        "Repo": {
            "name": analysis.github_metadata.repo_name,
            "filename": generate_filename(analysis.github_metadata.repo_name)
        },
        "URL": analysis.github_metadata.repo_url,
        "Language": analysis.github_metadata.language,
        "Contributors": analysis.github_metadata.contributors,
        "Overall Score": scores['normalized'],
        "Setup Score": scores['setup_completeness'],
        "README Score": scores['readme_quality'],
        "API Docs Score": scores['api_documentation'],
        "Code Comments Score": scores['code_comments'],
        "License Score": scores['license'],
        "Last Commit Date": analysis.last_commit_date,
        "Stars": analysis.github_metadata.stars,
        "Forks": analysis.github_metadata.forks
    }
    
    return report


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

    # Generate the index table
    values = list(data.values())
    columns = values[0].keys() if values else []
    column_unique_values = {
        col: [""] + sorted({
            str(item) for row in values 
            for item in ([row.get(col)] if not isinstance(row.get(col), list) else row.get(col))
            if item is not None and item != ""
        })
        for col in columns if col in ["Contributors", "Language"]
    }

    env = Environment(loader=FileSystemLoader('.'))

    # Render the index table
    index_template = env.get_template('templates/index.html')
    html_content = index_template.render(columns=columns, column_unique_values=column_unique_values, data=values)
    html_content = remove_empty_lines(html_content)
    output_html_file = os.path.join(args.output_dir, "index.html")
    with open(output_html_file, "w", encoding="utf-8") as htmlfile:
        htmlfile.write(html_content)
    print(f"Generated index table at {output_html_file}")

    # Generate individual repo HTML files
    repo_template = env.get_template('templates/repo.html')
    for analysis in analyses:
        repo_html = repo_template.render(analysis=analysis, report=data[analysis.github_metadata.repo_name], get_score_color=get_score_color)
        repo_html = remove_empty_lines(repo_html)
        
        filename = generate_filename(analysis.github_metadata.repo_name)
        output_repo_file = os.path.join(output_dir, filename)
        
        with open(output_repo_file, "w", encoding="utf-8") as htmlfile:
            htmlfile.write(repo_html)
        print(f"Generated report for {analysis.github_metadata.repo_name} at {output_repo_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate analysis output files.")
    parser.add_argument("--cache-dir", type=str, help="Directory to store analysis cache files", default="cache")
    parser.add_argument("--output-dir", type=str, default="[cache-dir]/output", help="Directory to write output files")
    parser.add_argument("--csv", dest="csv", action="store_true", help="Do not generate CSV output")
    parser.add_argument("--no-csv", dest="csv", action="store_false", help="Do not generate CSV output (default)")
    parser.add_argument("--html", dest="html", action="store_true", help="Generate HTML output (default)")
    parser.add_argument("--no-html", dest="html", action="store_false", help="Do not generate HTML output")
    parser.set_defaults(csv=False, html=True)

    args = parser.parse_args()
    output_dir = args.output_dir.replace("[cache-dir]", args.cache_dir)

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Load analyses from cache
    analyses = load_analysis_from_cache(args.cache_dir)    

    reports = {analysis.github_metadata.repo_name: build_report(analysis) for analysis in analyses}

    if args.csv:
        rows = []
        for report in reports.values():
            report_copy = report.copy()
            report_copy["Repo"] = report_copy["Repo"]["name"]
            rows.append(report_copy)
        generate_csv_output(rows, output_dir)

    if args.html:
        generate_html_output(analyses, reports, output_dir, get_score_color)
