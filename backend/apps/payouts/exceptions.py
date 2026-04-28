class InsufficientBalanceError(Exception):
    def __init__(self, available: int, requested: int):
        self.available = available
        self.requested = requested
        super().__init__(
            f'Available balance {available} paise is less than requested {requested} paise'
        )


class InvalidTransitionError(Exception):
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f'Invalid transition: {from_status} -> {to_status}')


class KeyInFlightError(Exception):
    pass


class RiskRuleViolationError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)
