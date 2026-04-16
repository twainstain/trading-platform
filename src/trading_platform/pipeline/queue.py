"""Generic bounded priority queue backed by heapq.

Thread-safe. Push is O(log n), pop is O(log n).
When full, lowest-priority item is evicted (back-pressure).

Products use this between their scanner/feed (producer) and
pipeline consumer. The candidate type is generic — any object works.
"""

from __future__ import annotations

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QueuedItem:
    """A candidate waiting in the queue."""
    item: Any
    enqueued_at: float = 0.0
    priority: float = 0.0
    metadata: dict = field(default_factory=dict)


class PriorityQueue:
    """Thread-safe bounded priority queue.

    Uses dual heaps so the queue can evict the lowest-priority item when full
    and pop the highest-priority item in O(log n). FIFO ordering is preserved
    for equal priorities.

    Args:
        max_size: Maximum items in the queue. 0 = unbounded.
    """

    def __init__(self, max_size: int = 333) -> None:
        self._lock = threading.Lock()
        self._min_heap: list[tuple[float, int, int]] = []
        self._max_heap: list[tuple[float, int, int]] = []
        self._items: dict[int, QueuedItem] = {}
        self._max_size = max_size
        self._seq = 0
        self._total_enqueued = 0
        self._total_dropped = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def is_empty(self) -> bool:
        return self.size == 0

    def push(self, item: Any, priority: float = 0.0,
             metadata: dict | None = None) -> bool:
        """Add an item. Returns False if it was dropped (back-pressure)."""
        queued = QueuedItem(
            item=item,
            enqueued_at=time.time(),
            priority=priority,
            metadata=metadata or {},
        )

        with self._lock:
            self._total_enqueued += 1
            self._seq += 1
            item_id = self._seq
            entry = (priority, self._seq, item_id)

            if self._max_size <= 0 or len(self._items) < self._max_size:
                self._add_entry(entry, queued)
                return True

            lowest = self._peek_lowest_live()
            if lowest is None or priority <= lowest[0]:
                self._total_dropped += 1
                return False

            dropped = self._pop_lowest_live()
            self._total_dropped += 1
            self._add_entry(entry, queued)
            logger.debug("Queue full — evicted item with priority %.4f", dropped.priority)
            return True

    def pop(self) -> QueuedItem | None:
        """Pop the highest-priority item. Returns None if empty."""
        with self._lock:
            return self._pop_highest_live()

    def pop_batch(self, max_count: int = 10) -> list[QueuedItem]:
        """Pop up to max_count items, highest priority first."""
        with self._lock:
            batch = []
            while len(batch) < max_count:
                item = self._pop_highest_live()
                if item is None:
                    break
                batch.append(item)
            return batch

    def clear(self) -> int:
        """Clear the queue. Returns count of items removed."""
        with self._lock:
            count = len(self._items)
            self._min_heap.clear()
            self._max_heap.clear()
            self._items.clear()
            return count

    def stats(self) -> dict:
        with self._lock:
            return {
                "current_size": len(self._items),
                "max_size": self._max_size,
                "total_enqueued": self._total_enqueued,
                "total_dropped": self._total_dropped,
            }

    def _add_entry(self, entry: tuple[float, int, int], queued: QueuedItem) -> None:
        priority, seq, item_id = entry
        self._items[item_id] = queued
        heapq.heappush(self._min_heap, (priority, seq, item_id))
        heapq.heappush(self._max_heap, (-priority, seq, item_id))

    def _peek_lowest_live(self) -> tuple[float, int, int] | None:
        self._discard_stale(self._min_heap)
        return self._min_heap[0] if self._min_heap else None

    def _pop_lowest_live(self) -> QueuedItem | None:
        self._discard_stale(self._min_heap)
        if not self._min_heap:
            return None
        _, _, item_id = heapq.heappop(self._min_heap)
        return self._items.pop(item_id, None)

    def _pop_highest_live(self) -> QueuedItem | None:
        self._discard_stale(self._max_heap)
        if not self._max_heap:
            return None
        _, _, item_id = heapq.heappop(self._max_heap)
        return self._items.pop(item_id, None)

    def _discard_stale(self, heap: list[tuple[float, int, int]]) -> None:
        while heap and heap[0][2] not in self._items:
            heapq.heappop(heap)
