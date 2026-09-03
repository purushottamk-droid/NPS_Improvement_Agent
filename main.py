"""
main.py — Run the full NPS Improvement Agent pipeline
"""
from dotenv import load_dotenv
load_dotenv()
import time
import asyncio
from scripts.SequentialAgent import workflow


async def run():
    print(f"\n── Running NPS Improvement pipeline ──\n")

    start_time = time.perf_counter()

    async for event in workflow.run_stream("start"):
        print(f"[event] {type(event).__name__}: {event}")

    end_time = time.perf_counter()
    print(f"\n⏱  Total pipeline time: {end_time - start_time:.2f} seconds")
    print("\n── Pipeline finished ──\n")


if __name__ == "__main__":
    asyncio.run(run())