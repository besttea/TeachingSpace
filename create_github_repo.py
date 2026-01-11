#!/usr/bin/env python
"""
GitHub Repository Creation Script

This script creates a GitHub repository and pushes the code to it.
Make sure GIT_API_KEY environment variable is set with your GitHub Personal Access Token.
"""

import os
import sys
import json
import subprocess
import requests


def get_github_token():
    """Get GitHub token from environment variable."""
    token = os.environ.get('GIT_API_KEY')
    if not token:
        print("Error: GIT_API_KEY environment variable is not set")
        print("\nTo set it:")
        print("  On Windows (PowerShell): $env:GIT_API_KEY = 'your_token_here'")
        print("  On Windows (CMD): set GIT_API_KEY=your_token_here")
        print("  On macOS/Linux: export GIT_API_KEY='your_token_here'")
        sys.exit(1)
    return token


def create_github_repo(token, repo_name, description, private=False):
    """Create a GitHub repository using the API."""
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "name": repo_name,
        "description": description,
        "private": private,
        "auto_init": False
    }

    print(f"Creating GitHub repository: {repo_name}")
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        repo_data = response.json()
        print(f"✓ Repository created successfully!")
        print(f"  Repository URL: {repo_data['html_url']}")
        print(f"  Clone URL: {repo_data['clone_url']}")
        return repo_data['clone_url']
    else:
        print(f"✗ Error creating repository:")
        print(f"  Status code: {response.status_code}")
        print(f"  Response: {response.text}")
        sys.exit(1)


def setup_remote_and_push(clone_url):
    """Add remote origin and push code to GitHub."""
    try:
        # Check if remote already exists
        result = subprocess.run(['git', 'remote', 'get-url', 'origin'],
                              capture_output=True, text=True)

        if result.returncode == 0:
            print("\nRemote 'origin' already exists. Removing it...")
            subprocess.run(['git', 'remote', 'remove', 'origin'], check=True)

        # Add new remote
        print("\nAdding remote origin...")
        subprocess.run(['git', 'remote', 'add', 'origin', clone_url], check=True)

        # Rename branch to main
        print("Renaming branch to main...")
        subprocess.run(['git', 'branch', '-M', 'main'], check=True)

        # Push to GitHub
        print("Pushing to GitHub...")
        result = subprocess.run(['git', 'push', '-u', 'origin', 'main'],
                              capture_output=True, text=True)

        if result.returncode == 0:
            print("\n✓ Successfully pushed to GitHub!")
            print("\nYour repository is now live on GitHub.")
            return True
        else:
            print(f"\n✗ Error pushing to GitHub:")
            print(result.stderr)
            return False

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Git command failed: {e}")
        return False


def main():
    """Main execution function."""
    # Configuration
    REPO_NAME = "TeachingSpace"
    DESCRIPTION = "Python Learning Platform with Jupyter-style notebook interface, coding exercises, and auto-grading system"
    PRIVATE = False  # Set to True for private repository

    print("=" * 60)
    print("GitHub Repository Setup")
    print("=" * 60)

    # Get token
    token = get_github_token()

    # Create repository
    clone_url = create_github_repo(token, REPO_NAME, DESCRIPTION, PRIVATE)

    # Setup remote and push
    if setup_remote_and_push(clone_url):
        print("\n" + "=" * 60)
        print("Setup Complete!")
        print("=" * 60)
        print(f"\nView your repository at:")
        print(f"https://github.com/besttea/{REPO_NAME}")
    else:
        print("\n⚠ Warning: Repository created but push failed.")
        print("You can manually push later with:")
        print(f"  git remote add origin {clone_url}")
        print("  git branch -M main")
        print("  git push -u origin main")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)
