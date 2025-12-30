import asyncio
import time
import random

# simula o esp_hub real
class MockEspHub:
    async def broadcast_text(self, cmd: str):
        print(f"[ESP] {cmd}")

    def set_last_vu(self, cmd: str):
        pass

    def set_last_ct(self, cmd: str):
        pass


async def mock_presentation(esp):
    print("== MOCK PRESENTATION START ==")

    # liga desenhos
    await esp.broadcast_text("FX:DRAW:ON")
    await esp.broadcast_text("FX:DRAW:EYES:ON")

    # simula VU subindo e descendo
    for i in range(3):
        for v in range(0, 35, 3):
            await esp.broadcast_text(f"VU:{v}")
            await asyncio.sleep(0.08)

        # boca falando
        await esp.broadcast_text("FX:DRAW:TALK:ON")
        await asyncio.sleep(1.2)
        await esp.broadcast_text("FX:DRAW:TALK:OFF")

        for v in range(35, 0, -4):
            await esp.broadcast_text(f"VU:{v}")
            await asyncio.sleep(0.08)

    # desliga olhos
    await esp.broadcast_text("FX:DRAW:EYES:OFF")

    # final
    await esp.broadcast_text("FX:DRAW:OFF")
    await esp.broadcast_text("VU:0")

    print("== MOCK PRESENTATION END ==")


async def mock_fx_show(esp):
    print("== MOCK FX SHOW ==")

    await esp.broadcast_text("FX:AUTO")
    await asyncio.sleep(1)

    await esp.broadcast_text("FX:STAR")
    for _ in range(40):
        await esp.broadcast_text(f"VU:{random.randint(5, 30)}")
        await asyncio.sleep(0.1)

    await esp.broadcast_text("FX:SNOW")
    for _ in range(40):
        await esp.broadcast_text(f"VU:{random.randint(5, 45)}")
        await asyncio.sleep(0.1)

    await esp.broadcast_text("FX:IDLE")
    await esp.broadcast_text("VU:0")

    print("== MOCK FX END ==")


async def main():
    esp = MockEspHub()

    # primeiro testa FX normais
    await mock_fx_show(esp)

    # depois testa apresentação
    await asyncio.sleep(2)
    await mock_presentation(esp)


if __name__ == "__main__":
    asyncio.run(main())