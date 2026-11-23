"""TCP forwarder 10.7.0.1:1883 -> 127.0.0.1:1883 (lets devices reach the broker through
the X1 emulated link without restarting the broker used by other experiments)."""
import asyncio
async def pipe(r, w):
    try:
        while (d := await r.read(65536)): w.write(d); await w.drain()
    except Exception: pass
    finally:
        try: w.close()
        except Exception: pass
async def handle(cr, cw):
    try: br, bw = await asyncio.open_connection("127.0.0.1", 1883)
    except Exception: cw.close(); return
    await asyncio.gather(pipe(cr, bw), pipe(br, cw))
async def main():
    s = await asyncio.start_server(handle, "10.7.0.1", 1883); await s.serve_forever()
asyncio.run(main())
