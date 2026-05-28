# ============================================================
# HELLENCOMMERCE 2.0.1 - Script de Inicio Rápido
# ============================================================
# PowerShell script para iniciar todos los servicios

param(
    [switch]$Build,
    [switch]$Stop,
    [switch]$Logs,
    [string]$Service
)

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  HellenCommerce 2.0.1 - Gestor de Inicio" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Función para verificar Docker
function Test-Docker {
    try {
        docker --version | Out-Null
        return $true
    } catch {
        return $false
    }
}

# Función para verificar Docker Compose
function Test-DockerCompose {
    try {
        docker-compose --version | Out-Null
        return $true
    } catch {
        docker compose version | Out-Null
        return $true
    }
}

# Verificar dependencias
if (-not (Test-Docker)) {
    Write-Host "❌ Error: Docker no está instalado o no está en el PATH" -ForegroundColor Red
    exit 1
}

if (-not (Test-DockerCompose)) {
    Write-Host "❌ Error: Docker Compose no está instalado" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Docker y Docker Compose detectados" -ForegroundColor Green
Write-Host ""

# Determinar comando de docker-compose
$COMPOSE_CMD = "docker-compose"
try {
    docker compose version | Out-Null
    $COMPOSE_CMD = "docker compose"
} catch {
    # Usar docker-compose clásico
}

# Detener servicios
if ($Stop) {
    Write-Host "🛑 Deteniendo todos los servicios..." -ForegroundColor Yellow
    & $COMPOSE_CMD down
    Write-Host "✅ Servicios detenidos" -ForegroundColor Green
    exit 0
}

# Ver logs
if ($Logs) {
    if ($Service) {
        Write-Host "📋 Mostrando logs de $Service..." -ForegroundColor Yellow
        & $COMPOSE_CMD logs -f $Service
    } else {
        Write-Host "📋 Mostrando logs de todos los servicios..." -ForegroundColor Yellow
        & $COMPOSE_CMD logs -f
    }
    exit 0
}

# Construir imágenes
if ($Build) {
    Write-Host "🔨 Construyendo imágenes Docker..." -ForegroundColor Yellow
    & $COMPOSE_CMD build --no-cache
    Write-Host "✅ Imágenes construidas" -ForegroundColor Green
}

# Iniciar servicios
Write-Host "🚀 Iniciando servicios..." -ForegroundColor Yellow
Write-Host ""

try {
    & $COMPOSE_CMD up -d
    
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  ✅ Servicios Iniciados Exitosamente" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "📍 Puntos de Acceso:" -ForegroundColor Cyan
    Write-Host "   • FastAPI Ingress:    http://localhost:8000" -ForegroundColor White
    Write-Host "   • Admin Dashboard:    http://localhost:3000" -ForegroundColor White
    Write-Host "   • Logging Service:    http://localhost:8099" -ForegroundColor White
    Write-Host ""
    Write-Host "🔗 WebSocket:" -ForegroundColor Cyan
    Write-Host "   • ws://localhost:8000/ws/{user_id}" -ForegroundColor White
    Write-Host ""
    Write-Host "📋 Comandos Útiles:" -ForegroundColor Cyan
    Write-Host "   • Ver logs:          .\start.ps1 -Logs" -ForegroundColor White
    Write-Host "   • Logs de servicio:  .\start.ps1 -Logs -Service fastapi_service" -ForegroundColor White
    Write-Host "   • Detener:           .\start.ps1 -Stop" -ForegroundColor White
    Write-Host "   • Rebuild:           .\start.ps1 -Build" -ForegroundColor White
    Write-Host ""
    Write-Host "🔍 Health Check:" -ForegroundColor Cyan
    Write-Host "   curl http://localhost:8000/health" -ForegroundColor White
    Write-Host ""
    
} catch {
    Write-Host ""
    Write-Host "❌ Error al iniciar servicios: $_" -ForegroundColor Red
    exit 1
}