# 🚀 Safe Deployment Guide for Digital Ocean

## 📋 Pre-Deployment Checklist

Before deploying, ensure:
- [ ] All changes are committed to git
- [ ] Backend is tested locally
- [ ] Frontend is tested locally
- [ ] You have SSH access via Termius
- [ ] You know your project directory path on server
- [ ] You have sudo access (if using systemd)

---

## 🔄 Deployment Methods

### Method 1: Using the Deploy Script (Recommended)

1. **Upload the deploy script to your server:**
   ```bash
   # From your local machine, upload via scp
   scp deploy.sh user@your-domain.com:/tmp/deploy.sh
   ```

2. **Connect to server via Termius**

3. **Make script executable and run:**
   ```bash
   chmod +x /tmp/deploy.sh
   sudo /tmp/deploy.sh
   ```

---

### Method 2: Manual Deployment (Step-by-Step)

#### Step 1: Connect via Termius
Connect to your Digital Ocean droplet

#### Step 2: Navigate to project directory
```bash
cd /var/www/backend  # Backend directory
```

#### Step 3: Create backup
```bash
timestamp=$(date +%Y%m%d_%H%M%S)
mkdir -p ~/forex-backups
tar -czf ~/forex-backups/backend_backup_$timestamp.tar.gz -C /var/www/backend .
tar -czf ~/forex-backups/frontend_backup_$timestamp.tar.gz -C /var/www/frontend .
echo "Backups created in ~/forex-backups/"
```

#### Step 4: Save .env file
```bash
cp /var/www/backend/.env /tmp/.env.backup
```

#### Step 5: Pull latest code
```bash
cd /var/www/backend
git fetch origin
git status  # Check current state
git pull origin main  # or 'master' depending on your branch

cd /var/www/frontend
git pull origin main  # or 'master'
```

#### Step 6: Restore .env
```bash
cp /tmp/.env.backup /var/www/backend/.env
```

#### Step 7: Update backend dependencies
```bash
cd /var/www/backend
source venv/bin/activate
pip install -r requirements.txt
```

#### Step 8: Update frontend dependencies and build
```bash
cd /var/www/frontend
npm install
npm run build
```

#### Step 9: Restart services

**If using systemd:**
```bash
sudo systemctl restart forex-backend
sudo systemctl restart forex-frontend
# Or restart nginx if frontend is static
sudo systemctl restart nginx
```

**If using PM2:**
```bash
pm2 restart forex-backend
pm2 restart forex-frontend
pm2 save
```

**If using standalone processes:**
```bash
# Find and kill existing processes
pkill -f "uvicorn server.api:app"
pkill -f "npm run dev"  # or next start

# Start backend
cd /var/www/backend
source venv/bin/activate
nohup uvicorn server.api:app --host 0.0.0.0 --port 8000 > logs/backend.log 2>&1 &

# Start frontend (if not using nginx for static files)
cd /var/www/frontend
nohup npm run start > logs/frontend.log 2>&1 &
```

#### Step 10: Verify deployment
```bash
# Check backend
curl http://localhost:8000/api/status | jq

# Check processes
ps aux | grep uvicorn
ps aux | grep node

# Check logs
tail -f logs/backend.log
```

#### Step 11: Test from browser
Visit your domain and verify:
- [ ] Dashboard loads
- [ ] Backend API is responding
- [ ] SSL certificate is working
- [ ] No console errors

---

## 🔧 Service Configuration Files

### Backend Systemd Service
If you need to create/update: `/etc/systemd/system/forex-backend.service`

```ini
[Unit]
Description=Forex Trading Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/backend
Environment="PATH=/var/www/backend/venv/bin"
ExecStart=/var/www/backend/venv/bin/uvicorn server.api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Frontend Systemd Service (if not using nginx static)
If you need to create/update: `/etc/systemd/system/forex-frontend.service`

```ini
[Unit]
Description=Forex Trading Frontend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/frontend
Environment="PATH=/usr/bin:/usr/local/bin"
Environment="NODE_ENV=production"
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

After creating services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable forex-backend
sudo systemctl enable forex-frontend
sudo systemctl start forex-backend
sudo systemctl start forex-frontend
```

---

## 🆘 Rollback Procedure

If something goes wrong:

```bash
# Stop services first
sudo systemctl stop forex-backend forex-frontend

# Restore from backup
cd /var/www/backend
tar -xzf ~/forex-backups/backend_backup_TIMESTAMP.tar.gz

cd /var/www/frontend
tar -xzf ~/forex-backups/frontend_backup_TIMESTAMP.tar.gz

# Restart services
sudo systemctl start forex-backend forex-frontend
```

---

## 📊 Post-Deployment Verification

### Check Backend Health
```bash
curl http://localhost:8000/api/status
```

Should return:
```json
{
  "bot_running": true,
  "signal_generation_running": true,
  ...
}
```

### Check Frontend
```bash
curl http://localhost:3001  # or your configured port
# Should return HTML
```

### Check Logs
```bash
# Backend logs
sudo journalctl -u forex-backend -f

# Frontend logs
sudo journalctl -u forex-frontend -f

# Nginx logs (if using nginx)
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Check Process Status
```bash
sudo systemctl status forex-backend
sudo systemctl status forex-frontend
sudo systemctl status nginx
```

---

## ⚠️ Important Notes

1. **Database**: SQLite database at `/var/www/backend/data/ats_trading.db` is preserved during deployment
2. **Environment Variables**: `.env` file is backed up and restored
3. **SSL Certificates**: Not affected by code deployment
4. **Domain Configuration**: nginx config remains unchanged
5. **Open Trades**: Active OANDA trades are not affected

---

## 🔍 Troubleshooting

### Backend won't start
```bash
# Check for port conflicts
sudo lsof -i :8000

# Check Python environment
cd /var/www/forex-trading/backend
source venv/bin/activate
python -c "import fastapi; print('FastAPI OK')"

# Check logs
sudo journalctl -u forex-backend -n 50
```

### Frontend won't start
```bash
# Check for port conflicts
sudo lsof -i :3001

# Rebuild frontend
cd /var/www/forex-trading/frontend
npm run build

# Check nginx config
sudo nginx -t
```

### Database issues
```bash
cd /var/www/forex-trading/backend
source venv/bin/activate
python -c "from database import db; db.init_db()"
```

---

## 📞 Quick Commands Reference

```bash
# Check all services
sudo systemctl status forex-backend forex-frontend nginx

# Restart all
sudo systemctl restart forex-backend forex-frontend nginx

# View logs
sudo journalctl -f  # All logs
sudo journalctl -u forex-backend -f  # Backend only

# Check processes
ps aux | grep -E "uvicorn|node|nginx"

# Test API
curl http://localhost:8000/api/status | jq

# Check disk space
df -h

# Check memory
free -h
```

---

## ✅ Success Indicators

After deployment, you should see:
- ✓ Backend returns status at `/api/status`
- ✓ Frontend loads at your domain
- ✓ SSL shows green padlock
- ✓ No errors in browser console
- ✓ Toast notifications working
- ✓ News panel buttons working
- ✓ Activity log expanding
- ✓ Signals generating (check after 5 minutes)
- ✓ OANDA trades syncing correctly
