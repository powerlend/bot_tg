"""Сторінка здоров'я та самопінг для безкоштовного хостингу (Render).

Render вимагає, щоб веб-сервіс слухав порт, а безкоштовний сервіс засинає після
15 хвилин без вхідних запитів. Тому бот:
  1) відповідає «ok» на запити за адресою /health (start_health_server);
  2) раз на кілька хвилин сам звертається до свого публічного посилання
     (keep_alive_loop), щоб Render бачив трафік і не присипляв сервіс.

Використовується лише стандартна бібліотека Python.
"""
import asyncio
import logging
import urllib.request

KEEPALIVE_INTERVAL = 480  # секунд (8 хвилин, менше за 15 хвилин простою)

_HEAD = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: close\r\n"
    b"\r\n"
)


async def _handle(reader, writer) -> None:
    """Відповідає «ok» на будь-який запит (GET або HEAD)."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5)
        # Дочитуємо заголовки до порожнього рядка (з обмеженням, щоб не зависнути)
        for _ in range(50):
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            if line in (b"\r\n", b"\n", b""):
                break
        method = request_line.split(b" ")[0].upper() if request_line else b""
        body = b"" if method == b"HEAD" else b"ok"
        writer.write(_HEAD + body)
        await writer.drain()
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def start_health_server(port: int):
    """Запускає мінімальний веб-сервер для перевірки здоров'я. Повертає сервер."""
    return await asyncio.start_server(_handle, "0.0.0.0", port)


def _ping(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "konspekt-bot-keepalive"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status


async def keep_alive_loop(base_url: str, interval: float = KEEPALIVE_INTERVAL) -> None:
    """Раз на interval секунд звертається до свого /health, щоб сервіс не засинав."""
    url = base_url.rstrip("/") + "/health"
    logging.info("Самопінг увімкнено: %s кожні %s с", url, int(interval))
    while True:
        await asyncio.sleep(interval)
        try:
            status = await asyncio.to_thread(_ping, url)
            logging.debug("Самопінг: %s", status)
        except Exception as error:
            logging.warning("Самопінг не вдався: %s", error)
