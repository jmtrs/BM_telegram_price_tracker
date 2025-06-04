import pytest
import asyncio
from prometheus_client import generate_latest
import scraper.core as core
from tasks.checker import check_alerts_periodically
from asyncio import Event

@pytest.mark.asyncio
async def test_metrics_exposure():
    # Incrementar métricas
    core.scraper_success_counter.inc()
    core.scraper_failure_counter.inc(2)
    core.scraper_incomplete_counter.inc(3)
    core.scraper_in_flight_gauge.inc()
    with core.scraper_duration_seconds.time():
        pass

    # Obtener texto de métricas
    metrics_text = generate_latest().decode()
    assert 'scraper_success_total' in metrics_text
    assert 'scraper_failure_total' in metrics_text
    assert 'scraper_incomplete_total' in metrics_text
    assert 'scraper_in_flight' in metrics_text
    assert 'scraper_duration_seconds_bucket' in metrics_text

@pytest.mark.asyncio
async def test_shutdown_interrupts_checker():
    class DummyApp:
        def __init__(self):
            self.bot = None

    shutdown_event = Event()
    shutdown_event.set()
    # Debe terminar rápidamente sin error
    await check_alerts_periodically(DummyApp(), shutdown_event)

@pytest.mark.asyncio
async def test_concurrency_limit():
    sem = core.scraper_semaphore
    concurrency = 0
    max_concurrency = 0

    async def worker():
        nonlocal concurrency, max_concurrency
        async with sem:
            concurrency += 1
            max_concurrency = max(max_concurrency, concurrency)
            await asyncio.sleep(0.1)
            concurrency -= 1

    # Iniciar más tareas que el límite
    task_count = sem._value * 2
    tasks = [asyncio.create_task(worker()) for _ in range(task_count)]
    await asyncio.gather(*tasks)
    assert max_concurrency <= sem._value

@pytest.mark.asyncio
async def test_circuit_breaker_db(monkeypatch):
    # Prueba básica de funciones de circuito breaker (requiere DB configurada)
    from db.queries import set_host_circuit_break, get_active_host_circuits, cleanup_expired_host_circuits
    # Limpiar registros expirados
    await asyncio.to_thread(cleanup_expired_host_circuits)
    # Establecer un nuevo breaker que expire en el futuro
    from datetime import datetime, timedelta
    host = 'example.com'
    until_ts = datetime.utcnow() + timedelta(hours=1)
    await asyncio.to_thread(set_host_circuit_break, host, until_ts)
    active = await asyncio.to_thread(get_active_host_circuits)
    assert host in active
    # Limpiar expirados (no eliminará este registro)
    deleted = await asyncio.to_thread(cleanup_expired_host_circuits)
    assert deleted == 0
    # Forzar expiración y limpiar
    past_ts = datetime.utcnow() - timedelta(hours=1)
    await asyncio.to_thread(set_host_circuit_break, host, past_ts)
    deleted2 = await asyncio.to_thread(cleanup_expired_host_circuits)
    assert deleted2 >= 1
