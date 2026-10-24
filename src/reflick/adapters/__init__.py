"""One adapter per source (a cinema or a group of cinemas), registered by id."""

from reflick.adapters.babylon import BabylonAdapter
from reflick.adapters.base import Adapter
from reflick.adapters.lichtblick import LichtblickAdapter
from reflick.adapters.yorck import YorckAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    adapter.id: adapter for adapter in (BabylonAdapter, LichtblickAdapter, YorckAdapter)
}
