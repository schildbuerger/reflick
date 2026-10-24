"""One adapter per cinema, registered by cinema id."""

from reflick.adapters.babylon import BabylonAdapter
from reflick.adapters.base import Adapter
from reflick.adapters.lichtblick import LichtblickAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    adapter.cinema.id: adapter for adapter in (BabylonAdapter, LichtblickAdapter)
}
