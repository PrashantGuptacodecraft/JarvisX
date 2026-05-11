"""
tools/bci/controller.py
Brain-Computer Interface controller for JarvisX.

Integrates with BrainFlow-compatible EEG headsets (Muse, OpenBCI, etc.)
Hardware-gated: gracefully no-ops without hardware.

Classifies EEG signals:
  Blink       → confirm/click action
  Focus       → wake Jarvis
  Relax       → sleep mode
  Mental push → execute last prediction
"""
from __future__ import annotations
import threading, time, logging
from typing import Optional, Callable

log = logging.getLogger("bci_controller")

_BLINK_THRESHOLD  = 80.0
_FOCUS_THRESHOLD  = 0.65
_RELAX_THRESHOLD  = 0.70
_SAMPLE_RATE      = 256


class BCIController:
    """
    BCI controller using BrainFlow library.

    Usage:
        bci = BCIController(command_queue=queue)
        bci.start()   # hardware-gated, no-ops silently without device
        bci.stop()
    """

    def __init__(self, command_queue=None, board_id: int = -1):
        """
        board_id: BrainFlow board ID (-1 = synthetic for testing, 0 = Cyton, 22 = Muse 2)
        """
        self.command_queue = command_queue
        self.board_id = board_id
        self.available: bool = False
        self._board = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_blink = 0.0
        self._last_event  = 0.0
        self._init_backend()

    def _init_backend(self):
        try:
            import brainflow  # noqa: F401
            self.available = True
            log.info(f"BCIController: brainflow ready (board_id={self.board_id})")
        except ImportError:
            log.info(
                "BCIController: brainflow not installed — BCI disabled. "
                "Run: pip install brainflow   (requires EEG hardware)"
            )

    def start(self) -> str:
        if not self.available:
            return "BCI not available (install brainflow + EEG hardware)."
        try:
            from brainflow.board_shim import BoardShim, BrainFlowInputParams
            params = BrainFlowInputParams()
            self._board = BoardShim(self.board_id, params)
            self._board.prepare_session()
            self._board.start_stream()
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="bci")
            self._thread.start()
            log.info("BCIController: streaming started.")
            return "BCI connected and streaming."
        except Exception as e:
            log.warning(f"BCIController start failed: {e}")
            return f"BCI start failed: {e}"

    def stop(self):
        self._running = False
        if self._board:
            try:
                self._board.stop_stream()
                self._board.release_session()
            except Exception:
                pass

    def _loop(self):
        from brainflow.board_shim import BoardShim
        from brainflow.data_filter import DataFilter, FilterTypes
        eeg_channels = BoardShim.get_eeg_channels(self.board_id)

        while self._running:
            time.sleep(0.25)
            try:
                data = self._board.get_board_data(64)
                if data is None or data.shape[1] < 32:
                    continue

                for ch in eeg_channels[:2]:
                    DataFilter.perform_bandpass(
                        data[ch], _SAMPLE_RATE, 1.0, 50.0, 4,
                        FilterTypes.BUTTERWORTH.value, 0,
                    )

                eeg = data[eeg_channels[0]] if eeg_channels else None
                if eeg is None:
                    continue

                # Blink detection (amplitude spike)
                peak = float(max(abs(eeg)))
                if peak > _BLINK_THRESHOLD and time.time() - self._last_blink > 0.8:
                    self._last_blink = time.time()
                    log.info("BCI: BLINK detected")
                    self._dispatch("__BCI_BLINK__")
                    continue

                # Band power analysis for focus/relax
                import numpy as np
                freq = _SAMPLE_RATE
                alpha_power = self._band_power(eeg, freq, 8, 13)
                beta_power  = self._band_power(eeg, freq, 14, 30)
                theta_power = self._band_power(eeg, freq, 4, 7)
                total = alpha_power + beta_power + theta_power + 1e-8

                focus_score = beta_power / total
                relax_score = alpha_power / total
                now = time.time()

                if focus_score > _FOCUS_THRESHOLD and now - self._last_event > 2.0:
                    self._last_event = now
                    log.info(f"BCI: FOCUS detected ({focus_score:.2f})")
                    self._dispatch("__WAKE__")

                elif relax_score > _RELAX_THRESHOLD and now - self._last_event > 3.0:
                    self._last_event = now
                    log.info(f"BCI: RELAX detected ({relax_score:.2f})")
                    self._dispatch("__SLEEP__")

            except Exception as e:
                log.debug(f"BCIController loop error: {e}")

    def _dispatch(self, command: str):
        if self.command_queue:
            self.command_queue.put(command)

    @staticmethod
    def _band_power(signal, sample_rate: int, low: float, high: float) -> float:
        import numpy as np
        fft_vals = np.abs(np.fft.rfft(signal)) ** 2
        fft_freq = np.fft.rfftfreq(len(signal), 1.0 / sample_rate)
        mask = (fft_freq >= low) & (fft_freq <= high)
        return float(np.mean(fft_vals[mask])) if mask.any() else 0.0
