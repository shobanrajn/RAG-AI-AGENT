import threading

stop_lock = threading.Lock()
stop_requested = False


def request_stop() -> None:
    global stop_requested
    with stop_lock:
        stop_requested = True


def reset_stop() -> None:
    global stop_requested
    with stop_lock:
        stop_requested = False


def is_stop_requested() -> bool:
    with stop_lock:
        return stop_requested
