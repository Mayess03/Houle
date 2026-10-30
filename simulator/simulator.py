import os
import requests
import math
import random
import time
import uuid
from datetime import datetime, timezone

API_URL = os.getenv("API_URL", "http://backend:8000")
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "5"))

class BuoySimulator:
    def __init__(self, buoy_id, latitude, longitude, initial_battery=90.0):
        self.buoy_id = buoy_id
        self.anchor_latitude = latitude
        self.anchor_longitude = longitude

        self.latitude = latitude
        self.longitude = longitude

        self.battery = initial_battery
        self.wave_height = random.uniform(0.5, 2.0)

        self.start_time = time.monotonic()
        self.last_update = self.start_time

    def generate_measurement(self):
        now = time.monotonic()
        elapsed = now - self.last_update
        self.last_update = now

        # Simulate waves with a calm baseline, periodic variation and noise.
        t = now - self.start_time
        baseline = 1.2
        periodic_variation = 0.5 * math.sin(t / 20)
        noise = random.uniform(-0.15, 0.15)

        self.wave_height = max(
            0.1,
            self.wave_height * 0.7
            + (baseline + periodic_variation + noise) * 0.3,
        )

        # Simulate battery consumption and daytime solar charging.
        hour = datetime.now().hour
        solar_factor = max(0.0, math.sin(math.pi * (hour - 6) / 12))
        consumption = 0.002 * elapsed
        charging = 0.01 * solar_factor * elapsed

        self.battery = max(
            0.0,
            min(100.0, self.battery - consumption + charging),
        )

        # Simulate a small GPS drift around the anchor.
        self.latitude = self.anchor_latitude + random.uniform(-0.0002, 0.0002)
        self.longitude = self.anchor_longitude + random.uniform(-0.0002, 0.0002)

        return {
            "measurement_id": str(uuid.uuid4()),
            "buoy_id": self.buoy_id,
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "wave_height": round(self.wave_height, 2),
            "battery_level": round(self.battery, 2),
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
        }


def main():
    buoys = [
        BuoySimulator("buoy-001", 36.85, 10.50),
        BuoySimulator("buoy-002", 36.87, 10.53, initial_battery=65.0),
        BuoySimulator("buoy-003", 36.90, 10.55, initial_battery=11.0),
    ]

    print("Houle simulator started.")

    try:
        while True:
            for buoy in buoys:
                measurement = buoy.generate_measurement()

                try:
                    response = requests.post(
                        f"{API_URL}/measurements",
                        json=measurement,
                        timeout=5,
                    )
                    response.raise_for_status()
                    print(f"Sent: {measurement['measurement_id']} - {response.json()}")

                except requests.RequestException as error:
                    print(f"Failed to send measurement: {error}")

            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("Simulator stopped.")



if __name__ == "__main__":
    main()
