# repocheck

This script analyzes GitHub repositories using OpenAI models to get a sense of the overall documentation quality and repository health.

## Getting Started

First you will need to set up your tokens for GitHub and OpenAI in your environment: 
```
export GITHUB_TOKEN=...
export OPENAI_API_KEY=...
```

Make sure you have [uv installed](https://docs.astral.sh/uv/getting-started/installation/), then create a virtual environment and install the dependencies:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip sync requirements-universal.txt
```

Run the repocheck script on a single repository:
```bash
python -m repocheck.repocheck --repos JaneliaSciComp/zarrcade
```

Run the repocheck script on all repositories in the `JaneliaSciComp` organization:
```bash
python -m repocheck.repocheck --orgs JaneliaSciComp
```

Generate an HTML report:

```bash
python -m repocheck.gentable
```

Generate a CSV spreadsheet:

```bash
python -m repocheck.gentable --no-html --csv
```

## Development

### Updating dependencies

Edit requirements.txt and then run this command to sync the universal requirements:

```bash
uv pip compile requirements.txt --universal --output-file  requirements-universal.txt
```

### Publishing the results

This will generate a file called `index.html` in the `output` directory. 

To publish it to the web, check out the web branch and copy the files to the `docs` directory:
```bash
git checkout web
cp -r output/* docs/
git add docs
git commit -a
git push
```

The results will be deployed to [https://krokicki.github.io/repocheck/](https://krokicki.github.io/repocheck/).
