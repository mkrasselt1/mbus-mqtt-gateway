import time

class MBusClient:
    def __init__(self, port):
        self.port = port

    def read_data(self):
        # Simulate reading data from M-Bus
        return {"temperature": 22.5, "humidity": 40}

    def start(self):
        while True:
            data = self.read_data()
            print(f"Read data from M-Bus: {data}")
            time.sleep(5)
