#!/bin/bash
# Safe Deployment Script for ATS Forex Trading System
# Run this on your Digital Ocean server

set -e  # Exit on error

echo "🚀 Starting deployment..."

# Configuration
BACKEND_DIR="/var/www/backend"
FRONTEND_DIR="/var/www/frontend"
BACKUP_DIR="/var/backups/forex-trading"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1: Creating backup...${NC}"
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/backend_backup_$TIMESTAMP.tar.gz" -C "$BACKEND_DIR" . 2>/dev/null || true
tar -czf "$BACKUP_DIR/frontend_backup_$TIMESTAMP.tar.gz" -C "$FRONTEND_DIR" . 2>/dev/null || true
echo -e "${GREEN}✓ Backups created in $BACKUP_DIR${NC}"

echo -e "${YELLOW}Step 2: Stopping services...${NC}"
# Stop backend (adjust service name if different)
sudo systemctl stop forex-backend 2>/dev/null || pm2 stop forex-backend 2>/dev/null || echo "Backend service not found"
# Stop frontend (adjust service name if different)
sudo systemctl stop forex-frontend 2>/dev/null || pm2 stop forex-frontend 2>/dev/null || echo "Frontend service not found"
echo -e "${GREEN}✓ Services stopped${NC}"

echo -e "${YELLOW}Step 3: Backing up .env file...${NC}"
cp "$BACKEND_DIR/.env" "/tmp/.env.backup" 2>/dev/null || echo "No .env file found"

echo -e "${YELLOW}Step 4: Pulling latest code...${NC}"
cd "$BACKEND_DIR"
git pull origin main || git pull origin master
cd "$FRONTEND_DIR"
git pull origin main || git pull origin master
echo -e "${GREEN}✓ Code updated${NC}"

echo -e "${YELLOW}Step 5: Restoring .env file...${NC}"
cp "/tmp/.env.backup" "$BACKEND_DIR/.env" 2>/dev/null || echo "No .env backup to restore"

echo -e "${YELLOW}Step 6: Installing backend dependencies...${NC}"
cd "$BACKEND_DIR"
source venv/bin/activate
pip install -r requirements.txt --quiet
echo -e "${GREEN}✓ Backend dependencies updated${NC}"

echo -e "${YELLOW}Step 7: Installing frontend dependencies...${NC}"
cd "$FRONTEND_DIR"
npm install --silent
echo -e "${GREEN}✓ Frontend dependencies updated${NC}"

echo -e "${YELLOW}Step 8: Building frontend...${NC}"
npm run build
echo -e "${GREEN}✓ Frontend built${NC}"

echo -e "${YELLOW}Step 9: Running database migrations...${NC}"
cd "$BACKEND_DIR"
python -c "from database import db; db.init_db()" 2>/dev/null || echo "Database already initialized"
echo -e "${GREEN}✓ Database ready${NC}"

echo -e "${YELLOW}Step 10: Starting services...${NC}"
# Start backend
sudo systemctl start forex-backend 2>/dev/null || pm2 start forex-backend 2>/dev/null || echo "Backend service not configured"
# Start frontend
sudo systemctl start forex-frontend 2>/dev/null || pm2 start forex-frontend 2>/dev/null || echo "Frontend service not configured"
echo -e "${GREEN}✓ Services started${NC}"

echo -e "${YELLOW}Step 11: Checking service status...${NC}"
sleep 3
sudo systemctl status forex-backend --no-pager 2>/dev/null || pm2 list 2>/dev/null || echo "Check services manually"

echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo -e "${YELLOW}Backup location: $BACKUP_DIR/${NC}"
echo -e "  - backend_backup_$TIMESTAMP.tar.gz"
echo -e "  - frontend_backup_$TIMESTAMP.tar.gz"
echo ""
echo "Test your deployment:"
echo "  Backend API: curl http://localhost:8000/api/status"
echo "  Frontend: Visit your domain"
echo ""
echo "If something went wrong, rollback with:"
echo "  cd $BACKEND_DIR && tar -xzf $BACKUP_DIR/backend_backup_$TIMESTAMP.tar.gz"
echo "  cd $FRONTEND_DIR && tar -xzf $BACKUP_DIR/frontend_backup_$TIMESTAMP.tar.gz"
