# repocheck

This script analyzes GitHub repositories using OpenAI models to get a sense of the overall documentation quality.

## Getting Started

Set up your tokens for GitHub and OpenAI in your environment: 
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

Run the repocheck script:
```bash
python -m repocheck.repocheck
```

