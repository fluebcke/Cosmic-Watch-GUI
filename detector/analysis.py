from collections import deque


class DetectorAnalysis:

    def __init__(self):
        self.events = 0
        self.adc_values = []

        self.last_time = None
        self.time_differences = []

        self.start_time = None

        self.rate_window = deque()


    def add_event(self, event):

        # count
        self.events += 1

        # ADC spectrum
        self.adc_values.append(event.adc)

        # time differences
        if self.last_time is not None:
            dt = event.time_ms - self.last_time
            self.time_differences.append(dt)

        self.last_time = event.time_ms


        # rolling rate (last 10 seconds)
        self.rate_window.append(event.time_ms)

        while (
            self.rate_window[-1] - self.rate_window[0]
            > 10000
        ):
            self.rate_window.popleft()


    def get_rolling_rate(self):

        if len(self.rate_window) == 0:
            return 0

        return len(self.rate_window) / 10


    def summary(self):

        return {
            "events": self.events,
            "mean_adc": (
                sum(self.adc_values) / len(self.adc_values)
                if self.adc_values else 0
            ),
            "rolling_rate": self.get_rolling_rate()
        }
