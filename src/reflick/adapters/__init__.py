"""One adapter per source (a cinema or a group of cinemas), registered by id."""

from reflick.adapters.arsenal import ArsenalAdapter
from reflick.adapters.babylon import BabylonAdapter
from reflick.adapters.base import Adapter
from reflick.adapters.brotfabrik import BrotfabrikAdapter
from reflick.adapters.hoefe import HoefeAdapter
from reflick.adapters.lichtblick import LichtblickAdapter
from reflick.adapters.transtopia import TranstopiaAdapter
from reflick.adapters.yorck import YorckAdapter
from reflick.adapters.zeughauskino import ZeughauskinoAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    adapter.id: adapter
    for adapter in (
        ArsenalAdapter,
        BabylonAdapter,
        BrotfabrikAdapter,
        HoefeAdapter,
        LichtblickAdapter,
        TranstopiaAdapter,
        YorckAdapter,
        ZeughauskinoAdapter,
    )
}
