@echo off
chcp 65001 >nul
title QQ音乐服务 :8080  -  关闭此窗口=停止
set PYTHONUTF8=1
cd /d E:\AI电台项目\third_party\QQMusicApi
"E:\AI电台项目\ai-radio\.venv\Scripts\python.exe" web\run.py
