import heapq
import time

class Queueable:
    def __init__(self, next_time=0):
        self.next = next_time
        self.queue_again = True

    def run(self) -> bool:
        ...

    def __lt__(self, other):
        return self.next < other.next

    def __eq__(self, other):
        return id(self) == id(other)

class Queue:
    def __init__(self, *values):
        self.queue = list(values)
        heapq.heapify(self.queue)

    def add(self, item: Queueable):
        if not isinstance(item, Queueable):
            raise TypeError("Not Queueable")
        if not item.queue_again:
            return
        if item.next and item.next < time.time():
            raise ValueError("Next invocation in past")
        heapq.heappush(self.queue, item)

    def get(self) -> Queueable:
        return heapq.heappop(self.queue)

    def __iter__(self):
        return iter(self.queue)

    def __bool__(self):
        return bool(self.queue)

class RemoveComment(Queueable):
    def __init__(self, comment):
        super().__init__(time.time() + 15*60)
        self.comment = comment

    def run(self):
        self.queue_again = False
        self.comment.refresh()
        if not self.comment.replies:
            self.comment.mod.remove()
