#!/usr/bin/env python3
"""Read-only BLE ELM327 probe for Vgate iCar Pro. Run while parked."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from bleak import BleakClient, BleakScanner

NOTIFY_UUID = "00002af0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "00002af1-0000-1000-8000-00805f9b34fb"
COMMANDS = ["ATI", "0100", "ATDP", "ATDPN", "0120", "0140", "0900", "0902", "090A"]
CAPTURES = Path(__file__).resolve().parents[1] / "captures"


async def main():
    print("Scanning for Vgate BLE (10 seconds)...")
    devices = await BleakScanner.discover(timeout=10)
    matches = [d for d in devices if any(k in (d.name or "").lower() for k in ("vlink", "vgate", "icar"))]
    if not matches:
        print("No Vgate device found. Available named BLE devices:")
        for d in devices:
            if d.name:
                print(" -", d.name, d.address)
        return
    for i, device in enumerate(matches):
        print(f"{i}: {device.name} ({device.address})")
    index = int(input("Choose adapter number: "))
    if not 0 <= index < len(matches):
        raise ValueError("Invalid selection")

    records = []
    buffer = bytearray()
    done = asyncio.Event()

    def notify(_sender, data):
        buffer.extend(data)
        if b">" in buffer:
            done.set()

    async with BleakClient(matches[index], timeout=20) as client:
        await client.start_notify(NOTIFY_UUID, notify)

        async def ask(command, timeout=15):
            buffer.clear()
            done.clear()
            sent = datetime.now(timezone.utc).isoformat()
            await client.write_gatt_char(WRITE_UUID, (command + "\r").encode("ascii"), response=False)
            try:
                await asyncio.wait_for(done.wait(), timeout=timeout)
                status = "ok"
            except asyncio.TimeoutError:
                status = "timeout"
            raw = buffer.decode("ascii", errors="replace")
            records.append({"timestamp": sent, "command": command, "status": status, "raw": raw})
            print(f"{command}: {status}: {raw.strip()[:240]}")
            return raw

        for command in ("ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"):
            await ask(command)
            await asyncio.sleep(0.3)
        for command in COMMANDS:
            await ask(command, timeout=30 if command == "0100" else 15)
            await asyncio.sleep(0.2)
        await client.stop_notify(NOTIFY_UUID)

    CAPTURES.mkdir(parents=True, exist_ok=True)
    path = CAPTURES / ("obd-probe-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(json.dumps({"vehicle": "Mercedes GLB X247 2020", "adapter": matches[index].name,
                                "records": records}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Saved locally:", path)
    print("WARNING: VIN may be present. Redact identifiers before sharing.")


if __name__ == "__main__":
    asyncio.run(main())
