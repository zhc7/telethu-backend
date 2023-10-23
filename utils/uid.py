from threading import Lock


class IdMaker:
    def __init__(self):
        self.lock = Lock()
        self.id = 0

    def get_id(self):
        with self.lock:
            self.id += 1
        return self.id


globalIdMaker = IdMaker()
