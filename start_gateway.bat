@echo off
REM llm-gateway v1 一键启动（Windows）
cd /d %~dp0
if not exist .env (
  copy .env.example .env
  echo 已从 .env.example 生成 .env，请先打开 .env 填上真实的 key 再启动。
  pause
  exit /b 1
)
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 4000
pause
