# repocheck

This script analyzes GitHub repositories using OpenAI models to get a sense of the overall documentation quality and repository health.

## Getting Started

First you will need to set up your tokens for GitHub and OpenAI in your environment: 
```
export GITHUB_TOKEN=...
export OPENAI_API_KEY=...
```

Create a virtualenv and install the dependencies:

```bash
virtualenv env
source env/bin/activate
pip install -r requirements.txt
```

Run the repocheck script on a single repository:
```bash
python -m repocheck.repocheck --single JaneliaSciComp/zarrcade
```

Run the repocheck script on all repositories in the `JaneliaSciComp` organization:
```bash
python -m repocheck.repocheck --org JaneliaSciComp
```

Generate the HTML results:
```bash
python -m repocheck.gentable
```

## Publishing the results

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
