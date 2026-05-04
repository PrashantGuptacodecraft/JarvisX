"""tools/tasks/controller.py — Reminders, todos, notes."""
import threading, time, datetime
from config.settings import USER_NAME
from config.logger import get_logger
log = get_logger("tasks")


class TaskController:
    def __init__(self, memory, speaker=None, gui_notify=None):
        self.memory = memory
        self.speaker = speaker
        self.gui_notify = gui_notify
        threading.Thread(target=self._reminder_loop, daemon=True).start()

    def add_reminder(self, task: str, time_str: str) -> str:
        return self.memory.add_reminder(task, time_str)

    def add_todo(self, item: str) -> str:
        return self.memory.add_todo(item)

    def add_note(self, content: str) -> str:
        return self.memory.add_note(content)

    def _reminder_loop(self):
        while True:
            time.sleep(30)
            try:
                now = datetime.datetime.now()
                for r in self.memory.get_pending_reminders():
                    if self._is_due(r["time"], now):
                        msg = f"Reminder, {USER_NAME}: {r['task']}"
                        if self.speaker:
                            self.speaker.speak(msg, blocking=False)
                        if self.gui_notify:
                            self.gui_notify("⏰ Reminder", r["task"])
                        self.memory.mark_reminder_done(r["id"])
            except Exception as e:
                log.error(f"Reminder error: {e}")

    def _is_due(self, time_str: str, now: datetime.datetime) -> bool:
        for fmt in ["%I %p", "%I:%M %p", "%H:%M", "%I%p"]:
            try:
                t = datetime.datetime.strptime(time_str.lower().strip(), fmt)
                due = now.replace(hour=t.hour, minute=t.minute, second=0)
                if abs((now - due).total_seconds()) < 60:
                    return True
            except ValueError:
                continue
        return False
