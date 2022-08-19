import random


class ExponentialBackoff:
    MAX_JITTER_FRACTION = 0.03125

    def __init__(self, base=2, min_time=4, max_time=20, max_jitter_fraction=MAX_JITTER_FRACTION):
        self.base = base
        self.min = min_time
        self.max = max_time
        self.jitter_factor = 2 * max_jitter_fraction
        self.counter = 1

    def increment(self):
        if self._value() > self.max:
            return
        self.counter += 1

    def reset(self):
        self.counter = 1

    def _value(self):
        return self.base**self.counter

    def value(self):
        value = min(max(self._value(), self.min), self.max)
        max_jitter = value * self.jitter_factor
        return value + (random.random() - 0.5) * max_jitter


class ConstantBackoff(ExponentialBackoff):
    def __init__(self, *values, max_jitter_fraction=ExponentialBackoff.MAX_JITTER_FRACTION):
        super().__init__(
            min_time=min(values),
            max_time=max(values),
            max_jitter_fraction=max_jitter_fraction)
        self.values = values

    def increment(self):
        if self.counter < len(self.values):
            self.counter += 1

    def _value(self):
        return self.values[self.counter - 1]
