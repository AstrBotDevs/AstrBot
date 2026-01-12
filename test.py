import boxlite


async def boot(session_id: str) -> None:
    box = boxlite.SimpleBox(
        image="soulter/shipyard-ship",
        memory_mib=512,
        cpus=1,
        ports=[{
            "host_port": 12345,
            "guest_port": 8123,
        }],
    )

    await box.start()


if __name__ == "__main__":
    import asyncio

    asyncio.run(boot("test-session"))
