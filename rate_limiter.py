import asyncio
import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class RateLimiter:
    def __init__(self):
        self.max_per_minute = int(os.getenv("MAX_QUERIES_PER_MINUTE", 4))
        self.max_per_hour = int(os.getenv("MAX_QUERIES_PER_HOUR", 60))
        self.max_per_day = int(os.getenv("MAX_QUERIES_PER_DAY", 500))
        self.min_delay = int(os.getenv("MIN_DELAY_BETWEEN_QUERIES", 8))
        self.max_delay = int(os.getenv("MAX_DELAY_BETWEEN_QUERIES", 20))
        
        self.simulate_sleep = os.getenv("SIMULATE_SLEEP_HOURS", "true").lower() == "true"
        self.sleep_start = int(os.getenv("SLEEP_START_HOUR", 1))
        self.sleep_end = int(os.getenv("SLEEP_END_HOUR", 7))
        
        self.requests = []
        self._lock = asyncio.Lock()
        self.consecutive_errors = 0
        self.throttle_multiplier = 1.0

    def is_sleep_time(self, hour):
        if self.sleep_start < self.sleep_end:
            return self.sleep_start <= hour < self.sleep_end
        else:
            return hour >= self.sleep_start or hour < self.sleep_end

    def report_error(self):
        self.consecutive_errors += 1
        self.throttle_multiplier = min(10.0, self.throttle_multiplier * 1.5)

    def report_success(self):
        self.consecutive_errors = 0
        self.throttle_multiplier = 1.0

    async def wait_if_needed(self):
        while True:
            sleep_time = 0
            async with self._lock:
                now = datetime.now()
                
                # Check sleep hours
                if self.simulate_sleep and self.is_sleep_time(now.hour):
                    wake_time = now.replace(hour=self.sleep_end, minute=0, second=0)
                    if wake_time <= now:
                        wake_time += timedelta(days=1)
                    sleep_time = (wake_time - now).total_seconds()
                
                if sleep_time == 0:
                    # Clean up old requests
                    self.requests = [req for req in self.requests if req > now - timedelta(days=1)]
                    
                    minute_count = len([req for req in self.requests if req > now - timedelta(minutes=1)])
                    hour_count = len([req for req in self.requests if req > now - timedelta(hours=1)])
                    day_count = len(self.requests)
                    
                    if minute_count >= self.max_per_minute or hour_count >= self.max_per_hour or day_count >= self.max_per_day:
                        sleep_time = 10.0 # Wait 10s before checking limits again

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            else:
                break
                
        # Apply random delay
        base_delay = random.uniform(self.min_delay, self.max_delay)
        delay = base_delay * self.throttle_multiplier
        await asyncio.sleep(delay)
        
        async with self._lock:
            self.requests.append(datetime.now())
            
        return delay

    def get_stats(self):
        now = datetime.now()
        return {
            "last_minute": len([req for req in self.requests if req > now - timedelta(minutes=1)]),
            "last_hour": len([req for req in self.requests if req > now - timedelta(hours=1)]),
            "last_day": len(self.requests),
            "consecutive_errors": self.consecutive_errors,
            "throttle_multiplier": self.throttle_multiplier,
            "is_sleeping": self.is_sleep_time(now.hour) if self.simulate_sleep else False
        }
