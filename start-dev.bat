## 该文件编码并非异常，docker程序可读，不要进行修改，否则项目本地启动会报错。
@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo  ��ƱͶ��ϵͳ - ���ؿ���һ������
echo ==========================================

echo [1/3] ��� .env.docker ...
if not exist ".env.docker" (
  echo   - δ�ҵ����� .env.docker.example ����
  copy ".env.docker.example" ".env.docker" >nul
)

echo [2/3] ����ɿ����������������ݾ�...
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml down --remove-orphans 2>nul

echo [3/3] ��������������ջ���״ι����� pip/npm ��װ�������ĵȴ���...
docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d --build

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
