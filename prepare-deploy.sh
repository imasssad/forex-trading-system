#!/bin/bash
# Pre-deployment commit and push script

echo "📝 Preparing code for deployment..."

# Check if there are uncommitted changes
if [[ -n $(git status -s) ]]; then
    echo "Found uncommitted changes:"
    git status -s
    echo ""
    read -p "Commit message: " commit_message
    
    if [ -z "$commit_message" ]; then
        echo "❌ Commit message cannot be empty"
        exit 1
    fi
    
    git add .
    git commit -m "$commit_message"
    echo "✓ Changes committed"
else
    echo "✓ No uncommitted changes"
fi

# Ask for push
read -p "Push to remote? (y/n): " push_confirm
if [ "$push_confirm" == "y" ]; then
    git push origin main || git push origin master
    echo "✓ Code pushed to remote"
else
    echo "⚠ Code not pushed. Remember to push before deploying!"
fi

echo ""
echo "🎯 Next steps:"
echo "1. Connect to server via Termius"
echo "2. Upload deploy.sh: scp deploy.sh user@your-domain.com:/tmp/"
echo "3. Run: chmod +x /tmp/deploy.sh && sudo /tmp/deploy.sh"
echo ""
echo "Or follow manual steps in DEPLOYMENT.md"
