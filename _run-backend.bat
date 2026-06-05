@echo off
chcp 65001 >nul
title 电台后端 :8000  -  关闭此窗口=停止
set PYTHONUTF8=1
cd /d E:\AI电台项目\ai-radio\backend
"E:\AI电台项目\ai-radio\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
