# GitHub Repository Setup Guide

This guide will help you create a GitHub repository and push your code to it.

## Prerequisites

- Git installed and configured
- GitHub account
- GitHub Personal Access Token (PAT)

## Step 1: Get Your GitHub Personal Access Token

If you don't have a GitHub Personal Access Token yet:

1. Go to GitHub.com and sign in
2. Click your profile picture → Settings
3. Scroll down and click "Developer settings" (left sidebar)
4. Click "Personal access tokens" → "Tokens (classic)"
5. Click "Generate new token" → "Generate new token (classic)"
6. Give it a descriptive name (e.g., "TeachingSpace Repo")
7. Select scopes:
   - ✓ `repo` (Full control of private repositories)
   - ✓ `workflow` (if you plan to use GitHub Actions)
8. Click "Generate token"
9. **IMPORTANT**: Copy the token immediately (you won't see it again!)

## Step 2: Set Environment Variable

### On Windows (PowerShell):
```powershell
$env:GIT_API_KEY = 'your_token_here'
```

### On Windows (CMD):
```cmd
set GIT_API_KEY=your_token_here
```

### On macOS/Linux (Bash):
```bash
export GIT_API_KEY='your_token_here'
```

### Make it Permanent (Optional):

**Windows:**
1. Open System Properties → Advanced → Environment Variables
2. Add new User Variable:
   - Variable name: `GIT_API_KEY`
   - Variable value: your token

**macOS/Linux:**
Add to `~/.bashrc` or `~/.zshrc`:
```bash
export GIT_API_KEY='your_token_here'
```

## Step 3: Run the Setup Script

### Option A: Use Python Script (Recommended)
```bash
cd C:\VSWork\TeachingSpace
python create_github_repo.py
```

### Option B: Use Bash Script
```bash
cd C:\VSWork\TeachingSpace
bash create_github_repo.sh
```

### Option C: Manual Setup

If the scripts don't work, you can set it up manually:

1. **Create repository on GitHub**:
   - Go to https://github.com/new
   - Repository name: `TeachingSpace`
   - Description: "Python Learning Platform with Jupyter-style notebook interface, coding exercises, and auto-grading system"
   - Choose Public or Private
   - **DO NOT** initialize with README (we already have one)
   - Click "Create repository"

2. **Add remote and push**:
   ```bash
   cd C:\VSWork\TeachingSpace
   git remote add origin https://github.com/besttea/TeachingSpace.git
   git branch -M main
   git push -u origin main
   ```

3. **If prompted for credentials**:
   - Username: `besttea`
   - Password: Use your Personal Access Token (not your GitHub password!)

## Step 4: Verify

Visit your repository at:
```
https://github.com/besttea/TeachingSpace
```

You should see all your code, including:
- README.md
- All Django apps (accounts, learning, training)
- Templates and static files
- Configuration files

## Troubleshooting

### Error: "remote origin already exists"
```bash
git remote remove origin
git remote add origin https://github.com/besttea/TeachingSpace.git
```

### Error: "Repository already exists"
The repository name is taken. Either:
- Delete the existing repository on GitHub
- Use a different name in the script

### Error: Authentication failed
- Make sure you're using the Personal Access Token, not your GitHub password
- Check that the token has the correct scopes (`repo`)
- Verify the token is still valid on GitHub

### Error: "This repository is empty"
Make sure you have at least one commit:
```bash
git log  # Should show your commits
```

## What's Next?

After successfully pushing to GitHub:

1. **Add collaborators** (if needed):
   - Go to repository Settings → Collaborators
   - Add team members

2. **Set up branch protection** (recommended):
   - Settings → Branches → Add rule
   - Protect `main` branch
   - Require pull request reviews

3. **Configure GitHub Pages** (optional):
   - Settings → Pages
   - Deploy documentation or demo

4. **Add GitHub Actions** (optional):
   - Set up CI/CD for automated testing
   - Auto-deployment workflows

## Support

If you encounter issues:
1. Check that Git is properly installed: `git --version`
2. Verify your GitHub token is valid
3. Ensure you have internet connectivity
4. Check GitHub status: https://www.githubstatus.com/

## Security Notes

⚠️ **IMPORTANT**:
- **NEVER** commit your Personal Access Token to the repository
- The `.gitignore` file already excludes `.env` files
- Keep your token secure and rotate it periodically
- If you accidentally expose your token, revoke it immediately on GitHub

---

For more information:
- [GitHub Documentation](https://docs.github.com)
- [Git Documentation](https://git-scm.com/doc)
- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
