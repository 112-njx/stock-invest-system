## 该文件编码并非异常，docker程序可读，不要进行修改，否则项目本地启动会报错。
@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo  ��ƱͶ��ϵͳ - ���ؿ���һ������
echo ==========================================

echo [1/4] ��� .env.docker ...
if not exist ".env.docker" (
  echo   - δ�ҵ����� .env.docker.example ����
  copy ".env.docker.example" ".env.docker" >nul
)

echo [2/4] ����ɿ����������������ݾ�...
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml down --remove-orphans 2>nul

echo [3/4] ��������������ջ���״ι����� pip/npm ��װ�������ĵȴ���...
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d --build

echo [4/4] Seed initial data from local PostgreSQL (auto-skip if container already has data) ...
if exist "stock_backend\.venv\Scripts\python.exe" (
  "stock_backend\.venv\Scripts\python.exe" deploy\seed_from_local.py
) else (
  echo   - backend venv not found, skip seeding.
)

echo.
echo ==========================================
echo  [���] ��� API : http://127.0.0.1:8000
echo  [���] ǰ��ҳ�� : http://127.0.0.1:8081
echo ==========================================
echo �鿴��־:
echo   docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml logs -f api
echo ֹͣ����:
echo   docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml down
echo ==========================================
pause
