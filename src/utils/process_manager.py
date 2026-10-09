"""
Cross-platform process management abstraction for subprocess lifecycle control.

Provides ManagedProcess class to handle platform-specific process group/job
termination semantics uniformly.
"""

import logging
import os
import signal
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

# Windows Job Objects API via ctypes
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    # Job Object API constants
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", ctypes.c_byte * 48),  # JOBOBJECT_BASIC_LIMIT_INFORMATION
            ("IoInfo", ctypes.c_byte * 32),  # IO_COUNTERS
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    # Windows API function signatures
    CreateJobObjectW = kernel32.CreateJobObjectW
    CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    CreateJobObjectW.restype = wintypes.HANDLE

    AssignProcessToJobObject = kernel32.AssignProcessToJobObject
    AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    AssignProcessToJobObject.restype = wintypes.BOOL

    SetInformationJobObject = kernel32.SetInformationJobObject
    SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    SetInformationJobObject.restype = wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    JobObjectExtendedLimitInformation = 9  # JOBOBJECTINFOCLASS enum value


class ManagedProcess:
    """
    Context manager for cross-platform process lifecycle management.

    Unix: Uses process groups (start_new_session=True + os.killpg)
    Windows: Uses Job Objects API (via ctypes) to terminate process trees

    Usage:
        with ManagedProcess(command, **kwargs) as managed:
            result = managed.process.wait()
        # Process tree automatically terminated on exit
    """

    def __init__(self, command: list[str], **popen_kwargs: Any):
        """
        Initialize managed process wrapper.

        Args:
            command: Command and arguments to execute
            **popen_kwargs: Additional arguments passed to subprocess.Popen
        """
        self.command = command
        self.popen_kwargs = popen_kwargs
        self.process: subprocess.Popen | None = None
        self._job_handle: Any = None  # Windows Job Object handle

    def __enter__(self) -> "ManagedProcess":
        """Start the process with platform-specific setup."""
        # Unix: Create new process group for killpg termination
        if os.name != "nt":
            self.popen_kwargs.setdefault("start_new_session", True)

        self.process = subprocess.Popen(self.command, **self.popen_kwargs)

        # Windows: Create Job Object and assign process to it
        if sys.platform == "win32":
            try:
                # Create Job Object
                self._job_handle = CreateJobObjectW(None, None)
                if not self._job_handle:
                    logger.warning(
                        "Failed to create Job Object, falling back to simple kill",
                        error_code=kernel32.GetLastError(),
                    )
                    return self

                # Configure Job to terminate all processes when closed
                job_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                # Set KILL_ON_JOB_CLOSE flag in BasicLimitInformation.LimitFlags
                # LimitFlags is at offset 16 in BasicLimitInformation
                limit_flags_offset = 16
                limit_flags = ctypes.c_ulong.from_buffer(
                    job_info.BasicLimitInformation, limit_flags_offset
                )
                limit_flags.value = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

                if not SetInformationJobObject(
                    self._job_handle,
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(job_info),
                    ctypes.sizeof(job_info),
                ):
                    logger.warning(
                        "Failed to set Job Object limits, falling back to simple kill",
                        error_code=kernel32.GetLastError(),
                    )
                    CloseHandle(self._job_handle)
                    self._job_handle = None
                    return self

                # Assign process to Job Object
                # Use OpenProcess to get process handle with necessary rights
                PROCESS_SET_QUOTA = 0x0100
                PROCESS_TERMINATE = 0x0001
                process_handle = kernel32.OpenProcess(
                    PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, self.process.pid
                )

                if not process_handle:
                    logger.warning(
                        "Failed to open process handle, falling back to simple kill",
                        pid=self.process.pid,
                        error_code=kernel32.GetLastError(),
                    )
                    CloseHandle(self._job_handle)
                    self._job_handle = None
                    return self

                try:
                    if not AssignProcessToJobObject(self._job_handle, process_handle):
                        logger.warning(
                            "Failed to assign process to Job Object, falling back to simple kill",
                            pid=self.process.pid,
                            error_code=kernel32.GetLastError(),
                        )
                        CloseHandle(self._job_handle)
                        self._job_handle = None
                finally:
                    CloseHandle(process_handle)

            except Exception as e:
                logger.warning(
                    "Exception during Job Object setup, falling back to simple kill", exception=str(e)
                )
                if self._job_handle:
                    CloseHandle(self._job_handle)
                    self._job_handle = None

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Terminate the process tree on exit."""
        if self.process is None:
            return

        # Unix: Terminate entire process group
        if os.name != "nt":
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Process group already exited
            return

        # Windows: Close Job Object handle to terminate all associated processes
        if self._job_handle:
            try:
                CloseHandle(self._job_handle)
                self._job_handle = None
                # Job Object automatically terminates all processes on close
                # due to JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE flag
            except Exception as e:
                logger.warning("Exception during Job Object cleanup", exception=str(e))
                # Fallback to simple kill
                try:
                    self.process.kill()
                except (ProcessLookupError, OSError):
                    pass
        else:
            # Fallback: Simple kill if Job Object was not created
            try:
                self.process.kill()
            except (ProcessLookupError, OSError):
                pass  # Process already exited
