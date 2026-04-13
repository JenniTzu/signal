# ==========================================
# SIGNAL 排程設定腳本 (最終正確版)
# 請務必以「系統管理員身分」執行此檔案
# ==========================================

$taskName    = "SIGNAL_Daily"
$batPath     = "C:\Users\USER\Desktop\03_signal\run_signal.bat"
$triggerTime = "08:00AM"

# 1. 設定執行的動作 (執行指定的 .bat 檔)
$action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""

# 2. 設定觸發時間 (每天早上 8:00)
$trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime

# 3. 設定排程細節 (包含：如果 8:00 沒開機，下次開機後儘快補執行)
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries

# 4. 正式註冊/建立排程
Register-ScheduledTask `
    -TaskName $taskName `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

# 5. 顯示提示資訊
Write-Host ""
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host " [成功] 排程設定完成！" -ForegroundColor Green
Write-Host " 每天早上 8:00 自動執行 SIGNAL" -ForegroundColor Green
Write-Host " (註：若 8:00 沒開機，將於下次開機進入桌面後自動補執行)" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------" -ForegroundColor Cyan
Write-Host ""
Write-Host "常用檢查指令："
Write-Host "  查看排程：Get-ScheduledTask -TaskName $taskName"
Write-Host "  手動執行：Start-ScheduledTask -TaskName $taskName"
Write-Host "  刪除排程：Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
Write-Host ""

pause