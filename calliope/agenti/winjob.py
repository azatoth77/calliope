"""
Job object di Windows per i processi figli degli agenti (02/10/2026).

Un job object raccoglie dei processi e ne limita le risorse; con
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, quando l'ultimo handle del job si chiude (anche perché
Calliope è morta) i processi muoiono con lui. Serve a due cose:

- **tunnel SSH**: se Calliope si chiude male, `ssh -N -L …` non resta vivo a tenere occupata
  la porta locale (su Windows i figli non muoiono con il padre);
- **sandbox del codice**: il processo Python che esegue il codice scritto dall'agente
  non può creare altri processi (ActiveProcessLimit = 1: niente shell, niente
  `subprocess`, anche se il blocco in Python venisse aggirato), ha un tetto di memoria e
  niente appunti, desktop, atomi globali o handle di altre finestre (restrizioni UI).

Il processo si crea **sospeso** (CREATE_SUSPENDED), si assegna al job e solo dopo riparte
(NtResumeProcess): non c'è un istante in cui gira fuori dal job.

Solo libreria standard (ctypes). Fuori da Windows `disponibile()` è False e i chiamanti
ripiegano (tunnel: niente job; sandbox: limiti POSIX con `resource`, vedi sandbox.py).
"""

import ctypes
import subprocess
import sys

CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000

_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JobObjectBasicUIRestrictions = 4
_JobObjectExtendedLimitInformation = 9
# Niente handle di altre finestre, appunti, parametri di sistema, impostazioni dello schermo,
# atomi globali, cambio di desktop, uscita da Windows
_UI_TUTTE = 0x01 | 0x02 | 0x04 | 0x08 | 0x10 | 0x20 | 0x40 | 0x80


def disponibile() -> bool:
    return sys.platform == "win32"


# ── Linux (DGX OS, 02/10): un equivalente parziale di KILL_ON_JOB_CLOSE ──
_PR_SET_PDEATHSIG = 1


def muori_con_il_padre(segnale: int | None = None) -> bool:
    """Da chiamare nel figlio (preexec_fn), solo su Linux: prctl(PR_SET_PDEATHSIG) fa
    arrivare SIGTERM (o `segnale`) al figlio quando muore il **thread** che l'ha creato
    (non il processo: per questo il tunnel, aperto da un thread breve, non lo usa). Serve
    alla sandbox, lanciata dal thread dei lavori che aspetta la fine del processo: con
    `start_new_session` il figlio non riceve più i segnali del terminale, e un Calliope
    ucciso con SIGKILL lo lascerebbe vivo. Sotto systemd basta già il cgroup del servizio
    (KillMode=control-group), che copre anche ssh. False fuori da Linux o se la chiamata
    non riesce: mai un'eccezione dentro preexec_fn."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        import signal
        libc = ctypes.CDLL(None, use_errno=True)
        sig = int(segnale if segnale is not None else signal.SIGTERM)
        return libc.prctl(_PR_SET_PDEATHSIG, sig, 0, 0, 0) == 0
    except Exception:  # noqa: BLE001
        return False


if sys.platform == "win32":
    from ctypes import wintypes

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BASIC_LIMIT),
                    ("IoInfo", _IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _UI_RESTRICTIONS(ctypes.Structure):
        _fields_ = [("UIRestrictionsClass", wintypes.DWORD)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                             wintypes.DWORD)
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _ntdll = ctypes.WinDLL("ntdll")
    _ntdll.NtResumeProcess.restype = ctypes.c_long
    _ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)


class JobObject:
    """Un job object con i suoi limiti. `close()` (o la morte di Calliope) uccide i processi
    che contiene."""

    def __init__(self, una_sola: bool = False, memoria_mb: int | None = None,
                 ui: bool = False):
        if not disponibile():
            raise OSError("i job object ci sono solo su Windows")
        self.handle = _k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _EXTENDED_LIMIT()
        flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | _JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        if una_sola:
            flags |= _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.BasicLimitInformation.ActiveProcessLimit = 1
        if memoria_mb:
            flags |= _JOB_OBJECT_LIMIT_PROCESS_MEMORY
            info.ProcessMemoryLimit = int(memoria_mb) * 1024 * 1024
        info.BasicLimitInformation.LimitFlags = flags
        if not _k32.SetInformationJobObject(self.handle, _JobObjectExtendedLimitInformation,
                                            ctypes.byref(info), ctypes.sizeof(info)):
            err = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(err)
        if ui:
            r = _UI_RESTRICTIONS(_UI_TUTTE)
            if not _k32.SetInformationJobObject(self.handle, _JobObjectBasicUIRestrictions,
                                                ctypes.byref(r), ctypes.sizeof(r)):
                err = ctypes.get_last_error()
                self.close()
                raise ctypes.WinError(err)

    def assegna(self, proc: subprocess.Popen):
        handle = int(proc._handle)      # noqa: SLF001 — l'handle del processo di Popen
        if not _k32.AssignProcessToJobObject(self.handle, handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def termina(self, codice: int = 1):
        if self.handle:
            _k32.TerminateJobObject(self.handle, codice)

    def close(self):
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass


def avvia_nel_job(cmd: list[str], job: JobObject, **kwargs) -> subprocess.Popen:
    """Avvia `cmd` sospeso, lo mette nel job e lo fa ripartire. Se l'assegnazione non
    riesce il processo si uccide prima che esegua una sola istruzione, e l'errore sale."""
    flags = kwargs.pop("creationflags", 0) | CREATE_SUSPENDED
    proc = subprocess.Popen(cmd, creationflags=flags, **kwargs)
    try:
        job.assegna(proc)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    if _ntdll.NtResumeProcess(int(proc._handle)) != 0:      # noqa: SLF001
        job.termina()
        proc.wait()
        raise OSError("NtResumeProcess non è riuscita")
    return proc
