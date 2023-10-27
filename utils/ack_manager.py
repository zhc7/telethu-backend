import threading
import time
from enum import StrEnum, auto
from typing import Any, Callable

from pydantic import BaseModel

MessageId = int | str


class ManagingStatus(StrEnum):
    PENDING = auto()
    CALLING = auto()
    REJECTING = auto()
    REJECTED = auto()
    DONE = auto()


class ManagingData(BaseModel):
    ack_callback: Callable[[], Any]
    rej_callback: Callable[[], Any]
    timeout: int
    status: ManagingStatus = ManagingStatus.PENDING
    lock: threading.Lock


class AckManager:
    def __init__(self):
        self.messages: dict[MessageId, ManagingData] = {}

    def manage(
        self,
        message_id: MessageId,
        ack_callback: Callable[[], Any],
        rej_callback: Callable[[], Any],
        timeout: int,
    ) -> bool:
        """
        manage a message

        :param message_id: message id
        :param ack_callback: callback when message is acknowledged
        :param rej_callback: callback when message isn't acknowledged in time
        :param timeout: timeout in seconds
        :return: whether the message is successfully managed

        note: callbacks are assumed to be non-blocking
        """
        if message_id in self.messages:
            return False
        self.messages[message_id] = ManagingData(
            ack_callback=ack_callback,
            rej_callback=rej_callback,
            timeout=timeout,
            lock=threading.Lock(),
        )

        def _timeout_hook():
            time.sleep(timeout)
            data = self.messages[message_id]
            with data.lock:
                if data.status == ManagingStatus.PENDING:
                    data.status = ManagingStatus.REJECTING
                    data.rej_callback()
                    data.status = ManagingStatus.REJECTED

        threading.Thread(target=_timeout_hook, daemon=True).start()
        return True

    def acknowledge(self, message_id: MessageId) -> bool | Any:
        """
        acknowledge a message

        :param message_id: message id
        :return: False if message status is abnormal, otherwise return value of ack_callback
        """
        if message_id not in self.messages:
            return False
        data = self.messages[message_id]
        with data.lock:
            if data.status != ManagingStatus.PENDING:
                return False
            data.status = ManagingStatus.CALLING
            ret = data.ack_callback()
            data.status = ManagingStatus.DONE
            return ret

    def status_of(self, message_id: MessageId) -> ManagingStatus:
        """
        get status of a message

        :param message_id: message id
        :return: status of the message
        """
        return self.messages[message_id].status

    def __contains__(self, message_id: MessageId):
        return message_id in self.messages
