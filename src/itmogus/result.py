from dataclasses import dataclass
from typing import Generic, Never, TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

    def is_ok(self) -> bool:
        return True

    def is_fail(self) -> bool:
        return False

    def ok(self) -> T:
        return self.value

    def err(self) -> None:
        return None

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value


@dataclass(frozen=True)
class Fail(Generic[E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def is_fail(self) -> bool:
        return True

    def ok(self) -> None:
        return None

    def err(self) -> E:
        return self.error

    def unwrap(self) -> Never:
        raise ValueError(f"Called unwrap on Fail: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default


Result = Ok[T] | Fail[E]
