# Deploy systemd service for RAMO bot
# Usage: ./deploy-systemd.ps1

$SERVER = "root@89.58.17.123"
$SERVICE_FILE = "C:\Users\user\Desktop\AMO\ramo-bot.service"
$REMOTE_SERVICE_PATH = "/etc/systemd/system/ramo-bot.service"

Write-Host "=== Deploying RAMO bot systemd service ===" -ForegroundColor Green

# 1. Copy service file to server
Write-Host "1. Copying service file to server..." -ForegroundColor Cyan
scp $SERVICE_FILE "${SERVER}:${REMOTE_SERVICE_PATH}"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to copy service file" -ForegroundColor Red
    exit 1
}

# 2. Reload systemd daemon
Write-Host "2. Reloading systemd daemon..." -ForegroundColor Cyan
ssh $SERVER "systemctl daemon-reload"

# 3. Enable and start the service
Write-Host "3. Enabling and starting service..." -ForegroundColor Cyan
ssh $SERVER "systemctl enable ramo-bot.service && systemctl start ramo-bot.service"

# 4. Verify service status
Write-Host "4. Checking service status..." -ForegroundColor Cyan
ssh $SERVER "systemctl status ramo-bot.service --no-pager"

Write-Host "`n=== Deployment complete ===" -ForegroundColor Green
Write-Host "Service enabled for auto-start on reboot" -ForegroundColor Green
Write-Host "`nTo monitor logs:" -ForegroundColor Yellow
Write-Host "ssh root@89.58.17.123 'journalctl -u ramo-bot.service -f'" -ForegroundColor Yellow
