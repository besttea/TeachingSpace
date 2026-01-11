#!/bin/bash
# GitHub Repository Creation Script
# This script creates a GitHub repository and pushes the initial commit

# Repository configuration
REPO_NAME="TeachingSpace"
DESCRIPTION="Python Learning Platform with Jupyter-style notebook interface, coding exercises, and auto-grading system"
PRIVATE="false"  # Set to "true" for private repository

# Get GitHub token from environment
GITHUB_TOKEN="${GIT_API_KEY}"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GIT_API_KEY environment variable is not set"
    echo "Please set it with: export GIT_API_KEY='your_github_token'"
    exit 1
fi

# Create GitHub repository using API
echo "Creating GitHub repository: $REPO_NAME"
response=$(curl -s -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    https://api.github.com/user/repos \
    -d "{\"name\":\"$REPO_NAME\",\"description\":\"$DESCRIPTION\",\"private\":$PRIVATE}")

# Check if repository was created successfully
if echo "$response" | grep -q '"full_name"'; then
    repo_url=$(echo "$response" | grep -o '"clone_url": "[^"]*' | cut -d'"' -f4)
    echo "Repository created successfully!"
    echo "Repository URL: $repo_url"

    # Add remote and push
    echo "Adding remote origin..."
    git remote add origin "$repo_url"

    echo "Pushing to GitHub..."
    git branch -M main
    git push -u origin main

    echo "Done! Repository is now available on GitHub."
else
    echo "Error creating repository:"
    echo "$response"
    exit 1
fi
