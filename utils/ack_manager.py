import asyncio
import dataclasses
import time
from enum import IntEnum, auto
from typing import Any, Awaitable

MessageId = int | str


class ManagingStatus(IntEnum):
    PENDING = auto()
    CALLING = auto()
    REJECTING = auto()
    REJECTED = auto()
    DONE = auto()


@dataclasses.dataclass
class ManagingData:
    ack_callback: Awaitable
    rej_callback: Awaitable
    timeout: int
    status: ManagingStatus = ManagingStatus.PENDING
    lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)


class AckManager:
    def __init__(self):
        self.messages: dict[MessageId, ManagingData] = {}

    def manage(
        self,
        message_id: MessageId,
        ack_callback: Awaitable,
        rej_callback: Awaitable,
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
        self.messages[message_id] = ManagingData(
            ack_callback=ack_callback,
            rej_callback=rej_callback,
            timeout=timeout,
        )

        async def _timeout_hook():
            print("callback registered")
            await asyncio.sleep(timeout)
            data = self.messages[message_id]
            print("rejecting", data, message_id)
            async with data.lock:
                if data.status == ManagingStatus.PENDING:
                    data.status = ManagingStatus.REJECTING
                    await data.rej_callback
                    print(message_id, "rejected")
                    data.status = ManagingStatus.REJECTED

        asyncio.create_task(_timeout_hook())
        return True

    async def acknowledge(self, message_id: MessageId) -> bool | Any:
        """
        acknowledge a message

        :param message_id: message id
        :return: False if message status is abnormal, otherwise return value of ack_callback
        """
        if message_id not in self.messages:
            return False
        data = self.messages[message_id]
        print("acknowledging", data, message_id)
        async with data.lock:
            if data.status != ManagingStatus.PENDING:
                return False
            data.status = ManagingStatus.CALLING
            ret = await data.ack_callback
            data.status = ManagingStatus.DONE
            print(message_id, "acknowledged")
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
