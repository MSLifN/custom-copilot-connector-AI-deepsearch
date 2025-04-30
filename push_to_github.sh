#!/bin/bash

# Script to push HR Assistant API project to GitHub
# This script will overwrite everything in the target repository

# Text colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Target GitHub repository
GITHUB_REPO="https://github.com/amir0135/restapi-demo.git"
MAIN_BRANCH="main"

echo -e "${YELLOW}Starting GitHub push process...${NC}"
echo -e "${YELLOW}Target: ${GITHUB_REPO}${NC}"
echo -e "${YELLOW}This will overwrite everything in the target repository.${NC}"
echo ""

# Confirm with the user
read -p "Do you want to proceed? (y/N): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo -e "${RED}Operation aborted.${NC}"
    exit 1
fi

# GitHub Authentication Notice
echo -e "${YELLOW}Note: This script assumes you have Git credentials set up via:${NC}"
echo -e "  - SSH keys configured"
echo -e "  - Git credential helper"
echo -e "  - GitHub CLI authentication"
echo -e "If you encounter authentication issues, you may need to authenticate first."
echo ""

# Initialize git repository
echo -e "${YELLOW}Initializing Git repository...${NC}"
git init

# Configure Git to handle line endings consistently
git config core.autocrlf input

# Add all files
echo -e "${YELLOW}Adding all files to Git...${NC}"
git add .

# Commit the changes
echo -e "${YELLOW}Committing changes...${NC}"
git commit -m "HR Assistant API with OpenAPI specification for Copilot Studio"

# Add the remote repository
echo -e "${YELLOW}Adding remote repository...${NC}"
git remote add origin $GITHUB_REPO

# Force push to overwrite everything on GitHub
echo -e "${YELLOW}Force pushing to ${MAIN_BRANCH} branch (this will overwrite everything)...${NC}"
git push -f origin $MAIN_BRANCH

# Check the result
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Success! The project has been pushed to ${GITHUB_REPO}${NC}"
    echo -e "${GREEN}All previous content has been replaced with the HR Assistant API project.${NC}"
else
    echo -e "${RED}Error pushing to GitHub. Please check your credentials and repository access.${NC}"
    echo -e "${YELLOW}You might need to use:${NC}"
    echo -e "  git push -f origin main:main"
    echo -e "${YELLOW}Or authenticate first with GitHub.${NC}"
fi