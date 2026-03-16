class ScalarKalmanFilter:
    def __init__(self, a: float, h: float, q: float, r: float, x0: float = 0.0, p0: float = 1.0):
        self.a = a
        self.h = h
        self.q = q
        self.r = r
        self.x = x0
        self.p = p0

    def predict(self) -> None:
        self.x = self.a * self.x
        self.p = self.a * self.p * self.a + self.q

    def update(self, z: float) -> None:
        innovation = z - self.h * self.x
        s = self.h * self.p * self.h + self.r
        k = (self.p * self.h) / s if s != 0 else 0.0
        self.x = self.x + k * innovation
        self.p = (1 - k * self.h) * self.p
