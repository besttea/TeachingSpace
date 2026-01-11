# GitHub Repository Creation and Push Script
# This PowerShell script accesses the system GIT_API_KEY environment variable
# and creates the GitHub repository

Write-Host "=" -NoNewline; Write-Host ("=" * 59)
Write-Host "GitHub Repository Setup - Python Learning Platform"
Write-Host "=" -NoNewline; Write-Host ("=" * 59)

# Get the system environment variable
$token = [System.Environment]::GetEnvironmentVariable("GIT_API_KEY", "User")
if (-not $token) {
    $token = [System.Environment]::GetEnvironmentVariable("GIT_API_KEY", "Machine")
}
if (-not $token) {
    $token = $env:GIT_API_KEY
}

if (-not $token) {
    Write-Host "`nError: GIT_API_KEY environment variable not found" -ForegroundColor Red
    Write-Host "`nPlease set it with:" -ForegroundColor Yellow
    Write-Host '  [System.Environment]::SetEnvironmentVariable("GIT_API_KEY", "your_token", "User")' -ForegroundColor Cyan
    Write-Host "`nOr temporarily for this session:" -ForegroundColor Yellow
    Write-Host '  $env:GIT_API_KEY = "your_token"' -ForegroundColor Cyan
    exit 1
}

Write-Host "`nFound GIT_API_KEY (length: $($token.Length) characters)" -ForegroundColor Green

# Repository configuration
$repoName = "TeachingSpace"
$description = "Python Learning Platform with Jupyter-style notebook interface, coding exercises, and auto-grading system"
$private = $false

# Create GitHub repository using API
Write-Host "`nCreating GitHub repository: $repoName" -ForegroundColor Cyan

$headers = @{
    "Authorization" = "token $token"
    "Accept" = "application/vnd.github.v3+json"
}

$body = @{
    name = $repoName
    description = $description
    private = $private
    auto_init = $false
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "https://api.github.com/user/repos" `
        -Method Post `
        -Headers $headers `
        -Body $body `
        -ContentType "application/json"

    Write-Host "✓ Repository created successfully!" -ForegroundColor Green
    Write-Host "  Repository URL: $($response.html_url)" -ForegroundColor White
    Write-Host "  Clone URL: $($response.clone_url)" -ForegroundColor White

    $cloneUrl = $response.clone_url

    # Setup remote and push
    Write-Host "`nSetting up git remote..." -ForegroundColor Cyan

    # Remove existing remote if present
    $remoteExists = git remote get-url origin 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Removing existing remote 'origin'..." -ForegroundColor Yellow
        git remote remove origin
    }

    # Add new remote
    Write-Host "Adding remote origin..." -ForegroundColor Cyan
    git remote add origin $cloneUrl

    # Rename branch to main
    Write-Host "Renaming branch to main..." -ForegroundColor Cyan
    git branch -M main

    # Push to GitHub
    Write-Host "`nPushing to GitHub..." -ForegroundColor Cyan
    $pushOutput = git push -u origin main 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✓ Successfully pushed to GitHub!" -ForegroundColor Green
        Write-Host "`n" + ("=" * 60)
        Write-Host "Setup Complete!" -ForegroundColor Green
        Write-Host ("=" * 60)
        Write-Host "`nView your repository at:" -ForegroundColor Cyan
        Write-Host "https://github.com/besttea/$repoName" -ForegroundColor White
    } else {
        Write-Host "`n✗ Error pushing to GitHub:" -ForegroundColor Red
        Write-Host $pushOutput -ForegroundColor Yellow
    }

} catch {
    Write-Host "`n✗ Error creating repository:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow

    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host "`nAPI Response: $responseBody" -ForegroundColor Yellow
    }
    exit 1
}
