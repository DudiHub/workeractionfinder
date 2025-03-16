import os
import requests
import argparse
import time
import base64
import yaml
import re

def search_for_action(org, action_name, token, broader_search=False):
    """
    Search for a specific GitHub Action in an organization using the GitHub Search API.
    """
    # For broader search, just search for workflow files
    if broader_search:
        search_query = f"org:{org} path:.github/workflows/ filename:.yml OR filename:.yaml"
    else:
        search_query = f"org:{org} path:.github/workflows/ {action_name}"
    
    url = f"https://api.github.com/search/code?q={requests.utils.quote(search_query)}&per_page=100"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    print(f"Searching for workflow files in {org} organization...")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        search_results = response.json()
        
        # Handle rate limiting
        if 'message' in search_results and 'rate limit' in search_results['message'].lower():
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            wait_time = max(0, reset_time - int(time.time()))
            print(f"Rate limit exceeded. Try again in {wait_time} seconds.")
            return []
            
        return search_results.get('items', [])
    except requests.exceptions.HTTPError as e:
        print(f"Error searching for actions: {e}")
        print(f"Response: {e.response.text}")
        return []

def get_file_content(url, token):
    """Get the content of a file from GitHub."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    content_info = response.json()
    if content_info["encoding"] == "base64":
        return base64.b64decode(content_info["content"]).decode('utf-8')
    return content_info["content"]

def analyze_workflow_content(content, action_name, file_info):
    """Analyze workflow content for action usage."""
    try:
        # First, do a quick string check to avoid parsing unnecessary files
        if action_name not in content:
            return []
            
        workflow_data = yaml.safe_load(content)
        instances = []
        
        # Look for the action in jobs
        if workflow_data and 'jobs' in workflow_data:
            for job_name, job_config in workflow_data['jobs'].items():
                # Check steps in the job
                if 'steps' in job_config:
                    for step_index, step in enumerate(job_config['steps']):
                        if 'uses' in step and action_name in step['uses']:
                            # Get step information
                            step_name = step.get('name', f"Step {step_index + 1}")
                            action_ref = step['uses']
                            step_inputs = step.get('with', {})
                            
                            instances.append({
                                'job': job_name,
                                'step_name': step_name,
                                'action_ref': action_ref,
                                'inputs': step_inputs
                            })
        
        return instances
    except Exception as e:
        print(f"Error parsing workflow {file_info['path']}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description='Find GitHub Actions usage in an organization')
    parser.add_argument('org', help='GitHub organization name')
    parser.add_argument('--action', help='Target GitHub Action to find', default='tj-actions/changed-files')
    parser.add_argument('--token', help='GitHub personal access token', default=os.environ.get('GITHUB_TOKEN'))
    parser.add_argument('--output', help='Output file path', default='action_usage_report.txt')
    parser.add_argument('--broad-search', action='store_true', help='Search all workflow files')
    args = parser.parse_args()
    
    if not args.token:
        print("Error: GitHub token is required. Set GITHUB_TOKEN environment variable or use --token.")
        exit(1)
    
    # Search for workflow files
    search_results = search_for_action(args.org, args.action, args.token, args.broad_search)
    
    print(f"Found {len(search_results)} workflow files to analyze")
    
    # Analyze each workflow file
    usage_by_repo = {}
    total_usages = 0
    total_files = len(search_results)
    files_processed = 0
    
    for item in search_results:
        repo_name = item['repository']['full_name']
        file_path = item['path']
        file_name = os.path.basename(file_path)
        
        files_processed += 1
        print(f"[{files_processed}/{total_files}] Analyzing {repo_name}/{file_path}...")
        
        try:
            # Get file content
            content = get_file_content(item['url'], args.token)
            
            # Look for action usage in the file
            instances = analyze_workflow_content(content, args.action, {
                'repo': repo_name,
                'path': file_path,
                'name': file_name
            })
            
            if instances:
                print(f"  Found {len(instances)} instances of {args.action}")
                total_usages += len(instances)
                
                if repo_name not in usage_by_repo:
                    usage_by_repo[repo_name] = []
                
                for instance in instances:
                    usage_by_repo[repo_name].append({
                        'workflow': file_name,
                        'path': file_path,
                        **instance
                    })
            
            # GitHub rate limiting - don't hit API too hard
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    # Write report
    repos_with_action = len(usage_by_repo)
    
    with open(args.output, 'w') as f:
        f.write(f"Usage Report for '{args.action}' in {args.org}\n")
        f.write(f"===============================================\n\n")
        f.write(f"Repositories using this action: {repos_with_action}\n")
        f.write(f"Total usages found: {total_usages}\n\n")
        
        if repos_with_action > 0:
            f.write("Detailed Usage by Repository:\n")
            f.write("============================\n\n")
            
            for repo, instances in sorted(usage_by_repo.items()):
                f.write(f"Repository: {repo}\n")
                f.write(f"{'-' * len('Repository: ' + repo)}\n")
                
                for i, instance in enumerate(instances, 1):
                    f.write(f"Instance #{i}:\n")
                    f.write(f"  Workflow: {instance['workflow']} ({instance['path']})\n")
                    f.write(f"  Job: {instance['job']}\n")
                    f.write(f"  Step: {instance['step_name']}\n")
                    f.write(f"  Action Reference: {instance['action_ref']}\n")
                    
                    if instance['inputs']:
                        f.write("  Configuration:\n")
                        for param, value in instance['inputs'].items():
                            f.write(f"    {param}: {value}\n")
                    
                    f.write("\n")
                
                f.write("\n")
        else:
            f.write("No instances of this action were found.\n")
    
    print(f"\nScan complete! Report written to {args.output}")
    print(f"Found {total_usages} instances of {args.action} across {repos_with_action} repositories")

if __name__ == "__main__":
    main()
