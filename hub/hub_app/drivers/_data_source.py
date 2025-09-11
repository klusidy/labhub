from typing import Set, Dict, Any, Callable, Awaitable, Optional, List
from contextlib import aclosing
import time
import asyncio
import inspect

Frame = Dict[str, Any]

# ---------- helper ----------
async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x

class DataSource:
    """
    A minimal hot/cold data source built around a frame function.

    Methods:
      - once()             -> compute and return one frame (no fan-out)
      - subscribe(maxsize) -> asyncio.Queue of frames
      - unsubscribe(q)
      - start(interval)    -> start hot mode (push frames to subscribers)
      - stop()
      - plot()             -> dict plot spec ({} if none)

    Policy: drop-oldest on overflow (keeps UI snappy).
    """
    def __init__(
        self,
        name: str,
        frame_fn: Callable[[], Frame | Awaitable[Frame]],
        plot_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        doc: str = "",
    ):
        self.name = name
        self._frame_fn = frame_fn
        self._plot_fn = plot_fn
        self.doc = doc

        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._seq = 0

    def __repr__(self) -> str:
        return f"<DataSource {self.name} running={self.running()}>"

    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def once(self) -> Frame:
        async with aclosing(self._frame_fn()) as frame_generator:
            frame = await anext(frame_generator)
        return self._envelope(frame)


    async def subscribe(self, maxsize: int = 8) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        # If unsubscribing the last listener, stop the producer.
        should_stop = False
        async with self._lock:
            self._subscribers.discard(q)
            # decide *outside* the lock to avoid deadlocks
            should_stop = (not self._subscribers) and self.running()
        if should_stop:
            await self.stop()

    async def start(self, interval: Optional[float] = None) -> None:
        """If interval is None, runs exactly one cycle and stops."""
        if self.running():
            return

        async def _runner():
            frame_generator = self._frame_fn() # should be async
            try:
                async with aclosing(frame_generator): # ensure generator cleanup (finally in the driver function)
                    async for frame in frame_generator: #await next infinite iterator
                        env = self._envelope(frame)
                        await self._fan_out(env)

                        if interval is None:
                            break # run once

                        async with self._lock:
                            if (len(self._subscribers) == 0):
                                break
         
                        await asyncio.sleep(interval)
        
            finally: # ensure task is cleared when finishing naturally/crashing (cancel case is handled in stop())
                self._task = None

        self._task = asyncio.create_task(_runner(), name=f"DataSource[{self.name}]") # creates independent task that can be stopped

        def _on_done(t: asyncio.Task):
            try:
                exc = t.exception()
                if exc and not isinstance(exc, asyncio.CancelledError):
                    print(f"DataSource crashed  \n {exc}")
            except asyncio.CancelledError:
                pass

        self._task.add_done_callback(_on_done)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def plot(self) -> Dict[str, Any]:
        if not self._plot_fn:
            return {}
        return self._plot_fn()

    # --- internals ---
    def _envelope(self, frame: Frame) -> Frame:
        self._seq += 1
        return {"source": self.name, "seq": self._seq, "ts": time.monotonic(), **frame}

    async def _fan_out(self, env: Frame) -> None:
        async with self._lock:
            subs = list(self._subscribers)

        dead: List[asyncio.Queue] = []
        for q in subs:
            try:
                q.put_nowait(env)
            except asyncio.QueueFull:
                # drop oldest and try once more (non-blocking)
                try:
                    _ = q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(env)
                except Exception:
                    dead.append(q)
            except Exception:
                dead.append(q)

        if dead:
            async with self._lock:
                for q in dead:
                    self._subscribers.discard(q)

# class Plot:
#     def __init__(self, initialize_plot, generate_frame):
#         self.init = initialize_plot # what driver sees is <driver>.<plot_name>.init()
#         self.frame = generate_frame

#         self._subscribers: Set[asyncio.Queue] = set()
#         self._stream_lock = asyncio.Lock()

#     # these are the same for all plots

#     async def subscribe(self, maxsize: int = 8) -> asyncio.Queue:
#         q: asyncio.Queue = asyncio.Queue(maxsize=maxsize) # todo - parametrized maxsize??
#         async with self._stream_lock:
#             self._subscribers.add(q)
#         return q
    
#     async def unsubscribe(self, q: asyncio.Queue) -> None:
#         async with self._stream_lock:
#             self._subscribers.discard(q)

#     async def _push_frame(self, frame: Dict[str, Any]) -> None:
#         """ Fan-out one frame to all subscribers (drop oldest on overflow) """
#         dead: list[asyncio.Queue] = []
#         async with self._stream_lock:
#             for q in list(self._subscribers):
#                 try:
#                     q.put_nowait(frame)
#                 except asyncio.QueueFull:
#                     # drop oldest, then put
#                     try: 
#                         _ = q.get_nowait()
#                         await q.put(frame)
#                     except Exception:
#                         dead.append(q)
#             for q in dead:
#                 self._subscribers.discard(q)


# class api_plot:
#     """descriptor wrapper so that plots can be specified via @api_plot and @<plot_name>.frame decorators"""

#     def __init__(self, finit, fframe=None, doc=None): # todo - also collect the name as with properties/commands
#         self._inner = Plot(finit, fframe)
        
#         if doc is None and finit is not None:
#             doc = finit.__doc__
#         self.__doc__ = doc
#         # todo - how to clear subs upon disconnect? base should have all PLOTS collected and here should be async function clear

#     def __set_name__(self, owner, name):
#         self.__name__ = name
    
#     def __get__(self, obj, objtype=None):
#         if obj is None:
#             return self # ApiPlot.psd (used for specifying decorators)
#         if self.finit is None:
#             raise AttributeError
#         return self._inner # device.psd (used for ordinary access)
    
#     def __set__(self, instance, value):
#         raise AttributeError("Can't override plot attribute (you can set the plot's init() and frame() functions though).")

#     def __delete__(self, instance):
#         raise AttributeError("Can't delete plot attribute (you can delete the plot's init() and frame() functions though).")

#     # decorator so that I can do @psd.frame  
#     def frame(self, fframe): # the psd.frame is called during class creation, so the __get__ returns the property object
#         return type(self)(self._inner.init, fframe, doc=self.__doc__)
    
   

    



    
