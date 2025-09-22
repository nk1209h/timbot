@echo off
cd C:/Users/JELLY_CHOU/timbot 
echo === 檢查狀態 ===
git status

echo.
echo === 新增所有檔案 ===
git add .

echo.
set /p msg="請輸入這次 Commit 訊息（預設: Auto update）: "
if "%msg%"=="" set msg=Auto update

git commit -m "%msg%"

echo.
echo === 推送到 GitHub main 分支 ===
git push origin main

echo.
echo ✅ 已完成更新！
pause