# Windows PowerShell Deployment Preparation Script
# Run this before deploying to Digital Ocean

Write-Host "📝 Preparing code for deployment..." -ForegroundColor Cyan

# Check git status
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host "`nFound uncommitted changes:" -ForegroundColor Yellow
    git status -s
    Write-Host ""
    
    $commitMessage = Read-Host "Commit message"
    if ([string]::IsNullOrWhiteSpace($commitMessage)) {
        Write-Host "❌ Commit message cannot be empty" -ForegroundColor Red
        exit 1
    }
    
    git add .
    git commit -m $commitMessage
    Write-Host "✓ Changes committed" -ForegroundColor Green
} else {
    Write-Host "✓ No uncommitted changes" -ForegroundColor Green
}

# Confirm push
Write-Host ""
$pushConfirm = Read-Host "Push to remote repository? (y/n)"
if ($pushConfirm -eq "y") {
    try {
        git push origin main
    } catch {
        git push origin master
    }
    Write-Host "✓ Code pushed to remote" -ForegroundColor Green
} else {
    Write-Host "⚠ Code not pushed. Remember to push before deploying!" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎯 Next steps:" -ForegroundColor Cyan
Write-Host "1. Connect to server via Termius" -ForegroundColor White
Write-Host "2. Method A - Automatic:" -ForegroundColor Yellow
Write-Host "   - Upload deploy.sh to server" -ForegroundColor Gray
Write-Host "   - Run: chmod +x deploy.sh && sudo ./deploy.sh" -ForegroundColor Gray
Write-Host "3. Method B - Manual:" -ForegroundColor Yellow
Write-Host "   - Follow steps in DEPLOYMENT.md" -ForegroundColor Gray
Write-Host ""
Write-Host "📖 Full guide: See DEPLOYMENT.md" -ForegroundColor Cyan

# Create a quick reference file
$quickRef = @"
=== QUICK DEPLOYMENT REFERENCE ===

Your Changes:
- ✓ Fixed JPY decimal places (3 decimals instead of 5)
- ✓ Added automatic trade sync on startup
- ✓ Added toast notifications (replaced alerts)
- ✓ Fixed "Full Calendar" and "View All" buttons
- ✓ Enhanced error logging with OANDA details
- ✓ Prevent orphaned trade records

Key Files Modified:
- backend/brokers/oanda.py (JPY decimal fix)
- backend/core/signal_generator.py (trade sync logic)
- backend/server/api.py (startup sync + /api/trades/sync endpoint)
- frontend/src/components/panels/SignalsPanel.tsx (toast notifications)
- frontend/src/components/panels/NewsPanel.tsx (expand button)
- frontend/src/components/panels/ActivityPanel.tsx (expand button)
- frontend/tailwind.config.js (slide-in animation)

Database Changes:
- None (no schema changes, backward compatible)

Environment Variables:
- No changes to .env file needed

Post-Deployment Testing:
1. Check /api/status - should show signal_generation_running: true
2. Test toast notifications (click START/STOP buttons)
3. Test "Full Calendar →" button in News panel
4. Test "View All →" button in Activity Log
5. Wait for next USD_JPY signal (should execute successfully)
6. Verify no orphaned trades: POST /api/trades/sync

"@

$quickRef | Out-File -FilePath "DEPLOYMENT_SUMMARY.txt" -Encoding UTF8
Write-Host "✓ Created DEPLOYMENT_SUMMARY.txt for your reference" -ForegroundColor Green
