import subprocess
import time
from enum import Enum
from threading import Thread, Barrier, BrokenBarrierError, Lock
from typing import Any, Callable


class ServiceState(Enum):
    ACTIVE = 0
    INACTIVE = 1
    FAILED = 2
    OTHER = 3


class Service:
    def __init__(self, name: str) -> None:
        self.service_name = name

        self._state = ServiceState.OTHER
        self._is_active = False
        self._is_failed = False
        self._update_thread = Thread(target = self._update_loop, daemon = True)
        self._shutdown = False
        self._update_barrier = Barrier(parties = 2)
        self._update_lock = Lock()

        self.on_state: Callable = lambda state: None
        self.on_fail: Callable = lambda: None

    def close(self) -> None:
        self._shutdown = True
        if self._update_thread is not None and self._update_thread.is_alive():
            self._update_thread.join(2)

    def _check_thread(self) -> bool:
        return_value = True
        self._update_lock.acquire(blocking = True, timeout = 4)
        if not self._update_thread.is_alive():
            self._update_thread = Thread(target = self._update_loop, daemon = True)
            self._update_thread.start()
            try:
                self._update_barrier.wait(2)
            except BrokenBarrierError:
                return_value = False
        self._update_lock.release()
        return return_value

    @property
    def state(self) -> ServiceState:
        if self._check_thread():
            return self._state
        else:
            return ServiceState.OTHER

    @property
    def is_active(self) -> bool:
        if self._check_thread():
            return self._is_active
        else:
            return False

    @property
    def is_failed(self) -> bool:
        if self._check_thread():
            return self._is_failed
        else:
            return False

    def _get_state(self) -> ServiceState:
        sysctl_process = subprocess.Popen(["systemctl", "is-active", self.service_name], stdout = subprocess.PIPE)
        output: bytes
        output, error = sysctl_process.communicate()
        sysctl_process.terminate()
        if error is None or error == 0:
            output_string = output.decode(encoding = "utf8", errors = "replace").strip().lower()
            state: ServiceState
            if output_string == "active":
                state = ServiceState.ACTIVE
            elif output_string == "inactive":
                state = ServiceState.INACTIVE
            elif output_string == "failed":
                state = ServiceState.FAILED
            else:
                state = ServiceState.OTHER
            return state
        else:
            return ServiceState.OTHER

    def _update_loop(self) -> Any:
        while not self._shutdown:
            try:
                self._update_barrier.wait(0)
            except BrokenBarrierError:
                self._update_barrier.reset()

            new_state = self._get_state()
            is_active = new_state == ServiceState.ACTIVE
            is_failed = new_state == ServiceState.FAILED

            if is_active is not self._is_active:
                self.on_state(is_active)
            if is_failed and not self._is_failed:
                self.on_fail()

            self._state = new_state
            self._is_active = is_active
            self._is_failed = is_failed

            time.sleep(0.5)

    def start(self) -> bool:
        sysctl_process = subprocess.Popen(["sudo", "systemctl", "start", self.service_name], stdout = subprocess.PIPE)
        try:
            ret_code = sysctl_process.wait(4)
            return ret_code == 0
        except subprocess.TimeoutExpired:
            return False

    def stop(self) -> bool:
        sysctl_process = subprocess.Popen(["sudo", "systemctl", "stop", self.service_name], stdout = subprocess.PIPE)
        try:
            ret_code = sysctl_process.wait(4)
            return ret_code == 0
        except subprocess.TimeoutExpired:
            return False

    def restart(self) -> bool:
        sysctl_process = subprocess.Popen(["sudo", "systemctl", "restart", self.service_name], stdout = subprocess.PIPE)
        try:
            ret_code = sysctl_process.wait(4)
            return ret_code == 0
        except subprocess.TimeoutExpired:
            return False
