"""One adapter per cinema, registered by cinema id."""

from reflick.adapters.base import Adapter
from reflick.adapters.lichtblick import LichtblickAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    LichtblickAdapter.cinema.id: LichtblickAdapter,
}
