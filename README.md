# Set your GitHub token
export GITHUB_TOKEN=your_token_here

# Run the script specifying your organization
python script.py YOUR_ORG_NAME

# Run the script
python findaction.py YOUR_ORG_NAME --action tj-actions/changed-files

# Run the script if you not find
python findaction.py YOUR_ORG_NAME --action tj-actions/changed-files --broad-search
