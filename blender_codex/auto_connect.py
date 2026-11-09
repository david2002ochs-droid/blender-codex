"""Bounded startup/reconnect policy; never sends a user/model turn."""
import time


class AutoConnect:
    def __init__(self):
        self.request()

    def request(self):
        self.attempts = 0
        self.next_at = 0.0
        self.blocked = False

    def tick(self, session, connect, now=None):
        now = time.monotonic() if now is None else now
        if session.ready:
            self.attempts = 0
            self.blocked = False
            self.next_at = now + 1
            return
        if session.busy or session.client is not None:
            return
        error = (session.error or "").lower()
        if self.attempts and any(word in error for word in ("not signed in", "codex login", "unauthorized", "authentication")):
            self.blocked = True
        if self.blocked or self.attempts >= 5 or now < self.next_at:
            return
        self.attempts += 1
        self.next_at = now + min(30, 2 ** self.attempts)
        connect()
