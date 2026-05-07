import argparse
import socket
import threading
import time

from src.core.config import MCAST_GRP, MCAST_PORT
from src.core.multicast_audio import MulticastReceiver, MulticastSender


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe UDP multicast connectivity.")
    parser.add_argument("--name", default=socket.gethostname(), help="name shown in probe packets")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between probe packets")
    args = parser.parse_args()

    sender_id = f"probe-{args.name}"
    sender = MulticastSender(sender_id=sender_id)
    receiver = MulticastReceiver()
    running = True

    def receive_loop() -> None:
        while running:
            payload, addr, header = receiver.recv()
            if not payload or not header:
                continue
            if header.get("sender") == sender_id:
                continue
            text = payload.decode("utf-8", errors="replace")
            print(f"[recv] from={header.get('sender')} addr={addr} payload={text}", flush=True)

    thread = threading.Thread(target=receive_loop, daemon=True)
    thread.start()

    print(f"[probe] multicast group={MCAST_GRP}:{MCAST_PORT} sender={sender_id}", flush=True)
    try:
        seq = 0
        while True:
            message = f"{sender_id} seq={seq} time={time.strftime('%H:%M:%S')}"
            sender.send(message.encode("utf-8"))
            print(f"[send] {message}", flush=True)
            seq += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        sender.close()
        receiver.close()


if __name__ == "__main__":
    main()
