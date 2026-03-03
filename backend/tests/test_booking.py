import threading


class SlotStore:
    def __init__(self):
        self.booked = False
        self.lock = threading.Lock()

    def book(self):
        with self.lock:
            if self.booked:
                return False
            self.booked = True
            return True


def test_concurrent_slot_booking_one_success():
    store = SlotStore()
    results = []

    def worker():
        results.append(store.book())

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count(True) == 1
    assert results.count(False) == 1